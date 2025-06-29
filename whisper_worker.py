from celery import Celery
from faster_whisper import WhisperModel
import os
import json
from deep_translator import GoogleTranslator
import sqlite3
from datetime import datetime
import librosa
import numpy as np
from pydub import AudioSegment
from pydub.silence import detect_silence

# Celery 설정
celery_app = Celery('whisper_worker', broker='redis://localhost:6379/0')

# Whisper 모델 초기화 (small 모델 사용)
model = WhisperModel("small", device="cpu", compute_type="int8")
translator = GoogleTranslator(source='en', target='ko')

def detect_silence_gaps(filepath):
    """무음 구간을 감지하여 챕터 분할점을 찾는다"""
    try:
        audio = AudioSegment.from_file(filepath)
        duration = len(audio) / 1000.0  # 초 단위
        
        # 무음 구간 감지 (3초 이상, -40dB 이하)
        silence_ranges = detect_silence(
            audio, 
            min_silence_len=3000,  # 3초
            silence_thresh=-40     # -40dB
        )
        
        if not silence_ranges:
            # 무음 구간이 없으면 단순히 시간으로 분할
            if duration > 300:  # 5분 이상
                return [0, duration/4, duration/2, duration*3/4, duration]
            else:
                return [0, duration]
        
        # 긴 무음 구간 상위 3개 선택
        silence_durations = [(end - start, start, end) for start, end in silence_ranges]
        silence_durations.sort(reverse=True)  # 긴 무음부터
        
        # 최대 4개 챕터 분할점
        chapter_points = [0]  # 시작점
        for duration_len, start, end in silence_durations[:3]:  # 상위 3개만 선택
            chapter_points.append(end / 1000.0)  # ms를 초로 변환
        
        chapter_points.append(duration)  # 끝점
        chapter_points = sorted(list(set(chapter_points)))  # 중복 제거 및 정렬
        
        return chapter_points
        
    except Exception as e:
        print(f"Silence detection error: {e}")
        # 기본값으로 전체 길이 반환
        try:
            audio = AudioSegment.from_file(filepath)
            return [0, len(audio) / 1000.0]
        except:
            return [0, 60]  # 기본 1분

def group_sentences_into_scenes(sentences, chapter_start, chapter_end):
    """문장들을 씬으로 그룹화 (무음 3초 + 6문장 이상 기준)"""
    scenes = []
    current_scene_sentences = []
    scene_start_time = chapter_start
    
    for sentence in sentences:
        if sentence['startTime'] < chapter_start or sentence['endTime'] > chapter_end:
            continue
            
        current_scene_sentences.append(sentence)
        
        # 다음 문장과의 간격이 3초 이상이고, 현재 씬에 6문장 이상이면 씬 분할
        if len(current_scene_sentences) >= 6:
            # 현재 씬 완료
            scene_end_time = current_scene_sentences[-1]['endTime']
            scenes.append({
                'start_time': scene_start_time,
                'end_time': scene_end_time,
                'sentences': current_scene_sentences.copy()
            })
            
            # 새 씬 시작
            current_scene_sentences = []
            scene_start_time = scene_end_time
    
    # 마지막 씬 처리
    if current_scene_sentences:
        scenes.append({
            'start_time': scene_start_time,
            'end_time': chapter_end,
            'sentences': current_scene_sentences
        })
    
    return scenes

@celery_app.task
def process_audio_file(filepath, media_id):
    """오디오 파일을 처리하여 문장을 추출하고 DB에 저장"""
    try:
        # Whisper로 전사
        segments, info = model.transcribe(filepath, beam_size=5)
        
        # 무음 구간 분석으로 챕터 분할점 찾기
        chapter_points = detect_silence_gaps(filepath)
        
        # DB 연결
        conn = sqlite3.connect('dev.db')
        cursor = conn.cursor()
        
        # 미디어 정보 업데이트
        cursor.execute(
            "UPDATE Media SET duration = ? WHERE id = ?",
            (info.duration, media_id)
        )
        
        # 모든 문장 먼저 수집
        all_sentences = []
        sentence_order = 1
        for segment in segments:
            english_text = segment.text.strip()
            
            # 한국어 번역
            try:
                korean_text = translator.translate(english_text)
            except:
                korean_text = ""
            
            all_sentences.append({
                'english': english_text,
                'korean': korean_text,
                'startTime': segment.start,
                'endTime': segment.end,
                'order': sentence_order
            })
            sentence_order += 1
        
        # 챕터별로 처리
        for i, (chapter_start, chapter_end) in enumerate(zip(chapter_points[:-1], chapter_points[1:])):
            # 챕터 생성
            cursor.execute(
                "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                (media_id, f"Chapter {i+1}", chapter_start, chapter_end, i+1)
            )
            chapter_id = cursor.lastrowid
            
            # 해당 챕터의 문장들로 씬 생성
            chapter_sentences = [s for s in all_sentences 
                               if s['startTime'] >= chapter_start and s['endTime'] <= chapter_end]
            
            scenes = group_sentences_into_scenes(chapter_sentences, chapter_start, chapter_end)
            
            # 씬 저장
            for j, scene in enumerate(scenes):
                cursor.execute(
                    "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                    (chapter_id, f"Scene {j+1}", scene['start_time'], scene['end_time'], j+1)
                )
                scene_id = cursor.lastrowid
                
                # 씬의 문장들 저장
                for sentence in scene['sentences']:
                    cursor.execute(
                        """INSERT INTO Sentence 
                        (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (scene_id, sentence['english'], sentence['korean'], 
                         sentence['startTime'], sentence['endTime'], 0, sentence['order'])
                    )
        
        conn.commit()
        conn.close()
        
        return {
            'success': True,
            'message': f'Successfully processed {len(all_sentences)} sentences into {len(chapter_points)-1} chapters'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

if __name__ == '__main__':
    celery_app.start()