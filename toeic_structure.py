#!/usr/bin/env python3
import sqlite3
import re

def analyze_toeic_structure(media_id):
    """토익 LC 구조 분석 및 재구성"""
    
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    # 모든 문장 가져오기
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
    
    print(f"총 {len(sentences)}개 문장 분석 중...")
    
    # 토익 파트별 특성 분석
    part_boundaries = detect_toeic_parts(sentences)
    
    # 기존 구조 삭제
    cursor.execute("DELETE FROM Sentence WHERE sceneId IN (SELECT id FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?))", (media_id,))
    cursor.execute("DELETE FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?)", (media_id,))
    cursor.execute("DELETE FROM Chapter WHERE mediaId = ?", (media_id,))
    
    # 토익 구조로 재생성
    toeic_parts = [
        {'title': 'Part 1 - 사진 묘사', 'description': '6-10문제'},
        {'title': 'Part 2 - 응답', 'description': '25문제'},
        {'title': 'Part 3 - 대화', 'description': '39문제 (13세트)'},
        {'title': 'Part 4 - 담화', 'description': '30문제 (10세트)'}
    ]
    
    for part_idx, (start_idx, end_idx) in enumerate(part_boundaries):
        if part_idx >= len(toeic_parts):
            break
            
        part_sentences = sentences[start_idx:end_idx]
        if not part_sentences:
            continue
            
        part_info = toeic_parts[part_idx]
        chapter_start = part_sentences[0]['start_time']
        chapter_end = part_sentences[-1]['end_time']
        
        # 챕터 생성
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, part_info['title'], chapter_start, chapter_end, part_idx + 1)
        )
        chapter_id = cursor.lastrowid
        
        # 파트별 씬 구성
        if part_idx == 0:  # Part 1: 사진별로 씬 구성
            scenes = create_part1_scenes(part_sentences)
        elif part_idx == 1:  # Part 2: 5문제씩 씬 구성
            scenes = create_part2_scenes(part_sentences)
        elif part_idx == 2:  # Part 3: 대화별로 씬 구성
            scenes = create_part3_scenes(part_sentences)
        else:  # Part 4: 담화별로 씬 구성
            scenes = create_part4_scenes(part_sentences)
        
        # 씬들 생성
        for scene_idx, scene_data in enumerate(scenes):
            cursor.execute(
                "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                (chapter_id, scene_data['title'], scene_data['start_time'], scene_data['end_time'], scene_idx + 1)
            )
            scene_id = cursor.lastrowid
            
            # 문장들 추가
            for sentence in scene_data['sentences']:
                cursor.execute(
                    """INSERT INTO Sentence 
                    (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (scene_id, sentence['english'], sentence['korean'], 
                     sentence['start_time'], sentence['end_time'], 0, sentence['order'])
                )
    
    conn.commit()
    conn.close()
    
    print(f"✅ 토익 LC 구조로 재구성 완료: {len(toeic_parts)}개 파트")
    return part_boundaries

def detect_toeic_parts(sentences):
    """토익 파트 경계 감지"""
    # 간단한 휴리스틱: 시간 기반으로 4등분
    total_sentences = len(sentences)
    
    # 토익 실제 비율 반영 (대략적)
    part1_ratio = 0.05  # Part 1: 5% (매우 짧음)
    part2_ratio = 0.25  # Part 2: 25%
    part3_ratio = 0.40  # Part 3: 40%
    part4_ratio = 0.30  # Part 4: 30%
    
    part1_end = int(total_sentences * part1_ratio)
    part2_end = int(total_sentences * (part1_ratio + part2_ratio))
    part3_end = int(total_sentences * (part1_ratio + part2_ratio + part3_ratio))
    
    boundaries = [
        (0, max(part1_end, 20)),  # Part 1: 최소 20문장
        (max(part1_end, 20), part2_end),  # Part 2
        (part2_end, part3_end),  # Part 3
        (part3_end, total_sentences)  # Part 4
    ]
    
    print("토익 파트 경계:")
    for i, (start, end) in enumerate(boundaries):
        print(f"  Part {i+1}: 문장 {start+1}-{end} ({end-start}개)")
    
    return boundaries

def create_part1_scenes(sentences):
    """Part 1: 사진별 씬 (2-3문장씩)"""
    scenes = []
    scene_size = 3
    
    for i in range(0, len(sentences), scene_size):
        scene_sentences = sentences[i:i+scene_size]
        if scene_sentences:
            scenes.append({
                'title': f"사진 {i//scene_size + 1}",
                'start_time': scene_sentences[0]['start_time'],
                'end_time': scene_sentences[-1]['end_time'],
                'sentences': scene_sentences
            })
    
    return scenes

def create_part2_scenes(sentences):
    """Part 2: 5문제씩 씬"""
    scenes = []
    scene_size = max(5, len(sentences) // 5)  # 대략 5개 씬
    
    for i in range(0, len(sentences), scene_size):
        scene_sentences = sentences[i:i+scene_size]
        if scene_sentences:
            scenes.append({
                'title': f"문제 {i//scene_size * scene_size + 1}-{min(i + scene_size, len(sentences))}",
                'start_time': scene_sentences[0]['start_time'],
                'end_time': scene_sentences[-1]['end_time'],
                'sentences': scene_sentences
            })
    
    return scenes

def create_part3_scenes(sentences):
    """Part 3: 대화별 씬 (3문제씩 13세트)"""
    scenes = []
    scene_size = max(3, len(sentences) // 13)  # 13개 대화
    
    for i in range(0, len(sentences), scene_size):
        scene_sentences = sentences[i:i+scene_size]
        if scene_sentences:
            scenes.append({
                'title': f"대화 {i//scene_size + 1}",
                'start_time': scene_sentences[0]['start_time'],
                'end_time': scene_sentences[-1]['end_time'],
                'sentences': scene_sentences
            })
    
    return scenes

def create_part4_scenes(sentences):
    """Part 4: 담화별 씬 (3문제씩 10세트)"""
    scenes = []
    scene_size = max(3, len(sentences) // 10)  # 10개 담화
    
    for i in range(0, len(sentences), scene_size):
        scene_sentences = sentences[i:i+scene_size]
        if scene_sentences:
            scenes.append({
                'title': f"담화 {i//scene_size + 1}",
                'start_time': scene_sentences[0]['start_time'],
                'end_time': scene_sentences[-1]['end_time'],
                'sentences': scene_sentences
            })
    
    return scenes

if __name__ == "__main__":
    boundaries = analyze_toeic_structure(9)
    print(f"토익 LC 구조 분석 결과: {boundaries}")