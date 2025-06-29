#!/usr/bin/env python3
"""
Part 1을 Number 1-24로 재구성
"""

import sqlite3

def reorganize_part1_to_number_24():
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    print("Part 1을 Number 1-24로 재구성 중...")
    
    # Part 1과 Part 2 챕터 ID 가져오기
    cursor.execute("SELECT id FROM Chapter WHERE mediaId = 9 AND `order` = 1")
    part1_id = cursor.fetchone()[0]
    
    cursor.execute("SELECT id FROM Chapter WHERE mediaId = 9 AND `order` = 2")
    part2_id = cursor.fetchone()[0]
    
    # Number 10-24까지의 Scene들을 Part 2에서 Part 1으로 이동
    for number in range(10, 25):
        print(f"Number {number} 처리 중...")
        
        # Part 2에서 해당 Scene 찾기
        cursor.execute("""
            SELECT id FROM Scene 
            WHERE chapterId = ? AND title = ?
        """, (part2_id, f'Number {number}'))
        
        scene_result = cursor.fetchone()
        if scene_result:
            old_scene_id = scene_result[0]
            
            # Part 1에 새 Scene 생성
            cursor.execute("""
                INSERT INTO Scene (chapterId, title, startTime, endTime, `order`)
                SELECT ?, title, startTime, endTime, ?
                FROM Scene WHERE id = ?
            """, (part1_id, number - 2, old_scene_id))  # order: 8부터 시작 (Directions + Number 1-6 = 7개)
            
            new_scene_id = cursor.lastrowid
            
            # 문장들을 새 Scene으로 이동
            cursor.execute("""
                UPDATE Sentence SET sceneId = ? WHERE sceneId = ?
            """, (new_scene_id, old_scene_id))
            
            # 기존 Scene 삭제
            cursor.execute("DELETE FROM Scene WHERE id = ?", (old_scene_id,))
            
            print(f"  Number {number} 완료")
    
    # Part 2의 Scene order 재정렬 (Number 25부터 시작)
    cursor.execute("""
        UPDATE Scene SET `order` = `order` - 15
        WHERE chapterId = ? AND title NOT LIKE '%Directions%'
    """, (part2_id,))
    
    conn.commit()
    conn.close()
    
    print("✅ Part 1 재구성 완료!")
    
    # 결과 확인
    print_structure()

def print_structure():
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    print("\n=== 재구성된 구조 ===")
    
    cursor.execute("""
        SELECT c.title, COUNT(sc.id) as scene_count
        FROM Chapter c
        LEFT JOIN Scene sc ON c.id = sc.chapterId
        WHERE c.mediaId = 9
        GROUP BY c.id
        ORDER BY c.`order`
    """)
    
    for title, scene_count in cursor.fetchall():
        print(f"{title}: {scene_count}개 씬")
        
        if "Part 1" in title:
            cursor.execute("""
                SELECT title FROM Scene 
                WHERE chapterId = (SELECT id FROM Chapter WHERE mediaId = 9 AND `order` = 1)
                ORDER BY `order`
                LIMIT 10
            """)
            scenes = cursor.fetchall()
            for scene_title, in scenes:
                print(f"  - {scene_title}")
            if len(scenes) > 10:
                print(f"  ... 및 {len(scenes) - 10}개 더")
    
    conn.close()

if __name__ == "__main__":
    reorganize_part1_to_number_24()