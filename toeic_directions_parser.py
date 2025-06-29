#!/usr/bin/env python3
import sqlite3
import re

def find_toeic_part_boundaries(sentences):
    """토익 파트 경계를 Directions 기준으로 찾기"""
    
    boundaries = []
    current_part = None
    
    for i, sentence in enumerate(sentences):
        text = sentence['english'].lower()
        
        # Part X 패턴 찾기
        part_match = re.search(r'part\s+(\d+)', text)
        if part_match:
            part_num = int(part_match.group(1))
            if part_num <= 4:  # LC는 Part 1-4만
                current_part = part_num
                print(f"Part {part_num} 발견: 문장 {i+1} ({sentence['start_time']:.1f}s)")
        
        # Directions 발견
        if 'directions' in text and current_part:
            # 이전 파트 경계 마무리
            if boundaries and 'end_index' not in boundaries[-1]:
                boundaries[-1]['end_index'] = i - 1
                boundaries[-1]['end_time'] = sentences[i-1]['end_time']
            
            # 새 파트 시작
            part_info = {
                'part': current_part,
                'start_index': i,
                'start_time': sentence['start_time'],
                'directions_text': sentence['english']
            }
            boundaries.append(part_info)
    
    # 마지막 파트 마무리
    if boundaries and 'end_index' not in boundaries[-1]:
        boundaries[-1]['end_index'] = len(sentences) - 1
        boundaries[-1]['end_time'] = sentences[-1]['end_time']
    
    return boundaries

def apply_directions_based_structure(media_id):
    """Directions 기반으로 토익 구조 적용"""
    
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    # 기존 문장들 로드
    cursor.execute('''
        SELECT s.english, s.korean, s.startTime, s.endTime, s.`order`
        FROM Sentence s
        JOIN Scene sc ON s.sceneId = sc.id
        JOIN Chapter c ON sc.chapterId = c.id
        WHERE c.mediaId = ?
        ORDER BY s.`order`
    ''', (media_id,))
    
    sentences = []
    for row in cursor.fetchall():
        sentences.append({
            'english': row[0],
            'korean': row[1] or '',
            'start_time': row[2],
            'end_time': row[3],
            'order': row[4]
        })
    
    print(f"총 {len(sentences)}개 문장 분석...")
    
    # Directions 기준으로 파트 경계 찾기
    boundaries = find_toeic_part_boundaries(sentences)
    
    print("\\n=== 발견된 파트 경계 ===")
    for boundary in boundaries:
        duration = boundary['end_time'] - boundary['start_time']
        sentence_count = boundary['end_index'] - boundary['start_index'] + 1
        print(f"Part {boundary['part']}: 문장 {boundary['start_index']+1}-{boundary['end_index']+1} ({sentence_count}개)")
        print(f"  시간: {boundary['start_time']//60:.0f}:{boundary['start_time']%60:02.0f} - {boundary['end_time']//60:.0f}:{boundary['end_time']%60:02.0f} ({duration/60:.1f}분)")
        print(f"  Directions: {boundary['directions_text'][:60]}...")
        print()
    
    # 기존 구조 삭제
    cursor.execute("DELETE FROM Sentence WHERE sceneId IN (SELECT id FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?))", (media_id,))
    cursor.execute("DELETE FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?)", (media_id,))
    cursor.execute("DELETE FROM Chapter WHERE mediaId = ?", (media_id,))
    
    # 파트별 구조 정의
    part_structures = {
        1: {
            'title': 'Part 1 - 사진 묘사',
            'scene_pattern': 'photograph',
            'sentences_per_scene': 4  # 사진당 대략 4-5문장
        },
        2: {
            'title': 'Part 2 - 응답',
            'scene_pattern': 'question_group',
            'sentences_per_scene': 8  # 문제 5개씩 그룹
        },
        3: {
            'title': 'Part 3 - 대화',
            'scene_pattern': 'conversation',
            'sentences_per_scene': 15  # 대화당 10-20문장
        },
        4: {
            'title': 'Part 4 - 담화',
            'scene_pattern': 'talk',
            'sentences_per_scene': 20  # 담화당 15-25문장
        }
    }
    
    # 새 구조 생성
    for boundary in boundaries:
        part_num = boundary['part']
        part_structure = part_structures.get(part_num, {})
        
        part_sentences = sentences[boundary['start_index']:boundary['end_index']+1]
        
        # 챕터 생성
        chapter_title = part_structure.get('title', f'Part {part_num}')
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, chapter_title, boundary['start_time'], boundary['end_time'], part_num)
        )
        chapter_id = cursor.lastrowid
        
        # 씬 생성
        sentences_per_scene = part_structure.get('sentences_per_scene', 20)
        scene_pattern = part_structure.get('scene_pattern', 'section')
        
        scene_count = 0
        for i in range(0, len(part_sentences), sentences_per_scene):
            scene_sentences = part_sentences[i:i+sentences_per_scene]
            if not scene_sentences:
                continue
                
            scene_count += 1
            
            # 씬 제목 생성
            if scene_pattern == 'photograph':
                scene_title = f"사진 {scene_count}"
            elif scene_pattern == 'question_group':
                start_q = (scene_count - 1) * 5 + 1
                end_q = min(scene_count * 5, 25)
                scene_title = f"문제 {start_q}-{end_q}"
            elif scene_pattern == 'conversation':
                scene_title = f"대화 {scene_count}"
            elif scene_pattern == 'talk':
                scene_title = f"담화 {scene_count}"
            else:
                scene_title = f"섹션 {scene_count}"
            
            scene_start = scene_sentences[0]['start_time']
            scene_end = scene_sentences[-1]['end_time']
            
            cursor.execute(
                "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                (chapter_id, scene_title, scene_start, scene_end, scene_count)
            )
            scene_id = cursor.lastrowid
            
            # 문장들 추가
            for sentence in scene_sentences:
                cursor.execute(
                    """INSERT INTO Sentence 
                    (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (scene_id, sentence['english'], sentence['korean'], 
                     sentence['start_time'], sentence['end_time'], 0, sentence['order'])
                )
    
    conn.commit()
    conn.close()
    
    print(f"✅ Directions 기반 토익 구조 적용 완료: {len(boundaries)}개 파트")
    return boundaries

if __name__ == "__main__":
    boundaries = apply_directions_based_structure(9)
    
    # 결과 확인
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    print("\\n=== 최종 구조 확인 ===")
    cursor.execute('''
        SELECT c.title, c.startTime, c.endTime,
               COUNT(DISTINCT sc.id) as scene_count,
               COUNT(s.id) as sentence_count
        FROM Chapter c
        LEFT JOIN Scene sc ON c.id = sc.chapterId
        LEFT JOIN Sentence s ON sc.id = s.sceneId
        WHERE c.mediaId = 9
        GROUP BY c.id
        ORDER BY c.`order`
    ''')
    
    for row in cursor.fetchall():
        title, start_time, end_time, scene_count, sentence_count = row
        duration = end_time - start_time
        print(f"{title}")
        print(f"  시간: {start_time//60:.0f}:{start_time%60:02.0f} - {end_time//60:.0f}:{end_time%60:02.0f} ({duration/60:.1f}분)")
        print(f"  구성: {scene_count}개 씬, {sentence_count}개 문장")
        print()
    
    conn.close()