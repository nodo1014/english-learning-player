#!/usr/bin/env python3
import sqlite3
import sys
from vad_filters import apply_time_filters, apply_content_filters

def apply_smart_filters_to_media(media_id):
    """미디어에 스마트 필터 적용"""
    
    # 기존 데이터 로드
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    print(f"미디어 {media_id}에 스마트 필터 적용 중...")
    
    # 기존 문장들 가져오기
    cursor.execute('''
        SELECT s.id, s.english, s.korean, s.startTime, s.endTime, s.`order`, s.sceneId
        FROM Sentence s
        JOIN Scene sc ON s.sceneId = sc.id
        JOIN Chapter c ON sc.chapterId = c.id
        WHERE c.mediaId = ?
        ORDER BY s.`order`
    ''', (media_id,))
    
    original_sentences = cursor.fetchall()
    print(f"원본 문장 수: {len(original_sentences)}개")
    
    # 필터 적용을 위한 형식 변환
    sentences_for_filter = []
    for row in original_sentences:
        sentences_for_filter.append({
            'id': row[0],
            'english': row[1],
            'korean': row[2] or '',
            'start_time': row[3],
            'end_time': row[4],
            'order': row[5],
            'scene_id': row[6]
        })
    
    # 1단계: 시간 기반 필터
    print("1단계: 시간 기반 필터 적용...")
    time_filtered = apply_time_filters(sentences_for_filter, min_duration=0.5, max_duration=20.0)
    print(f"시간 필터 후: {len(time_filtered)}개")
    
    # 2단계: 내용 기반 필터
    print("2단계: 내용 기반 필터 적용...")
    final_filtered = apply_content_filters(time_filtered, min_words=1)
    print(f"최종 필터 후: {len(final_filtered)}개")
    
    # 3단계: 길이별 챕터 재구성
    print("3단계: 길이별 챕터 재구성...")
    
    # 기존 챕터/씬/문장 삭제
    cursor.execute("DELETE FROM Sentence WHERE sceneId IN (SELECT id FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?))", (media_id,))
    cursor.execute("DELETE FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?)", (media_id,))
    cursor.execute("DELETE FROM Chapter WHERE mediaId = ?", (media_id,))
    
    # 4개 챕터로 고정 분할
    total_sentences = len(final_filtered)
    chapter_size = total_sentences // 4  # 전체를 4등분
    remainder = total_sentences % 4  # 나머지
    chapters_created = 0
    
    current_index = 0
    for chapter_num in range(4):
        # 각 챕터별 문장 수 계산 (나머지를 앞쪽 챕터에 분배)
        current_chapter_size = chapter_size + (1 if chapter_num < remainder else 0)
        
        # 현재 챕터의 문장들 추출
        chapter_sentences = final_filtered[current_index:current_index + current_chapter_size]
        current_index += current_chapter_size
        
        if not chapter_sentences:
            continue
            
        chapters_created += 1
        chapter_start = chapter_sentences[0]['start_time']
        chapter_end = chapter_sentences[-1]['end_time']
        chapter_title = f"Chapter {chapters_created}"
        
        # 챕터 생성
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, chapter_title, chapter_start, chapter_end, chapters_created)
        )
        chapter_id = cursor.lastrowid
        
        # 각 챕터를 적절한 수의 씬으로 세분화
        sentences_per_scene = max(10, len(chapter_sentences) // 5)  # 최소 10문장, 최대 5개 씬
        scenes_in_chapter = 0
        
        for j in range(0, len(chapter_sentences), sentences_per_scene):
            scene_sentences = chapter_sentences[j:j+sentences_per_scene]
            if not scene_sentences:
                continue
                
            scenes_in_chapter += 1
            scene_start = scene_sentences[0]['start_time']
            scene_end = scene_sentences[-1]['end_time']
            scene_title = f"Scene {scenes_in_chapter}"
            
            # 씬 생성
            cursor.execute(
                "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                (chapter_id, scene_title, scene_start, scene_end, scenes_in_chapter)
            )
            scene_id = cursor.lastrowid
            
            # 문장들 추가
            for k, sentence in enumerate(scene_sentences):
                cursor.execute(
                    """INSERT INTO Sentence 
                    (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (scene_id, sentence['english'], sentence['korean'], 
                     sentence['start_time'], sentence['end_time'], 0, sentence['order'])
                )
    
    # 커밋
    conn.commit()
    conn.close()
    
    print(f"✅ 완료: {chapters_created}개 챕터, {len(final_filtered)}개 문장")
    return {
        'original_count': len(original_sentences),
        'filtered_count': len(final_filtered),
        'chapters_created': chapters_created
    }

if __name__ == "__main__":
    media_id = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    result = apply_smart_filters_to_media(media_id)
    print(f"필터링 결과: {result}")