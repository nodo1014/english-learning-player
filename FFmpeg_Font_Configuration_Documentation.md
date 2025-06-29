# FFmpeg 한글/영어 폰트 설정 로직 상세 문서

## 개요
이 문서는 영어 학습 플레이어에서 MP4 생성 시 사용되는 FFmpeg의 한글/영어 폰트 설정 로직을 상세히 설명합니다. 
복잡한 개발 과정을 거쳐 완성된 시스템으로, ASS(Advanced SubStation Alpha) 형식을 활용하여 영어와 한글에 각각 다른 스타일을 적용합니다.

## 시스템 아키텍처

### 1. 자막 형식 선택: ASS vs SRT
- **SRT (SubRip Text)**: 기본적인 자막 형식, 폰트 스타일 제한적
- **ASS (Advanced SubStation Alpha)**: 고급 자막 형식, 정교한 스타일링 가능

**선택 이유: ASS 형식 채택**
- SRT: FFmpeg 기본 스타일만 적용, 예쁘지 않은 폰트
- ASS: 폰트 크기, 색상, 위치, 볼드체 등 세밀한 제어 가능

### 2. SRT vs ASS 상세 비교

#### SRT 형식의 한계점

**1. 기본 SRT 파일 구조**:
```srt
1
00:00:00,000 --> 00:00:05,000
Hello world this is a test
```

**2. FFmpeg에서 SRT 사용시**:
```python
# 이전 방식 (현재 사용 안함)
def create_srt_subtitle_file(text, duration, output_path):
    wrapped_text = wrap_text(text, max_chars_per_line=40)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"1\n00:00:00,000 --> {duration}\n{wrapped_text}\n\n")
```

**3. FFmpeg 명령어에서의 차이**:
```bash
# SRT 사용시 (이전)
-vf "subtitles=temp_file.srt:fontsdir=fonts:force_style='FontName=\"Noto Sans KR\",FontSize=38,PrimaryColour=&Hffffff,Bold=1,Alignment=2,MarginV=50'"

# ASS 사용시 (현재)
-vf "subtitles=temp_file.ass:fontsdir=fonts"
```

#### SRT vs ASS 기술적 차이점

| 항목 | SRT | ASS |
|------|-----|-----|
| **폰트 제어** | force_style로만 가능, 제한적 | 완전한 스타일 제어 |
| **폰트 크기 단위** | 픽셀 절대값 | 상대값 (해상도 기준) |
| **다중 스타일** | 불가능 (전체 동일) | 가능 (영어/한글 별도) |
| **정확한 위치** | 제한적 | 픽셀 단위 정밀 제어 |
| **줄바꿈 제어** | 수동만 가능 | WrapStyle로 자동 제어 |
| **볼드/이탤릭** | force_style로만 | 스타일별 개별 설정 |
| **색상 제어** | 제한적 | RGB+투명도 완전 제어 |
| **테두리/그림자** | 불가능 | 완전 제어 |

#### SRT 사용시 발생했던 문제점들

**1. 폰트 스타일 적용 방식**:
```python
# SRT에서 영어만 선택시 (이전 방식)
elif subtitle_english:
    srt_filename = f'temp_all_{uuid.uuid4().hex}.srt'
    subtitle_path = os.path.join(all_dir, srt_filename)
    create_srt_subtitle_file(sentence['english'], duration, subtitle_path)
```

**FFmpeg 명령어**:
```bash
# SRT는 force_style로 모든 스타일을 명령어에 포함해야 함
-vf "subtitles=temp.srt:fontsdir=fonts:force_style='FontName=\"Noto Sans KR\",FontSize=38,PrimaryColour=&Hffffff,Bold=1,Alignment=2,MarginV=50'"
```

**문제점**:
- force_style이 적용되지 않는 경우가 많음
- 폰트 크기가 일관되지 않음
- 볼드체가 제대로 적용되지 않음
- 위치 조정이 부정확함

**2. 다중 언어 처리 불가**:
```python
# SRT로는 불가능했던 방식
if subtitle_english and subtitle_korean:
    # SRT는 한 파일에 다른 스타일 적용 불가능
    # 영어와 한글을 다른 크기로 표시할 방법이 없음
```

**3. 텍스트 잘림 문제**:
- SRT에서는 텍스트 영역 계산이 부정확
- force_style의 MarginV가 제대로 적용되지 않음
- 긴 텍스트 처리 시 예측 불가능한 동작

#### ASS 도입 후 해결된 문제들

**1. 영어/한글 개별 스타일 적용**:
```python
# ASS에서 가능해진 방식
if english_text and korean_text:
    ass_content += f"Dialogue: 0,{start_time},{end_time},English,,0,0,0,,{english_text}\n"
    ass_content += f"Dialogue: 1,{start_time},{end_time},Korean,,0,0,0,,{korean_text}\n"
```

**2. 정확한 폰트 크기 제어**:
```ass
Style: English,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,1,0,0,0,100,100,0,0,1,2,0,2,3,3,60,1
Style: Korean,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,16,1
```

**3. 자동 줄바꿈 제어**:
```ass
[Script Info]
WrapStyle: 0  # 이제 Python wrap_text() 불필요
```

#### 이전 SRT 구현의 잔재

**현재 코드에 남아있는 SRT 함수** (사용 안함):
```python
def create_srt_subtitle_file(text, duration, output_path):
    """SRT 형식 자막 파일 생성 (단일 언어용)"""
    wrapped_text = wrap_text(text, max_chars_per_line=40)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"1\n00:00:00,000 --> {int(duration//3600):02d}:{int((duration%3600)//60):02d}:{duration%60:06.3f}\n{wrapped_text}\n\n")
    
    return output_path
```

**이 함수가 사용되지 않는 이유**:
- 모든 자막 처리가 ASS로 통일됨
- 더 나은 스타일링과 일관성을 위해

#### 성능 및 호환성 비교

| 측면 | SRT | ASS |
|------|-----|-----|
| **파일 크기** | 작음 | 약간 큰편 (헤더 포함) |
| **처리 속도** | 빠름 | 약간 느림 (복잡한 렌더링) |
| **호환성** | 거의 모든 플레이어 | 대부분 플레이어 (libass 필요) |
| **편집 용이성** | 텍스트만 수정 | 스타일 복잡 |
| **품질** | 기본적 | 전문적 |

#### 개발 과정에서의 시행착오

**1. 초기 시도 - SRT + force_style**:
```bash
# 시도했지만 일관되지 않았던 방식
-vf "subtitles=temp.srt:fontsdir=fonts:force_style='FontName=\"Noto Sans KR\",FontSize=38,Bold=1'"
```
- 결과: 폰트 크기가 예측 불가능
- 결과: 볼드체 적용 불일치
- 결과: 위치 조정 실패

**2. 중간 시도 - 혼합 방식**:
```python
# 영어는 SRT, 한글은 별도 처리 시도
if subtitle_english:
    create_srt_subtitle_file(...)
elif subtitle_korean:
    create_srt_subtitle_file(...)
```
- 결과: 일관성 부족
- 결과: 유지보수 복잡

**3. 최종 해결 - 완전 ASS 전환**:
```python
# 모든 경우에 ASS 사용
create_ass_subtitle_file(english_text, korean_text, duration, subtitle_path)
```
- 결과: 완벽한 일관성
- 결과: 정밀한 제어
- 결과: 예측 가능한 동작

## 핵심 함수 구조

### 1. create_ass_subtitle_file() 함수
```python
def create_ass_subtitle_file(english_text, korean_text, duration, output_path):
    """ASS 형식 자막 파일 생성 (영어와 한글에 다른 스타일 적용, 단일 언어도 지원)"""
```

**위치**: `/home/kang/dev/english/app.py:287`

### 2. wrap_text() 함수 (현재 사용 안함)
**진화 과정**:
1. **초기**: 4줄 제한으로 텍스트 잘림 문제 발생
2. **중간**: 12줄로 확장, 하지만 여전히 잘림
3. **현재**: 제거됨 - ASS 자동 줄바꿈 사용

## ASS 헤더 구조 상세 분석

### 1. Script Info 섹션
```ass
[Script Info]
Title: Subtitle
ScriptType: v4.00+
WrapStyle: 0
```

**WrapStyle 설정**:
- `0`: 스마트 래핑 (줄 길이 균등화) ← 현재 사용
- `1`: 끝-줄 래핑 (가능한 한 많은 텍스트를 한 줄에)
- `2`: 줄바꿈 없음 (수동 \N만 인식)
- `3`: 스마트 래핑 (아래 줄을 더 길게)

### 2. V4+ Styles 섹션
```ass
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
```

## 폰트 스타일 설정 상세

### 1. 영어 스타일
```ass
Style: English,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,1,0,0,0,100,100,0,0,1,2,0,2,3,3,60,1
```

**각 매개변수 분석**:
- **Name**: `English` - 스타일 식별자
- **Fontname**: `Noto Sans KR` - 폰트 패밀리
- **Fontsize**: `24` - 상대 크기 (픽셀 아님!)
- **PrimaryColour**: `&Hffffff` - 흰색 (BGR 형식)
- **SecondaryColour**: `&Hffffff` - 보조 색상
- **OutlineColour**: `&H0` - 검은색 테두리
- **BackColour**: `&H80000000` - 투명한 배경
- **Bold**: `1` - 볼드체 활성화
- **Italic**: `0` - 이탤릭 비활성화
- **Underline**: `0` - 밑줄 비활성화
- **StrikeOut**: `0` - 취소선 비활성화
- **ScaleX**: `100` - 가로 스케일 100%
- **ScaleY**: `100` - 세로 스케일 100%
- **Spacing**: `0` - 문자 간격
- **Angle**: `0` - 회전 각도
- **BorderStyle**: `1` - 테두리 스타일
- **Outline**: `2` - 테두리 두께
- **Shadow**: `0` - 그림자 깊이
- **Alignment**: `2` - 하단 중앙 정렬
- **MarginL**: `3` - 왼쪽 마진 (픽셀)
- **MarginR**: `3` - 오른쪽 마진 (픽셀)
- **MarginV**: `60` - 세로 마진 (하단에서의 거리, 픽셀)
- **Encoding**: `1` - 인코딩 설정

### 2. 한글 스타일
```ass
Style: Korean,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,16,1
```

**영어와의 차이점**:
- **Bold**: `0` - 볼드체 비활성화 (영어는 1)
- **MarginL**: `10` - 왼쪽 마진 (영어는 3)
- **MarginR**: `10` - 오른쪽 마진 (영어는 3)
- **MarginV**: `16` - 세로 마진 (영어는 60)

## 중요한 기술적 발견들

### 1. ASS 폰트 크기의 특성
- **절대값이 아닌 상대값**: PlayResY(해상도 높이)를 기준으로 계산
- **Noto Sans KR의 특이성**: 일반 픽셀 단위와 매우 다르게 렌더링
- **스케일링**: 영상 해상도에 따라 자동 스케일링

### 2. 마진 시스템의 복잡성
- **픽셀 단위**: MarginL, MarginR, MarginV는 실제 픽셀 값
- **Alignment=2의 영향**: 하단 중앙 정렬에서 마진의 역할
- **텍스트 영역 계산**: `화면폭 - MarginL - MarginR = 실제 텍스트 표시 영역`

### 3. 줄바꿈 처리의 진화
**문제점 발견 과정**:
1. **초기 문제**: `wrap_text()` 함수에서 4줄 초과 시 "..." 추가로 텍스트 잘림
2. **중간 해결**: 12줄로 확장했지만 여전히 문제
3. **근본 원인**: Python 수동 줄바꿈과 ASS 자동 줄바꿈의 이중 처리
4. **최종 해결**: `wrap_text()` 제거, ASS WrapStyle 0으로 자동 줄바꿈

## 자막 옵션별 처리 로직

### 1. 영어만 선택 시
```python
elif subtitle_english:
    # 영어만: ASS 형식 (예쁜 폰트 적용)
    ass_filename = f'temp_all_{uuid.uuid4().hex}.ass'
    subtitle_path = os.path.join(all_dir, ass_filename)
    create_ass_subtitle_file(sentence['english'], None, duration, subtitle_path)
```

### 2. 한글만 선택 시
```python
elif subtitle_korean:
    # 한글만: ASS 형식 (예쁜 폰트 적용)
    korean_text = sentence.get('korean', '')
    if korean_text:
        ass_filename = f'temp_all_{uuid.uuid4().hex}.ass'
        subtitle_path = os.path.join(all_dir, ass_filename)
        create_ass_subtitle_file(None, korean_text, duration, subtitle_path)
```

### 3. 영어+한글 선택 시
```python
if subtitle_english and subtitle_korean:
    # 영어 + 한글: ASS 형식 사용 (다른 글꼴 크기)
    english_text = sentence['english']
    korean_text = sentence.get('korean', '')
    if korean_text:
        ass_filename = f'temp_all_{uuid.uuid4().hex}.ass'
        subtitle_path = os.path.join(all_dir, ass_filename)
        create_ass_subtitle_file(english_text, korean_text, duration, subtitle_path)
```

## ASS Dialogue 생성 로직

### 1. 영어+한글 동시 표시
```python
if english_text and korean_text:
    # 영어와 한글을 각각 다른 스타일로 표시
    ass_content += f"Dialogue: 0,{start_time},{end_time},English,,0,0,0,,{english_text}\n"
    ass_content += f"Dialogue: 1,{start_time},{end_time},Korean,,0,0,0,,{korean_text}\n"
```

**레이어 구조**:
- **Layer 0**: 영어 텍스트 (위쪽, MarginV=60)
- **Layer 1**: 한글 텍스트 (아래쪽, MarginV=16)

### 2. 단일 언어 표시
```python
elif english_text:
    ass_content += f"Dialogue: 0,{start_time},{end_time},English,,0,0,0,,{english_text}\n"
elif korean_text:
    ass_content += f"Dialogue: 0,{start_time},{end_time},Korean,,0,0,0,,{korean_text}\n"
```

## FFmpeg 명령어 통합

### 1. 비디오 파일 처리
```python
if subtitle_path:
    # 자막 있는 경우: 원본 영상에 자막 추가
    cmd = [
        'ffmpeg',
        '-ss', str(sentence['startTime']),
        '-i', input_file,
        '-t', str(duration),
        '-vf', f"subtitles={subtitle_path}:fontsdir=fonts",
        '-af', 'volume=3.0',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-y',
        output_file
    ]
```

**핵심 매개변수**:
- `subtitles={subtitle_path}:fontsdir=fonts`: ASS 파일 적용
- `fontsdir=fonts`: 폰트 디렉토리 지정

### 2. 오디오 파일 처리
```python
if subtitle_path:
    # 자막 있는 경우: 검정 배경 비디오 + 자막 + 오디오
    cmd = [
        'ffmpeg',
        '-f', 'lavfi',
        '-i', f'color=black:size=1920x1080:duration={duration}:rate=30',
        '-ss', str(sentence['startTime']),
        '-i', input_file,
        '-t', str(duration),
        '-filter_complex',
        f"[0:v]subtitles={subtitle_path}:fontsdir=fonts[v]",
        '-map', '[v]',
        '-map', '1:a',
        '-af', 'volume=3.0',
        '-c:v', 'libx264',
        '-preset', 'fast', 
        '-crf', '23',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-shortest',
        '-y',
        output_file
    ]
```

## 폴더 구조 및 파일명 규칙

### 1. 자막 옵션별 폴더
```python
if subtitle_english and subtitle_korean:
    folder_suffix = 'all_engkor'    # 또는 'bookmarked_engkor'
    file_suffix = '_engkor'
elif subtitle_english:
    folder_suffix = 'all_eng'       # 또는 'bookmarked_eng'
    file_suffix = '_eng'
elif subtitle_korean:
    folder_suffix = 'all_kor'       # 또는 'bookmarked_kor'
    file_suffix = '_kor'
else:
    folder_suffix = 'all'           # 또는 'bookmarked'
    file_suffix = '_nosub'
```

### 2. 출력 파일명 규칙
- **전체 문장**: `0001_eng.mp4`, `0001_kor.mp4`, `0001_engkor.mp4`, `0001_nosub.mp4`
- **북마크**: `bookmarked_0009_eng.mp4` (실제 문장 순서 번호 사용)

## 임시 파일 관리

### 1. ASS 파일 생성
```python
ass_filename = f'temp_all_{uuid.uuid4().hex}.ass'
subtitle_path = os.path.join(all_dir, ass_filename)
create_ass_subtitle_file(english_text, korean_text, duration, subtitle_path)
```

### 2. 임시 파일 정리
```python
# 임시 자막 파일 삭제
if subtitle_path:
    try:
        os.remove(subtitle_path)
    except:
        pass
```

## 성능 최적화 설정

### 1. FFmpeg 인코딩 설정
- **해상도**: 1920x1080 유지
- **프리셋**: 'fast' (속도 우선)
- **CRF**: 23 (품질/용량 균형)
- **오디오**: AAC, 128k

### 2. 메모리 관리
- **타임아웃**: 120초 (문장별), 900초 (챕터별)
- **UUID 기반 임시파일**: 충돌 방지
- **즉시 정리**: FFmpeg 완료 후 임시파일 삭제

## 트러블슈팅 가이드

### 1. 자막이 잘리는 경우
- `wrap_text()` 함수 제거 확인
- `WrapStyle: 0` 설정 확인
- MarginL, MarginR 값 조정

### 2. 폰트 크기가 이상한 경우
- ASS 폰트 크기는 상대값임을 확인
- Noto Sans KR 특성 고려
- 해상도별 테스트 필요

### 3. 마진이 적용되지 않는 경우
- Alignment=2 설정 확인
- 픽셀 단위 vs 상대값 구분
- PlayResX, PlayResY 명시적 설정 고려

## 향후 개선 가능 사항

### 1. PlayRes 명시적 설정
```ass
[Script Info]
Title: Subtitle
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
```

### 2. 더 넓은 마진 적용
- 현재: MarginL=3, MarginR=3 (매우 좁음)
- 권장: MarginL=50, MarginR=50 (안전 영역 확보)

### 3. 폰트 대체 설정
- Noto Sans KR 없을 경우 대체 폰트 지정
- 시스템별 폰트 호환성 향상

## 결론

이 시스템은 다음과 같은 복잡한 과정을 거쳐 완성되었습니다:

1. **SRT → ASS 전환**: 더 나은 스타일링을 위해
2. **이중 줄바꿈 문제 해결**: Python 수동 줄바꿈 제거
3. **폰트 크기 조정**: ASS 상대값 특성 이해
4. **마진 시스템 구축**: 픽셀 단위 정밀 제어
5. **자막 옵션 다양화**: 영어, 한글, 혼합, 무자막 지원

현재 설정은 1920x1080 해상도에서 최적화되어 있으며, 영어와 한글에 각각 다른 스타일을 적용하여 가독성을 극대화합니다.