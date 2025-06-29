#!/usr/bin/env python3
"""
Voice Activity Detection (VAD) 프로세서
음성 구간 감지 및 무음 제거 기능
"""

import numpy as np
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import sqlite3
import json

class VADProcessor:
    def __init__(self, silence_thresh=-40, min_silence_len=500, chunk_size=10):
        """
        VAD 프로세서 초기화
        
        Args:
            silence_thresh: 무음 기준 데시벨 (낮을수록 더 민감)
            min_silence_len: 최소 무음 길이 (ms)
            chunk_size: 처리 단위 (ms)
        """
        self.silence_thresh = silence_thresh
        self.min_silence_len = min_silence_len
        self.chunk_size = chunk_size
    
    def detect_voice_segments(self, audio_file_path):
        """
        오디오 파일에서 음성 구간 감지
        
        Args:
            audio_file_path: 오디오 파일 경로
            
        Returns:
            list: [(start_ms, end_ms), ...] 음성 구간 리스트
        """
        try:
            # 오디오 로드
            audio = AudioSegment.from_file(audio_file_path)
            
            # 음성이 있는 구간 감지 (무음이 아닌 구간)
            nonsilent_ranges = detect_nonsilent(
                audio,
                min_silence_len=self.min_silence_len,
                silence_thresh=self.silence_thresh,
                seek_step=self.chunk_size
            )
            
            # 결과를 초 단위로 변환
            voice_segments = []
            for start_ms, end_ms in nonsilent_ranges:
                voice_segments.append({
                    'start_time': start_ms / 1000.0,
                    'end_time': end_ms / 1000.0,
                    'duration': (end_ms - start_ms) / 1000.0
                })
            
            return voice_segments
            
        except Exception as e:
            print(f"VAD 처리 오류: {e}")
            return []
    
    def filter_sentences_by_vad(self, media_id, vad_threshold=0.3):
        """
        VAD 결과를 기반으로 문장 필터링
        
        Args:
            media_id: 미디어 ID
            vad_threshold: VAD 임계값 (0.0-1.0, 높을수록 더 엄격)
            
        Returns:
            list: 필터링된 문장 리스트
        """
        conn = sqlite3.connect('dev.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 미디어 파일 경로 가져오기
        cursor.execute("SELECT filename FROM Media WHERE id = ?", (media_id,))
        media = cursor.fetchone()
        
        if not media:
            conn.close()
            return []
        
        # 모든 문장 가져오기
        cursor.execute("""
            SELECT s.*, sc.title as scene_title, c.title as chapter_title
            FROM Sentence s
            JOIN Scene sc ON s.sceneId = sc.id
            JOIN Chapter c ON sc.chapterId = c.id
            WHERE c.mediaId = ?
            ORDER BY s.startTime
        """, (media_id,))
        
        sentences = cursor.fetchall()
        conn.close()
        
        if not sentences:
            return []
        
        # VAD 처리
        import os
        audio_path = os.path.join('upload', media['filename'])
        voice_segments = self.detect_voice_segments(audio_path)
        
        # 문장과 음성 구간 매칭
        filtered_sentences = []
        
        for sentence in sentences:
            sentence_dict = dict(sentence)
            sentence_start = sentence['startTime']
            sentence_end = sentence['endTime']
            sentence_duration = sentence_end - sentence_start
            
            # 이 문장과 겹치는 음성 구간들 찾기
            overlapping_voice_time = 0
            
            for voice_seg in voice_segments:
                # 겹치는 구간 계산
                overlap_start = max(sentence_start, voice_seg['start_time'])
                overlap_end = min(sentence_end, voice_seg['end_time'])
                
                if overlap_start < overlap_end:
                    overlapping_voice_time += (overlap_end - overlap_start)
            
            # VAD 비율 계산
            if sentence_duration > 0:
                vad_ratio = overlapping_voice_time / sentence_duration
                sentence_dict['vad_ratio'] = vad_ratio
                
                # 임계값 이상인 문장만 포함
                if vad_ratio >= vad_threshold:
                    sentence_dict['vad_filtered'] = True
                    filtered_sentences.append(sentence_dict)
                else:
                    sentence_dict['vad_filtered'] = False
                    # 필터링된 문장도 포함하되 표시만 다르게
                    filtered_sentences.append(sentence_dict)
        
        return filtered_sentences
    
    def create_vad_audio(self, audio_file_path, output_path, padding_ms=100):
        """
        VAD 결과를 기반으로 음성 구간만 포함하는 오디오 생성
        
        Args:
            audio_file_path: 원본 오디오 파일 경로
            output_path: 출력 파일 경로
            padding_ms: 음성 구간 앞뒤 패딩 (ms)
            
        Returns:
            bool: 성공 여부
        """
        try:
            audio = AudioSegment.from_file(audio_file_path)
            voice_segments = self.detect_voice_segments(audio_file_path)
            
            # 음성 구간들을 하나로 합치기
            combined_audio = AudioSegment.empty()
            
            for segment in voice_segments:
                start_ms = max(0, int(segment['start_time'] * 1000) - padding_ms)
                end_ms = min(len(audio), int(segment['end_time'] * 1000) + padding_ms)
                
                voice_chunk = audio[start_ms:end_ms]
                combined_audio += voice_chunk
                
                # 구간 사이에 짧은 무음 추가 (자연스러운 연결)
                if len(combined_audio) > 0:
                    silence = AudioSegment.silent(duration=50)  # 50ms 무음
                    combined_audio += silence
            
            # 결과 저장
            combined_audio.export(output_path, format="mp3", bitrate="128k")
            return True
            
        except Exception as e:
            print(f"VAD 오디오 생성 오류: {e}")
            return False

def apply_vad_filter(media_id, vad_threshold=0.3):
    """미디어에 VAD 필터 적용"""
    processor = VADProcessor()
    return processor.filter_sentences_by_vad(media_id, vad_threshold)

if __name__ == "__main__":
    # 테스트
    processor = VADProcessor()
    result = processor.filter_sentences_by_vad(9, 0.3)
    print(f"VAD 필터링 결과: {len(result)}개 문장")
    
    # 통계 출력
    filtered_count = sum(1 for s in result if s.get('vad_filtered', False))
    print(f"음성 구간 포함: {filtered_count}개")
    print(f"무음 구간: {len(result) - filtered_count}개")