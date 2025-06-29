#!/usr/bin/env python3
"""
토익 LC 스마트 템플릿
실제 토익 구조를 반영한 정확한 Scene 분할 시스템
"""

import sqlite3
import re

class TOEICSmartTemplate:
    def __init__(self):
        self.part_patterns = {
            1: {
                'title': 'Part 1 - 사진 묘사',
                'scene_method': 'by_number',
                'number_pattern': r'^Number\s+(\d+)\.',
                'description': 'Number X 기준으로 Scene 분할'
            },
            2: {
                'title': 'Part 2 - 응답',  
                'scene_method': 'by_number',
                'number_pattern': r'^Number\s+(\d+)\.',
                'description': 'Number X 기준으로 Scene 분할'
            },
            3: {
                'title': 'Part 3 - 대화',
                'scene_method': 'by_question_range',
                'question_pattern': r'Questions?\s+(\d+)\s+through\s+(\d+)',
                'description': 'Questions X through Y 기준으로 Scene 분할'
            },
            4: {
                'title': 'Part 4 - 담화',
                'scene_method': 'by_question_range', 
                'question_pattern': r'Questions?\s+(\d+)\s+through\s+(\d+)',
                'description': 'Questions X through Y 기준으로 Scene 분할'
            }
        }
    
    def find_scene_boundaries(self, sentences, part_num):
        """파트별 Scene 경계 찾기"""
        part_config = self.part_patterns.get(part_num)
        if not part_config:
            return []
        
        boundaries = []
        
        # 먼저 Directions Scene 찾기
        directions_boundary = self._find_directions_boundary(sentences, part_num)
        if directions_boundary:
            boundaries.append(directions_boundary)
        
        # 메인 Scene들 찾기
        if part_config['scene_method'] == 'by_number':
            main_boundaries = self._find_number_boundaries(sentences, part_config['number_pattern'])
        elif part_config['scene_method'] == 'by_question_range':
            main_boundaries = self._find_question_range_boundaries(sentences, part_config['question_pattern'])
        else:
            main_boundaries = []
        
        # Directions Scene가 있으면 메인 Scene들의 인덱스 조정
        if directions_boundary and main_boundaries:
            directions_end = directions_boundary['end_index']
            adjusted_boundaries = []
            for boundary in main_boundaries:
                if boundary['start_index'] > directions_end:
                    adjusted_boundaries.append(boundary)
            main_boundaries = adjusted_boundaries
        
        boundaries.extend(main_boundaries)
        
        print(f"Part {part_num}: {len(boundaries)}개 Scene 경계 발견")
        for i, boundary in enumerate(boundaries):
            print(f"  Scene {i+1}: {boundary['title']} (문장 {boundary['start_index']+1}-{boundary['end_index']+1})")
        
        return boundaries
    
    def _find_directions_boundary(self, sentences, part_num):
        """Directions Scene 경계 찾기"""
        # Part X로 시작하는 문장부터 첫 번째 Number/Questions 패턴 전까지
        part_start_pattern = rf'^Part\s+{part_num}[.\s]'
        
        start_index = None
        end_index = None
        
        # Part X 시작점 찾기
        for i, sentence in enumerate(sentences):
            text = sentence['english']
            if re.search(part_start_pattern, text, re.IGNORECASE):
                start_index = i
                break
        
        if start_index is None:
            return None
        
        # 첫 번째 Number/Questions 패턴 전까지 찾기
        if part_num in [1, 2]:
            # Part 1, 2: Number X 패턴 전까지
            number_pattern = r'^Number\s+(\d+)\.'
            for i in range(start_index + 1, len(sentences)):
                if re.search(number_pattern, sentences[i]['english'], re.IGNORECASE):
                    end_index = i - 1
                    break
        else:
            # Part 3, 4: Questions X through Y 패턴 전까지
            question_pattern = r'Questions?\s+(\d+)\s+through\s+(\d+)'
            for i in range(start_index + 1, len(sentences)):
                if re.search(question_pattern, sentences[i]['english'], re.IGNORECASE):
                    end_index = i - 1
                    break
        
        # 끝점을 찾지 못했으면 다음 10개 문장까지만 (Directions는 보통 짧음)
        if end_index is None:
            end_index = min(start_index + 10, len(sentences) - 1)
        
        # 유효한 범위인지 확인
        if start_index >= end_index:
            end_index = start_index
        
        return {
            'title': f'Part {part_num} Directions',
            'start_index': start_index,
            'end_index': end_index,
            'start_time': sentences[start_index]['start_time'],
            'end_time': sentences[end_index]['end_time'],
            'is_directions': True
        }
    
    def _find_number_boundaries(self, sentences, pattern):
        """Number X 패턴으로 Scene 경계 찾기 (Part 1, 2)"""
        boundaries = []
        
        # 모든 Number X 패턴의 위치를 먼저 찾기
        number_positions = []
        for i, sentence in enumerate(sentences):
            text = sentence['english']
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                number = int(match.group(1))
                number_positions.append({
                    'index': i,
                    'number': number,
                    'text': text
                })
        
        # 각 Number X부터 다음 Number Y 전까지를 하나의 Scene으로 묶기
        for i, pos in enumerate(number_positions):
            start_index = pos['index']
            
            # 다음 Number의 인덱스 찾기 (없으면 끝까지)
            if i + 1 < len(number_positions):
                end_index = number_positions[i + 1]['index'] - 1
            else:
                end_index = len(sentences) - 1
            
            boundary = {
                'title': f"Number {pos['number']}",
                'number': pos['number'],
                'start_index': start_index,
                'end_index': end_index,
                'start_time': sentences[start_index]['start_time'],
                'end_time': sentences[end_index]['end_time'],
                'pattern_text': pos['text']
            }
            boundaries.append(boundary)
        
        return boundaries
    
    def _find_question_range_boundaries(self, sentences, pattern):
        """Questions X through Y 패턴으로 Scene 경계 찾기 (Part 3, 4)"""
        boundaries = []
        current_boundary = None
        
        for i, sentence in enumerate(sentences):
            text = sentence['english']
            
            # Questions X through Y 패턴 찾기
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start_q = int(match.group(1))
                end_q = int(match.group(2))
                
                # 이전 경계 마무리
                if current_boundary:
                    current_boundary['end_index'] = i - 1
                    current_boundary['end_time'] = sentences[i-1]['end_time']
                    boundaries.append(current_boundary)
                
                # 새 경계 시작
                current_boundary = {
                    'title': f"Questions {start_q}-{end_q}",
                    'start_question': start_q,
                    'end_question': end_q,
                    'start_index': i,
                    'start_time': sentence['start_time'],
                    'pattern_text': text
                }
        
        # 마지막 경계 마무리  
        if current_boundary:
            current_boundary['end_index'] = len(sentences) - 1
            current_boundary['end_time'] = sentences[-1]['end_time']
            boundaries.append(current_boundary)
        
        return boundaries
    
    def group_sentences_by_scenes(self, sentences, scene_boundaries):
        """Scene 경계에 따라 문장들 그룹화"""
        if not scene_boundaries:
            # 경계가 없으면 전체를 하나의 Scene으로
            return [{
                'title': 'All Sentences',
                'sentences': sentences,
                'start_time': sentences[0]['start_time'] if sentences else 0,
                'end_time': sentences[-1]['end_time'] if sentences else 0
            }]
        
        scenes = []
        for boundary in scene_boundaries:
            start_idx = boundary['start_index']
            end_idx = boundary['end_index']
            
            scene_sentences = sentences[start_idx:end_idx+1]
            if scene_sentences:
                scenes.append({
                    'title': boundary['title'],
                    'sentences': scene_sentences,
                    'start_time': boundary['start_time'],
                    'end_time': boundary['end_time'],
                    'sentence_count': len(scene_sentences)
                })
        
        return scenes

def apply_toeic_smart_template(media_id):
    """토익 스마트 템플릿 적용"""
    
    template = TOEICSmartTemplate()
    
    # 데이터베이스 연결
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    print("=== 토익 스마트 템플릿 적용 ===")
    
    # 현재 Part별 문장들 가져오기
    cursor.execute('''
        SELECT c.id, c.title, c.`order`, c.startTime, c.endTime
        FROM Chapter c
        WHERE c.mediaId = ?
        ORDER BY c.`order`
    ''', (media_id,))
    
    chapters = cursor.fetchall()
    
    for chapter_id, chapter_title, chapter_order, chapter_start, chapter_end in chapters:
        part_num = chapter_order  # Part 번호
        
        print(f"\n📝 {chapter_title} (Part {part_num}) 처리 중...")
        
        # 해당 Part의 모든 문장 가져오기
        cursor.execute('''
            SELECT s.english, s.korean, s.startTime, s.endTime, s.`order`, s.id
            FROM Sentence s
            JOIN Scene sc ON s.sceneId = sc.id
            WHERE sc.chapterId = ?
            ORDER BY s.`order`
        ''', (chapter_id,))
        
        sentences = []
        for row in cursor.fetchall():
            sentences.append({
                'english': row[0],
                'korean': row[1] or '',
                'start_time': row[2],
                'end_time': row[3],
                'order': row[4],
                'id': row[5]
            })
        
        if not sentences:
            print(f"  ⚠️ Part {part_num}: 문장이 없음")
            continue
        
        print(f"  총 {len(sentences)}개 문장")
        
        # Scene 경계 찾기
        scene_boundaries = template.find_scene_boundaries(sentences, part_num)
        
        # Scene별로 그룹화
        scenes = template.group_sentences_by_scenes(sentences, scene_boundaries)
        
        print(f"  → {len(scenes)}개 Scene 생성")
        
        # 기존 Scene들 삭제
        cursor.execute("DELETE FROM Sentence WHERE sceneId IN (SELECT id FROM Scene WHERE chapterId = ?)", (chapter_id,))
        cursor.execute("DELETE FROM Scene WHERE chapterId = ?", (chapter_id,))
        
        # 새 Scene들 생성
        for scene_order, scene_data in enumerate(scenes):
            cursor.execute(
                "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                (chapter_id, scene_data['title'], scene_data['start_time'], scene_data['end_time'], scene_order + 1)
            )
            scene_id = cursor.lastrowid
            
            # Scene에 문장들 추가
            for sentence in scene_data['sentences']:
                cursor.execute(
                    """INSERT INTO Sentence 
                    (sceneId, english, korean, startTime, endTime, bookmark, `order`) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (scene_id, sentence['english'], sentence['korean'], 
                     sentence['start_time'], sentence['end_time'], 0, sentence['order'])
                )
            
            print(f"    Scene {scene_order+1}: '{scene_data['title']}' - {len(scene_data['sentences'])}개 문장")
    
    conn.commit()
    conn.close()
    
    print("\n✅ 토익 스마트 템플릿 적용 완료!")
    
    # 결과 확인
    print_final_structure(media_id)

def print_final_structure(media_id):
    """최종 구조 출력"""
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    print("\n=== 최종 구조 ===")
    
    cursor.execute('''
        SELECT c.title, c.startTime, c.endTime
        FROM Chapter c
        WHERE c.mediaId = ?
        ORDER BY c.`order`
    ''', (media_id,))
    
    chapters = cursor.fetchall()
    
    for chapter_title, chapter_start, chapter_end in chapters:
        duration = chapter_end - chapter_start
        print(f"\n📚 {chapter_title} ({duration/60:.1f}분)")
        
        cursor.execute('''
            SELECT sc.title, sc.startTime, sc.endTime, COUNT(s.id) as sentence_count
            FROM Scene sc
            LEFT JOIN Sentence s ON sc.id = s.sceneId
            JOIN Chapter c ON sc.chapterId = c.id
            WHERE c.title = ? AND c.mediaId = ?
            GROUP BY sc.id
            ORDER BY sc.`order`
        ''', (chapter_title, media_id))
        
        scenes = cursor.fetchall()
        for scene_title, scene_start, scene_end, sentence_count in scenes:
            scene_duration = scene_end - scene_start
            print(f"  🎬 {scene_title} ({scene_duration/60:.1f}분) - {sentence_count}개 문장")
    
    conn.close()

def test_pattern_detection(media_id):
    """패턴 감지 테스트"""
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    print("=== 패턴 감지 테스트 ===")
    
    # 모든 문장에서 패턴 찾기
    cursor.execute('''
        SELECT s.english, s.startTime, c.title
        FROM Sentence s
        JOIN Scene sc ON s.sceneId = sc.id
        JOIN Chapter c ON sc.chapterId = c.id
        WHERE c.mediaId = ?
        ORDER BY s.`order`
    ''', (media_id,))
    
    sentences = cursor.fetchall()
    
    # Number 패턴
    print("\n🔍 Number 패턴:")
    number_pattern = r'^Number\s+(\d+)\.'
    for i, (text, start_time, chapter_title) in enumerate(sentences):
        match = re.search(number_pattern, text, re.IGNORECASE)
        if match:
            number = match.group(1)
            print(f"  {chapter_title}: Number {number} at {start_time/60:.1f}m - {text[:50]}...")
    
    # Question range 패턴
    print("\n🔍 Questions X through Y 패턴:")
    question_pattern = r'Questions?\s+(\d+)\s+through\s+(\d+)'
    for i, (text, start_time, chapter_title) in enumerate(sentences):
        match = re.search(question_pattern, text, re.IGNORECASE)
        if match:
            start_q, end_q = match.group(1), match.group(2)
            print(f"  {chapter_title}: Questions {start_q}-{end_q} at {start_time/60:.1f}m - {text[:50]}...")
    
    conn.close()

if __name__ == "__main__":
    print("토익 스마트 템플릿 시작...")
    
    # 먼저 패턴 감지 테스트
    test_pattern_detection(9)
    
    print("\n" + "="*60)
    
    # 스마트 템플릿 적용
    apply_toeic_smart_template(9)