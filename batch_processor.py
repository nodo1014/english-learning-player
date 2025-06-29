from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator
import sqlite3
import re
from pydub import AudioSegment
from pydub.silence import detect_silence

# Whisper 모델 초기화
model = None
translator = GoogleTranslator(source='en', target='ko')

def process_audio_batch(filepath, media_id, model_size="medium", template="auto"):
    """오디오 파일을 한번에 처리하여 배치로 DB에 저장"""
    global model
    
    try:
        print(f"Starting batch processing: {filepath} with model: {model_size}")
        
        # 모델 지연 로딩 (모델 크기가 바뀌면 새로 로드)
        current_model_size = getattr(model, '_model_size', None) if model else None
        if model is None or current_model_size != model_size:
            print(f"Loading Whisper model: {model_size}...")
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            model._model_size = model_size  # 현재 모델 크기 저장
            print(f"Model {model_size} loaded!")
        
        # Whisper로 전체 전사
        print("Transcribing audio...")
        segments, info = model.transcribe(filepath, beam_size=1)
        
        # 모든 문장을 메모리에 수집
        all_sentences = []
        sentence_order = 1
        
        for i, segment in enumerate(segments):
            english_text = segment.text.strip()
            
            # 현재 처리 중인 문장 상태 업데이트
            update_processing_status(media_id, 'transcribing', f"세그먼트 {i+1} 처리 중: {english_text[:30]}...")
            
            # 문장 분리 (마침표, 느낌표, 물음표 기준)
            split_sentences = split_into_sentences(english_text)
            
            if len(split_sentences) > 1:
                # 여러 문장으로 분리된 경우, 시간을 균등 분할
                segment_duration = segment.end - segment.start
                time_per_sentence = segment_duration / len(split_sentences)
                
                for j, sent in enumerate(split_sentences):
                    sent = sent.strip()
                    if len(sent) < 3:  # 너무 짧은 문장 제외
                        continue
                        
                    start_time = segment.start + (j * time_per_sentence)
                    end_time = segment.start + ((j + 1) * time_per_sentence)
                    
                    # 현재 번역 중인 문장 표시
                    update_processing_status(media_id, 'translating', f"문장 {sentence_order} 번역 중: {sent[:30]}...")
                    
                    # 한국어 번역 (속도 개선을 위해 임시 비활성화)
                    try:
                        # korean_text = translator.translate(sent)  # 임시 비활성화
                        korean_text = ''  # 빈 문자열로 처리
                    except:
                        korean_text = sent
                    
                    all_sentences.append({
                        'english': sent,
                        'korean': korean_text,
                        'start_time': start_time,
                        'end_time': end_time,
                        'order': sentence_order
                    })
                    
                    print(f"Split sentence {sentence_order}: {sent[:50]}...")
                    sentence_order += 1
            else:
                # 단일 문장인 경우
                if len(english_text) >= 3:  # 너무 짧은 문장 제외
                    # 현재 번역 중인 문장 표시
                    update_processing_status(media_id, 'translating', f"문장 {sentence_order} 번역 중: {english_text[:30]}...")
                    
                    # 한국어 번역 (업로드 시 비활성화)
                    korean_text = ''  # 빈 문자열로 처리, 나중에 별도 번역
                    
                    all_sentences.append({
                        'english': english_text,
                        'korean': korean_text,
                        'start_time': segment.start,
                        'end_time': segment.end,
                        'order': sentence_order
                    })
                    
                    print(f"Processed sentence {sentence_order}: {english_text[:50]}...")
                    sentence_order += 1
        
        print(f"Transcription completed. Total sentences: {len(all_sentences)}")
        
        # DB에 배치로 저장
        print("Saving to database...")
        update_processing_status(media_id, 'saving', f"데이터베이스에 {len(all_sentences)}개 문장 저장 중...")
        save_to_database(media_id, info.duration, all_sentences)
        
        # 무음 구간 분석 후 챕터/씬 재구성
        print(f"Analyzing audio for chapter/scene organization using template: {template}...")
        update_processing_status(media_id, 'organizing', f"{template} 템플릿으로 구조 분석 중...")
        reorganize_chapters_scenes(media_id, filepath, all_sentences, template)
        
        # 완료 상태로 업데이트
        update_processing_status(media_id, 'completed', f"처리 완료! {len(all_sentences)}개 문장")
        
        print(f"Batch processing completed: {len(all_sentences)} sentences saved")
        
        return {
            'success': True,
            'sentence_count': len(all_sentences),
            'duration': info.duration
        }
        
    except Exception as e:
        print(f"Batch processing error: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def update_processing_status(media_id, status, current_sentence=''):
    """처리 상태 업데이트"""
    try:
        conn = sqlite3.connect('dev.db')
        cursor = conn.cursor()
        
        # 먼저 테이블 구조 확인
        cursor.execute("PRAGMA table_info(Media)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'status' in columns and 'current_sentence' in columns:
            cursor.execute(
                "UPDATE Media SET status = ?, current_sentence = ? WHERE id = ?",
                (status, current_sentence, media_id)
            )
        else:
            print(f"Missing columns in Media table. Available: {columns}")
            
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Status update error: {e}")
        try:
            conn.close()
        except:
            pass

def save_to_database(media_id, duration, sentences):
    """배치로 DB에 저장"""
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    try:
        # 미디어 정보 업데이트
        cursor.execute(
            "UPDATE Media SET duration = ?, status = ? WHERE id = ?",
            (duration, 'organizing', media_id)
        )
        
        # 기본 챕터 생성 (전체를 하나의 챕터로)
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, "전체", 0, duration, 1)
        )
        chapter_id = cursor.lastrowid
        
        # 각 문장마다 개별 씬 생성
        sentence_data = []
        for i, s in enumerate(sentences):
            # 각 문장을 위한 씬 생성
            scene_title = f"문장 {i+1}"
            cursor.execute(
                "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                (chapter_id, scene_title, s['start_time'], s['end_time'], i+1)
            )
            scene_id = cursor.lastrowid
            
            # 문장 데이터 추가
            sentence_data.append((scene_id, s['english'], s['korean'], s['start_time'], s['end_time'], 0, s['order']))
        
        cursor.executemany(
            """INSERT INTO Sentence 
            (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            sentence_data
        )
        
        # 한번에 커밋
        conn.commit()
        print(f"Database batch save completed: {len(sentences)} sentences")
        
    except Exception as e:
        conn.rollback()
        print(f"Database save error: {e}")
        raise e
    finally:
        conn.close()

def split_into_sentences(text):
    """텍스트를 문장 단위로 분리"""
    if not text:
        return []
    
    # 마침표, 느낌표, 물음표를 기준으로 분리
    # 하지만 Mr., Dr., vs. 등은 보존
    sentences = re.split(r'(?<![A-Z][a-z]\.)\s*[.!?]+\s+(?=[A-Z])', text)
    
    # 빈 문장 제거 및 정리
    cleaned_sentences = []
    for sent in sentences:
        sent = sent.strip()
        if sent and len(sent) > 2:
            # 문장 끝에 구두점이 없으면 추가
            if not re.search(r'[.!?]$', sent):
                sent += '.'
            cleaned_sentences.append(sent)
    
    return cleaned_sentences

def detect_silence_breaks(filepath, min_silence_len=2000, silence_thresh=-40):
    """무음 구간을 감지하여 챕터/씬 분할점을 찾는다"""
    try:
        audio = AudioSegment.from_file(filepath)
        
        # 무음 구간 감지 (2초 이상, -40dB 이하)
        silence_ranges = detect_silence(
            audio, 
            min_silence_len=min_silence_len,  # 최소 2초
            silence_thresh=silence_thresh     # -40dB 이하
        )
        
        # 무음 구간의 중점을 분할점으로 사용
        break_points = []
        for start_silence, end_silence in silence_ranges:
            mid_point = (start_silence + end_silence) / 2 / 1000.0  # 초 단위로 변환
            break_points.append(mid_point)
        
        # 시작과 끝 추가
        break_points = [0] + break_points + [len(audio) / 1000.0]
        break_points = sorted(list(set(break_points)))  # 중복 제거 및 정렬
        
        print(f"Detected {len(break_points)-1} segments from silence analysis")
        return break_points
        
    except Exception as e:
        print(f"Silence detection error: {e}")
        # 에러시 기본값 반환 (시간 기반 분할)
        try:
            audio = AudioSegment.from_file(filepath)
            duration = len(audio) / 1000.0
            if duration > 600:  # 10분 이상
                return [0, duration/4, duration/2, duration*3/4, duration]
            elif duration > 300:  # 5분 이상
                return [0, duration/2, duration]
            else:
                return [0, duration]
        except:
            return [0, 60]  # 최소 기본값

def group_sentences_by_breaks(sentences, break_points):
    """무음 구간 기준으로 문장들을 그룹화"""
    groups = []
    
    for i in range(len(break_points) - 1):
        start_time = break_points[i]
        end_time = break_points[i + 1]
        
        # 해당 구간에 속하는 문장들 찾기
        group_sentences = []
        for sentence in sentences:
            sent_start = sentence['start_time']
            sent_end = sentence['end_time']
            
            # 문장이 이 구간에 속하는지 확인
            if sent_start >= start_time and sent_end <= end_time:
                group_sentences.append(sentence)
            elif sent_start < end_time and sent_end > start_time:  # 구간과 겹치는 경우
                group_sentences.append(sentence)
        
        if group_sentences:  # 빈 그룹 제외
            groups.append({
                'start_time': start_time,
                'end_time': end_time,
                'sentences': group_sentences
            })
    
    return groups

def reorganize_chapters_scenes(media_id, filepath, sentences, template="auto"):
    """템플릿 기반 챕터/씬 재구성"""
    try:
        conn = sqlite3.connect('dev.db')
        cursor = conn.cursor()
        
        # 기존 챕터/씬/문장 삭제
        cursor.execute("DELETE FROM Sentence WHERE sceneId IN (SELECT id FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?))", (media_id,))
        cursor.execute("DELETE FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?)", (media_id,))
        cursor.execute("DELETE FROM Chapter WHERE mediaId = ?", (media_id,))
        
        # 템플릿별 처리
        if template == "toeic_lc":
            print("Using TOEIC LC template for organization")
            apply_toeic_lc_template(cursor, media_id, sentences)
        elif template == "toeic_rc":
            print("Using TOEIC RC template for organization")
            apply_toeic_rc_template(cursor, media_id, sentences)
        elif template == "general":
            print("Using general lecture template for organization")
            apply_general_template(cursor, media_id, sentences)
        elif template == "conversation":
            print("Using conversation template for organization")
            apply_conversation_template(cursor, media_id, sentences)
        elif template == "audiobook":
            print("Using audiobook template for organization")
            apply_audiobook_template(cursor, media_id, sentences)
        elif template == "manual":
            print("Using manual setup template for organization")
            apply_manual_template(cursor, media_id, sentences)
        else:  # auto or any unknown template
            print("Using automatic silence-based organization")
            apply_auto_template(cursor, media_id, filepath, sentences)
        
        conn.commit()
        conn.close()
        
        print(f"Chapter/Scene reorganization completed using {template} template")
        
    except Exception as e:
        print(f"Reorganization error: {e}")
        # 에러시 기본 구조로 복원
        try:
            conn.rollback()
            conn.close()
        except:
            pass

def apply_toeic_lc_template(cursor, media_id, sentences):
    """TOEIC LC 템플릿 적용 - Part 1-4 구조"""
    try:
        # 먼저 모든 문장을 DB에 저장
        conn = sqlite3.connect('dev.db')
        
        # 단일 챕터/씬으로 일단 저장
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, "임시", 0, sentences[-1]['end_time'] if sentences else 60, 1)
        )
        temp_chapter_id = cursor.lastrowid
        
        cursor.execute(
            "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (temp_chapter_id, "임시", 0, sentences[-1]['end_time'] if sentences else 60, 1)
        )
        temp_scene_id = cursor.lastrowid
        
        # 모든 문장 저장
        for sentence in sentences:
            cursor.execute(
                """INSERT INTO Sentence 
                (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (temp_scene_id, sentence['english'], sentence['korean'], 
                 sentence['start_time'], sentence['end_time'], 0, sentence['order'])
            )
        
        conn.commit()
        conn.close()
        
        # TOEIC 템플릿 적용
        from toeic_smart_template import apply_toeic_smart_template
        apply_toeic_smart_template(media_id)
        print("TOEIC LC template applied successfully")
        
    except Exception as e:
        print(f"TOEIC template error: {e}")
        print("Using general template as fallback")
        # 에러 시 임시 데이터 삭제하고 일반 템플릿 적용
        try:
            cursor.execute("DELETE FROM Sentence WHERE sceneId IN (SELECT id FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?))", (media_id,))
            cursor.execute("DELETE FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?)", (media_id,))
            cursor.execute("DELETE FROM Chapter WHERE mediaId = ?", (media_id,))
            apply_general_template(cursor, media_id, sentences)
        except:
            pass

def apply_toeic_rc_template(cursor, media_id, sentences):
    """TOEIC RC 템플릿 적용 - Part 5-7 구조"""
    # TOEIC RC는 일반적으로 Part 5 (문법), Part 6 (빈칸), Part 7 (독해)로 구성
    # 시간 기반으로 3개 파트로 분할
    total_duration = sentences[-1]['end_time'] if sentences else 60
    part_duration = total_duration / 3
    
    parts = ["Part 5 - Grammar", "Part 6 - Text Completion", "Part 7 - Reading Comprehension"]
    
    for i, part_title in enumerate(parts):
        start_time = i * part_duration
        end_time = (i + 1) * part_duration
        
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, part_title, start_time, end_time, i + 1)
        )
        chapter_id = cursor.lastrowid
        
        # 해당 구간의 문장들 찾기
        part_sentences = [s for s in sentences if start_time <= s['start_time'] < end_time]
        
        if part_sentences:
            # 10문장씩 씬으로 분할
            scene_size = 10
            for scene_idx in range(0, len(part_sentences), scene_size):
                scene_sentences = part_sentences[scene_idx:scene_idx + scene_size]
                scene_title = f"Section {scene_idx // scene_size + 1}"
                
                scene_start = scene_sentences[0]['start_time']
                scene_end = scene_sentences[-1]['end_time']
                
                cursor.execute(
                    "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                    (chapter_id, scene_title, scene_start, scene_end, scene_idx // scene_size + 1)
                )
                scene_id = cursor.lastrowid
                
                for sentence in scene_sentences:
                    cursor.execute(
                        """INSERT INTO Sentence 
                        (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (scene_id, sentence['english'], sentence['korean'], 
                         sentence['start_time'], sentence['end_time'], 0, sentence['order'])
                    )

def apply_general_template(cursor, media_id, sentences):
    """일반 강의 템플릿 - 시간 기반 챕터 분할"""
    total_duration = sentences[-1]['end_time'] if sentences else 60
    
    # 시간 길이에 따라 적절한 챕터 수 결정
    if total_duration > 3600:  # 1시간 이상
        chapter_count = 6
    elif total_duration > 1800:  # 30분 이상
        chapter_count = 4
    else:
        chapter_count = 2
    
    chapter_duration = total_duration / chapter_count
    
    for i in range(chapter_count):
        start_time = i * chapter_duration
        end_time = (i + 1) * chapter_duration
        
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, f"강의 {i + 1}", start_time, end_time, i + 1)
        )
        chapter_id = cursor.lastrowid
        
        # 해당 구간의 문장들
        chapter_sentences = [s for s in sentences if start_time <= s['start_time'] < end_time]
        
        if chapter_sentences:
            # 15문장씩 씬으로 분할
            scene_size = 15
            for scene_idx in range(0, len(chapter_sentences), scene_size):
                scene_sentences = chapter_sentences[scene_idx:scene_idx + scene_size]
                scene_title = f"섹션 {scene_idx // scene_size + 1}"
                
                scene_start = scene_sentences[0]['start_time']
                scene_end = scene_sentences[-1]['end_time']
                
                cursor.execute(
                    "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                    (chapter_id, scene_title, scene_start, scene_end, scene_idx // scene_size + 1)
                )
                scene_id = cursor.lastrowid
                
                for sentence in scene_sentences:
                    cursor.execute(
                        """INSERT INTO Sentence 
                        (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (scene_id, sentence['english'], sentence['korean'], 
                         sentence['start_time'], sentence['end_time'], 0, sentence['order'])
                    )

def apply_conversation_template(cursor, media_id, sentences):
    """대화/인터뷰 템플릿 - 화자 변경 기반"""
    # 간단한 구현: 시간 기반으로 대화 턴 추정
    total_duration = sentences[-1]['end_time'] if sentences else 60
    segment_duration = 300  # 5분 세그먼트
    
    segment_count = max(1, int(total_duration / segment_duration))
    
    for i in range(segment_count):
        start_time = i * segment_duration
        end_time = min((i + 1) * segment_duration, total_duration)
        
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, f"대화 세그먼트 {i + 1}", start_time, end_time, i + 1)
        )
        chapter_id = cursor.lastrowid
        
        # 해당 구간의 문장들
        segment_sentences = [s for s in sentences if start_time <= s['start_time'] < end_time]
        
        if segment_sentences:
            # 8문장씩 씬으로 분할 (대화 턴)
            scene_size = 8
            for scene_idx in range(0, len(segment_sentences), scene_size):
                scene_sentences = segment_sentences[scene_idx:scene_idx + scene_size]
                scene_title = f"턴 {scene_idx // scene_size + 1}"
                
                scene_start = scene_sentences[0]['start_time']
                scene_end = scene_sentences[-1]['end_time']
                
                cursor.execute(
                    "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                    (chapter_id, scene_title, scene_start, scene_end, scene_idx // scene_size + 1)
                )
                scene_id = cursor.lastrowid
                
                for sentence in scene_sentences:
                    cursor.execute(
                        """INSERT INTO Sentence 
                        (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (scene_id, sentence['english'], sentence['korean'], 
                         sentence['start_time'], sentence['end_time'], 0, sentence['order'])
                    )

def apply_audiobook_template(cursor, media_id, sentences):
    """오디오북 템플릿 - 챕터 기반"""
    total_duration = sentences[-1]['end_time'] if sentences else 60
    chapter_duration = 900  # 15분 챕터
    
    chapter_count = max(1, int(total_duration / chapter_duration))
    
    for i in range(chapter_count):
        start_time = i * chapter_duration
        end_time = min((i + 1) * chapter_duration, total_duration)
        
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, f"챕터 {i + 1}", start_time, end_time, i + 1)
        )
        chapter_id = cursor.lastrowid
        
        # 해당 구간의 문장들
        chapter_sentences = [s for s in sentences if start_time <= s['start_time'] < end_time]
        
        if chapter_sentences:
            # 20문장씩 씬으로 분할
            scene_size = 20
            for scene_idx in range(0, len(chapter_sentences), scene_size):
                scene_sentences = chapter_sentences[scene_idx:scene_idx + scene_size]
                scene_title = f"섹션 {scene_idx // scene_size + 1}"
                
                scene_start = scene_sentences[0]['start_time']
                scene_end = scene_sentences[-1]['end_time']
                
                cursor.execute(
                    "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                    (chapter_id, scene_title, scene_start, scene_end, scene_idx // scene_size + 1)
                )
                scene_id = cursor.lastrowid
                
                for sentence in scene_sentences:
                    cursor.execute(
                        """INSERT INTO Sentence 
                        (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (scene_id, sentence['english'], sentence['korean'], 
                         sentence['start_time'], sentence['end_time'], 0, sentence['order'])
                    )

def apply_manual_template(cursor, media_id, sentences):
    """수동 설정 템플릿 - 시간 간격 기반 자동 챕터/씬 분할"""
    if not sentences:
        return
    
    # 시간 간격 분석하여 챕터/씬 분할점 찾기
    chapter_breaks = []  # 큰 간격 (10초 이상)
    scene_breaks = []    # 중간 간격 (3초 이상)
    
    for i in range(1, len(sentences)):
        gap = sentences[i]['start_time'] - sentences[i-1]['end_time']
        
        if gap >= 10.0:  # 10초 이상 간격 -> 새 챕터
            chapter_breaks.append(i)
        elif gap >= 3.0:  # 3초 이상 간격 -> 새 씬
            scene_breaks.append(i)
    
    # 챕터 단위로 문장 그룹화
    chapter_groups = []
    chapter_start = 0
    
    for break_idx in chapter_breaks + [len(sentences)]:
        chapter_sentences = sentences[chapter_start:break_idx]
        if chapter_sentences:
            chapter_groups.append({
                'sentences': chapter_sentences,
                'start': chapter_sentences[0]['start_time'],
                'end': chapter_sentences[-1]['end_time'],
                'scene_breaks': [sb - chapter_start for sb in scene_breaks if chapter_start <= sb < break_idx]
            })
        chapter_start = break_idx
    
    # 챕터와 씬 생성
    for c_idx, chapter_group in enumerate(chapter_groups):
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, f"Chapter {c_idx + 1}", chapter_group['start'], chapter_group['end'], c_idx + 1)
        )
        chapter_id = cursor.lastrowid
        
        # 씬 단위로 문장 그룹화
        scene_groups = []
        scene_start = 0
        
        for break_idx in chapter_group['scene_breaks'] + [len(chapter_group['sentences'])]:
            scene_sentences = chapter_group['sentences'][scene_start:break_idx]
            if scene_sentences:
                scene_groups.append(scene_sentences)
            scene_start = break_idx
        
        # 씬 생성 및 문장 삽입
        for s_idx, scene_sentences in enumerate(scene_groups):
            cursor.execute(
                "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                (chapter_id, f"Scene {s_idx + 1}", 
                 scene_sentences[0]['start_time'], 
                 scene_sentences[-1]['end_time'], 
                 s_idx + 1)
            )
            scene_id = cursor.lastrowid
            
            # 문장 삽입
            for sentence in scene_sentences:
                cursor.execute(
                    """INSERT INTO Sentence 
                    (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (scene_id, sentence['english'], sentence['korean'], 
                     sentence['start_time'], sentence['end_time'], 0, sentence['order'])
                )
    
    print(f"Created {len(chapter_groups)} chapters based on time gaps (10s+ breaks)")
    total_scenes = sum(len(cg['scene_breaks']) + 1 for cg in chapter_groups)
    print(f"Created {total_scenes} scenes based on time gaps (3s+ breaks)")

def apply_auto_template(cursor, media_id, filepath, sentences):
    """자동 감지 템플릿 - 무음 구간 기반"""
    # 기존 무음 구간 분석 로직 사용
    break_points = detect_silence_breaks(filepath)
    groups = group_sentences_by_breaks(sentences, break_points)
    
    if not groups:
        print("No groups found, using single chapter/scene")
        # 기본 단일 챕터/씬으로 복원
        duration = sentences[-1]['end_time'] if sentences else 60
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, "전체", 0, duration, 1)
        )
        chapter_id = cursor.lastrowid
        
        cursor.execute(
            "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (chapter_id, "전체", 0, duration, 1)
        )
        scene_id = cursor.lastrowid
        
        # 모든 문장을 단일 씬에 추가
        for sentence in sentences:
            cursor.execute(
                """INSERT INTO Sentence 
                (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (scene_id, sentence['english'], sentence['korean'], 
                 sentence['start_time'], sentence['end_time'], 0, sentence['order'])
            )
    else:
        # 그룹 기반 챕터/씬 생성
        for chapter_idx, group in enumerate(groups):
            chapter_title = f"Chapter {chapter_idx + 1}"
            
            cursor.execute(
                "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                (media_id, chapter_title, group['start_time'], group['end_time'], chapter_idx + 1)
            )
            chapter_id = cursor.lastrowid
            
            # 큰 그룹은 씬으로 세분화 (문장 20개 이상)
            if len(group['sentences']) > 20:
                # 10문장씩 씬으로 분할
                scene_size = 10
                for scene_idx in range(0, len(group['sentences']), scene_size):
                    scene_sentences = group['sentences'][scene_idx:scene_idx + scene_size]
                    scene_title = f"Scene {scene_idx // scene_size + 1}"
                    
                    scene_start = scene_sentences[0]['start_time']
                    scene_end = scene_sentences[-1]['end_time']
                    
                    cursor.execute(
                        "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                        (chapter_id, scene_title, scene_start, scene_end, scene_idx // scene_size + 1)
                    )
                    scene_id = cursor.lastrowid
                    
                    # 씬에 문장들 추가
                    for sentence in scene_sentences:
                        cursor.execute(
                            """INSERT INTO Sentence 
                            (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (scene_id, sentence['english'], sentence['korean'], 
                             sentence['start_time'], sentence['end_time'], 0, sentence['order'])
                        )
            else:
                # 작은 그룹은 단일 씬으로
                scene_title = "Scene 1"
                
                cursor.execute(
                    "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                    (chapter_id, scene_title, group['start_time'], group['end_time'], 1)
                )
                scene_id = cursor.lastrowid
                
                # 모든 문장을 씬에 추가
                for sentence in group['sentences']:
                    cursor.execute(
                        """INSERT INTO Sentence 
                        (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (scene_id, sentence['english'], sentence['korean'], 
                         sentence['start_time'], sentence['end_time'], 0, sentence['order'])
                    )