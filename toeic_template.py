#!/usr/bin/env python3
"""
토익 LC (Listening Comprehension) 구조 템플릿
실제 토익 시험 구조를 반영한 정확한 분할 기준
"""

class TOEICTemplate:
    def __init__(self):
        self.structure = {
            "Part 1": {
                "title": "Part 1 - 사진 묘사 (Photographs)",
                "question_count": 6,
                "time_per_question": 20,  # 초
                "total_time": 120,  # 2분
                "description": "6개 사진, 각 사진당 4개 선택지",
                "scenes": [
                    {"title": "사진 1-2", "questions": 2},
                    {"title": "사진 3-4", "questions": 2}, 
                    {"title": "사진 5-6", "questions": 2}
                ]
            },
            "Part 2": {
                "title": "Part 2 - 응답 (Question-Response)",
                "question_count": 25,
                "time_per_question": 18,  # 초
                "total_time": 450,  # 7.5분
                "description": "25개 질문, 각 질문당 3개 응답 선택지",
                "scenes": [
                    {"title": "문제 1-5", "questions": 5},
                    {"title": "문제 6-10", "questions": 5},
                    {"title": "문제 11-15", "questions": 5},
                    {"title": "문제 16-20", "questions": 5},
                    {"title": "문제 21-25", "questions": 5}
                ]
            },
            "Part 3": {
                "title": "Part 3 - 대화 (Conversations)",
                "question_count": 39,
                "conversation_count": 13,
                "time_per_conversation": 180,  # 3분 (대화 + 문제 3개)
                "total_time": 2340,  # 39분
                "description": "13개 대화, 각 대화당 3개 문제",
                "scenes": [
                    {"title": "대화 1", "questions": 3, "conversation_id": 1},
                    {"title": "대화 2", "questions": 3, "conversation_id": 2},
                    {"title": "대화 3", "questions": 3, "conversation_id": 3},
                    {"title": "대화 4", "questions": 3, "conversation_id": 4},
                    {"title": "대화 5", "questions": 3, "conversation_id": 5},
                    {"title": "대화 6", "questions": 3, "conversation_id": 6},
                    {"title": "대화 7", "questions": 3, "conversation_id": 7},
                    {"title": "대화 8", "questions": 3, "conversation_id": 8},
                    {"title": "대화 9", "questions": 3, "conversation_id": 9},
                    {"title": "대화 10", "questions": 3, "conversation_id": 10},
                    {"title": "대화 11", "questions": 3, "conversation_id": 11},
                    {"title": "대화 12", "questions": 3, "conversation_id": 12},
                    {"title": "대화 13", "questions": 3, "conversation_id": 13}
                ]
            },
            "Part 4": {
                "title": "Part 4 - 담화 (Talks)",
                "question_count": 30,
                "talk_count": 10,
                "time_per_talk": 210,  # 3.5분 (담화 + 문제 3개)
                "total_time": 2100,  # 35분
                "description": "10개 담화, 각 담화당 3개 문제",
                "scenes": [
                    {"title": "담화 1", "questions": 3, "talk_id": 1},
                    {"title": "담화 2", "questions": 3, "talk_id": 2},
                    {"title": "담화 3", "questions": 3, "talk_id": 3},
                    {"title": "담화 4", "questions": 3, "talk_id": 4},
                    {"title": "담화 5", "questions": 3, "talk_id": 5},
                    {"title": "담화 6", "questions": 3, "talk_id": 6},
                    {"title": "담화 7", "questions": 3, "talk_id": 7},
                    {"title": "담화 8", "questions": 3, "talk_id": 8},
                    {"title": "담화 9", "questions": 3, "talk_id": 9},
                    {"title": "담화 10", "questions": 3, "talk_id": 10}
                ]
            }
        }
    
    def get_part_info(self, part_name):
        """특정 파트 정보 반환"""
        return self.structure.get(part_name)
    
    def get_total_time(self):
        """전체 시험 시간 계산"""
        total = sum(part["total_time"] for part in self.structure.values())
        return total  # 초 단위
    
    def get_time_boundaries(self, total_duration_seconds):
        """실제 오디오 길이 기반으로 파트별 시간 경계 계산"""
        total_expected = self.get_total_time()
        ratio = total_duration_seconds / total_expected
        
        boundaries = {}
        current_time = 0
        
        for part_name, part_info in self.structure.items():
            part_duration = part_info["total_time"] * ratio
            boundaries[part_name] = {
                "start": current_time,
                "end": current_time + part_duration,
                "duration": part_duration
            }
            current_time += part_duration
        
        return boundaries
    
    def apply_template_to_sentences(self, sentences, total_audio_duration):
        """문장들을 토익 템플릿에 맞게 분할"""
        time_boundaries = self.get_time_boundaries(total_audio_duration)
        
        result = {}
        
        for part_name, part_info in self.structure.items():
            boundary = time_boundaries[part_name]
            
            # 시간 범위에 해당하는 문장들 찾기
            part_sentences = []
            for sentence in sentences:
                if (sentence['start_time'] >= boundary['start'] and 
                    sentence['end_time'] <= boundary['end']):
                    part_sentences.append(sentence)
            
            # 씬별로 문장 분할
            scenes = []
            sentences_per_scene = len(part_sentences) // len(part_info['scenes'])
            
            for i, scene_info in enumerate(part_info['scenes']):
                start_idx = i * sentences_per_scene
                end_idx = start_idx + sentences_per_scene
                
                # 마지막 씬은 남은 모든 문장 포함
                if i == len(part_info['scenes']) - 1:
                    end_idx = len(part_sentences)
                
                scene_sentences = part_sentences[start_idx:end_idx]
                
                if scene_sentences:
                    scenes.append({
                        "title": scene_info["title"],
                        "sentences": scene_sentences,
                        "start_time": scene_sentences[0]['start_time'],
                        "end_time": scene_sentences[-1]['end_time'],
                        "sentence_count": len(scene_sentences)
                    })
            
            result[part_name] = {
                "info": part_info,
                "boundary": boundary,
                "scenes": scenes,
                "total_sentences": len(part_sentences)
            }
        
        return result
    
    def print_template_info(self):
        """템플릿 정보 출력"""
        print("=== 토익 LC 구조 템플릿 ===")
        print(f"전체 예상 시간: {self.get_total_time()//60}분 {self.get_total_time()%60}초")
        print()
        
        for part_name, part_info in self.structure.items():
            print(f"📝 {part_info['title']}")
            print(f"   문제 수: {part_info['question_count']}문제")
            print(f"   예상 시간: {part_info['total_time']//60}분 {part_info['total_time']%60}초")
            print(f"   설명: {part_info['description']}")
            print(f"   씬 구성: {len(part_info['scenes'])}개 씬")
            for scene in part_info['scenes']:
                print(f"     - {scene['title']}")
            print()

def apply_toeic_template_to_media(media_id):
    """미디어에 토익 템플릿 적용"""
    import sqlite3
    
    template = TOEICTemplate()
    
    # 데이터 로드
    conn = sqlite3.connect('dev.db')
    cursor = conn.cursor()
    
    # 미디어 정보
    cursor.execute('SELECT duration FROM Media WHERE id = ?', (media_id,))
    duration_result = cursor.fetchone()
    total_duration = duration_result[0] if duration_result else 2735  # 기본값
    
    # 문장들 로드
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
    
    print(f"총 문장 수: {len(sentences)}개, 오디오 길이: {total_duration//60}분 {total_duration%60:.0f}초")
    
    # 템플릿 적용
    structured_data = template.apply_template_to_sentences(sentences, total_duration)
    
    # 기존 데이터 삭제
    cursor.execute("DELETE FROM Sentence WHERE sceneId IN (SELECT id FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?))", (media_id,))
    cursor.execute("DELETE FROM Scene WHERE chapterId IN (SELECT id FROM Chapter WHERE mediaId = ?)", (media_id,))
    cursor.execute("DELETE FROM Chapter WHERE mediaId = ?", (media_id,))
    
    # 새 구조 생성
    for part_order, (part_name, part_data) in enumerate(structured_data.items()):
        if not part_data['scenes']:
            continue
            
        # 챕터 생성
        boundary = part_data['boundary']
        cursor.execute(
            "INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
            (media_id, part_data['info']['title'], boundary['start'], boundary['end'], part_order + 1)
        )
        chapter_id = cursor.lastrowid
        
        # 씬들 생성
        for scene_order, scene_data in enumerate(part_data['scenes']):
            cursor.execute(
                "INSERT INTO Scene (chapterId, title, startTime, endTime, `order`) VALUES (?, ?, ?, ?, ?)",
                (chapter_id, scene_data['title'], scene_data['start_time'], scene_data['end_time'], scene_order + 1)
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
    
    # 결과 출력
    print("\n=== 토익 템플릿 적용 결과 ===")
    for part_name, part_data in structured_data.items():
        boundary = part_data['boundary']
        print(f"{part_data['info']['title']}")
        print(f"  시간: {boundary['start']//60:.0f}:{boundary['start']%60:02.0f} - {boundary['end']//60:.0f}:{boundary['end']%60:02.0f}")
        print(f"  문장: {part_data['total_sentences']}개")
        print(f"  씬: {len(part_data['scenes'])}개")
        for scene in part_data['scenes']:
            print(f"    - {scene['title']}: {scene['sentence_count']}개 문장")
        print()

if __name__ == "__main__":
    template = TOEICTemplate()
    template.print_template_info()
    print("\n" + "="*50)
    apply_toeic_template_to_media(9)