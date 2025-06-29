from pydub import AudioSegment
from pydub.silence import detect_silence
import re

def apply_time_filters(sentences, min_duration=1.0, max_duration=15.0):
    """시간 기반 필터 적용"""
    filtered = []
    
    for sentence in sentences:
        duration = sentence['end_time'] - sentence['start_time']
        
        # 너무 짧은 문장 제거
        if duration < min_duration:
            print(f"제거됨 (너무 짧음): {sentence['english'][:30]}... ({duration:.1f}s)")
            continue
            
        # 너무 긴 문장 분할
        if duration > max_duration:
            # 긴 문장을 2개로 분할
            mid_time = sentence['start_time'] + duration / 2
            
            # 첫 번째 반쪽
            filtered.append({
                **sentence,
                'end_time': mid_time,
                'english': sentence['english'] + ' (1/2)',
                'order': sentence['order']
            })
            
            # 두 번째 반쪽  
            filtered.append({
                **sentence,
                'start_time': mid_time,
                'english': sentence['english'] + ' (2/2)',
                'order': sentence['order'] + 0.1
            })
            
            print(f"분할됨 (너무 김): {sentence['english'][:30]}... ({duration:.1f}s)")
        else:
            filtered.append(sentence)
    
    return filtered

def apply_content_filters(sentences, min_words=2):
    """내용 기반 필터 적용"""
    filtered = []
    noise_patterns = [
        r'\b(um|uh|ah|er|mm|hmm)\b',  # 소음
        r'\[.*?\]',  # [음악], [박수] 등
        r'\(.*?\)',  # (웃음), (기침) 등
    ]
    
    for sentence in sentences:
        text = sentence['english'].strip()
        
        # 소음 패턴 제거
        for pattern in noise_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        text = re.sub(r'\s+', ' ', text).strip()  # 공백 정리
        
        # 최소 단어 수 확인
        word_count = len(text.split())
        if word_count < min_words:
            print(f"제거됨 (단어 부족): {sentence['english'][:30]}... ({word_count}단어)")
            continue
            
        # 정리된 텍스트로 업데이트
        filtered.append({
            **sentence,
            'english': text
        })
    
    return filtered

def detect_natural_breaks(sentences, audio_file, silence_thresh=-40, min_silence_len=2000):
    """자연스러운 브레이크 포인트 감지"""
    try:
        audio = AudioSegment.from_file(audio_file)
        
        # 무음 구간 감지
        silence_ranges = detect_silence(
            audio, 
            min_silence_len=min_silence_len,  # 2초 이상
            silence_thresh=silence_thresh     # -40dB 이하
        )
        
        break_points = []
        for start_silence, end_silence in silence_ranges:
            mid_point = (start_silence + end_silence) / 2 / 1000.0  # 초 단위
            break_points.append(mid_point)
        
        print(f"감지된 자연스러운 브레이크: {len(break_points)}개")
        return break_points
        
    except Exception as e:
        print(f"브레이크 감지 오류: {e}")
        return []

def group_by_natural_breaks(sentences, break_points, min_gap=3.0):
    """자연스러운 브레이크로 그룹화"""
    if not break_points:
        return [sentences]  # 브레이크가 없으면 전체를 하나의 그룹으로
    
    groups = []
    current_group = []
    
    for sentence in sentences:
        sent_start = sentence['start_time']
        sent_end = sentence['end_time']
        
        # 이 문장 뒤에 브레이크가 있는지 확인
        has_break_after = any(
            bp >= sent_end and bp <= sent_end + min_gap 
            for bp in break_points
        )
        
        current_group.append(sentence)
        
        # 브레이크가 있으면 그룹 종료
        if has_break_after and len(current_group) >= 3:  # 최소 3문장
            groups.append(current_group)
            current_group = []
    
    # 마지막 그룹 추가
    if current_group:
        if len(current_group) >= 3:
            groups.append(current_group)
        elif groups:  # 마지막 그룹이 작으면 이전 그룹에 합치기
            groups[-1].extend(current_group)
        else:
            groups.append(current_group)
    
    print(f"자연스러운 브레이크로 {len(groups)}개 그룹 생성")
    return groups

def create_smart_chapters(sentences, audio_file):
    """똑똑한 챕터 생성"""
    print("=== 스마트 챕터 생성 시작 ===")
    
    # 1단계: 필터 적용
    print("1단계: 시간 기반 필터 적용")
    filtered_sentences = apply_time_filters(sentences)
    
    print("2단계: 내용 기반 필터 적용")
    filtered_sentences = apply_content_filters(filtered_sentences)
    
    # 2단계: 자연스러운 브레이크 감지
    print("3단계: 자연스러운 브레이크 감지")
    break_points = detect_natural_breaks(filtered_sentences, audio_file)
    
    # 3단계: 그룹화
    print("4단계: 스마트 그룹화")
    groups = group_by_natural_breaks(filtered_sentences, break_points)
    
    # 4단계: 챕터/씬 구조 생성
    chapters = []
    for i, group in enumerate(groups):
        if not group:
            continue
            
        chapter_start = group[0]['start_time']
        chapter_end = group[-1]['end_time']
        chapter_title = f"Chapter {i+1}"
        
        # 큰 그룹은 씬으로 세분화
        if len(group) > 20:
            # 10문장씩 씬으로 분할
            scenes = []
            for j in range(0, len(group), 10):
                scene_sentences = group[j:j+10]
                scene_start = scene_sentences[0]['start_time']
                scene_end = scene_sentences[-1]['end_time']
                
                scenes.append({
                    'title': f"Scene {j//10 + 1}",
                    'start_time': scene_start,
                    'end_time': scene_end,
                    'sentences': scene_sentences
                })
        else:
            # 작은 그룹은 단일 씬
            scenes = [{
                'title': "Scene 1",
                'start_time': chapter_start,
                'end_time': chapter_end,
                'sentences': group
            }]
        
        chapters.append({
            'title': chapter_title,
            'start_time': chapter_start,
            'end_time': chapter_end,
            'scenes': scenes
        })
    
    print(f"=== 완료: {len(chapters)}개 챕터, 총 {sum(len(ch['scenes']) for ch in chapters)}개 씬 ===")
    return chapters