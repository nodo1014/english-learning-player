from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator
import sqlite3
from pydub import AudioSegment
from pydub.silence import detect_silence

# Whisper 모델 초기화 (base 모델로 정확도와 속도 균형)
model = None  # 지연 로딩
translator = GoogleTranslator(source='en', target='ko')

def detect_silence_gaps(filepath):
    """무음 구간을 감지하여 챕터 분할점을 찾는다"""
    try:
        audio = AudioSegment.from_file(filepath)
        duration = len(audio) / 1000.0  # 초 단위
        
        # 단순히 시간으로 분할 (빠른 처리를 위해)
        if duration > 300:  # 5분 이상
            return [0, duration/4, duration/2, duration*3/4, duration]
        elif duration > 120:  # 2분 이상
            return [0, duration/2, duration]
        else:
            return [0, duration]
        
    except Exception as e:
        print(f"Audio processing error: {e}")
        return [0, 60]  # 기본 1분

def group_sentences_into_scenes(sentences, chapter_start, chapter_end):
    """문장들을 씬으로 그룹화"""
    if len(sentences) <= 6:
        return [{
            'start_time': chapter_start,
            'end_time': chapter_end,
            'sentences': sentences
        }]
    
    # 6문장씩 그룹화
    scenes = []
    for i in range(0, len(sentences), 6):
        scene_sentences = sentences[i:i+6]
        start_time = scene_sentences[0]['startTime']
        end_time = scene_sentences[-1]['endTime']
        
        scenes.append({
            'start_time': start_time,
            'end_time': end_time,
            'sentences': scene_sentences
        })
    
    return scenes

def process_audio_file_realtime(filepath, media_id, progress_callback=None):
    """실시간으로 문장을 추출하고 DB에 저장하며 진행상황을 알린다"""
    global model
    try:
        print(f"Processing {filepath}...")
        
        # 모델 지연 로딩
        if model is None:
            if progress_callback:
                progress_callback("모델 로딩 중...")
            print("Loading Whisper model...")
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            print("Model loaded!")
        
        # Whisper로 전사 시작
        if progress_callback:
            progress_callback("음성 인식 시작...")
        
        segments, info = model.transcribe(filepath, beam_size=1)
        
        # DB 연결
        conn = sqlite3.connect('dev.db')
        cursor = conn.cursor()
        
        # 미디어 정보 업데이트
        cursor.execute(
            "UPDATE Media SET duration = ? WHERE id = ?",
            (info.duration, media_id)
        )
        
        # 기본 챕터/씬 생성 (나중에 재구성 가능)
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, "Chapter 1", 0, info.duration, 1)
        )
        chapter_id = cursor.lastrowid
        
        cursor.execute(
            "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (chapter_id, "Scene 1", 0, info.duration, 1)
        )
        scene_id = cursor.lastrowid
        
        # 실시간으로 문장 처리
        sentence_count = 0
        for segment in segments:
            sentence_count += 1
            english_text = segment.text.strip()
            
            if progress_callback:
                progress_callback(f"문장 {sentence_count} 처리 중: {english_text[:30]}...")
            
            # 한국어 번역
            try:
                korean_text = translator.translate(english_text)
            except:
                korean_text = english_text
            
            # DB에 즉시 저장
            cursor.execute(
                """INSERT INTO Sentence 
                (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (scene_id, english_text, korean_text, segment.start, segment.end, 0, sentence_count)
            )
            
            # 실시간 커밋 (매 문장마다)
            conn.commit()
            
            print(f"Added sentence {sentence_count}: {english_text}")
        
        conn.close()
        
        if progress_callback:
            progress_callback(f"완료! 총 {sentence_count}개 문장 추출")
        
        print(f"Processing completed: {sentence_count} sentences")
        
        return {
            'success': True,
            'message': f'Successfully processed {sentence_count} sentences'
        }
        
    except Exception as e:
        print(f"Processing error: {e}")
        if progress_callback:
            progress_callback(f"오류: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def process_audio_file(filepath, media_id):
    """기존 함수 호환성 유지"""
    return process_audio_file_realtime(filepath, media_id)