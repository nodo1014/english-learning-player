#!/usr/bin/env python3
"""
Clean subtitle text by removing unwanted elements
"""
import re
import sqlite3
from pathlib import Path

def clean_subtitle_text(text):
    """
    Clean subtitle text by removing:
    - Sound effects: (효과음), [묘사], {action}
    - Speaker names: MONICA:, Speaker:
    - Music: ♪ lyrics ♪
    - Multiple spaces and newlines
    - Special patterns like www, release info
    """
    if not text:
        return ""
    
    original_text = text
    
    # Remove music/songs (♪ or ♫)
    text = re.sub(r'♪[^♪]*♪', '', text)
    text = re.sub(r'♫[^♫]*♫', '', text)
    text = re.sub(r'[♪♫].*?[♪♫]', '', text)
    text = re.sub(r'[♪♫]', '', text)
    
    # Remove sound effects and descriptions
    text = re.sub(r'\([^)]*\)', '', text)  # (sound effects)
    text = re.sub(r'\[[^\]]*\]', '', text)  # [descriptions]
    text = re.sub(r'\{[^}]*\}', '', text)   # {actions}
    
    # Remove speaker names (SPEAKER: or Speaker:)
    text = re.sub(r'^[A-Z][A-Z\s]*:', '', text)  # ALL CAPS speaker names
    text = re.sub(r'^[A-Z][a-z]+:', '', text)    # Title case speaker names
    text = re.sub(r'\b[A-Z]+:', '', text)        # Any caps word followed by colon
    
    # Remove subtitle/release info patterns
    text = re.sub(r'.*Sub Upload Date.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*subtitle.*upload.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*www\..*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*\.com.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*\.org.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*\.net.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*release.*info.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*addic7ed.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*subscene.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*opensubtitles.*', '', text, flags=re.IGNORECASE)
    
    # Remove hyphen dialogues (- Speaker: text)
    text = re.sub(r'^-\s*[A-Z]+:\s*', '', text)
    text = re.sub(r'\s*-\s*[A-Z]+:\s*', '. ', text)
    
    # Clean up multiple dialogue lines
    text = re.sub(r'^-\s*', '', text)  # Remove leading hyphens
    text = re.sub(r'\s*-\s*', '. ', text)  # Replace internal hyphens with periods
    
    # Remove multiple spaces, tabs, newlines
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Remove empty sentences or very short ones
    if len(text) < 3 or text in ['', '.', '..', '...', '-', '--']:
        return ""
    
    # Log significant changes for debugging
    if len(original_text) - len(text) > 20:
        print(f"Cleaned: '{original_text[:50]}...' -> '{text[:50]}...'")
    
    return text

def clean_existing_subtitles():
    """Clean all existing subtitle entries in the database"""
    db_path = '/home/kang/dev/english/dev.db'
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Get all sentences
        cursor.execute('SELECT id, english FROM Sentence WHERE english IS NOT NULL AND english != ""')
        sentences = cursor.fetchall()
        
        print(f"Found {len(sentences)} sentences to process...")
        
        cleaned_count = 0
        deleted_count = 0
        
        for sentence_id, english_text in sentences:
            cleaned_text = clean_subtitle_text(english_text)
            
            if not cleaned_text:
                # Delete empty sentences
                cursor.execute('DELETE FROM Sentence WHERE id = ?', (sentence_id,))
                deleted_count += 1
            elif cleaned_text != english_text:
                # Update cleaned sentences
                cursor.execute('UPDATE Sentence SET english = ? WHERE id = ?', (cleaned_text, sentence_id))
                cleaned_count += 1
        
        conn.commit()
        print(f"Cleaned {cleaned_count} sentences, deleted {deleted_count} empty sentences")

def test_cleaning():
    """Test the cleaning function with sample data"""
    test_cases = [
        "♪ Oh, oh, oh, oh, oh! ♪",
        "That one, I've never had. PHOEBE: No",
        "Hey. MONICA: All right",
        "(sound effect) Hello there",
        "[door closes] What's up?",
        "SPEAKER: This is dialogue",
        "- MONICA: Hi there - RACHEL: Hello",
        "Fidel33 Sub Upload Date: May 21, 2016",
        "www.addic7ed.com subtitle info",
        "Normal dialogue here",
        "",
        "   ",
        "...",
    ]
    
    print("Testing cleaning function:")
    for test in test_cases:
        cleaned = clean_subtitle_text(test)
        print(f"'{test}' -> '{cleaned}'")

if __name__ == '__main__':
    print("Testing cleaning function first...")
    test_cleaning()
    
    print("\nCleaning existing database entries...")
    clean_existing_subtitles()
    
    print("Done!")