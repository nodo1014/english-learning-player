#!/usr/bin/env python3
"""
Process existing subtitle files for imported media
"""
import os
import sqlite3
from pathlib import Path
import re

def parse_srt_time(time_str):
    """Parse SRT time format to seconds"""
    # Format: 00:01:11,518
    time_parts = time_str.replace(',', '.').split(':')
    hours = int(time_parts[0])
    minutes = int(time_parts[1])
    seconds = float(time_parts[2])
    return hours * 3600 + minutes * 60 + seconds

def clean_subtitle_text(text):
    """Clean subtitle text by removing unwanted elements"""
    if not text:
        return ""
    
    # Remove music/songs (♪ or ♫)
    text = re.sub(r'♪[^♪]*♪', '', text)
    text = re.sub(r'♫[^♫]*♫', '', text)
    text = re.sub(r'[♪♫]', '', text)
    
    # Remove sound effects and descriptions
    text = re.sub(r'\([^)]*\)', '', text)  # (sound effects)
    text = re.sub(r'\[[^\]]*\]', '', text)  # [descriptions]
    text = re.sub(r'\{[^}]*\}', '', text)   # {actions}
    
    # Remove speaker names
    text = re.sub(r'^[A-Z][A-Z\s]*:', '', text)  # ALL CAPS speaker names
    text = re.sub(r'^[A-Z][a-z]+:', '', text)    # Title case speaker names
    text = re.sub(r'\b[A-Z]+:', '', text)        # Any caps word followed by colon
    
    # Remove subtitle/release info patterns
    text = re.sub(r'.*Sub Upload Date.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*www\..*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*\.com.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*addic7ed.*', '', text, flags=re.IGNORECASE)
    
    # Remove dialogue hyphens
    text = re.sub(r'^-\s*[A-Z]+:\s*', '', text)
    text = re.sub(r'\s*-\s*[A-Z]+:\s*', '. ', text)
    text = re.sub(r'^-\s*', '', text)
    text = re.sub(r'\s*-\s*', '. ', text)
    
    # Clean up spaces
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text if len(text) >= 3 else ""

def parse_srt_file(file_path):
    """Parse SRT file and return list of cleaned sentences"""
    sentences = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    
    # Split by double newlines to get subtitle blocks
    blocks = re.split(r'\n\s*\n', content)
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            # Skip subtitle number (first line)
            time_line = lines[1]
            text_lines = lines[2:]
            
            # Parse time range
            if ' --> ' in time_line:
                start_time_str, end_time_str = time_line.split(' --> ')
                start_time = parse_srt_time(start_time_str.strip())
                end_time = parse_srt_time(end_time_str.strip())
                
                # Join and clean text lines
                text = ' '.join(text_lines).strip()
                cleaned_text = clean_subtitle_text(text)
                
                if cleaned_text:
                    sentences.append({
                        'english': cleaned_text,
                        'startTime': start_time,
                        'endTime': end_time
                    })
    
    return sentences

def process_subtitle_for_media(media_id, subtitle_path, duration=7200.0):
    """Process subtitle file for a specific media"""
    db_path = '/home/kang/dev/english/dev.db'
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Create chapter
        cursor.execute('''
            INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`)
            VALUES (?, ?, ?, ?, ?)
        ''', (media_id, 'Subtitles', 0.0, duration, 1))
        chapter_id = cursor.lastrowid
        
        # Create scene
        cursor.execute('''
            INSERT INTO Scene (chapterId, title, startTime, endTime, `order`)
            VALUES (?, ?, ?, ?, ?)
        ''', (chapter_id, 'Main Scene', 0.0, duration, 1))
        scene_id = cursor.lastrowid
        
        # Parse and insert sentences
        sentences = parse_srt_file(subtitle_path)
        print(f"Found {len(sentences)} sentences in {subtitle_path}")
        
        for i, sentence in enumerate(sentences):
            cursor.execute('''
                INSERT INTO Sentence (sceneId, english, startTime, endTime, `order`)
                VALUES (?, ?, ?, ?, ?)
            ''', (scene_id, sentence['english'], sentence['startTime'], 
                  sentence['endTime'], i + 1))
        
        conn.commit()
        print(f"Processed {len(sentences)} sentences for media {media_id}")

def main():
    upload_dir = Path('/home/kang/dev/english/upload')
    
    # Find all SRT files and their corresponding media
    subtitle_files = list(upload_dir.glob('*.srt'))
    
    for srt_file in subtitle_files:
        # Extract media ID from filename
        filename = srt_file.name
        if '_' in filename:
            media_id = filename.split('_')[0]
            print(f"Processing {filename} for media {media_id}")
            
            try:
                process_subtitle_for_media(media_id, str(srt_file))
            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == '__main__':
    main()