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

# spaCy import (with fallback)
try:
    import spacy
    # Load English model
    nlp = spacy.load("en_core_web_sm")
    SPACY_AVAILABLE = True
except (ImportError, OSError):
    SPACY_AVAILABLE = False
    nlp = None

# Import our new modules
from database import media_repo, chapter_repo, scene_repo, sentence_repo, db_manager
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

# Load CEFR-J word difficulty data
CEFR_WORD_LEVELS = {}
def load_cefr_data():
    """Load CEFR-J vocabulary data from octanove C1/C2 dataset"""
    global CEFR_WORD_LEVELS
    try:
        csv_path = '/home/kang/dev/english/data/olp-en-cefrj-master/octanove-vocabulary-profile-c1c2-1.0.csv'
        import csv
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                word = row['headword'].lower().strip()
                cefr_level = row['CEFR'].strip()
                
                # Only C1/C2 words are marked as difficult
                if cefr_level in ['C1', 'C2']:
                    CEFR_WORD_LEVELS[word] = 'hard'
        
        logger.info(f"Loaded {len(CEFR_WORD_LEVELS)} C1/C2 words from CEFR-J data")
    except Exception as e:
        logger.error(f"Failed to load CEFR data: {e}")

# Load data at startup
load_cefr_data()

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

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
    """Get sentences grouped by chapters and scenes"""
    try:
        chapters = chapter_repo.get_by_media_id(media_id)
        
        for chapter in chapters:
            scenes = scene_repo.get_by_chapter_id(chapter['id'])
            for scene in scenes:
                scene['sentences'] = sentence_repo.get_by_scene_id(scene['id'])
            chapter['scenes'] = scenes
        
        return jsonify(chapters)
    except Exception as e:
        logger.error(f"Error getting grouped sentences for media {media_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/sentences', methods=['GET'])
def get_sentences(media_id):
    """Get flat list of sentences for a media"""
    try:
        sentences = sentence_repo.get_by_media_id(media_id)
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
        
        # Create output directory
        output_dir = file_manager.create_output_directory(media_id, media['filename'])
        output_filename = f'sentence_{sentence_id}_{sentence["startTime"]:.1f}s-{sentence["endTime"]:.1f}s.mp4'
        output_file = os.path.join(output_dir, output_filename)
        
        # Extract with subtitles (always include English for single sentence)
        subtitle_options = {'english': True, 'korean': False}
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
        
        # Get bookmarked sentences
        bookmarked_sentences = sentence_repo.get_bookmarked_by_media_id(media_id)
        if not bookmarked_sentences:
            return jsonify({'error': 'No bookmarked sentences found'}), 404
        
        # Start background processing
        thread = threading.Thread(
            target=extract_bulk_mp4_background,
            args=(media_id, bookmarked_sentences, 'bookmarked', subtitle_english, subtitle_korean)
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
        
        # Get all sentences
        all_sentences = sentence_repo.get_by_media_id(media_id)
        if not all_sentences:
            return jsonify({'error': 'No sentences found'}), 404
        
        # Start background processing
        thread = threading.Thread(
            target=extract_bulk_mp4_background,
            args=(media_id, all_sentences, 'all', subtitle_english, subtitle_korean)
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

def extract_bulk_mp4_background(media_id, sentences, extraction_type, subtitle_english, subtitle_korean):
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
        subtitle_options = {'english': subtitle_english, 'korean': subtitle_korean}
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
                
                # Generate output filename
                if extraction_type == 'bookmarked':
                    output_filename = f'bookmarked_{sentence["order"]:04d}_{extraction_type}.mp4'
                else:
                    output_filename = f'{sentence["order"]:04d}_{extraction_type}.mp4'
                
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
# PERSONAL VOCABULARY API
# =============================================================================

@app.route('/api/vocabulary/add', methods=['POST'])
def add_word_to_vocabulary():
    """Add word to personal vocabulary"""
    try:
        data = request.get_json()
        word = data.get('word', '').lower().strip()
        
        if not word:
            return jsonify({'error': 'Word is required'}), 400
        
        # Prepare word data with defaults
        word_data = {
            'word': word,
            'lemma': data.get('lemma', word),
            'definition': data.get('definition', ''),
            'pos': data.get('pos', ''),
            'difficulty_level': data.get('difficulty_level', 'medium'),
            'frequency_rank': data.get('frequency_rank', 5000),
            'context_sentence': data.get('context_sentence', ''),
            'sentence_id': data.get('sentence_id')
        }
        
        success = vocab_repo.add_word(word_data)
        
        if success:
            return jsonify({'success': True, 'message': 'Word added to vocabulary'})
        else:
            return jsonify({'error': 'Failed to add word'}), 500
            
    except Exception as e:
        logger.error(f"Add vocabulary error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vocabulary', methods=['GET'])
def get_vocabulary():
    """Get personal vocabulary list"""
    try:
        difficulty = request.args.get('difficulty')
        
        if difficulty:
            words = vocab_repo.get_words_by_difficulty(difficulty)
        else:
            words = vocab_repo.get_all_words()
        
        return jsonify({'words': words})
        
    except Exception as e:
        logger.error(f"Get vocabulary error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vocabulary/statistics', methods=['GET'])
def get_vocabulary_statistics():
    """Get vocabulary learning statistics"""
    try:
        stats = vocab_repo.get_statistics()
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Get vocabulary stats error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vocabulary/mark-known', methods=['POST'])
def mark_word_known():
    """Mark word as known"""
    try:
        data = request.get_json()
        word = data.get('word', '').lower().strip()
        lemma = data.get('lemma', word)
        
        if not word:
            return jsonify({'error': 'Word is required'}), 400
        
        success = vocab_repo.mark_as_known(word, lemma)
        
        if success:
            return jsonify({'success': True, 'message': 'Word marked as known'})
        else:
            return jsonify({'error': 'Failed to mark word as known'}), 500
            
    except Exception as e:
        logger.error(f"Mark known error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vocabulary/mark-unknown', methods=['POST'])
def mark_word_unknown():
    """Mark word as unknown"""
    try:
        data = request.get_json()
        word = data.get('word', '').lower().strip()
        lemma = data.get('lemma', word)
        
        if not word:
            return jsonify({'error': 'Word is required'}), 400
        
        success = vocab_repo.mark_as_unknown(word, lemma)
        
        if success:
            return jsonify({'success': True, 'message': 'Word marked as unknown'})
        else:
            return jsonify({'error': 'Failed to mark word as unknown'}), 500
            
    except Exception as e:
        logger.error(f"Mark unknown error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vocabulary/check-known', methods=['POST'])
def check_word_known():
    """Check if word is known"""
    try:
        data = request.get_json()
        word = data.get('word', '').lower().strip()
        lemma = data.get('lemma', word)
        
        if not word:
            return jsonify({'error': 'Word is required'}), 400
        
        is_known = vocab_repo.is_word_known(word, lemma)
        
        return jsonify({'word': word, 'is_known': is_known})
        
    except Exception as e:
        logger.error(f"Check known error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/word/difficulty/<word>', methods=['GET'])
def get_word_difficulty(word):
    """Get word difficulty level based on CEFR data"""
    try:
        word_lower = word.lower().strip()
        
        # Check if word is in C1/C2 (hard) category
        if word_lower in CEFR_WORD_LEVELS:
            difficulty = CEFR_WORD_LEVELS[word_lower]
        else:
            difficulty = 'normal'  # Not in C1/C2 list
        
        return jsonify({
            'word': word,
            'difficulty': difficulty,
            'level': 'C1/C2' if difficulty == 'hard' else 'A1-B2'
        })
        
    except Exception as e:
        logger.error(f"Word difficulty error: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# VERB DETECTION API (spaCy-based)
# =============================================================================

@app.route('/api/detect-verbs', methods=['POST'])
def detect_verbs():
    """Detect verbs in text - now returns cached results instantly"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        sentence_id = data.get('sentence_id')
        
        if not text:
            return jsonify({'verbs': []})
        
        # Try to get from DB first if sentence_id provided
        if sentence_id:
            try:
                sentence = sentence_repo.get_by_id(sentence_id)
                if sentence and sentence.get('detectedVerbs'):
                    import json
                    cached_verbs = json.loads(sentence['detectedVerbs'])
                    return jsonify({'verbs': cached_verbs, 'cached': True})
            except Exception as e:
                logger.warning(f"Could not load cached verbs for sentence {sentence_id}: {e}")
        
        # Fallback to real-time analysis (should be rare now)
        if not SPACY_AVAILABLE:
            return jsonify({'verbs': _detect_verbs_fallback(text)})
        
        # Use spaCy for accurate POS tagging
        doc = nlp(text)
        verbs = []
        
        for token in doc:
            if token.pos_ == 'VERB' and not token.is_stop and len(token.text) > 2:
                verbs.append(token.text)
        
        # Remove duplicates and limit to top 3
        unique_verbs = list(set(verbs))[:3]
        
        return jsonify({'verbs': unique_verbs, 'cached': False})
        
    except Exception as e:
        logger.error(f"Error detecting verbs: {e}")
        return jsonify({'verbs': _detect_verbs_fallback(text)})

def _detect_verbs_fallback(text):
    """Fallback verb detection using simple patterns"""
    # Basic patterns for common verbs
    common_verbs = ['am', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 'do', 'does', 'did', 
                   'will', 'would', 'can', 'could', 'should', 'go', 'went', 'come', 'came', 
                   'get', 'got', 'make', 'made', 'take', 'took', 'give', 'gave', 'see', 'saw',
                   'work', 'works', 'working', 'worked', 'play', 'plays', 'playing', 'played',
                   'run', 'runs', 'running', 'ran', 'walk', 'walks', 'walking', 'walked',
                   'talk', 'talks', 'talking', 'talked', 'eat', 'eats', 'eating', 'ate',
                   'think', 'thinks', 'thinking', 'thought', 'say', 'says', 'saying', 'said']
    
    words = re.findall(r'\b\w+\b', text.lower())
    found_verbs = [word for word in words if word in common_verbs]
    
    return list(set(found_verbs))[:3]

@app.route('/api/media/<media_id>/analyze-verbs', methods=['POST'])
def analyze_verbs_background(media_id):
    """Start background verb analysis for all sentences"""
    try:
        def analyze_verbs_task():
            """Background task to analyze verbs"""
            sentences = sentence_repo.get_sentences_without_verbs(media_id)
            
            if not sentences:
                logger.info(f"No sentences need verb analysis for media {media_id}")
                return
            
            logger.info(f"Starting verb analysis for {len(sentences)} sentences")
            
            for sentence in sentences:
                try:
                    if not sentence.get('english'):
                        continue
                        
                    # Detect verbs using spaCy
                    if SPACY_AVAILABLE:
                        doc = nlp(sentence['english'])
                        verbs = []
                        
                        for token in doc:
                            if token.pos_ == 'VERB' and not token.is_stop and len(token.text) > 2:
                                verbs.append(token.text)
                        
                        # Remove duplicates and limit to top 3
                        unique_verbs = list(set(verbs))[:3]
                    else:
                        # Fallback
                        unique_verbs = _detect_verbs_fallback(sentence['english'])
                    
                    # Store as JSON
                    import json
                    verbs_json = json.dumps(unique_verbs)
                    sentence_repo.update_verbs(sentence['id'], verbs_json)
                    
                except Exception as e:
                    logger.error(f"Error analyzing sentence {sentence['id']}: {e}")
                    continue
            
            logger.info(f"Completed verb analysis for media {media_id}")
        
        # Start background thread
        thread = threading.Thread(target=analyze_verbs_task)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': '동사 분석이 백그라운드에서 시작되었습니다.'
        })
        
    except Exception as e:
        logger.error(f"Error starting verb analysis: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)