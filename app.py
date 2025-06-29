from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import os
from datetime import datetime
import json
import io
import sqlite3
from werkzeug.utils import secure_filename
from celery import Celery
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key'
app.config['UPLOAD_FOLDER'] = 'upload'
app.config['MAX_CONTENT_LENGTH'] = None  # 용량 제한 없음

# Celery 설정
celery = Celery('tasks', broker='redis://localhost:6379/0')

# 허용된 파일 확장자
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'mp4', 'm4a', 'ogg', 'avi', 'mov', 'mkv', 'webm', 'flv'}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/media', methods=['GET'])
def get_media_list():
    conn = sqlite3.connect('dev.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM Media ORDER BY createdAt DESC")
    media = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return jsonify(media)

@app.route('/api/media/<media_id>/chapters', methods=['GET'])
def get_chapters(media_id):
    conn = sqlite3.connect('dev.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 챕터 및 씨 정보 가져오기
    cursor.execute("""
        SELECT c.*, 
               (SELECT COUNT(*) FROM Scene WHERE chapterId = c.id) as scene_count
        FROM Chapter c
        WHERE c.mediaId = ?
        ORDER BY c.`order`
    """, (media_id,))
    
    chapters = []
    for chapter_row in cursor.fetchall():
        chapter = dict(chapter_row)
        
        # 챕터의 씨들 가져오기
        cursor.execute("""
            SELECT sc.*, 
                   (SELECT COUNT(*) FROM Sentence WHERE sceneId = sc.id) as sentence_count
            FROM Scene sc
            WHERE sc.chapterId = ?
            ORDER BY sc.`order`
        """, (chapter['id'],))
        
        chapter['scenes'] = [dict(scene_row) for scene_row in cursor.fetchall()]
        chapters.append(chapter)
    
    conn.close()
    return jsonify(chapters)

@app.route('/api/media/<media_id>/sentences-grouped', methods=['GET'])
def get_sentences_grouped(media_id):
    """챕터/씬별로 그룹화된 문장 반환"""
    conn = sqlite3.connect('dev.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 챕터 정보 가져오기
    cursor.execute("""
        SELECT c.*, COUNT(sc.id) as scene_count
        FROM Chapter c
        LEFT JOIN Scene sc ON c.id = sc.chapterId
        WHERE c.mediaId = ?
        GROUP BY c.id
        ORDER BY c.`order`
    """, (media_id,))
    
    chapters = []
    for chapter_row in cursor.fetchall():
        chapter = dict(chapter_row)
        
        # 챕터의 씬들 가져오기
        cursor.execute("""
            SELECT sc.*, COUNT(s.id) as sentence_count
            FROM Scene sc
            LEFT JOIN Sentence s ON sc.id = s.sceneId
            WHERE sc.chapterId = ?
            GROUP BY sc.id
            ORDER BY sc.`order`
        """, (chapter['id'],))
        
        scenes = []
        for scene_row in cursor.fetchall():
            scene = dict(scene_row)
            
            # 씬의 문장들 가져오기
            cursor.execute("""
                SELECT * FROM Sentence
                WHERE sceneId = ?
                ORDER BY `order`
            """, (scene['id'],))
            
            scene['sentences'] = [dict(row) for row in cursor.fetchall()]
            scenes.append(scene)
        
        chapter['scenes'] = scenes
        chapters.append(chapter)
    
    conn.close()
    return jsonify(chapters)

@app.route('/api/media/<media_id>/sentences', methods=['GET'])
def get_sentences(media_id):
    """기존 호환성을 위한 평면적 문장 리스트"""
    conn = sqlite3.connect('dev.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.*, sc.title as scene_title, c.title as chapter_title
        FROM Sentence s
        JOIN Scene sc ON s.sceneId = sc.id
        JOIN Chapter c ON sc.chapterId = c.id
        WHERE c.mediaId = ?
        ORDER BY c.`order`, sc.`order`, s.`order`
    """, (media_id,))
    
    sentences = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(sentences)

@app.route('/api/media/<media_id>/sentences/<int:sentence_id>/bookmark', methods=['POST'])
def toggle_bookmark(media_id, sentence_id):
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    # 현재 북마크 상태 가져오기
    cursor.execute("SELECT bookmark FROM Sentence WHERE id = ?", (sentence_id,))
    result = cursor.fetchone()
    
    if result:
        new_bookmark = 0 if result[0] else 1
        cursor.execute("UPDATE Sentence SET bookmark = ? WHERE id = ?", (new_bookmark, sentence_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'bookmark': bool(new_bookmark)})
    
    conn.close()
    return jsonify({'success': False}), 404

@app.route('/api/media/<media_id>/export-bookmarks', methods=['GET'])
def export_bookmarks(media_id):
    conn = sqlite3.connect('dev.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.*, sc.title as scene_title, c.title as chapter_title, m.filename
        FROM Sentence s
        JOIN Scene sc ON s.sceneId = sc.id
        JOIN Chapter c ON sc.chapterId = c.id
        JOIN Media m ON c.mediaId = m.id
        WHERE c.mediaId = ? AND s.bookmark = 1
        ORDER BY s.`order`
    """, (media_id,))
    
    bookmarked = cursor.fetchall()
    conn.close()
    
    if not bookmarked:
        return jsonify({'error': 'No bookmarked sentences'}), 404
    
    # MP3 부분 추출 및 TXT 내보내기
    content_lines = []
    for s in bookmarked:
        content_lines.append(f"{s['chapter_title']} > {s['scene_title']}")
        content_lines.append(f"Time: {s['startTime']:.1f}s - {s['endTime']:.1f}s")
        content_lines.append(f"English: {s['english']}")
        content_lines.append(f"Korean: {s['korean']}")
        content_lines.append("-" * 50)
    
    content = '\n'.join(content_lines)
    
    return send_file(
        io.BytesIO(content.encode('utf-8')),
        mimetype='text/plain',
        as_attachment=True,
        download_name=f'bookmarks_{media_id}.txt'
    )

@app.route('/api/sentence/<media_id>/<int:sentence_id>/extract-mp3', methods=['POST'])
def extract_mp3(media_id, sentence_id):
    try:
        conn = sqlite3.connect('dev.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 문장 정보 가져오기
        cursor.execute("""
            SELECT s.*, m.filename
            FROM Sentence s
            JOIN Scene sc ON s.sceneId = sc.id
            JOIN Chapter c ON sc.chapterId = c.id
            JOIN Media m ON c.mediaId = m.id
            WHERE s.id = ?
        """, (sentence_id,))
        
        sentence = cursor.fetchone()
        conn.close()
        
        if not sentence:
            return jsonify({'error': 'Sentence not found'}), 404
        
        # FFmpeg로 실제 MP3 추출
        import subprocess
        import uuid
        
        input_file = os.path.join(app.config['UPLOAD_FOLDER'], sentence['filename'])
        output_filename = f'sentence_{sentence_id}_{sentence["startTime"]:.1f}s-{sentence["endTime"]:.1f}s.mp3'
        output_file = os.path.join('output', output_filename)
        
        # extracted 디렉토리 생성
        os.makedirs(os.path.join('output'), exist_ok=True)
        
        # FFmpeg 명령어로 구간 추출
        cmd = [
            'ffmpeg', '-y',  # -y: 덮어쓰기 허용
            '-i', input_file,
            '-ss', str(sentence['startTime']),  # 시작 시간
            '-t', str(sentence['endTime'] - sentence['startTime']),  # 구간 길이
            '-acodec', 'mp3',
            '-ab', '128k',  # 비트레이트
            output_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and os.path.exists(output_file):
            return jsonify({
                'success': True,
                'message': f'MP3 extracted successfully',
                'filename': output_filename,
                'output_path': output_file,
                'timeRange': f'{sentence["startTime"]:.1f}s - {sentence["endTime"]:.1f}s'
            })
        else:
            app.logger.error(f"FFmpeg error: {result.stderr}")
            return jsonify({'error': 'MP3 extraction failed'}), 500
            
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'MP3 extraction timeout'}), 500
    except Exception as e:
        app.logger.error(f"MP3 extraction error: {str(e)}")
        return jsonify({'error': f'Extraction failed: {str(e)}'}), 500

def wrap_text(text, max_chars_per_line=60, for_ass=False):
    """텍스트를 적절한 길이로 줄바꿈"""
    import textwrap
    
    # textwrap을 사용하여 더 나은 줄바꿈
    wrapped_lines = textwrap.wrap(text, width=max_chars_per_line, break_long_words=False, break_on_hyphens=False)
    
    # 줄 수 제한 제거 - 전체 텍스트 표시
    # 너무 긴 경우만 제한 (12줄 이상)
    if len(wrapped_lines) > 12:
        wrapped_lines = wrapped_lines[:12]
        wrapped_lines[-1] = wrapped_lines[-1][:-3] + '...'
    
    # ASS 파일용 줄바꿈과 일반 줄바꿈 구분
    if for_ass:
        return '\\N'.join(wrapped_lines)  # ASS는 \N으로 줄바꿈
    else:
        return '\n'.join(wrapped_lines)

def create_ass_subtitle_file(english_text, korean_text, duration, output_path):
    """ASS 형식 자막 파일 생성 (영어와 한글에 다른 스타일 적용, 단일 언어도 지원)"""
    
    # ASS 헤더
    ass_content = """[Script Info]
Title: Subtitle
ScriptType: v4.00+
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: English,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,1,0,0,0,100,100,0,0,1,2,0,2,3,3,60,1
Style: Korean,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,16,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # 시간 형식 변환 (ASS는 h:mm:ss.cc 형식)
    def seconds_to_ass_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"
    
    start_time = "0:00:00.00"
    end_time = seconds_to_ass_time(duration)
    
    # 영어와 한글을 한 줄에 표시 (ASS 자동 줄바꿈 사용)
    if english_text and korean_text:
        # 영어와 한글을 각각 다른 스타일로 표시
        ass_content += f"Dialogue: 0,{start_time},{end_time},English,,0,0,0,,{english_text}\n"
        ass_content += f"Dialogue: 1,{start_time},{end_time},Korean,,0,0,0,,{korean_text}\n"
    elif english_text:
        ass_content += f"Dialogue: 0,{start_time},{end_time},English,,0,0,0,,{english_text}\n"
    elif korean_text:
        ass_content += f"Dialogue: 0,{start_time},{end_time},Korean,,0,0,0,,{korean_text}\n"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    
    return output_path

def create_srt_subtitle_file(text, duration, output_path):
    """SRT 형식 자막 파일 생성 (단일 언어용)"""
    wrapped_text = wrap_text(text, max_chars_per_line=40)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"1\n00:00:00,000 --> {int(duration//3600):02d}:{int((duration%3600)//60):02d}:{duration%60:06.3f}\n{wrapped_text}\n\n")
    
    return output_path

def get_media_name(media_id):
    """미디어 ID로부터 미디어 이름 가져오기"""
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM Media WHERE id = ?", (media_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        # 확장자 제거하여 깔끔한 디렉토리명 생성
        filename = result[0]
        return filename.rsplit('.', 1)[0] if '.' in filename else filename
    return f"media_{media_id}"

def create_default_structure_for_video(media_id, filename):
    """영상 파일을 위한 기본 챕터/신/문장 구조 생성"""
    try:
        import subprocess
        
        # FFprobe로 영상 길이 가져오기
        input_file = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', input_file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            app.logger.error(f"Failed to get video duration: {result.stderr}")
            return False
            
        try:
            duration = float(result.stdout.strip())
        except:
            app.logger.error(f"Invalid duration format: {result.stdout}")
            return False
        
        conn = sqlite3.connect('dev.db')
        cursor = conn.cursor()
        
        # 기본 챕터 생성
        cursor.execute("""
            INSERT INTO Chapter (mediaId, title, `order`, startTime, endTime)
            VALUES (?, 'Full Video', 1, 0, ?)
        """, (media_id, duration))
        chapter_id = cursor.lastrowid
        
        # 기본 신 생성
        cursor.execute("""
            INSERT INTO Scene (chapterId, title, `order`, startTime, endTime)
            VALUES (?, 'Full Scene', 1, 0, ?)
        """, (chapter_id, duration))
        scene_id = cursor.lastrowid
        
        # 기본 문장 생성 (전체 영상을 하나의 문장으로)
        cursor.execute("""
            INSERT INTO Sentence (sceneId, `order`, startTime, endTime, english, korean, bookmark)
            VALUES (?, 1, 0, ?, 'Full video content', '전체 영상 내용', 0)
        """, (scene_id, duration))
        
        conn.commit()
        conn.close()
        
        app.logger.info(f"Created default structure for video {filename} (duration: {duration}s)")
        return True
        
    except Exception as e:
        app.logger.error(f"Failed to create default structure: {e}")
        return False

@app.route('/api/sentence/<media_id>/<int:sentence_id>/extract-mp4', methods=['POST'])
def extract_mp4(media_id, sentence_id):
    try:
        conn = sqlite3.connect('dev.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 문장 정보 가져오기
        cursor.execute("""
            SELECT s.*, m.filename
            FROM Sentence s
            JOIN Scene sc ON s.sceneId = sc.id
            JOIN Chapter c ON sc.chapterId = c.id
            JOIN Media m ON c.mediaId = m.id
            WHERE s.id = ?
        """, (sentence_id,))
        
        sentence = cursor.fetchone()
        conn.close()
        
        if not sentence:
            return jsonify({'error': 'Sentence not found'}), 404
            
        # FFmpeg로 MP4 생성 (1920x1080 검정배경 + 중앙 영어자막)
        import subprocess
        import uuid
        
        # Convert Row to dict for easier access
        sentence = dict(sentence)
        
        # Check if english text exists
        if not sentence.get('english'):
            return jsonify({'error': 'Sentence has no English text'}), 400
        
        input_file = os.path.join(app.config['UPLOAD_FOLDER'], sentence['filename'])
        
        # 파일 확장자로 비디오/오디오 구분
        video_extensions = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv'}
        file_ext = sentence['filename'].rsplit('.', 1)[1].lower() if '.' in sentence['filename'] else ''
        is_video_file = file_ext in video_extensions
        
        # 미디어별 디렉토리 생성
        media_name = get_media_name(media_id)
        media_dir = os.path.join('output', media_name)
        os.makedirs(media_dir, exist_ok=True)
        
        output_filename = f'sentence_{sentence_id}_{sentence["startTime"]:.1f}s-{sentence["endTime"]:.1f}s.mp4'
        output_file = os.path.join(media_dir, output_filename)
        
        # 텍스트 줄바꿈 처리
        wrapped_text = wrap_text(sentence['english'], max_chars_per_line=40)
        
        duration = sentence['endTime'] - sentence['startTime']
        
        # SRT 자막 파일 생성
        srt_filename = f'temp_subtitle_{uuid.uuid4().hex}.srt'
        srt_path = os.path.join(media_dir, srt_filename)
        
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(f"1\n00:00:00,000 --> {int(duration//3600):02d}:{int((duration%3600)//60):02d}:{duration%60:06.3f}\n{wrapped_text}\n\n")
        
        # FFmpeg 명령어 구성 (비디오/오디오 파일에 따라 다르게 처리)
        if is_video_file:
            # 비디오 파일: 원본 영상에 자막만 추가
            cmd = [
                'ffmpeg',
                '-ss', str(sentence['startTime']),
                '-i', input_file,
                '-t', str(duration),
                '-vf', f"subtitles={srt_path}:fontsdir=fonts:force_style='FontName=\"Noto Sans KR\",FontSize=38,PrimaryColour=&Hffffff,Bold=1,Alignment=2,MarginV=50'",
                '-af', 'volume=3.0',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-y',
                output_file
            ]
        else:
            # 오디오 파일: 검정 배경 비디오 + SRT 자막 + 오디오
            cmd = [
                'ffmpeg',
                '-f', 'lavfi',
                '-i', f'color=black:size=1920x1080:duration={duration}:rate=30',
                '-ss', str(sentence['startTime']),
                '-i', input_file,
                '-t', str(duration),
                '-filter_complex',
                f"[0:v]subtitles={srt_path}:fontsdir=fonts:force_style='FontName=\"Noto Sans KR\",FontSize=38,PrimaryColour=&Hffffff,Bold=1,Alignment=2,MarginV=50'[v]",
                '-map', '[v]',
                '-map', '1:a',
                '-af', 'volume=3.0',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-shortest',
                '-y',
                output_file
            ]
        
        # FFmpeg 실행
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # 임시 자막 파일 삭제
        try:
            os.remove(srt_path)
        except:
            pass
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'message': f'MP4 created successfully',
                'filename': output_filename,
                'output_path': output_file,
                'duration': duration
            })
        else:
            app.logger.error(f"FFmpeg error: {result.stderr}")
            return jsonify({'error': 'MP4 creation failed'}), 500
            
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'MP4 creation timeout'}), 500
    except Exception as e:
        app.logger.error(f"MP4 creation error: {str(e)}")
        return jsonify({'error': f'Creation failed: {str(e)}'}), 500

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_audio_from_video(video_path, unique_filename):
    """영상 파일에서 오디오 추출"""
    try:
        import subprocess
        
        # 출력 파일 경로 (MP3)
        base_name = unique_filename.rsplit('.', 1)[0]
        audio_filename = f"{base_name}.mp3"
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
        
        # FFmpeg 명령어로 오디오 추출
        cmd = [
            'ffmpeg', '-y',  # -y: 덮어쓰기 허용
            '-i', video_path,  # 입력 영상 파일
            '-vn',  # 비디오 스트림 제외
            '-acodec', 'mp3',  # 오디오 코덱: MP3
            '-ab', '128k',  # 비트레이트: 128kbps
            '-ar', '16000',  # 샘플링 레이트: 16kHz (Whisper 최적화)
            '-ac', '1',  # 모노 채널
            audio_path
        ]
        
        # FFmpeg 실행
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5분 타임아웃
        
        if result.returncode == 0 and os.path.exists(audio_path):
            app.logger.info(f"Audio extracted successfully: {audio_filename}")
            return audio_path
        else:
            app.logger.error(f"FFmpeg error: {result.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        app.logger.error("Audio extraction timeout")
        return None
    except Exception as e:
        app.logger.error(f"Audio extraction error: {str(e)}")
        return None

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        app.logger.info("Upload request received")
        
        if 'file' not in request.files:
            app.logger.error("No file part in request")
            return jsonify({'error': 'No file part'}), 400
        
        file = request.files['file']
        if file.filename == '':
            app.logger.error("No selected file")
            return jsonify({'error': 'No selected file'}), 400
        
        app.logger.info(f"Uploading file: {file.filename}, size: {file.content_length if hasattr(file, 'content_length') else 'unknown'}")
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            # 업로드 폴더 존재 확인
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            app.logger.info(f"Saving file to: {filepath}")
            
            # 파일 저장
            file.save(filepath)
            
            app.logger.info(f"File saved successfully: {filepath}")
            
            # 영상 파일인 경우 오디오 추출
            video_extensions = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv'}
            file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
            
            # 영상 파일 처리 로직 변경: 영상 파일을 그대로 유지
            is_video = file_ext in video_extensions
            if is_video:
                app.logger.info(f"Video file detected: {filename}, keeping original video file")
                # 영상 파일은 그대로 유지 (오디오 추출하지 않음)
            
            # DB에 미디어 정보 저장
            conn = sqlite3.connect('dev.db')
            cursor = conn.cursor()
            
            # 영상 파일인 경우 바로 사용 가능한 상태로, 오디오 파일인 경우 처리 대기 상태로 설정
            status = 'completed' if is_video else 'uploaded'
            cursor.execute(
                "INSERT INTO Media (filename, createdAt, status) VALUES (?, datetime('now'), ?)",
                (unique_filename, status)
            )
            media_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # 영상 파일인 경우 기본 구조 생성
            if is_video:
                create_default_structure_for_video(media_id, unique_filename)
                message = 'Video uploaded successfully. Ready for MP3/MP4 extraction.'
            else:
                message = 'Audio file uploaded successfully. Ready for processing.'
            
            return jsonify({
                'success': True,
                'media_id': media_id,
                'message': message,
                'filename': unique_filename,
                'original_filename': filename,
                'status': status,
                'is_video': is_video
            })
        
        return jsonify({'error': 'Invalid file type'}), 400
        
    except Exception as e:
        app.logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/media/<int:media_id>/status', methods=['GET'])
def get_processing_status(media_id):
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    # 미디어 처리 상태 확인
    cursor.execute("SELECT status, current_sentence FROM Media WHERE id = ?", (media_id,))
    media_result = cursor.fetchone()
    
    # 문장, 챕터, 씨 개수 확인
    cursor.execute("""
        SELECT 
            COUNT(DISTINCT c.id) as chapter_count,
            COUNT(DISTINCT sc.id) as scene_count,
            COUNT(s.id) as sentence_count
        FROM Chapter c
        LEFT JOIN Scene sc ON c.id = sc.chapterId
        LEFT JOIN Sentence s ON sc.id = s.sceneId
        WHERE c.mediaId = ?
    """, (media_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    status = media_result[0] if media_result else 'processing'
    current_sentence = media_result[1] if media_result else ''
    
    return jsonify({
        'processed': result[2] > 0 and status == 'completed',
        'sentence_count': result[2],
        'status': status,
        'current_sentence': current_sentence
    })

@app.route('/api/media/<int:media_id>', methods=['DELETE'])
def delete_media(media_id):
    """미디어 삭제 (파일 및 모든 관련 데이터)"""
    try:
        conn = sqlite3.connect('dev.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 미디어 정보 가져오기
        cursor.execute("SELECT filename FROM Media WHERE id = ?", (media_id,))
        media = cursor.fetchone()
        
        if not media:
            conn.close()
            return jsonify({'error': 'Media not found'}), 404
        
        # 파일 삭제
        try:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], media['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"Deleted file: {filepath}")
        except Exception as e:
            print(f"File deletion error: {e}")
        
        # DB에서 모든 관련 데이터 삭제 (외래키 관계 순서대로)
        cursor.execute("DELETE FROM Sentence WHERE sceneId IN (SELECT id FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?))", (media_id,))
        cursor.execute("DELETE FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?)", (media_id,))
        cursor.execute("DELETE FROM Chapter WHERE mediaId = ?", (media_id,))
        cursor.execute("DELETE FROM Media WHERE id = ?", (media_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Media deleted successfully'})
        
    except Exception as e:
        app.logger.error(f"Delete media error: {str(e)}")
        return jsonify({'error': f'Delete failed: {str(e)}'}), 500

@app.route('/api/media/<int:media_id>/subtitles', methods=['DELETE'])
def delete_subtitles(media_id):
    """미디어의 자막(문장) 데이터만 삭제"""
    try:
        conn = sqlite3.connect('dev.db')
        cursor = conn.cursor()
        
        # 미디어 존재 확인
        cursor.execute("SELECT filename FROM Media WHERE id = ?", (media_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({'error': 'Media not found'}), 404
        
        # 관련 자막 데이터 삭제 (외래키 제약조건에 따라 역순으로)
        cursor.execute("DELETE FROM Sentence WHERE sceneId IN (SELECT id FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?))", (media_id,))
        cursor.execute("DELETE FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?)", (media_id,))
        cursor.execute("DELETE FROM Chapter WHERE mediaId = ?", (media_id,))
        
        # 미디어 상태를 업로드 상태로 되돌리기
        cursor.execute("UPDATE Media SET status = 'uploaded', current_sentence = '' WHERE id = ?", (media_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Subtitles deleted successfully. Media is ready for re-processing.'})
        
    except Exception as e:
        app.logger.error(f"Delete subtitles error: {str(e)}")
        return jsonify({'error': f'Delete subtitles failed: {str(e)}'}), 500

@app.route('/api/download/<filename>')
def download_extracted_mp3(filename):
    """추출된 MP3 파일 다운로드 - 호환성을 위한 리다이렉트"""
    try:
        return send_file(
            os.path.join('output', filename),
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': 'File not found'}), 404

@app.route('/api/audio/<filename>')
def serve_audio(filename):
    """업로드된 오디오/비디오 파일 서빙"""
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # 파일 확장자로 MIME 타입 결정
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if file_ext in ['mp4', 'avi', 'mov', 'mkv', 'webm']:
            mimetype = 'video/mp4' if file_ext == 'mp4' else f'video/{file_ext}'
        elif file_ext in ['mp3', 'wav', 'm4a', 'ogg']:
            mimetype = 'audio/mpeg' if file_ext == 'mp3' else f'audio/{file_ext}'
        else:
            mimetype = 'application/octet-stream'
        
        return send_file(filepath, mimetype=mimetype)
    except Exception as e:
        return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    # upload 디렉토리 생성
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # DB 테이블 생성 (간단한 버전)
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS Media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            duration REAL,
            createdAt TIMESTAMP,
            status TEXT DEFAULT 'processing',
            current_sentence TEXT DEFAULT ''
        );
        
        CREATE TABLE IF NOT EXISTS Chapter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mediaId INTEGER,
            title TEXT,
            startTime REAL,
            endTime REAL,
            `order` INTEGER
        );
        
        CREATE TABLE IF NOT EXISTS Scene (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapterId INTEGER,
            title TEXT,
            startTime REAL,
            endTime REAL,
            `order` INTEGER
        );
        
        CREATE TABLE IF NOT EXISTS Sentence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sceneId INTEGER,
            english TEXT,
            korean TEXT,
            keyWords TEXT,
            startTime REAL,
            endTime REAL,
            bookmark INTEGER DEFAULT 0,
            `order` INTEGER
        );
    """)
    
    # 기존 Media 테이블에 새 컬럼 추가 (마이그레이션)
    try:
        cursor.execute("ALTER TABLE Media ADD COLUMN status TEXT DEFAULT 'completed'")
        print("Added status column to Media table")
    except sqlite3.OperationalError:
        pass  # 컬럼이 이미 존재함
        
    try:
        cursor.execute("ALTER TABLE Media ADD COLUMN current_sentence TEXT DEFAULT ''")
        print("Added current_sentence column to Media table")
    except sqlite3.OperationalError:
        pass  # 컬럼이 이미 존재함
    
    conn.commit()
    conn.close()
    
    
    # MP3 추출 API들
    @app.route('/api/media/<media_id>/chapter/<int:chapter_id>/extract-mp3', methods=['POST'])
    def extract_chapter_mp3(media_id, chapter_id):
        """챕터별 MP3 추출"""
        try:
            conn = sqlite3.connect('dev.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 챕터 정보 가져오기
            cursor.execute("""
                SELECT c.*, m.filename
                FROM Chapter c
                JOIN Media m ON c.mediaId = m.id
                WHERE c.id = ? AND c.mediaId = ?
            """, (chapter_id, media_id))
            
            chapter = cursor.fetchone()
            conn.close()
            
            if not chapter:
                return jsonify({'success': False, 'error': 'Chapter not found'}), 404
            
            # FFmpeg로 MP3 추출
            import subprocess
            import uuid
            
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], chapter['filename'])
            output_filename = f'chapter_{chapter_id}_{chapter["title"].replace(" ", "_")}.mp3'
            output_file = os.path.join('output', output_filename)
            
            # extracted 디렉토리 생성
            os.makedirs(os.path.join('output'), exist_ok=True)
            
            # FFmpeg 명령어로 구간 추출
            cmd = [
                'ffmpeg', '-y',  # -y: 덮어쓰기 허용
                '-i', input_file,
                '-ss', str(chapter['startTime']),  # 시작 시간
                '-t', str(chapter['endTime'] - chapter['startTime']),  # 구간 길이
                '-acodec', 'mp3',
                '-ab', '128k',  # 비트레이트
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                output_path = output_file
                return jsonify({'success': True, 'output_path': output_path})
            else:
                return jsonify({'success': False, 'error': f'FFmpeg error: {result.stderr}'}), 500
                
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/media/<media_id>/scene/<int:scene_id>/extract-mp3', methods=['POST'])
    def extract_scene_mp3(media_id, scene_id):
        """씬별 MP3 추출"""
        try:
            conn = sqlite3.connect('dev.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 씬 정보 가져오기
            cursor.execute("""
                SELECT sc.*, c.title as chapter_title, m.filename
                FROM Scene sc
                JOIN Chapter c ON sc.chapterId = c.id
                JOIN Media m ON c.mediaId = m.id
                WHERE sc.id = ? AND c.mediaId = ?
            """, (scene_id, media_id))
            
            scene = cursor.fetchone()
            conn.close()
            
            if not scene:
                return jsonify({'success': False, 'error': 'Scene not found'}), 404
            
            # FFmpeg로 MP3 추출
            import subprocess
            
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], scene['filename'])
            output_filename = f'scene_{scene_id}_{scene["title"].replace(" ", "_")}.mp3'
            output_file = os.path.join('output', output_filename)
            
            # extracted 디렉토리 생성
            os.makedirs(os.path.join('output'), exist_ok=True)
            
            # FFmpeg 명령어로 구간 추출
            cmd = [
                'ffmpeg', '-y',
                '-i', input_file,
                '-ss', str(scene['startTime']),
                '-t', str(scene['endTime'] - scene['startTime']),
                '-acodec', 'mp3',
                '-ab', '128k',
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                output_path = output_file
                return jsonify({'success': True, 'output_path': output_path})
            else:
                return jsonify({'success': False, 'error': f'FFmpeg error: {result.stderr}'}), 500
                
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/media/<media_id>/extract-all-chapters', methods=['POST'])
    def extract_all_chapters_mp3(media_id):
        """모든 챕터 MP3 추출 후 ZIP으로 압축"""
        try:
            conn = sqlite3.connect('dev.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT c.*, m.filename
                FROM Chapter c
                JOIN Media m ON c.mediaId = m.id
                WHERE c.mediaId = ?
                ORDER BY c.`order`
            """, (media_id,))
            
            chapters = cursor.fetchall()
            conn.close()
            
            if not chapters:
                return jsonify({'success': False, 'error': 'No chapters found'}), 404
            
            import subprocess, zipfile
            from datetime import datetime
            
            extracted_files = []
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], chapters[0]['filename'])
            
            os.makedirs(os.path.join('output'), exist_ok=True)
            
            for chapter in chapters:
                safe_title = "".join(c for c in chapter['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                output_filename = f'chapter_{chapter["order"]:02d}_{safe_title}.mp3'
                output_file = os.path.join('output', output_filename)
                
                cmd = ['ffmpeg', '-y', '-i', input_file, '-ss', str(chapter['startTime']), 
                      '-t', str(chapter['endTime'] - chapter['startTime']), '-acodec', 'mp3', '-ab', '128k', output_file]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    extracted_files.append(output_file)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f'chapters_{media_id}_{timestamp}.zip'
            zip_path = os.path.join('output', zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for file_path in extracted_files:
                    zipf.write(file_path, os.path.basename(file_path))
            
            for file_path in extracted_files:
                try: os.remove(file_path)
                except: pass
            
            return jsonify({'success': True, 'output_path': zip_path})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/media/<media_id>/extract-all-scenes', methods=['POST'])
    def extract_all_scenes_mp3(media_id):
        """모든 씬 MP3 추출 후 ZIP으로 압축"""
        try:
            conn = sqlite3.connect('dev.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT sc.*, c.`order` as chapter_order, m.filename
                FROM Scene sc
                JOIN Chapter c ON sc.chapterId = c.id
                JOIN Media m ON c.mediaId = m.id
                WHERE c.mediaId = ?
                ORDER BY c.`order`, sc.`order`
            """, (media_id,))
            
            scenes = cursor.fetchall()
            conn.close()
            
            if not scenes:
                return jsonify({'success': False, 'error': 'No scenes found'}), 404
            
            import subprocess, zipfile
            from datetime import datetime
            
            extracted_files = []
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], scenes[0]['filename'])
            
            os.makedirs(os.path.join('output'), exist_ok=True)
            
            for scene in scenes:
                safe_title = "".join(c for c in scene['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                output_filename = f'scene_{scene["chapter_order"]:02d}_{scene["order"]:02d}_{safe_title}.mp3'
                output_file = os.path.join('output', output_filename)
                
                cmd = ['ffmpeg', '-y', '-i', input_file, '-ss', str(scene['startTime']), 
                      '-t', str(scene['endTime'] - scene['startTime']), '-acodec', 'mp3', '-ab', '128k', output_file]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    extracted_files.append(output_file)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f'scenes_{media_id}_{timestamp}.zip'
            zip_path = os.path.join('output', zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for file_path in extracted_files:
                    zipf.write(file_path, os.path.basename(file_path))
            
            for file_path in extracted_files:
                try: os.remove(file_path)
                except: pass
            
            return jsonify({'success': True, 'output_path': zip_path})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/media/<media_id>/extract-bookmarked', methods=['POST'])
    def extract_bookmarked_mp3(media_id):
        """북마크된 문장들 MP3 추출 후 ZIP으로 압축"""
        try:
            conn = sqlite3.connect('dev.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT s.*, sc.title as scene_title, c.title as chapter_title, m.filename
                FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                JOIN Chapter c ON sc.chapterId = c.id
                JOIN Media m ON c.mediaId = m.id
                WHERE c.mediaId = ? AND s.bookmark = 1
                ORDER BY s.`order`
            """, (media_id,))
            
            bookmarked = cursor.fetchall()
            conn.close()
            
            if not bookmarked:
                return jsonify({'success': False, 'error': 'No bookmarked sentences found'}), 404
            
            import subprocess, zipfile
            from datetime import datetime
            
            extracted_files = []
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], bookmarked[0]['filename'])
            
            os.makedirs(os.path.join('output'), exist_ok=True)
            
            for i, sentence in enumerate(bookmarked):
                output_filename = f'bookmarked_{i+1:03d}_{sentence["startTime"]:.1f}s-{sentence["endTime"]:.1f}s.mp3'
                output_file = os.path.join('output', output_filename)
                
                cmd = ['ffmpeg', '-y', '-i', input_file, '-ss', str(sentence['startTime']), 
                      '-t', str(sentence['endTime'] - sentence['startTime']), '-acodec', 'mp3', '-ab', '128k', output_file]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    extracted_files.append(output_file)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f'bookmarked_{media_id}_{timestamp}.zip'
            zip_path = os.path.join('output', zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for file_path in extracted_files:
                    zipf.write(file_path, os.path.basename(file_path))
            
            for file_path in extracted_files:
                try: os.remove(file_path)
                except: pass
            
            return jsonify({'success': True, 'output_path': zip_path})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/media/<media_id>/vad-filter', methods=['POST'])
    def apply_vad_filter_api(media_id):
        """VAD 필터 적용"""
        try:
            data = request.get_json() or {}
            threshold = data.get('threshold', 0.3)
            
            from vad_processor import VADProcessor
            processor = VADProcessor()
            
            filtered_sentences = processor.filter_sentences_by_vad(media_id, threshold)
            
            # 통계 계산
            total_count = len(filtered_sentences)
            voice_count = sum(1 for s in filtered_sentences if s.get('vad_filtered', False))
            silence_count = total_count - voice_count
            
            return jsonify({
                'success': True,
                'total_sentences': total_count,
                'voice_sentences': voice_count,
                'silence_sentences': silence_count,
                'threshold': threshold,
                'filtered_data': filtered_sentences[:10]  # 첫 10개만 미리보기
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/media/<media_id>/create-vad-audio', methods=['POST'])
    def create_vad_audio_api(media_id):
        """VAD 기반 오디오 생성"""
        try:
            conn = sqlite3.connect('dev.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT filename FROM Media WHERE id = ?", (media_id,))
            media = cursor.fetchone()
            conn.close()
            
            if not media:
                return jsonify({'success': False, 'error': 'Media not found'}), 404
            
            from vad_processor import VADProcessor
            from datetime import datetime
            
            processor = VADProcessor()
            
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], media['filename'])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f'vad_filtered_{media_id}_{timestamp}.mp3'
            output_file = os.path.join('output', output_filename)
            
            os.makedirs(os.path.join('output'), exist_ok=True)
            
            success = processor.create_vad_audio(input_file, output_file)
            
            if success:
                output_path = output_file
                return jsonify({'success': True, 'output_path': output_path})
            else:
                return jsonify({'success': False, 'error': 'VAD audio creation failed'}), 500
                
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # MP4 내보내기 API들
    @app.route('/api/media/<media_id>/chapter/<int:chapter_id>/extract-mp4', methods=['POST'])
    def extract_chapter_mp4(media_id, chapter_id):
        """챕터별 MP4 내보내기 (전체 챕터를 하나의 파일로)"""
        try:
            conn = sqlite3.connect('dev.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 챕터 정보와 첫번째/마지막 문장 시간 가져오기
            cursor.execute("""
                SELECT c.title as chapter_title, m.filename,
                       MIN(s.startTime) as start_time,
                       MAX(s.endTime) as end_time
                FROM Chapter c
                JOIN Media m ON c.mediaId = m.id
                JOIN Scene sc ON sc.chapterId = c.id
                JOIN Sentence s ON s.sceneId = sc.id
                WHERE c.id = ? AND c.mediaId = ?
                GROUP BY c.id
            """, (chapter_id, media_id))
            
            chapter_info = cursor.fetchone()
            
            # 모든 문장들 가져오기 (자막용)
            cursor.execute("""
                SELECT s.*, ROW_NUMBER() OVER (ORDER BY s.startTime) as seq
                FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                JOIN Chapter c ON sc.chapterId = c.id
                WHERE c.id = ? AND c.mediaId = ? AND s.english IS NOT NULL AND s.english != ''
                ORDER BY s.startTime
            """, (chapter_id, media_id))
            
            sentences = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            if not chapter_info or not sentences:
                return jsonify({'success': False, 'error': 'No chapter or sentences found'}), 404
            
            chapter_info = dict(chapter_info)
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], chapter_info['filename'])
            
            import subprocess
            
            # 미디어별/챕터별 디렉토리 생성
            media_name = get_media_name(media_id)
            chapter_dir = os.path.join('output', media_name, 'chapter')
            os.makedirs(chapter_dir, exist_ok=True)
            
            # 챕터 전체를 하나의 MP4로 생성
            output_filename = f'chapter_{chapter_id}_{chapter_info["chapter_title"]}.mp4'
            output_file = os.path.join(chapter_dir, output_filename)
            
            # SRT 자막 파일 생성 (전체 문장들)
            srt_filename = f'temp_chapter_{uuid.uuid4().hex}.srt'
            srt_path = os.path.join(chapter_dir, srt_filename)
            
            with open(srt_path, 'w', encoding='utf-8') as f:
                for i, sentence in enumerate(sentences):
                    wrapped_text = wrap_text(sentence['english'], max_chars_per_line=40)
                    start_offset = sentence['startTime'] - chapter_info['start_time']
                    end_offset = sentence['endTime'] - chapter_info['start_time']
                    
                    f.write(f"{i+1}\n")
                    f.write(f"{int(start_offset//3600):02d}:{int((start_offset%3600)//60):02d}:{start_offset%60:06.3f} --> ")
                    f.write(f"{int(end_offset//3600):02d}:{int((end_offset%3600)//60):02d}:{end_offset%60:06.3f}\n")
                    f.write(f"{wrapped_text}\n\n")
            
            duration = chapter_info['end_time'] - chapter_info['start_time']
            
            # FFmpeg 명령어 구성 (최적화된 설정)
            cmd = [
                'ffmpeg',
                '-ss', str(chapter_info['start_time']),
                '-i', input_file,
                '-t', str(duration),
                '-f', 'lavfi',
                '-i', f'color=black:size=1920x1080:duration={duration}:rate=30',
                '-filter_complex',
                f"[1:v]subtitles={srt_path}:fontsdir=fonts:force_style='FontName=\"Noto Sans KR\",FontSize=38,PrimaryColour=&Hffffff,Bold=1,Alignment=2,MarginV=50'[v]",
                '-map', '[v]',
                '-map', '0:a',
                '-af', 'volume=3.0',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',  # 인코딩 속도 우선
                '-crf', '28',  # 품질 낮춤 (용량 감소)
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '96k',  # 오디오 비트레이트 낮춤
                '-threads', '2',  # CPU 스레드 제한
                '-shortest',
                '-y',
                output_file
            ]
            
            # FFmpeg 실행 (타임아웃 증가)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            
            # 임시 자막 파일 삭제
            try:
                os.remove(srt_path)
            except:
                pass
            
            if result.returncode == 0:
                return jsonify({
                    'success': True,
                    'message': f'Chapter MP4 created successfully',
                    'filename': output_filename,
                    'output_path': output_file,
                    'duration': duration
                })
            else:
                app.logger.error(f"FFmpeg error: {result.stderr}")
                return jsonify({'error': 'MP4 creation failed'}), 500
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/media/<media_id>/scene/<int:scene_id>/extract-mp4', methods=['POST'])
    def extract_scene_mp4(media_id, scene_id):
        """씬별 MP4 내보내기 (전체 씬을 하나의 파일로)"""
        try:
            conn = sqlite3.connect('dev.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 씬 정보와 첫번째/마지막 문장 시간 가져오기
            cursor.execute("""
                SELECT sc.title as scene_title, m.filename,
                       MIN(s.startTime) as start_time,
                       MAX(s.endTime) as end_time
                FROM Scene sc
                JOIN Chapter c ON sc.chapterId = c.id
                JOIN Media m ON c.mediaId = m.id
                JOIN Sentence s ON s.sceneId = sc.id
                WHERE sc.id = ? AND c.mediaId = ?
                GROUP BY sc.id
            """, (scene_id, media_id))
            
            scene_info = cursor.fetchone()
            
            # 모든 문장들 가져오기 (자막용)
            cursor.execute("""
                SELECT s.*, ROW_NUMBER() OVER (ORDER BY s.startTime) as seq
                FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                JOIN Chapter c ON sc.chapterId = c.id
                WHERE sc.id = ? AND c.mediaId = ? AND s.english IS NOT NULL AND s.english != ''
                ORDER BY s.startTime
            """, (scene_id, media_id))
            
            sentences = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            if not scene_info or not sentences:
                return jsonify({'success': False, 'error': 'No scene or sentences found'}), 404
            
            scene_info = dict(scene_info)
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], scene_info['filename'])
            
            # 파일 확장자로 비디오/오디오 구분
            video_extensions = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv'}
            file_ext = scene_info['filename'].rsplit('.', 1)[1].lower() if '.' in scene_info['filename'] else ''
            is_video_file = file_ext in video_extensions
            
            import subprocess
            
            # 미디어별/신별 디렉토리 생성
            media_name = get_media_name(media_id)
            scene_dir = os.path.join('output', media_name, 'scene')
            os.makedirs(scene_dir, exist_ok=True)
            
            # 씬 전체를 하나의 MP4로 생성
            output_filename = f'scene_{scene_id}_{scene_info["scene_title"]}.mp4'
            output_file = os.path.join(scene_dir, output_filename)
            
            # SRT 자막 파일 생성 (전체 문장들)
            srt_filename = f'temp_scene_{uuid.uuid4().hex}.srt'
            srt_path = os.path.join(scene_dir, srt_filename)
            
            with open(srt_path, 'w', encoding='utf-8') as f:
                for i, sentence in enumerate(sentences):
                    wrapped_text = wrap_text(sentence['english'], max_chars_per_line=40)
                    start_offset = sentence['startTime'] - scene_info['start_time']
                    end_offset = sentence['endTime'] - scene_info['start_time']
                    
                    f.write(f"{i+1}\n")
                    f.write(f"{int(start_offset//3600):02d}:{int((start_offset%3600)//60):02d}:{start_offset%60:06.3f} --> ")
                    f.write(f"{int(end_offset//3600):02d}:{int((end_offset%3600)//60):02d}:{end_offset%60:06.3f}\n")
                    f.write(f"{wrapped_text}\n\n")
            
            duration = scene_info['end_time'] - scene_info['start_time']
            
            # FFmpeg 명령어 구성
            if is_video_file:
                # 비디오 파일: 원본 영상에 자막만 추가
                cmd = [
                    'ffmpeg',
                    '-ss', str(scene_info['start_time']),
                    '-i', input_file,
                    '-t', str(duration),
                    '-vf', f"subtitles={srt_path}:fontsdir=fonts:force_style='FontName=\"Noto Sans KR\",FontSize=38,PrimaryColour=&Hffffff,Bold=1,Alignment=2,MarginV=50'",
                    '-af', 'volume=3.0',
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '23',
                    '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-y',
                    output_file
                ]
            else:
                # 오디오 파일: 검정 배경 비디오 + SRT 자막 + 오디오
                cmd = [
                    'ffmpeg',
                    '-ss', str(scene_info['start_time']),
                    '-i', input_file,
                    '-t', str(duration),
                    '-f', 'lavfi',
                    '-i', f'color=black:size=1920x1080:duration={duration}:rate=30',
                    '-filter_complex',
                    f"[1:v]subtitles={srt_path}:fontsdir=fonts:force_style='FontName=\"Noto Sans KR\",FontSize=38,PrimaryColour=&Hffffff,Bold=1,Alignment=2,MarginV=50'[v]",
                    '-map', '[v]',
                    '-map', '0:a',
                    '-af', 'volume=3.0',
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '23',
                    '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-shortest',
                    '-y',
                    output_file
                ]
            
            # FFmpeg 실행
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            # 임시 자막 파일 삭제
            try:
                os.remove(srt_path)
            except:
                pass
            
            if result.returncode == 0:
                return jsonify({
                    'success': True,
                    'message': f'Scene MP4 created successfully',
                    'filename': output_filename,
                    'output_path': output_file,
                    'duration': duration
                })
            else:
                app.logger.error(f"FFmpeg error: {result.stderr}")
                return jsonify({'error': 'MP4 creation failed'}), 500
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/media/<media_id>/extract-bookmarked-mp4', methods=['POST'])
    def extract_bookmarked_mp4(media_id):
        """북마크된 문장들 MP4 내보내기"""
        try:
            # 요청 데이터에서 자막 옵션 가져오기
            data = request.get_json() if request.is_json else {}
            subtitle_english = data.get('subtitle_english', True)
            subtitle_korean = data.get('subtitle_korean', False)
            
            conn = sqlite3.connect('dev.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT s.*, m.filename
                FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                JOIN Chapter c ON sc.chapterId = c.id
                JOIN Media m ON c.mediaId = m.id
                WHERE c.mediaId = ? AND s.bookmark = 1
                ORDER BY s.`order`
            """, (media_id,))
            
            bookmarked_sentences = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            if not bookmarked_sentences:
                return jsonify({'success': False, 'error': 'No bookmarked sentences found'}), 404
            
            app.logger.info(f"Found {len(bookmarked_sentences)} bookmarked sentences")
            
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], bookmarked_sentences[0]['filename'])
            
            # 파일 확장자로 비디오/오디오 구분
            video_extensions = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv'}
            file_ext = bookmarked_sentences[0]['filename'].rsplit('.', 1)[1].lower() if '.' in bookmarked_sentences[0]['filename'] else ''
            is_video_file = file_ext in video_extensions
            
            # 자막 옵션에 따른 폴더명과 파일명 suffix 결정
            if subtitle_english and subtitle_korean:
                folder_suffix = 'bookmarked_engkor'
                file_suffix = '_engkor'
            elif subtitle_english:
                folder_suffix = 'bookmarked_eng'
                file_suffix = '_eng'
            elif subtitle_korean:
                folder_suffix = 'bookmarked_kor'
                file_suffix = '_kor'
            else:
                folder_suffix = 'bookmarked'
                file_suffix = '_nosub'
            
            # 미디어별/자막옵션별 북마크 디렉토리 생성
            media_name = get_media_name(media_id)
            bookmarked_dir = os.path.join('output', media_name, folder_suffix)
            os.makedirs(bookmarked_dir, exist_ok=True)
            
            extracted_files = []
            
            import subprocess
            import zipfile
            
            for i, sentence in enumerate(bookmarked_sentences):
                # 영어 텍스트 확인
                if not sentence.get('english'):
                    continue
                    
                # 실제 문장 순서번호 사용 (sentence['order'] 또는 sequence number)
                sentence_order = sentence.get('order', i+1)
                output_filename = f'bookmarked_{sentence_order:04d}{file_suffix}.mp4'
                output_file = os.path.join(bookmarked_dir, output_filename)
                
                duration = sentence['endTime'] - sentence['startTime']
                
                # 자막 파일 생성
                subtitle_path = None
                if subtitle_english or subtitle_korean:
                    import uuid
                    
                    if subtitle_english and subtitle_korean:
                        # 영어 + 한글: ASS 형식 사용 (다른 글꼴 크기)
                        english_text = sentence['english']
                        korean_text = sentence.get('korean', '')
                        if korean_text:
                            ass_filename = f'temp_bookmark_{uuid.uuid4().hex}.ass'
                            subtitle_path = os.path.join(bookmarked_dir, ass_filename)
                            create_ass_subtitle_file(english_text, korean_text, duration, subtitle_path)
                        else:
                            # 한글이 없으면 영어만
                            srt_filename = f'temp_bookmark_{uuid.uuid4().hex}.srt'
                            subtitle_path = os.path.join(bookmarked_dir, srt_filename)
                            create_srt_subtitle_file(english_text, duration, subtitle_path)
                    elif subtitle_english:
                        # 영어만: ASS 형식 (예쁜 폰트 적용)
                        ass_filename = f'temp_bookmark_{uuid.uuid4().hex}.ass'
                        subtitle_path = os.path.join(bookmarked_dir, ass_filename)
                        create_ass_subtitle_file(sentence['english'], None, duration, subtitle_path)
                    elif subtitle_korean:
                        # 한글만: ASS 형식 (예쁜 폰트 적용)
                        korean_text = sentence.get('korean', '')
                        if korean_text:
                            ass_filename = f'temp_bookmark_{uuid.uuid4().hex}.ass'
                            subtitle_path = os.path.join(bookmarked_dir, ass_filename)
                            create_ass_subtitle_file(None, korean_text, duration, subtitle_path)
                
                if is_video_file:
                    # 비디오 파일 처리
                    if subtitle_path:
                        # 자막 있는 경우: 원본 영상에 자막 추가
                        cmd = [
                            'ffmpeg',
                            '-ss', str(sentence['startTime']),
                            '-i', input_file,
                            '-t', str(duration),
                            '-vf', f"subtitles={subtitle_path}:fontsdir=fonts",
                            '-af', 'volume=3.0',
                            '-c:v', 'libx264',
                            '-preset', 'fast',
                            '-crf', '23',
                            '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac',
                            '-b:a', '128k',
                            '-y',
                            output_file
                        ]
                    else:
                        # 자막 없는 경우: 원본 영상만
                        cmd = [
                            'ffmpeg',
                            '-ss', str(sentence['startTime']),
                            '-i', input_file,
                            '-t', str(duration),
                            '-af', 'volume=3.0',
                            '-c:v', 'libx264',
                            '-preset', 'fast',
                            '-crf', '23',
                            '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac',
                            '-b:a', '128k',
                            '-y',
                            output_file
                        ]
                else:
                    # 오디오 파일 처리
                    if subtitle_path:
                        # 자막 있는 경우: 검정 배경 비디오 + 자막 + 오디오
                        cmd = [
                            'ffmpeg',
                            '-f', 'lavfi',
                            '-i', f'color=black:size=1920x1080:duration={duration}:rate=30',
                            '-ss', str(sentence['startTime']),
                            '-i', input_file,
                            '-t', str(duration),
                            '-filter_complex',
                            f"[0:v]subtitles={subtitle_path}:fontsdir=fonts[v]",
                            '-map', '[v]',
                            '-map', '1:a',
                            '-af', 'volume=3.0',
                            '-c:v', 'libx264',
                            '-preset', 'fast',
                            '-crf', '23',
                            '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac',
                            '-b:a', '128k',
                            '-shortest',
                            '-y',
                            output_file
                        ]
                    else:
                        # 자막 없는 경우: 검정 배경 비디오 + 오디오만
                        cmd = [
                            'ffmpeg',
                            '-f', 'lavfi',
                            '-i', f'color=black:size=1920x1080:duration={duration}:rate=30',
                            '-ss', str(sentence['startTime']),
                            '-i', input_file,
                            '-t', str(duration),
                            '-map', '0:v',
                            '-map', '1:a',
                            '-af', 'volume=3.0',
                            '-c:v', 'libx264',
                            '-preset', 'fast',
                            '-crf', '23',
                            '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac',
                            '-b:a', '128k',
                            '-shortest',
                            '-y',
                            output_file
                        ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                
                # 임시 자막 파일 삭제
                if subtitle_path:
                    try:
                        os.remove(subtitle_path)
                    except:
                        pass
                
                if result.returncode == 0:
                    extracted_files.append(output_file)
                else:
                    app.logger.error(f"FFmpeg error for bookmarked sentence {i+1}: {result.stderr}")
            
            return jsonify({
                'success': True, 
                'message': f'{len(extracted_files)} bookmarked MP4 files created',
                'output_path': bookmarked_dir,
                'file_count': len(extracted_files)
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/media/<media_id>/extract-all-sentences-mp4', methods=['POST'])
    def extract_all_sentences_mp4(media_id):
        """전체 문장 분할 MP4 내보내기"""
        try:
            # 요청 데이터에서 자막 옵션 가져오기
            data = request.get_json() if request.is_json else {}
            subtitle_english = data.get('subtitle_english', True)
            subtitle_korean = data.get('subtitle_korean', False)
            
            conn = sqlite3.connect('dev.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 모든 문장 정보 가져오기 (한글 번역도 포함)
            cursor.execute("""
                SELECT s.*, m.filename
                FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                JOIN Chapter c ON sc.chapterId = c.id
                JOIN Media m ON c.mediaId = m.id
                WHERE c.mediaId = ?
                ORDER BY s.`order`
            """, (media_id,))
            
            sentences = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            if not sentences:
                return jsonify({'success': False, 'error': 'No sentences found'}), 404
                
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], sentences[0]['filename'])
            
            # 파일 확장자로 비디오/오디오 구분
            video_extensions = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv'}
            file_ext = sentences[0]['filename'].rsplit('.', 1)[1].lower() if '.' in sentences[0]['filename'] else ''
            is_video_file = file_ext in video_extensions
            
            # 자막 옵션에 따른 폴더명과 파일명 suffix 결정
            if subtitle_english and subtitle_korean:
                folder_suffix = 'all_engkor'
                file_suffix = '_engkor'
            elif subtitle_english:
                folder_suffix = 'all_eng'
                file_suffix = '_eng'
            elif subtitle_korean:
                folder_suffix = 'all_kor'
                file_suffix = '_kor'
            else:
                folder_suffix = 'all'
                file_suffix = '_nosub'
            
            # 미디어별/자막옵션별 디렉토리 생성
            media_name = get_media_name(media_id)
            all_dir = os.path.join('output', media_name, folder_suffix)
            os.makedirs(all_dir, exist_ok=True)
            
            extracted_files = []
            
            import subprocess
            import zipfile
            
            for i, sentence in enumerate(sentences):
                if not sentence.get('english'):  # 영어 텍스트가 없으면 건너뛰기
                    continue
                    
                output_filename = f'{i+1:04d}{file_suffix}.mp4'
                output_file = os.path.join(all_dir, output_filename)
                
                duration = sentence['endTime'] - sentence['startTime']
                
                # 자막 파일 생성
                subtitle_path = None
                if subtitle_english or subtitle_korean:
                    import uuid
                    
                    if subtitle_english and subtitle_korean:
                        # 영어 + 한글: ASS 형식 사용 (다른 글꼴 크기)
                        english_text = sentence['english']
                        korean_text = sentence.get('korean', '')
                        if korean_text:
                            ass_filename = f'temp_all_{uuid.uuid4().hex}.ass'
                            subtitle_path = os.path.join(all_dir, ass_filename)
                            create_ass_subtitle_file(english_text, korean_text, duration, subtitle_path)
                        else:
                            # 한글이 없으면 영어만
                            srt_filename = f'temp_all_{uuid.uuid4().hex}.srt'
                            subtitle_path = os.path.join(all_dir, srt_filename)
                            create_srt_subtitle_file(english_text, duration, subtitle_path)
                    elif subtitle_english:
                        # 영어만: ASS 형식 (예쁜 폰트 적용)
                        ass_filename = f'temp_all_{uuid.uuid4().hex}.ass'
                        subtitle_path = os.path.join(all_dir, ass_filename)
                        create_ass_subtitle_file(sentence['english'], None, duration, subtitle_path)
                    elif subtitle_korean:
                        # 한글만: ASS 형식 (예쁜 폰트 적용)
                        korean_text = sentence.get('korean', '')
                        if korean_text:
                            ass_filename = f'temp_all_{uuid.uuid4().hex}.ass'
                            subtitle_path = os.path.join(all_dir, ass_filename)
                            create_ass_subtitle_file(None, korean_text, duration, subtitle_path)
                
                if is_video_file:
                    # 비디오 파일 처리
                    if subtitle_path:
                        # 자막 있는 경우: 원본 영상에 자막 추가
                        cmd = [
                            'ffmpeg',
                            '-ss', str(sentence['startTime']),
                            '-i', input_file,
                            '-t', str(duration),
                            '-vf', f"subtitles={subtitle_path}:fontsdir=fonts",
                            '-af', 'volume=3.0',
                            '-c:v', 'libx264',
                            '-preset', 'fast',
                            '-crf', '23',
                            '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac',
                            '-b:a', '128k',
                            '-y',
                            output_file
                        ]
                    else:
                        # 자막 없는 경우: 원본 영상만
                        cmd = [
                            'ffmpeg',
                            '-ss', str(sentence['startTime']),
                            '-i', input_file,
                            '-t', str(duration),
                            '-af', 'volume=3.0',
                            '-c:v', 'libx264',
                            '-preset', 'fast',
                            '-crf', '23',
                            '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac',
                            '-b:a', '128k',
                            '-y',
                            output_file
                        ]
                else:
                    # 오디오 파일 처리
                    if subtitle_path:
                        # 자막 있는 경우: 검정 배경 비디오 + 자막 + 오디오
                        cmd = [
                            'ffmpeg',
                            '-f', 'lavfi',
                            '-i', f'color=black:size=1920x1080:duration={duration}:rate=30',
                            '-ss', str(sentence['startTime']),
                            '-i', input_file,
                            '-t', str(duration),
                            '-filter_complex',
                            f"[0:v]subtitles={subtitle_path}:fontsdir=fonts[v]",
                            '-map', '[v]',
                            '-map', '1:a',
                            '-af', 'volume=3.0',
                            '-c:v', 'libx264',
                            '-preset', 'fast', 
                            '-crf', '23',
                            '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac',
                            '-b:a', '128k',
                            '-shortest',
                            '-y',
                            output_file
                        ]
                    else:
                        # 자막 없는 경우: 검정 배경 비디오 + 오디오만
                        cmd = [
                            'ffmpeg',
                            '-f', 'lavfi',
                            '-i', f'color=black:size=1920x1080:duration={duration}:rate=30',
                            '-ss', str(sentence['startTime']),
                            '-i', input_file,
                            '-t', str(duration),
                            '-map', '0:v',
                            '-map', '1:a',
                            '-af', 'volume=3.0',
                            '-c:v', 'libx264',
                            '-preset', 'fast',
                            '-crf', '23',
                            '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac',
                            '-b:a', '128k',
                            '-shortest',
                            '-y',
                            output_file
                        ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                
                # 임시 자막 파일 삭제
                if subtitle_path:
                    try:
                        os.remove(subtitle_path)
                    except:
                        pass
                
                if result.returncode == 0:
                    extracted_files.append(output_file)
                else:
                    app.logger.error(f"FFmpeg error for sentence {i+1}: {result.stderr}")
            
            return jsonify({
                'success': True, 
                'message': f'{len(extracted_files)} sentence MP4 files created',
                'output_path': all_dir,
                'file_count': len(extracted_files)
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/media/<media_id>/extract_all_mp4', methods=['POST'])
    def extract_all_mp4(media_id):
        """전체 미디어를 하나의 MP4로 내보내기"""
        try:
            conn = sqlite3.connect('dev.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 미디어 정보와 모든 문장 가져오기
            cursor.execute("""
                SELECT m.filename,
                       MIN(s.startTime) as start_time,
                       MAX(s.endTime) as end_time
                FROM Media m
                JOIN Chapter c ON c.mediaId = m.id
                JOIN Scene sc ON sc.chapterId = c.id
                JOIN Sentence s ON s.sceneId = sc.id
                WHERE m.id = ? AND s.english IS NOT NULL AND s.english != ''
                GROUP BY m.id
            """, (media_id,))
            
            media_info = cursor.fetchone()
            
            # 모든 문장들 가져오기 (자막용)
            cursor.execute("""
                SELECT s.*, ROW_NUMBER() OVER (ORDER BY s.startTime) as seq
                FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                JOIN Chapter c ON sc.chapterId = c.id
                WHERE c.mediaId = ? AND s.english IS NOT NULL AND s.english != ''
                ORDER BY s.startTime
            """, (media_id,))
            
            sentences = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            if not media_info or not sentences:
                return jsonify({'success': False, 'error': 'No media or sentences found'}), 404
            
            media_info = dict(media_info)
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], media_info['filename'])
            
            import subprocess
            import uuid
            
            # 미디어별 디렉토리 생성
            media_name = get_media_name(media_id)
            full_dir = os.path.join('output', media_name, 'full')
            os.makedirs(full_dir, exist_ok=True)
            
            # 전체 MP4 파일명
            output_filename = f'full_{media_name}.mp4'
            output_file = os.path.join(full_dir, output_filename)
            
            # SRT 자막 파일 생성 (전체 문장들)
            srt_filename = f'temp_full_{uuid.uuid4().hex}.srt'
            srt_path = os.path.join(full_dir, srt_filename)
            
            with open(srt_path, 'w', encoding='utf-8') as f:
                for i, sentence in enumerate(sentences):
                    wrapped_text = wrap_text(sentence['english'], max_chars_per_line=40)
                    start_offset = sentence['startTime'] - media_info['start_time']
                    end_offset = sentence['endTime'] - media_info['start_time']
                    
                    f.write(f"{i+1}\n")
                    f.write(f"{int(start_offset//3600):02d}:{int((start_offset%3600)//60):02d}:{start_offset%60:06.3f} --> ")
                    f.write(f"{int(end_offset//3600):02d}:{int((end_offset%3600)//60):02d}:{end_offset%60:06.3f}\n")
                    f.write(f"{wrapped_text}\n\n")
            
            duration = media_info['end_time'] - media_info['start_time']
            
            # FFmpeg 명령어 구성 (최적화된 설정)
            cmd = [
                'ffmpeg',
                '-ss', str(media_info['start_time']),
                '-i', input_file,
                '-t', str(duration),
                '-f', 'lavfi',
                '-i', f'color=black:size=1920x1080:duration={duration}:rate=30',
                '-filter_complex',
                f"[1:v]subtitles={srt_path}:fontsdir=fonts:force_style='FontName=\"Noto Sans KR\",FontSize=38,PrimaryColour=&Hffffff,Bold=1,Alignment=2,MarginV=50'[v]",
                '-map', '[v]',
                '-map', '0:a',
                '-af', 'volume=3.0',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '28',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '96k',
                '-threads', '2',
                '-shortest',
                '-y',
                output_file
            ]
            
            # FFmpeg 실행 (타임아웃 증가)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            
            # 임시 자막 파일 삭제
            try:
                os.remove(srt_path)
            except:
                pass
            
            if result.returncode == 0:
                return jsonify({
                    'success': True,
                    'message': f'Full MP4 created successfully',
                    'filename': output_filename,
                    'output_path': output_file,
                    'duration': duration
                })
            else:
                app.logger.error(f"FFmpeg error: {result.stderr}")
                return jsonify({'error': 'MP4 creation failed'}), 500
                
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/download/extracted/<filename>')
    def download_extracted_file(filename):
        """추출된 파일 다운로드"""
        try:
            extracted_dir = os.path.join('output')
            return send_from_directory(extracted_dir, filename, as_attachment=True)
        except Exception as e:
            return jsonify({'error': str(e)}), 404
    
    @app.route('/api/media/<media_id>/translate', methods=['POST'])
    def translate_media(media_id):
        """미디어의 모든 빈 문장 번역 (백그라운드)"""
        try:
            import threading
            
            def background_translate():
                try:
                    from deep_translator import GoogleTranslator
                    import time
                    
                    conn = sqlite3.connect('dev.db')
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    
                    # 빈 번역 문장 찾기
                    cursor.execute("""
                        SELECT s.id, s.english 
                        FROM Sentence s
                        JOIN Scene sc ON s.sceneId = sc.id
                        JOIN Chapter c ON sc.chapterId = c.id
                        WHERE c.mediaId = ? AND (s.korean = '' OR s.korean IS NULL)
                        ORDER BY s.id
                    """, (media_id,))
                    
                    empty_sentences = cursor.fetchall()
                    
                    if not empty_sentences:
                        conn.close()
                        return
                    
                    translator = GoogleTranslator(source='en', target='ko')
                    translated = 0
                    errors = 0
                    
                    # 상태 업데이트
                    cursor.execute("UPDATE Media SET status = 'translating' WHERE id = ?", (media_id,))
                    conn.commit()
                    
                    for sentence in empty_sentences:
                        try:
                            korean = translator.translate(sentence['english'])
                            cursor.execute("UPDATE Sentence SET korean = ? WHERE id = ?", (korean, sentence['id']))
                            translated += 1
                            
                            # 10개마다 커밋 및 진행률 업데이트
                            if translated % 10 == 0:
                                conn.commit()
                                progress = int((translated / len(empty_sentences)) * 100)
                                cursor.execute(
                                    "UPDATE Media SET current_sentence = ? WHERE id = ?", 
                                    (f"번역 진행: {translated}/{len(empty_sentences)} ({progress}%)", media_id)
                                )
                                conn.commit()
                                time.sleep(0.5)  # API 제한 방지
                                
                        except Exception as e:
                            app.logger.error(f"Translation error for sentence {sentence['id']}: {e}")
                            # 번역 실패 시 원문 사용
                            cursor.execute("UPDATE Sentence SET korean = ? WHERE id = ?", (sentence['english'], sentence['id']))
                            errors += 1
                    
                    conn.commit()
                    
                    # 상태 완료로 업데이트
                    cursor.execute("UPDATE Media SET status = 'completed', current_sentence = '' WHERE id = ?", (media_id,))
                    conn.commit()
                    conn.close()
                    
                    app.logger.info(f"Translation completed for media {media_id}: {translated} success, {errors} errors")
                    
                except Exception as e:
                    app.logger.error(f"Background translation error: {str(e)}")
                    try:
                        cursor.execute("UPDATE Media SET status = 'error', current_sentence = ? WHERE id = ?", 
                                     (f"번역 오류: {str(e)}", media_id))
                        conn.commit()
                        conn.close()
                    except:
                        pass
            
            # 백그라운드 스레드 시작
            thread = threading.Thread(target=background_translate)
            thread.daemon = True
            thread.start()
            
            return jsonify({
                'success': True,
                'message': '번역이 백그라운드에서 시작되었습니다.'
            })
            
        except Exception as e:
            app.logger.error(f"Translate media error: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/media/<media_id>/translation-status', methods=['GET'])
    def get_translation_status(media_id):
        """번역 상태 확인"""
        try:
            conn = sqlite3.connect('dev.db')
            cursor = conn.cursor()
            
            # 전체 문장 수와 번역된 문장 수 확인
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN korean != '' AND korean IS NOT NULL THEN 1 END) as translated
                FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                JOIN Chapter c ON sc.chapterId = c.id
                WHERE c.mediaId = ?
            """, (media_id,))
            
            result = cursor.fetchone()
            total = result[0]
            translated = result[1]
            
            # 미디어 상태 확인
            cursor.execute("SELECT status, current_sentence FROM Media WHERE id = ?", (media_id,))
            media_result = cursor.fetchone()
            
            conn.close()
            
            return jsonify({
                'total': total,
                'translated': translated,
                'untranslated': total - translated,
                'progress': int((translated / total * 100)) if total > 0 else 100,
                'status': media_result[0] if media_result else 'unknown',
                'current': media_result[1] if media_result else ''
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/media/<media_id>/process-whisper', methods=['POST'])
    def process_whisper(media_id):
        """Whisper로 문장 생성"""
        try:
            data = request.get_json() or {}
            model_size = data.get('model', 'medium')
            template = data.get('template', 'auto')
            force_restart = data.get('force_restart', False)
            
            conn = sqlite3.connect('dev.db')
            cursor = conn.cursor()
            
            # 미디어 정보 확인
            cursor.execute("SELECT filename, status FROM Media WHERE id = ?", (media_id,))
            media = cursor.fetchone()
            
            if not media:
                conn.close()
                return jsonify({'success': False, 'error': 'Media not found'}), 404
            
            # 영상 파일 확인
            video_extensions = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv'}
            file_ext = media[0].rsplit('.', 1)[1].lower() if '.' in media[0] else ''
            is_video = file_ext in video_extensions
            
            # 처리 중인 상태는 force_restart가 true일 때만 허용
            if media[1] == 'processing' and not force_restart:
                conn.close()
                return jsonify({'success': False, 'error': f'Media is currently being processed', 'can_force_restart': True}), 400
            
            # 상태를 처리 중으로 업데이트
            cursor.execute("UPDATE Media SET status = 'processing' WHERE id = ?", (media_id,))
            conn.commit()
            conn.close()
            
            # 백그라운드에서 Whisper 처리
            import threading
            
            def background_whisper():
                try:
                    from batch_processor import process_audio_batch
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], media[0])
                    
                    # 영상 파일인 경우 임시 오디오 추출
                    if is_video:
                        app.logger.info(f"Video file detected, extracting audio for Whisper: {media[0]}")
                        temp_audio_path = extract_audio_from_video(filepath, media[0])
                        if temp_audio_path:
                            process_filepath = temp_audio_path
                            app.logger.info(f"Audio extracted successfully: {temp_audio_path}")
                        else:
                            raise Exception("Failed to extract audio from video for Whisper processing")
                    else:
                        process_filepath = filepath
                    
                    result = process_audio_batch(process_filepath, media_id, model_size, template)
                    
                    # 영상 파일의 경우 임시 오디오 파일 삭제
                    if is_video and temp_audio_path:
                        try:
                            os.remove(temp_audio_path)
                            app.logger.info(f"Temporary audio file removed: {temp_audio_path}")
                        except:
                            pass
                    
                    app.logger.info(f"Whisper processing result: {result}")
                except Exception as e:
                    app.logger.error(f"Whisper processing error: {e}")
                    # 오류 상태로 업데이트
                    try:
                        conn = sqlite3.connect('dev.db')
                        cursor = conn.cursor()
                        cursor.execute("UPDATE Media SET status = 'error', current_sentence = ? WHERE id = ?", 
                                     (f"처리 오류: {str(e)}", media_id))
                        conn.commit()
                        conn.close()
                    except:
                        pass
            
            thread = threading.Thread(target=background_whisper)
            thread.daemon = True
            thread.start()
            
            return jsonify({
                'success': True,
                'message': f'Whisper 처리가 시작되었습니다. (모델: {model_size}, 템플릿: {template})'
            })
            
        except Exception as e:
            app.logger.error(f"Process whisper error: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/media/<media_id>/upload-sentences', methods=['POST'])
    def upload_sentences(media_id):
        """문장 데이터 직접 업로드 (JSON 또는 SRT 형식)"""
        try:
            conn = sqlite3.connect('dev.db')
            cursor = conn.cursor()
            
            # 미디어 정보 확인
            cursor.execute("SELECT filename, status FROM Media WHERE id = ?", (media_id,))
            media = cursor.fetchone()
            
            if not media:
                conn.close()
                return jsonify({'success': False, 'error': 'Media not found'}), 404
            
            # 처리 중인 상태는 재처리 불가, 나머지는 모두 허용
            if media[1] == 'processing':
                conn.close()
                return jsonify({'success': False, 'error': f'Media is currently being processed'}), 400
            
            # 파일 업로드 또는 JSON 데이터 처리
            if 'file' in request.files:
                # SRT 파일 업로드
                file = request.files['file']
                if file.filename.endswith('.srt'):
                    content = file.read().decode('utf-8')
                    sentences = parse_srt_content(content)
                else:
                    return jsonify({'success': False, 'error': 'Only SRT files are supported'}), 400
            else:
                # JSON 데이터 직접 전송
                data = request.get_json()
                if not data or 'sentences' not in data:
                    return jsonify({'success': False, 'error': 'No sentences data provided'}), 400
                sentences = data['sentences']
            
            # 템플릿 설정
            template = request.form.get('template') or (request.get_json() or {}).get('template', 'manual')
            
            # 상태를 처리 중으로 업데이트
            cursor.execute("UPDATE Media SET status = 'processing' WHERE id = ?", (media_id,))
            conn.commit()
            conn.close()
            
            # 백그라운드에서 문장 저장
            import threading
            
            def background_save():
                try:
                    save_sentences_to_db(media_id, sentences, template)
                    app.logger.info(f"Sentences uploaded for media {media_id}: {len(sentences)} sentences")
                except Exception as e:
                    app.logger.error(f"Save sentences error: {e}")
                    # 오류 상태로 업데이트
                    try:
                        conn = sqlite3.connect('dev.db')
                        cursor = conn.cursor()
                        cursor.execute("UPDATE Media SET status = 'error', current_sentence = ? WHERE id = ?", 
                                     (f"저장 오류: {str(e)}", media_id))
                        conn.commit()
                        conn.close()
                    except:
                        pass
            
            thread = threading.Thread(target=background_save)
            thread.daemon = True
            thread.start()
            
            return jsonify({
                'success': True,
                'message': f'문장 데이터 저장이 시작되었습니다. ({len(sentences)}개 문장)'
            })
            
        except Exception as e:
            app.logger.error(f"Upload sentences error: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    def parse_srt_content(content):
        """SRT 파일 내용을 문장 리스트로 변환"""
        import re
        
        # BOM 제거
        if content.startswith('\ufeff'):
            content = content[1:]
        
        app.logger.info(f"Starting SRT parsing. Content length: {len(content)}")
        
        sentences = []
        # 다양한 줄바꿈 형식 처리
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        blocks = content.strip().split('\n\n')
        
        app.logger.info(f"Found {len(blocks)} blocks in SRT file")
        
        for i, block in enumerate(blocks):
            lines = block.strip().split('\n')
            app.logger.debug(f"Block {i+1}: {len(lines)} lines - {lines[:2] if len(lines) >= 2 else lines}")
            
            if len(lines) >= 3:
                # 시간 정보 파싱
                time_line = lines[1]
                time_match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
                
                if time_match:
                    try:
                        start_h, start_m, start_s, start_ms = map(int, time_match.groups()[:4])
                        end_h, end_m, end_s, end_ms = map(int, time_match.groups()[4:])
                        
                        start_time = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000
                        end_time = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000
                        
                        # 텍스트 합치기 (HTML 태그 및 불필요한 텍스트 제거)
                        text = ' '.join(lines[2:]).strip()
                        # HTML 태그 제거
                        text = re.sub(r'<[^>]+>', '', text)
                        # 웹사이트, 대괄호, 콜론 패턴 제거
                        text = re.sub(r'www\.[^\s]+', '', text)  # www.* 제거
                        text = re.sub(r'\[.*?\]', '', text)      # [텍스트] 제거
                        text = re.sub(r'^\s*:\s*', '', text)     # 시작 콜론 제거
                        # 대시(-) 화자 구분을 줄바꿈으로 변경
                        text = re.sub(r'\s*-\s*', '\n', text)    # - 를 줄바꿈으로
                        text = re.sub(r'\s+', ' ', text).strip() # 다중 공백 정리 (줄바꿈 제외)
                        
                        # 크레딧/빈 텍스트/불필요한 텍스트 제외
                        skip_patterns = ['subtitles by', 'sync by', 'opensubtitles', 'yify', 'explosiveskull', 'goldenbeard']
                        should_skip = any(pattern in text.lower() for pattern in skip_patterns)
                        
                        if text and len(text.strip()) > 2 and not should_skip:
                            sentences.append({
                                'english': text,
                                'korean': '',
                                'start_time': start_time,
                                'end_time': end_time,
                                'order': len(sentences) + 1
                            })
                            app.logger.debug(f"Added sentence {len(sentences)}: {text[:50]}...")
                        else:
                            app.logger.warning(f"Block {i+1}: Empty text, skipping")
                    except ValueError as e:
                        app.logger.error(f"Block {i+1}: Time parsing error - {e}, time_line: {time_line}")
                else:
                    app.logger.warning(f"Block {i+1}: Time format not matched - {time_line}")
            else:
                app.logger.warning(f"Block {i+1}: Insufficient lines ({len(lines)}) - {block[:100]}")
        
        app.logger.info(f"SRT parsing completed. Extracted {len(sentences)} sentences")
        return sentences
    
    def save_sentences_to_db(media_id, sentences, template):
        """문장 데이터를 DB에 저장"""
        from batch_processor import save_to_database, reorganize_chapters_scenes
        
        # 오디오 길이 계산
        duration = sentences[-1]['end_time'] if sentences else 60
        
        # DB에 저장
        save_to_database(media_id, duration, sentences)
        
        # 템플릿에 따라 구조 재구성
        reorganize_chapters_scenes(media_id, '', sentences, template)
        
        # 완료 상태로 업데이트
        conn = sqlite3.connect('dev.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE Media SET status = 'completed', current_sentence = '' WHERE id = ?", (media_id,))
        conn.commit()
        conn.close()
    
    app.run(debug=True, port=8000)