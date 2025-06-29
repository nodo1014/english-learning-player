#!/usr/bin/env python3
"""
기존 미디어의 빈 번역을 채우는 스크립트
"""

import sqlite3
from deep_translator import GoogleTranslator
import time

def translate_empty_sentences(media_id):
    """빈 번역을 가진 문장들을 번역"""
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    # 빈 번역 문장 찾기
    cursor.execute("""
        SELECT s.id, s.english 
        FROM Sentence s
        JOIN Scene sc ON s.sceneId = sc.id
        JOIN Chapter c ON sc.chapterId = c.id
        WHERE c.mediaId = ? AND (s.korean = '' OR s.korean IS NULL)
    """, (media_id,))
    
    empty_sentences = cursor.fetchall()
    
    if not empty_sentences:
        print(f"Media {media_id}: 모든 문장이 이미 번역되어 있습니다.")
        return
    
    print(f"Media {media_id}: {len(empty_sentences)}개 문장 번역 시작...")
    
    translator = GoogleTranslator(source='en', target='ko')
    translated = 0
    
    for sentence_id, english in empty_sentences:
        try:
            korean = translator.translate(english)
            cursor.execute("UPDATE Sentence SET korean = ? WHERE id = ?", (korean, sentence_id))
            translated += 1
            
            if translated % 10 == 0:
                print(f"  {translated}/{len(empty_sentences)} 번역 완료...")
                conn.commit()
                time.sleep(0.5)  # API 제한 방지
                
        except Exception as e:
            print(f"  번역 오류 (ID {sentence_id}): {e}")
            cursor.execute("UPDATE Sentence SET korean = ? WHERE id = ?", (english, sentence_id))
    
    conn.commit()
    conn.close()
    
    print(f"✅ 번역 완료: {translated}/{len(empty_sentences)} 문장")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        media_id = int(sys.argv[1])
        translate_empty_sentences(media_id)
    else:
        # 모든 미디어의 빈 번역 채우기
        conn = sqlite3.connect('dev.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM Media ORDER BY id DESC")
        media_ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        for media_id in media_ids:
            translate_empty_sentences(media_id)
            time.sleep(1)