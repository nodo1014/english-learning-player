"""
English Learning Player - Refactored Flask Application
"""
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import os
import json
import logging
import threading
import time
import uuid
import re
from datetime import datetime
from pathlib import Path

# Simple phrase matching system (replacing spaCy, VAD, patterns)

# Import our new modules
from database import media_repo, chapter_repo, scene_repo, sentence_repo, db_manager, words_repo
from file_manager import file_manager
from ffmpeg_processor import ffmpeg_processor, media_extractor, subtitle_processor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key'
app.config['UPLOAD_FOLDER'] = 'upload'
app.config['MAX_CONTENT_LENGTH'] = None

# Global variables for background tasks
processing_status = {}
translation_status = {}

# Load words database on startup
def load_words_database():
    """Load words from static/data/words_db.txt into database"""
    try:
        # Check if words are already loaded
        if words_repo.get_phrase_count() > 0:
            logger.info(f"Words already loaded: {words_repo.get_phrase_count()} phrases")
            return
        
        # Load from file
        words_file = '/home/kang/dev/english/static/data/words_db.txt'
        count = words_repo.load_from_file(words_file)
        logger.info(f"Loaded {count} phrases into database")
    except Exception as e:
        logger.error(f"Failed to load words database: {e}")

# Load words data on startup
load_words_database()

# Word matching system
def find_phrase_matches(text, blank_mode=False):
    """Find matching phrases in text using optimized database search"""
    try:
        import re
        
        # Use database search to get only relevant phrases
        candidate_phrases = words_repo.find_matching_phrases(text, limit=20)
        
        matches = []
        highlighted_text = text
        
        # Sort by length (longest first) to match longer phrases first
        sorted_phrases = sorted(candidate_phrases, key=lambda x: len(x['phrase']), reverse=True)
        
        for phrase_data in sorted_phrases:
            phrase = phrase_data['phrase']
            meaning = phrase_data['meaning']
            
            # Simple case-insensitive search first (faster than regex)
            if phrase.lower() in text.lower():
                # Use simple string replacement for exact matches
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                match = pattern.search(highlighted_text)
                
                if match:
                    matched_text = match.group(0)
                    matches.append({
                        'phrase': phrase,
                        'meaning': meaning,
                        'matched_text': matched_text
                    })
                    
                    if blank_mode:
                        # Create blank spaces (underlines)
                        blank_length = len(matched_text)
                        underline = '_' * max(blank_length, 3)
                        highlighted_text = pattern.sub(
                            f'<span class="blank-space" title="{meaning}">{underline}</span>',
                            highlighted_text,
                            count=1
                        )
                    else:
                        # Highlight in text (billiard hall style: matched_text : meaning)
                        highlighted_text = pattern.sub(
                            f'<span class="phrase-match" title="{meaning}">{matched_text} : {meaning}</span>',
                            highlighted_text,
                            count=1
                        )
                    
                    # Stop after finding first match to avoid overlapping
                    break
            
            # Check for placeholder patterns (A, B, C) - only for patterns containing single capital letters
            elif re.search(r'\b[A-Z]\b', phrase):
                # Replace placeholder letters with regex patterns
                flexible_phrase = phrase
                flexible_phrase = re.sub(r'\b[A-Z]\b', r'\\w+', flexible_phrase)
                
                # Escape other special regex characters but keep our \w+ patterns
                parts = flexible_phrase.split('\\w+')
                escaped_parts = [re.escape(part) for part in parts]
                regex_pattern = '\\w+'.join(escaped_parts)
                
                try:
                    pattern = re.compile(regex_pattern, re.IGNORECASE)
                    match = pattern.search(highlighted_text)
                    
                    if match:
                        matched_text = match.group(0)
                        matches.append({
                            'phrase': phrase,
                            'meaning': meaning,
                            'matched_text': matched_text
                        })
                        
                        if blank_mode:
                            blank_length = len(matched_text)
                            underline = '_' * max(blank_length, 3)
                            highlighted_text = pattern.sub(
                                f'<span class="blank-space" title="{meaning}">{underline}</span>',
                                highlighted_text,
                                count=1
                            )
                        else:
                            highlighted_text = pattern.sub(
                                f'<span class="phrase-match" title="{meaning}">{matched_text} : {meaning}</span>',
                                highlighted_text,
                                count=1
                            )
                        break
                except re.error:
                    # Skip invalid regex patterns
                    continue
        
        return {
            'highlighted_text': highlighted_text,
            'matches': matches,
            'blank_mode': blank_mode
        }
    except Exception as e:
        logger.error(f"Error in phrase matching: {e}")
        return {
            'highlighted_text': text,
            'matches': [],
            'blank_mode': blank_mode
        }

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/phrase-matching', methods=['POST'])
def phrase_matching():
    """API for phrase matching in text"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        blank_mode = data.get('blank_mode', False)
        
        if not text:
            return jsonify({'error': 'Text is required'}), 400
        
        result = find_phrase_matches(text, blank_mode)
        return jsonify({
            'success': True,
            'highlighted_text': result['highlighted_text'],
            'matches': result['matches'],
            'blank_mode': result['blank_mode']
        })
        
    except Exception as e:
        logger.error(f"Error in phrase matching API: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/words/reload', methods=['POST'])
def reload_words():
    """API to reload words database from file"""
    try:
        # Clear existing words
        with words_repo.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Words")
            conn.commit()
        
        # Reload from file
        words_file = '/home/kang/dev/english/static/data/words_db.txt'
        count = words_repo.load_from_file(words_file)
        
        return jsonify({
            'success': True,
            'message': f'Reloaded {count} phrases'
        })
        
    except Exception as e:
        logger.error(f"Error reloading words: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/words/stats', methods=['GET'])
def words_stats():
    """Get words database statistics"""
    try:
        count = words_repo.get_phrase_count()
        return jsonify({
            'success': True,
            'phrase_count': count
        })
        
    except Exception as e:
        logger.error(f"Error getting words stats: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# MEDIA MANAGEMENT ROUTES
# =============================================================================

@app.route('/api/media', methods=['GET'])
def get_media_list():
    """Get all media files"""
    try:
        media_list = media_repo.get_all()
        return jsonify(media_list)
    except Exception as e:
        logger.error(f"Error getting media list: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/chapters', methods=['GET'])
def get_chapters(media_id):
    """Get chapters for a media with scenes"""
    try:
        chapters = chapter_repo.get_by_media_id(media_id)
        
        # Add scenes to each chapter
        for chapter in chapters:
            chapter['scenes'] = scene_repo.get_by_chapter_id(chapter['id'])
        
        return jsonify(chapters)
    except Exception as e:
        logger.error(f"Error getting chapters for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/sentences-grouped', methods=['GET'])
def get_sentences_grouped(media_id):
    """Get sentences grouped by chapters and scenes with phrase matching"""
    try:
        chapters = chapter_repo.get_by_media_id(media_id)
        
        for chapter in chapters:
            scenes = scene_repo.get_by_chapter_id(chapter['id'])
            for scene in scenes:
                sentences = sentence_repo.get_by_scene_id(scene['id'])
                
                # Apply phrase matching to each sentence
                for sentence in sentences:
                    if sentence.get('english'):
                        match_result = find_phrase_matches(sentence['english'])
                        sentence['highlighted_english'] = match_result['highlighted_text']
                        sentence['phrase_matches'] = match_result['matches']
                
                scene['sentences'] = sentences
            chapter['scenes'] = scenes
        
        return jsonify(chapters)
    except Exception as e:
        logger.error(f"Error getting grouped sentences for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/sentences', methods=['GET'])
def get_sentences(media_id):
    """Get flat list of sentences for a media with optimized phrase matching"""
    try:
        sentences = sentence_repo.get_by_media_id(media_id)
        
        # Apply fast phrase matching to each sentence
        for sentence in sentences:
            if sentence.get('english'):
                # Use cached highlighted_english if available
                if sentence.get('highlighted_english'):
                    continue
                
                # Apply optimized phrase matching
                match_result = find_phrase_matches(sentence['english'])
                sentence['highlighted_english'] = match_result['highlighted_text']
                sentence['phrase_matches'] = match_result['matches']
        
        return jsonify(sentences)
    except Exception as e:
        logger.error(f"Error getting sentences for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>', methods=['DELETE'])
def delete_media(media_id):
    """Delete media and all related data"""
    try:
        # Get media info first
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        # Delete media file
        if media.get('filename'):
            file_manager.delete_media_file(media['filename'])
            
            # Also delete converted MP3 if it's a video
            if media.get('fileType') == 'video':
                mp3_filename = f"{media_id}.mp3"
                file_manager.delete_media_file(mp3_filename)
        
        # Delete output files
        file_manager.cleanup_media_outputs(media_id)
        
        # Delete from database (cascades to chapters, scenes, sentences)
        success = media_repo.delete(media_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Media deleted successfully'
            })
        else:
            return jsonify({'error': 'Failed to delete media from database'}), 500
            
    except Exception as e:
        logger.error(f"Error deleting media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# FILE UPLOAD ROUTES
# =============================================================================

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle file upload"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'error': 'No file selected'}), 400
        
        # Save file using file manager
        filename, media_id, file_info = file_manager.save_uploaded_file(file)
        
        # Extract audio if video file
        if file_info['file_type'] == 'video':
            video_path = file_manager.get_media_path(filename)
            audio_filename = f"{media_id}.mp3"
            audio_path = file_manager.upload_folder / audio_filename
            
            if ffmpeg_processor.extract_audio_from_video(video_path, str(audio_path)):
                file_info['audio_filename'] = audio_filename
        
        # Get duration
        media_path = file_manager.get_media_path(filename)
        duration = ffmpeg_processor.get_media_duration(media_path)
        if duration:
            file_info['duration'] = duration
        
        # Save to database
        media_repo.create(file_info)
        
        return jsonify({
            'success': True,
            'mediaId': media_id,
            'filename': filename,
            'fileType': file_info['file_type'],
            'duration': duration
        })
    
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sync-directory', methods=['GET'])
def list_sync_directory():
    """List files in sync_directory for selection"""
    try:
        sync_dir = Path('sync_directory')
        if not sync_dir.exists():
            return jsonify({'files': []})
        
        files = []
        media_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm', '.m4v', '.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.wma'}
        subtitle_extensions = {'.srt', '.ass', '.vtt'}
        
        for file_path in sync_dir.iterdir():
            if file_path.is_file():
                file_ext = file_path.suffix.lower()
                if file_ext in media_extensions or file_ext in subtitle_extensions:
                    file_info = {
                        'name': file_path.name,
                        'size': file_path.stat().st_size,
                        'type': 'media' if file_ext in media_extensions else 'subtitle',
                        'extension': file_ext
                    }
                    files.append(file_info)
        
        # Group files by base name for media-subtitle pairing
        paired_files = {}
        
        for file_info in files:
            base_name = Path(file_info['name']).stem
            
            if base_name not in paired_files:
                paired_files[base_name] = {
                    'baseName': base_name,
                    'mediaFile': None,
                    'subtitleFile': None
                }
            
            if file_info['type'] == 'media':
                paired_files[base_name]['mediaFile'] = file_info
            elif file_info['type'] == 'subtitle':
                paired_files[base_name]['subtitleFile'] = file_info
        
        # Convert to list and filter out entries without media files
        paired_files = [pair for pair in paired_files.values() if pair['mediaFile'] is not None]
        
        return jsonify({'files': paired_files})
        
    except Exception as e:
        logger.error(f"Error listing sync directory: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sync-directory/import', methods=['POST'])
def import_from_sync_directory():
    """Import selected files from sync_directory to upload folder"""
    try:
        data = request.get_json()
        selected_files = data.get('selectedFiles', [])
        
        if not selected_files:
            return jsonify({'error': 'No files selected'}), 400
        
        sync_dir = Path('sync_directory')
        upload_dir = Path('upload')
        results = []
        
        for base_name in selected_files:
            result = {'baseName': base_name, 'success': False, 'mediaId': None, 'error': None}
            
            try:
                # Find media and subtitle files
                media_file = None
                subtitle_file = None
                
                for file_path in sync_dir.iterdir():
                    if file_path.is_file():
                        file_base_name = file_path.stem
                        if file_base_name == base_name:
                            file_ext = file_path.suffix.lower()
                            media_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm', '.m4v', '.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.wma'}
                            
                            if file_ext in media_extensions:
                                media_file = file_path
                            elif file_ext == '.srt':
                                subtitle_file = file_path
                
                if media_file is None:
                    result['error'] = 'No media file found'
                    results.append(result)
                    continue
                
                # Generate unique media ID
                media_id = str(uuid.uuid4())
                
                # Move media file to upload folder
                media_filename = f"{media_id}_{media_file.name}"
                media_dest = upload_dir / media_filename
                
                import shutil
                shutil.move(str(media_file), str(media_dest))
                
                # Move subtitle file if exists
                subtitle_filename = None
                if subtitle_file and subtitle_file.exists():
                    subtitle_filename = f"{media_id}_{subtitle_file.name}"
                    subtitle_dest = upload_dir / subtitle_filename
                    shutil.move(str(subtitle_file), str(subtitle_dest))
                
                # Process file like in upload_file function
                file_ext = media_file.suffix.lower()
                file_type = 'video' if file_ext in {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm', '.m4v'} else 'audio'
                
                file_info = {
                    'id': media_id,
                    'originalFilename': media_file.name,
                    'filename': media_filename,
                    'fileType': file_type,
                    'fileSize': media_dest.stat().st_size,
                    'status': 'uploaded'
                }
                
                # Extract audio if video file
                if file_type == 'video':
                    audio_filename = f"{media_id}.mp3"
                    audio_path = upload_dir / audio_filename
                    
                    if ffmpeg_processor.extract_audio_from_video(str(media_dest), str(audio_path)):
                        file_info['audio_filename'] = audio_filename
                
                # Get duration
                duration = ffmpeg_processor.get_media_duration(str(media_dest))
                if duration:
                    file_info['duration'] = duration
                
                # Save to database
                media_repo.create(file_info)
                
                # Process subtitle file if exists
                if subtitle_filename:
                    subtitle_path = upload_dir / subtitle_filename
                    if subtitle_path.exists():
                        # Import subtitle sentences
                        try:
                            # Create default chapter for subtitles
                            chapter_data = {
                                'mediaId': media_id,
                                'title': 'Subtitles',
                                'startTime': 0.0,
                                'endTime': duration or 7200.0,  # Default 2 hours if no duration
                                'order': 1
                            }
                            chapter_id = chapter_repo.create(chapter_data)
                            
                            # Create default scene for subtitles
                            scene_data = {
                                'chapterId': chapter_id,
                                'title': 'Main Scene',
                                'startTime': 0.0,
                                'endTime': duration or 7200.0,
                                'order': 1
                            }
                            scene_id = scene_repo.create(scene_data)
                            
                            # Parse and import subtitle sentences
                            sentences = subtitle_processor.parse_srt_file(str(subtitle_path))
                            if sentences:
                                sentence_ids = []
                                for i, sentence_data in enumerate(sentences):
                                    sentence_data['sceneId'] = scene_id
                                    sentence_data['order'] = i + 1
                                    sentence_id = sentence_repo.create(sentence_data)
                                    sentence_ids.append(sentence_id)
                                
                                # Auto analysis disabled - only using words_db matching
                                    
                        except Exception as subtitle_error:
                            logger.warning(f"Failed to process subtitle file {subtitle_filename}: {subtitle_error}")
                
                result['success'] = True
                result['mediaId'] = media_id
                
            except Exception as file_error:
                logger.error(f"Error processing file {base_name}: {file_error}")
                result['error'] = str(file_error)
            
            results.append(result)
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error importing from sync directory: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/status', methods=['GET'])
def get_processing_status(media_id):
    """Get processing status for media"""
    try:
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        status = processing_status.get(media_id, {})
        
        return jsonify({
            'status': media['status'],
            'processing': status,
            'hasSubtitles': bool(sentence_repo.get_by_media_id(media_id))
        })
    
    except Exception as e:
        logger.error(f"Error getting status for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# WHISPER PROCESSING
# =============================================================================

def process_with_whisper_background(media_id, template_type):
    """Background Whisper processing"""
    try:
        processing_status[media_id] = {
            'stage': 'starting',
            'progress': 0,
            'message': 'Whisper 처리를 시작합니다...'
        }
        
        media = media_repo.get_by_id(media_id)
        if not media:
            raise Exception("Media not found")
        
        # Update status to processing
        media_repo.update_status(media_id, 'processing')
        
        # Get audio file path
        if media['fileType'] == 'video':
            audio_filename = f"{media_id}.mp3"
        else:
            audio_filename = media['filename']
        
        audio_path = file_manager.get_media_path(audio_filename)
        if not audio_path:
            raise Exception("Audio file not found")
        
        # Update progress
        processing_status[media_id].update({
            'stage': 'transcribing',
            'progress': 20,
            'message': 'Whisper로 음성을 텍스트로 변환 중...'
        })
        
        # Use simple_processor for actual Whisper transcription
        from simple_processor import process_audio_file_realtime
        
        # Get audio file path
        if template_type == 'video':
            audio_path = file_manager.upload_folder / audio_filename
        else:
            # For audio files, use the original file
            media = media_repo.get_by_id(media_id)
            audio_path = file_manager.get_media_path(media['filename'])
        
        # Update progress callback
        def progress_callback(message):
            processing_status[media_id].update({
                'stage': 'transcribing',
                'progress': min(processing_status[media_id]['progress'] + 5, 90),
                'message': message
            })
        
        # Process with Whisper
        result = process_audio_file_realtime(str(audio_path), media_id, progress_callback)
        
        if not result['success']:
            raise Exception(f"Whisper processing failed: {result.get('error', 'Unknown error')}")
        
        processing_status[media_id].update({
            'stage': 'structuring',
            'progress': 95,
            'message': '문장 구조 완료 중...'
        })
        
        # Complete
        processing_status[media_id].update({
            'stage': 'completed',
            'progress': 100,
            'message': '처리가 완료되었습니다.'
        })
        
        media_repo.update_status(media_id, 'completed')
        
    except Exception as e:
        logger.error(f"Whisper processing failed for media {media_id}: {e}")
        processing_status[media_id] = {
            'stage': 'error',
            'progress': 0,
            'message': f'처리 중 오류가 발생했습니다: {str(e)}'
        }
        media_repo.update_status(media_id, 'error')

@app.route('/api/media/<media_id>/process-whisper', methods=['POST'])
def process_whisper(media_id):
    """Start Whisper processing"""
    try:
        data = request.get_json()
        template_type = data.get('template', 'toeic_lc')
        
        # Start background processing
        thread = threading.Thread(
            target=process_with_whisper_background,
            args=(media_id, template_type)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': 'Whisper 처리를 시작했습니다.'})
    
    except Exception as e:
        logger.error(f"Error starting Whisper processing for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# SENTENCE EXTRACTION ROUTES
# =============================================================================

@app.route('/api/sentence/<media_id>/<int:sentence_id>/extract-mp3', methods=['POST'])
def extract_sentence_mp3(media_id, sentence_id):
    """Extract single sentence as MP3"""
    try:
        # Get sentence data
        sentences = sentence_repo.get_by_media_id(media_id)
        sentence = next((s for s in sentences if s['id'] == sentence_id), None)
        
        if not sentence:
            return jsonify({'error': 'Sentence not found'}), 404
        
        # Get media info
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        # Prepare file paths
        audio_filename = f"{media_id}.mp3" if media['fileType'] == 'video' else media['filename']
        input_file = file_manager.get_media_path(audio_filename)
        
        # Create output directory
        output_dir = file_manager.create_output_directory(media_id, media['filename'])
        output_filename = f'sentence_{sentence_id}_{sentence["startTime"]:.1f}s-{sentence["endTime"]:.1f}s.mp3'
        output_file = os.path.join(output_dir, output_filename)
        
        # Extract audio segment
        duration = sentence['endTime'] - sentence['startTime']
        success = ffmpeg_processor.extract_audio_segment(
            input_file, output_file, sentence['startTime'], duration
        )
        
        if success:
            return jsonify({
                'success': True,
                'filename': output_filename,
                'download_url': f'/api/download/{output_filename}'
            })
        else:
            return jsonify({'error': 'Extraction failed'}), 500
    
    except Exception as e:
        logger.error(f"Error extracting MP3 for sentence {sentence_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sentence/<media_id>/<int:sentence_id>/extract-mp4', methods=['POST'])
def extract_sentence_mp4(media_id, sentence_id):
    """Extract single sentence as MP4 with subtitles"""
    try:
        # Get request data
        data = request.get_json() or {}
        english_subtitle = data.get('english_subtitle', True)
        korean_subtitle = data.get('korean_subtitle', False)
        english_font_size = data.get('english_font_size', 32)
        korean_font_size = data.get('korean_font_size', 24)
        
        # 디버깅: 실제 받은 데이터 로그
        logger.info(f"단일 문장 MP4 추출 요청 데이터: {data}")
        logger.info(f"korean_subtitle 값: {korean_subtitle} (타입: {type(korean_subtitle)})")
        
        # Get sentence data
        sentences = sentence_repo.get_by_media_id(media_id)
        sentence = next((s for s in sentences if s['id'] == sentence_id), None)
        
        if not sentence:
            return jsonify({'error': 'Sentence not found'}), 404
        
        # Get media info
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        # Prepare paths
        is_video = media['fileType'] == 'video'
        input_file = file_manager.get_media_path(media['filename'])
        
        # Debug logging
        logger.info(f"Extracting sentence: is_video={is_video}, input_file={input_file}, file_exists={os.path.exists(input_file) if input_file else False}")
        
        # Create output directory
        output_dir = file_manager.create_output_directory(media_id, media['filename'])
        
        # Generate filename with subtitle suffix
        subtitle_suffix = file_manager._get_subtitle_suffix({
            'english': english_subtitle,
            'korean': korean_subtitle
        })
        output_filename = f'sentence_{sentence_id}_{sentence["startTime"]:.1f}s-{sentence["endTime"]:.1f}s{subtitle_suffix}.mp4'
        output_file = os.path.join(output_dir, output_filename)
        
        # Extract with subtitles
        subtitle_options = {
            'english': english_subtitle,
            'korean': korean_subtitle,
            'english_font_size': english_font_size,
            'korean_font_size': korean_font_size
        }
        success = media_extractor.extract_sentence_with_subtitles(
            input_file, output_file, sentence, subtitle_options, is_video
        )
        
        if success:
            return jsonify({
                'success': True,
                'filename': output_filename,
                'download_url': f'/api/download/{output_filename}'
            })
        else:
            return jsonify({'error': 'Extraction failed'}), 500
    
    except Exception as e:
        logger.error(f"Error extracting MP4 for sentence {sentence_id}: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# TRANSLATION ROUTES
# =============================================================================

@app.route('/api/media/<media_id>/translate', methods=['POST'])
def translate_sentences(media_id):
    """Start background translation of sentences"""
    try:
        # Start background translation
        thread = threading.Thread(
            target=translate_sentences_background,
            args=(media_id,)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': '번역을 시작했습니다.'})
    
    except Exception as e:
        logger.error(f"Error starting translation for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/translation-status', methods=['GET'])
def get_translation_status(media_id):
    """Get translation progress status"""
    try:
        status = translation_status.get(media_id, {
            'stage': 'idle',
            'progress': 0,
            'message': '번역 대기 중'
        })
        return jsonify(status)
    
    except Exception as e:
        logger.error(f"Error getting translation status for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

def translate_sentences_background(media_id):
    """Background translation processing"""
    try:
        from deep_translator import GoogleTranslator
        
        translation_status[media_id] = {
            'stage': 'starting',
            'progress': 0,
            'message': '번역을 시작합니다...'
        }
        
        # Get sentences without Korean translation
        sentences = sentence_repo.get_by_media_id(media_id)
        sentences_to_translate = [s for s in sentences if not s.get('korean')]
        
        if not sentences_to_translate:
            translation_status[media_id] = {
                'stage': 'completed',
                'progress': 100,
                'message': '번역할 문장이 없습니다.'
            }
            return
        
        translator = GoogleTranslator(source='en', target='ko')
        total_sentences = len(sentences_to_translate)
        
        for i, sentence in enumerate(sentences_to_translate):
            try:
                # Update progress
                progress = int((i / total_sentences) * 100)
                translation_status[media_id] = {
                    'stage': 'translating',
                    'progress': progress,
                    'message': f'번역 중... ({i+1}/{total_sentences})'
                }
                
                # Translate
                korean_text = translator.translate(sentence['english'])
                
                # Update in database
                sentence_repo.update_translation(sentence['id'], korean_text)
                
                # Small delay to avoid rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error translating sentence {sentence['id']}: {e}")
                continue
        
        translation_status[media_id] = {
            'stage': 'completed',
            'progress': 100,
            'message': f'번역이 완료되었습니다. ({total_sentences}개 문장)'
        }
        
    except Exception as e:
        logger.error(f"Translation failed for media {media_id}: {e}")
        translation_status[media_id] = {
            'stage': 'error',
            'progress': 0,
            'message': f'번역 중 오류가 발생했습니다: {str(e)}'
        }

# =============================================================================
# SRT UPLOAD AND PROCESSING
# =============================================================================

@app.route('/api/media/<media_id>/subtitles', methods=['DELETE'])
def delete_subtitles(media_id):
    """Delete all subtitles (sentences) for a media"""
    try:
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        # Delete all sentences for this media
        success = sentence_repo.delete_by_media_id(media_id)
        
        if success:
            # Update media status back to uploaded
            media_repo.update_status(media_id, 'uploaded')
            
            return jsonify({
                'success': True,
                'message': 'Subtitles deleted successfully'
            })
        else:
            return jsonify({'error': 'Failed to delete subtitles'}), 500
            
    except Exception as e:
        logger.error(f"Error deleting subtitles for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/upload-sentences', methods=['POST'])
def upload_sentences(media_id):
    """Upload SRT file or JSON data"""
    try:
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        # Check if file upload or JSON data
        if 'srt_file' in request.files:
            # SRT file upload
            srt_file = request.files['srt_file']
            if not srt_file.filename.endswith('.srt'):
                return jsonify({'error': 'Only SRT files are allowed'}), 400
            
            srt_content = srt_file.read().decode('utf-8')
            sentences_data = parse_srt_content(srt_content)
            
        else:
            # JSON data
            data = request.get_json()
            sentences_data = data.get('sentences', [])
        
        if not sentences_data:
            return jsonify({'error': 'No sentence data provided'}), 400
        
        # Save sentences to database
        save_sentences_to_db(media_id, sentences_data)
        media_repo.update_status(media_id, 'completed')
        
        return jsonify({
            'success': True,
            'message': f'{len(sentences_data)}개 문장이 저장되었습니다.'
        })
    
    except Exception as e:
        logger.error(f"Error uploading sentences for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

def clean_subtitle_text(text):
    """Clean subtitle text by removing unnecessary elements"""
    import re
    
    if not text:
        return text
    
    # Remove speaker names (화자: 형태)
    text = re.sub(r'^[^:]*:\s*', '', text)
    
    # Remove sound effects in parentheses (의성어)
    text = re.sub(r'\([^)]*\)', '', text)
    
    # Remove descriptions in brackets [묘사]
    text = re.sub(r'\[[^\]]*\]', '', text)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]*>', '', text)
    
    # Remove common filler words and expressions
    filler_patterns = [
        r'\bwww+\b',  # www, wwww, etc.
        r'\bahh*\b',  # ah, ahh, ahhh
        r'\bumm*\b',  # um, umm, ummm
        r'\berr*\b',  # er, err, errr
        r'\buh+\b',   # uh, uhh, uhhh
        r'\bmm+\b',   # mm, mmm, mmmm
        r'\bhm+\b',   # hm, hmm, hmmm
    ]
    
    for pattern in filler_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Remove multiple spaces and clean up
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Remove leading/trailing punctuation if it's isolated
    text = re.sub(r'^[.,!?;:-]+\s*', '', text)
    text = re.sub(r'\s*[.,!?;:-]+$', '', text)
    
    return text

def parse_srt_content(srt_content):
    """Parse SRT file content into sentence data"""
    import re
    
    sentences = []
    blocks = re.split(r'\n\s*\n', srt_content.strip())
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        
        try:
            # Extract number, time, and text
            number = int(lines[0])
            time_line = lines[1]
            text = ' '.join(lines[2:])
            
            # Clean the subtitle text
            cleaned_text = clean_subtitle_text(text)
            
            # Skip empty or very short text after cleaning
            if not cleaned_text or len(cleaned_text.strip()) < 3:
                continue
            
            # Parse time format: 00:00:10,500 --> 00:00:13,240
            time_match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
            if not time_match:
                continue
            
            start_h, start_m, start_s, start_ms = map(int, time_match.groups()[:4])
            end_h, end_m, end_s, end_ms = map(int, time_match.groups()[4:])
            
            start_time = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000
            end_time = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000
            
            sentences.append({
                'english': cleaned_text,
                'startTime': start_time,
                'endTime': end_time,
                'order': number
            })
            
        except (ValueError, IndexError) as e:
            logger.warning(f"Skipping invalid SRT block: {e}")
            continue
    
    return sentences

def save_sentences_to_db(media_id, sentences_data):
    """Save parsed sentences to database"""
    
    # Create default chapter and scene structure
    chapter_data = {
        'mediaId': media_id,
        'title': 'Main Content',
        'startTime': sentences_data[0]['startTime'] if sentences_data else 0,
        'endTime': sentences_data[-1]['endTime'] if sentences_data else 0,
        'order': 1
    }
    
    chapter_ids = chapter_repo.create_batch([chapter_data])
    chapter_id = chapter_ids[0]
    
    scene_data = {
        'chapterId': chapter_id,
        'title': 'Scene 1',
        'startTime': chapter_data['startTime'],
        'endTime': chapter_data['endTime'],
        'order': 1
    }
    
    scene_ids = scene_repo.create_batch([scene_data])
    scene_id = scene_ids[0]
    
    # Prepare sentences for batch insert
    db_sentences = []
    for sentence in sentences_data:
        db_sentences.append({
            'sceneId': scene_id,
            'english': sentence['english'],
            'korean': sentence.get('korean'),
            'startTime': sentence['startTime'],
            'endTime': sentence['endTime'],
            'order': sentence['order'],
            'confidence': sentence.get('confidence', 0.95)
        })
    
    sentence_repo.create_batch(db_sentences)

# =============================================================================
# BOOKMARK ROUTES
# =============================================================================

@app.route('/api/media/<media_id>/sentences/<int:sentence_id>/bookmark', methods=['POST'])
def toggle_bookmark(media_id, sentence_id):
    """Toggle bookmark status of a sentence"""
    try:
        result = sentence_repo.toggle_bookmark(sentence_id)
        return jsonify({'success': True, **result})
    
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error toggling bookmark for sentence {sentence_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/export-bookmarks', methods=['GET'])
def export_bookmarks(media_id):
    """Export bookmarked sentences as text"""
    try:
        bookmarked_sentences = sentence_repo.get_bookmarked_by_media_id(media_id)
        
        if not bookmarked_sentences:
            return jsonify({'error': 'No bookmarked sentences found'}), 404
        
        # Create text content
        lines = ["# Bookmarked Sentences\n"]
        for sentence in bookmarked_sentences:
            lines.append(f"## Sentence {sentence['order']}")
            lines.append(f"**English:** {sentence['english']}")
            if sentence.get('korean'):
                lines.append(f"**Korean:** {sentence['korean']}")
            lines.append(f"**Time:** {sentence['startTime']:.1f}s - {sentence['endTime']:.1f}s")
            lines.append("")
        
        content = '\n'.join(lines)
        
        # Save to file
        media = media_repo.get_by_id(media_id)
        output_dir = file_manager.create_output_directory(media_id, media['filename'])
        filename = 'bookmarked_sentences.txt'
        file_path = os.path.join(output_dir, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'download_url': f'/api/download/{filename}',
            'count': len(bookmarked_sentences)
        })
    
    except Exception as e:
        logger.error(f"Error exporting bookmarks for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# BULK EXTRACTION ROUTES
# =============================================================================

@app.route('/api/media/<media_id>/extract-bookmarked', methods=['POST'])
def extract_bookmarked_mp3(media_id):
    """Extract all bookmarked sentences as MP3 ZIP"""
    try:
        import zipfile
        import tempfile
        
        # Get bookmarked sentences
        bookmarked_sentences = sentence_repo.get_bookmarked_by_media_id(media_id)
        if not bookmarked_sentences:
            return jsonify({'error': 'No bookmarked sentences found'}), 404
        
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        # Prepare input file
        audio_filename = f"{media_id}.mp3" if media['fileType'] == 'video' else media['filename']
        input_file = file_manager.get_media_path(audio_filename)
        
        # Create output directory
        output_dir = file_manager.create_output_directory(media_id, media['filename'])
        
        # Create temporary directory for individual files
        with tempfile.TemporaryDirectory() as temp_dir:
            extracted_files = []
            
            for sentence in bookmarked_sentences:
                # Generate filename
                output_filename = f'bookmarked_{sentence["order"]:04d}_{sentence["startTime"]:.1f}s-{sentence["endTime"]:.1f}s.mp3'
                output_file = os.path.join(temp_dir, output_filename)
                
                # Extract audio segment
                duration = sentence['endTime'] - sentence['startTime']
                success = ffmpeg_processor.extract_audio_segment(
                    input_file, output_file, sentence['startTime'], duration
                )
                
                if success:
                    extracted_files.append((output_file, output_filename))
            
            if not extracted_files:
                return jsonify({'error': 'Failed to extract any files'}), 500
            
            # Create ZIP file
            zip_filename = f'bookmarked_sentences_{media_id}.zip'
            zip_path = os.path.join(output_dir, zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w') as zip_file:
                for file_path, filename in extracted_files:
                    zip_file.write(file_path, filename)
        
        return jsonify({
            'success': True,
            'filename': zip_filename,
            'download_url': f'/api/download/{zip_filename}',
            'count': len(extracted_files)
        })
    
    except Exception as e:
        logger.error(f"Error extracting bookmarked MP3 for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/extract-bookmarked-mp4', methods=['POST'])
def extract_bookmarked_mp4(media_id):
    """Extract bookmarked sentences as MP4 with subtitle options"""
    try:
        data = request.get_json() or {}
        subtitle_english = data.get('subtitle_english', True)
        subtitle_korean = data.get('subtitle_korean', False)
        include_commentary = data.get('include_commentary', False)
        commentary_style = data.get('commentary_style', 'orange')
        english_font_size = data.get('english_font_size', 32)
        korean_font_size = data.get('korean_font_size', 24)
        
        # 디버깅: 실제 받은 데이터 로그
        logger.info(f"북마크 MP4 추출 요청 데이터: {data}")
        logger.info(f"subtitle_korean 값: {subtitle_korean} (타입: {type(subtitle_korean)})")
        
        # Get bookmarked sentences
        bookmarked_sentences = sentence_repo.get_bookmarked_by_media_id(media_id)
        if not bookmarked_sentences:
            return jsonify({'error': 'No bookmarked sentences found'}), 404
        
        # Start background processing
        thread = threading.Thread(
            target=extract_bulk_mp4_background,
            args=(media_id, bookmarked_sentences, 'bookmarked', subtitle_english, subtitle_korean, english_font_size, korean_font_size, include_commentary, commentary_style)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': '북마크 MP4 추출을 시작했습니다.'})
    
    except Exception as e:
        logger.error(f"Error starting bookmarked MP4 extraction for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/extract-all-sentences-mp4', methods=['POST'])
def extract_all_sentences_mp4(media_id):
    """Extract all sentences as MP4 with subtitle options"""
    try:
        data = request.get_json() or {}
        subtitle_english = data.get('subtitle_english', True)
        subtitle_korean = data.get('subtitle_korean', False)
        include_commentary = data.get('include_commentary', False)
        commentary_style = data.get('commentary_style', 'orange')
        english_font_size = data.get('english_font_size', 32)
        korean_font_size = data.get('korean_font_size', 24)
        
        # 디버깅 로그 추가
        logger.info(f"전체 문장 추출 요청 데이터: {data}")
        logger.info(f"subtitle_english: {subtitle_english}, subtitle_korean: {subtitle_korean}")
        
        # 디버깅: 실제 받은 데이터 로그
        logger.info(f"전체 문장 MP4 추출 요청 데이터: {data}")
        logger.info(f"subtitle_korean 값: {subtitle_korean} (타입: {type(subtitle_korean)})")
        
        # 디버깅: 북마크 함수와 일반 함수 비교
        bookmarked_test = sentence_repo.get_bookmarked_by_media_id(media_id)
        all_test = sentence_repo.get_by_media_id(media_id)
        if bookmarked_test and all_test:
            logger.info(f"북마크 문장 첫번째 korean: {bookmarked_test[0].get('korean', 'None')}")
            logger.info(f"전체 문장 첫번째 korean: {all_test[0].get('korean', 'None')}")
            # 동일한 ID 찾기
            for sentence in all_test:
                if sentence['id'] == bookmarked_test[0]['id']:
                    logger.info(f"동일 문장 ID {sentence['id']} - 전체에서: {sentence.get('korean', 'None')}")
                    break
        
        # Get all sentences
        all_sentences = sentence_repo.get_by_media_id(media_id)
        if not all_sentences:
            return jsonify({'error': 'No sentences found'}), 404
        
        # 한글 자막이 필요한데 번역이 없는 문장들 필터링
        if subtitle_korean:
            all_sentences = [s for s in all_sentences if s.get('korean')]
            logger.info(f"한글 번역이 있는 문장 수: {len(all_sentences)}")
        
        # Start background processing
        thread = threading.Thread(
            target=extract_bulk_mp4_background,
            args=(media_id, all_sentences, 'all', subtitle_english, subtitle_korean, english_font_size, korean_font_size, include_commentary, commentary_style)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': '전체 문장 MP4 추출을 시작했습니다.'})
    
    except Exception as e:
        logger.error(f"Error starting all sentences MP4 extraction for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/extract_all_mp4', methods=['POST'])
def extract_all_mp4(media_id):
    """Extract entire media as single MP4 with subtitles"""
    try:
        data = request.get_json() or {}
        subtitle_english = data.get('subtitle_english', True)
        subtitle_korean = data.get('subtitle_korean', False)
        
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        # Get all sentences for subtitles
        sentences = sentence_repo.get_by_media_id(media_id)
        
        # Start background processing
        thread = threading.Thread(
            target=extract_full_media_mp4_background,
            args=(media_id, sentences, subtitle_english, subtitle_korean)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': '전체 미디어 MP4 추출을 시작했습니다.'})
    
    except Exception as e:
        logger.error(f"Error starting full media MP4 extraction for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

def extract_bulk_mp4_background(media_id, sentences, extraction_type, subtitle_english, subtitle_korean, english_font_size=32, korean_font_size=24, include_commentary=False, commentary_style='orange'):
    """Background processing for bulk MP4 extraction"""
    try:
        processing_status[f"{media_id}_{extraction_type}"] = {
            'stage': 'starting',
            'progress': 0,
            'message': f'{extraction_type} MP4 추출을 시작합니다...'
        }
        
        media = media_repo.get_by_id(media_id)
        if not media:
            raise Exception("Media not found")
        
        is_video = media['fileType'] == 'video'
        input_file = file_manager.get_media_path(media['filename'])
        
        # Create output directory with subtitle suffix
        subtitle_options = {
            'english': subtitle_english, 
            'korean': subtitle_korean,
            'english_font_size': english_font_size,
            'korean_font_size': korean_font_size,
            'include_commentary': include_commentary,
            'commentary_style': commentary_style
        }
        base_dir = file_manager.create_output_directory(media_id, media['filename'])
        output_dir = file_manager.create_extraction_directory(base_dir, extraction_type, subtitle_options)
        
        total_sentences = len(sentences)
        for i, sentence in enumerate(sentences):
            try:
                # Update progress
                progress = int((i / total_sentences) * 100)
                processing_status[f"{media_id}_{extraction_type}"] = {
                    'stage': 'extracting',
                    'progress': progress,
                    'message': f'추출 중... ({i+1}/{total_sentences})'
                }
                
                # Generate output filename with subtitle suffix
                subtitle_suffix = file_manager._get_subtitle_suffix(subtitle_options)
                base_filename = f'{sentence["order"]:04d}'
                output_filename = f'{base_filename}{subtitle_suffix}.mp4'
                
                output_file = os.path.join(output_dir, output_filename)
                
                # Extract with subtitles
                success = media_extractor.extract_sentence_with_subtitles(
                    input_file, output_file, sentence, subtitle_options, is_video
                )
                
                if not success:
                    logger.warning(f"Failed to extract sentence {sentence['id']}")
                
            except Exception as e:
                logger.error(f"Error extracting sentence {sentence['id']}: {e}")
                continue
        
        processing_status[f"{media_id}_{extraction_type}"] = {
            'stage': 'completed',
            'progress': 100,
            'message': f'{extraction_type} MP4 추출이 완료되었습니다.'
        }
        
    except Exception as e:
        logger.error(f"Bulk MP4 extraction failed for media {media_id}: {e}")
        processing_status[f"{media_id}_{extraction_type}"] = {
            'stage': 'error',
            'progress': 0,
            'message': f'추출 중 오류가 발생했습니다: {str(e)}'
        }

def extract_full_media_mp4_background(media_id, sentences, subtitle_english, subtitle_korean):
    """Background processing for full media MP4 extraction"""
    try:
        processing_status[f"{media_id}_full"] = {
            'stage': 'starting',
            'progress': 0,
            'message': '전체 미디어 MP4 추출을 시작합니다...'
        }
        
        media = media_repo.get_by_id(media_id)
        if not media:
            raise Exception("Media not found")
        
        is_video = media['fileType'] == 'video'
        input_file = file_manager.get_media_path(media['filename'])
        
        # Create output directory
        base_dir = file_manager.create_output_directory(media_id, media['filename'])
        
        # Create subtitle file if needed
        subtitle_file = None
        if (subtitle_english or subtitle_korean) and sentences:
            import uuid
            subtitle_filename = f'full_media_{uuid.uuid4().hex}.ass'
            subtitle_file = os.path.join(base_dir, subtitle_filename)
            
            # Create full ASS file with all sentences
            create_full_ass_subtitle_file(sentences, subtitle_file, subtitle_english, subtitle_korean)
        
        # Generate output filename
        media_duration = ffmpeg_processor.get_media_duration(input_file)
        suffix = ''
        if subtitle_english and subtitle_korean:
            suffix = '_engkor'
        elif subtitle_english:
            suffix = '_eng'
        elif subtitle_korean:
            suffix = '_kor'
        else:
            suffix = '_nosub'
        
        output_filename = f'full_media{suffix}.mp4'
        output_file = os.path.join(base_dir, output_filename)
        
        # Extract full media
        if is_video and subtitle_file:
            success = ffmpeg_processor.extract_video_segment(
                input_file, output_file, 0, media_duration, subtitle_file, timeout=1800
            )
        elif not is_video and subtitle_file:
            success = ffmpeg_processor.create_video_from_audio(
                input_file, output_file, 0, media_duration, subtitle_file, timeout=1800
            )
        else:
            # Copy without subtitles
            import shutil
            shutil.copy2(input_file, output_file)
            success = True
        
        # Clean up subtitle file
        if subtitle_file and os.path.exists(subtitle_file):
            os.remove(subtitle_file)
        
        if success:
            processing_status[f"{media_id}_full"] = {
                'stage': 'completed',
                'progress': 100,
                'message': '전체 미디어 MP4 추출이 완료되었습니다.'
            }
        else:
            raise Exception("FFmpeg processing failed")
        
    except Exception as e:
        logger.error(f"Full media MP4 extraction failed for media {media_id}: {e}")
        processing_status[f"{media_id}_full"] = {
            'stage': 'error',
            'progress': 0,
            'message': f'추출 중 오류가 발생했습니다: {str(e)}'
        }

def create_full_ass_subtitle_file(sentences, output_path, include_english, include_korean):
    """Create ASS subtitle file with all sentences"""
    
    def seconds_to_ass_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"
    
    # ASS header
    ass_content = """[Script Info]
Title: Full Media Subtitles
ScriptType: v4.00+
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: English,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,1,0,0,0,100,100,0,0,1,2,0,2,3,3,60,1
Style: Korean,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,16,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # Add dialogue lines
    for sentence in sentences:
        start_time = seconds_to_ass_time(sentence['startTime'])
        end_time = seconds_to_ass_time(sentence['endTime'])
        
        if include_english and sentence.get('english'):
            ass_content += f"Dialogue: 0,{start_time},{end_time},English,,0,0,0,,{sentence['english']}\n"
        
        if include_korean and sentence.get('korean'):
            ass_content += f"Dialogue: 1,{start_time},{end_time},Korean,,0,0,0,,{sentence['korean']}\n"
    
    # Write file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

# =============================================================================
# FILE SERVING ROUTES
# =============================================================================

@app.route('/api/download/<filename>')
def download_file(filename):
    """Download extracted files"""
    try:
        file_path = file_manager.get_download_path(filename)
        if not file_path:
            return jsonify({'error': 'File not found'}), 404
        
        directory = os.path.dirname(file_path)
        return send_from_directory(directory, os.path.basename(file_path), as_attachment=True)
    
    except Exception as e:
        logger.error(f"Error downloading file {filename}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/audio/<filename>')
def serve_audio(filename):
    """Serve audio files for playback"""
    try:
        file_path = file_manager.get_media_path(filename)
        if not file_path:
            return jsonify({'error': 'File not found'}), 404
        
        return send_file(file_path)
    
    except Exception as e:
        logger.error(f"Error serving audio file {filename}: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# HELPER FUNCTIONS (TO BE MOVED TO SEPARATE MODULES)
# =============================================================================

def create_default_structure_for_video(media_id, audio_filename, template_type):
    """Create default chapter/scene structure - this should be moved to a separate module"""
    
    # Get audio duration
    audio_path = file_manager.get_media_path(audio_filename)
    duration = ffmpeg_processor.get_media_duration(audio_path)
    
    if not duration:
        raise Exception("Could not get audio duration")
    
    # Create default structure based on template
    if template_type == 'toeic_lc':
        chapters_data = [
            {'title': 'Part 1: Photos', 'start': 0, 'end': duration * 0.15, 'scenes': 6},
            {'title': 'Part 2: Question-Response', 'start': duration * 0.15, 'end': duration * 0.4, 'scenes': 25},
            {'title': 'Part 3: Conversations', 'start': duration * 0.4, 'end': duration * 0.7, 'scenes': 13},
            {'title': 'Part 4: Talks', 'start': duration * 0.7, 'end': duration, 'scenes': 10}
        ]
    else:
        # General template
        chapter_count = max(1, int(duration / 600))  # 10-minute chapters
        chapters_data = []
        for i in range(chapter_count):
            start_time = (duration / chapter_count) * i
            end_time = (duration / chapter_count) * (i + 1)
            chapters_data.append({
                'title': f'Chapter {i + 1}',
                'start': start_time,
                'end': end_time,
                'scenes': 5
            })
    
    # Create chapters and scenes
    for order, chapter_data in enumerate(chapters_data):
        chapter = {
            'mediaId': media_id,
            'title': chapter_data['title'],
            'startTime': chapter_data['start'],
            'endTime': chapter_data['end'],
            'order': order + 1
        }
        
        chapter_ids = chapter_repo.create_batch([chapter])
        chapter_id = chapter_ids[0]
        
        # Create scenes for this chapter
        scene_duration = (chapter_data['end'] - chapter_data['start']) / chapter_data['scenes']
        scenes = []
        
        for scene_order in range(chapter_data['scenes']):
            scene_start = chapter_data['start'] + (scene_duration * scene_order)
            scene_end = chapter_data['start'] + (scene_duration * (scene_order + 1))
            
            scenes.append({
                'chapterId': chapter_id,
                'title': f"Scene {scene_order + 1}",
                'startTime': scene_start,
                'endTime': scene_end,
                'order': scene_order + 1
            })
        
        scene_ids = scene_repo.create_batch(scenes)
        
        # Create sample sentences for first scene only (to demonstrate)
        if order == 0 and scene_ids:
            sentences = [{
                'sceneId': scene_ids[0],
                'english': "This is a sample sentence for demonstration.",
                'korean': "이것은 시연을 위한 샘플 문장입니다.",
                'startTime': chapter_data['start'],
                'endTime': chapter_data['start'] + 5.0,
                'order': 1,
                'confidence': 0.95
            }]
            sentence_repo.create_batch(sentences)

# =============================================================================
# CHAPTER EXTRACTION ROUTES
# =============================================================================

@app.route('/api/media/<media_id>/chapter/<int:chapter_id>/extract-mp3', methods=['POST'])
def extract_chapter_mp3(media_id, chapter_id):
    """Extract chapter as MP3"""
    try:
        # Get chapter info
        chapter = chapter_repo.get_by_id(chapter_id)
        if not chapter:
            return jsonify({'error': 'Chapter not found'}), 404
            
        # Get media info
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        # Get input file path
        input_path = file_manager.get_media_path(media['filename'])
        if not input_path:
            return jsonify({'error': 'Media file not found'}), 404
        
        # Create output directory
        output_dir = file_manager.create_output_directory(media_id, media['filename'])
        chapter_dir = file_manager.create_extraction_directory(output_dir, 'chapters')
        
        # Generate output filename
        clean_name = file_manager.get_clean_media_name(media['filename'])
        output_filename = f"{clean_name}_chapter_{chapter['order']}.mp3"
        output_path = os.path.join(chapter_dir, output_filename)
        
        # Extract chapter audio
        start_time = chapter['startTime']
        duration = chapter['endTime'] - chapter['startTime']
        
        success = ffmpeg_processor.extract_audio_segment(
            input_path, output_path, start_time, duration, timeout=300
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Chapter MP3 extracted successfully',
                'filename': output_filename
            })
        else:
            return jsonify({'error': 'Failed to extract chapter MP3'}), 500
            
    except Exception as e:
        logger.error(f"Error extracting chapter MP3: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/chapter/<int:chapter_id>/extract-mp4', methods=['POST'])
def extract_chapter_mp4(media_id, chapter_id):
    """Extract chapter as MP4 with subtitles"""
    try:
        # Get subtitle options from request
        subtitle_options = request.get_json() or {}
        
        # Get chapter info
        chapter = chapter_repo.get_by_id(chapter_id)
        if not chapter:
            return jsonify({'error': 'Chapter not found'}), 404
            
        # Get media info
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        # Get input file path
        input_path = file_manager.get_media_path(media['filename'])
        if not input_path:
            return jsonify({'error': 'Media file not found'}), 404
        
        # Create output directory
        output_dir = file_manager.create_output_directory(media_id, media['filename'])
        chapter_dir = file_manager.create_extraction_directory(output_dir, 'chapters', subtitle_options)
        
        # Generate output filename
        clean_name = file_manager.get_clean_media_name(media['filename'])
        output_filename = f"{clean_name}_chapter_{chapter['order']}.mp4"
        output_path = os.path.join(chapter_dir, output_filename)
        
        # Get all sentences for this chapter
        sentences = sentence_repo.get_by_chapter_id(chapter_id)
        if not sentences:
            return jsonify({'error': 'No sentences found for chapter'}), 404
        
        # Create chapter subtitle file if needed
        subtitle_file = None
        if any(subtitle_options.values()):
            subtitle_file = _create_chapter_subtitle_file(chapter, sentences, subtitle_options)
        
        try:
            # Extract chapter video
            start_time = chapter['startTime']
            duration = chapter['endTime'] - chapter['startTime']
            is_video = file_manager.is_video_file(media['filename'])
            
            if is_video:
                success = ffmpeg_processor.extract_video_segment(
                    input_path, output_path, start_time, duration, subtitle_file, timeout=900
                )
            else:
                success = ffmpeg_processor.create_video_from_audio(
                    input_path, output_path, start_time, duration, subtitle_file, timeout=900
                )
            
            if success:
                return jsonify({
                    'success': True,
                    'message': 'Chapter MP4 extracted successfully',
                    'filename': output_filename
                })
            else:
                return jsonify({'error': 'Failed to extract chapter MP4'}), 500
                
        finally:
            # Clean up subtitle file
            if subtitle_file and os.path.exists(subtitle_file):
                try:
                    os.remove(subtitle_file)
                except Exception as e:
                    logger.warning(f"Failed to remove subtitle file: {e}")
            
    except Exception as e:
        logger.error(f"Error extracting chapter MP4: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# SCENE EXTRACTION ROUTES
# =============================================================================

@app.route('/api/media/<media_id>/scene/<int:scene_id>/extract-mp3', methods=['POST'])
def extract_scene_mp3(media_id, scene_id):
    """Extract scene as MP3"""
    try:
        # Get scene info
        scene = scene_repo.get_by_id(scene_id)
        if not scene:
            return jsonify({'error': 'Scene not found'}), 404
            
        # Get media info
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        # Get input file path
        input_path = file_manager.get_media_path(media['filename'])
        if not input_path:
            return jsonify({'error': 'Media file not found'}), 404
        
        # Create output directory
        output_dir = file_manager.create_output_directory(media_id, media['filename'])
        scene_dir = file_manager.create_extraction_directory(output_dir, 'scenes')
        
        # Generate output filename
        clean_name = file_manager.get_clean_media_name(media['filename'])
        output_filename = f"{clean_name}_scene_{scene['order']}.mp3"
        output_path = os.path.join(scene_dir, output_filename)
        
        # Extract scene audio
        start_time = scene['startTime']
        duration = scene['endTime'] - scene['startTime']
        
        success = ffmpeg_processor.extract_audio_segment(
            input_path, output_path, start_time, duration, timeout=300
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Scene MP3 extracted successfully',
                'filename': output_filename
            })
        else:
            return jsonify({'error': 'Failed to extract scene MP3'}), 500
            
    except Exception as e:
        logger.error(f"Error extracting scene MP3: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/scene/<int:scene_id>/extract-mp4', methods=['POST'])
def extract_scene_mp4(media_id, scene_id):
    """Extract scene as MP4 with subtitles"""
    try:
        # Get subtitle options from request
        subtitle_options = request.get_json() or {}
        
        # Get scene info
        scene = scene_repo.get_by_id(scene_id)
        if not scene:
            return jsonify({'error': 'Scene not found'}), 404
            
        # Get media info
        media = media_repo.get_by_id(media_id)
        if not media:
            return jsonify({'error': 'Media not found'}), 404
        
        # Get input file path
        input_path = file_manager.get_media_path(media['filename'])
        if not input_path:
            return jsonify({'error': 'Media file not found'}), 404
        
        # Create output directory
        output_dir = file_manager.create_output_directory(media_id, media['filename'])
        scene_dir = file_manager.create_extraction_directory(output_dir, 'scenes', subtitle_options)
        
        # Generate output filename
        clean_name = file_manager.get_clean_media_name(media['filename'])
        output_filename = f"{clean_name}_scene_{scene['order']}.mp4"
        output_path = os.path.join(scene_dir, output_filename)
        
        # Get all sentences for this scene
        sentences = sentence_repo.get_by_scene_id(scene_id)
        if not sentences:
            return jsonify({'error': 'No sentences found for scene'}), 404
        
        # Create scene subtitle file if needed
        subtitle_file = None
        if any(subtitle_options.values()):
            subtitle_file = _create_scene_subtitle_file(scene, sentences, subtitle_options)
        
        try:
            # Extract scene video
            start_time = scene['startTime']
            duration = scene['endTime'] - scene['startTime']
            is_video = file_manager.is_video_file(media['filename'])
            
            if is_video:
                success = ffmpeg_processor.extract_video_segment(
                    input_path, output_path, start_time, duration, subtitle_file, timeout=900
                )
            else:
                success = ffmpeg_processor.create_video_from_audio(
                    input_path, output_path, start_time, duration, subtitle_file, timeout=900
                )
            
            if success:
                return jsonify({
                    'success': True,
                    'message': 'Scene MP4 extracted successfully',
                    'filename': output_filename
                })
            else:
                return jsonify({'error': 'Failed to extract scene MP4'}), 500
                
        finally:
            # Clean up subtitle file
            if subtitle_file and os.path.exists(subtitle_file):
                try:
                    os.remove(subtitle_file)
                except Exception as e:
                    logger.warning(f"Failed to remove subtitle file: {e}")
            
    except Exception as e:
        logger.error(f"Error extracting scene MP4: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# HELPER FUNCTIONS FOR SUBTITLE CREATION
# =============================================================================

def _create_chapter_subtitle_file(chapter, sentences, subtitle_options):
    """Create subtitle file for chapter with all sentences"""
    try:
        # Create temporary subtitle file
        subtitle_filename = f'temp_chapter_{chapter["id"]}_{uuid.uuid4().hex}.ass'
        subtitle_path = os.path.join(os.path.dirname(__file__), subtitle_filename)
        
        # Build ASS content
        chapter_duration = chapter['endTime'] - chapter['startTime']
        chapter_start = chapter['startTime']
        
        # Create combined text for the chapter
        english_lines = []
        korean_lines = []
        
        for sentence in sentences:
            if subtitle_options.get('english') and sentence.get('english'):
                english_lines.append(sentence['english'])
            if subtitle_options.get('korean') and sentence.get('korean'):
                korean_lines.append(sentence['korean'])
        
        english_text = ' '.join(english_lines) if english_lines else None
        korean_text = ' '.join(korean_lines) if korean_lines else None
        
        return subtitle_processor.create_ass_subtitle_file(
            english_text, korean_text, chapter_duration, subtitle_path
        )
        
    except Exception as e:
        logger.error(f"Error creating chapter subtitle file: {e}")
        return None

def _create_scene_subtitle_file(scene, sentences, subtitle_options):
    """Create subtitle file for scene with all sentences"""
    try:
        # Create temporary subtitle file
        subtitle_filename = f'temp_scene_{scene["id"]}_{uuid.uuid4().hex}.ass'
        subtitle_path = os.path.join(os.path.dirname(__file__), subtitle_filename)
        
        # Build ASS content
        scene_duration = scene['endTime'] - scene['startTime']
        scene_start = scene['startTime']
        
        # Create combined text for the scene
        english_lines = []
        korean_lines = []
        
        for sentence in sentences:
            if subtitle_options.get('english') and sentence.get('english'):
                english_lines.append(sentence['english'])
            if subtitle_options.get('korean') and sentence.get('korean'):
                korean_lines.append(sentence['korean'])
        
        english_text = ' '.join(english_lines) if english_lines else None
        korean_text = ' '.join(korean_lines) if korean_lines else None
        
        return subtitle_processor.create_ass_subtitle_file(
            english_text, korean_text, scene_duration, subtitle_path
        )
        
    except Exception as e:
        logger.error(f"Error creating scene subtitle file: {e}")
        return None


# =============================================================================
# WORDS DATABASE API (words_db.txt based)
# =============================================================================

@app.route('/api/words/reload', methods=['POST'])
def reload_words_database():
    """Reload words database from file"""
    try:
        words_file = '/home/kang/dev/english/static/data/words_db.txt'
        count = words_repo.load_from_file(words_file)
        
        return jsonify({
            'success': True,
            'message': f'{count}개의 구문을 다시 로드했습니다.'
        })
    except Exception as e:
        logger.error(f"Error reloading words database: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/words/stats', methods=['GET'])
def get_words_stats():
    """Get words database statistics"""
    try:
        phrase_count = words_repo.get_phrase_count()
        
        return jsonify({
            'success': True,
            'phrase_count': phrase_count
        })
    except Exception as e:
        logger.error(f"Error getting words stats: {e}")
        return jsonify({'error': str(e)}), 500
        
        logger.info(f"Completed auto vocabulary analysis for media {media_id}")
        
    except Exception as e:
        logger.error(f"Error in auto vocabulary analysis: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)