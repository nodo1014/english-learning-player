# FFmpeg 폰트 설정 종합 문서

## 개요

영어 학습 플레이어의 MP4 생성 기능에서 사용되는 FFmpeg 폰트 설정에 대한 종합 문서입니다. 현재 시스템은 **두 가지 다른 방식**으로 폰트를 적용합니다.

## 폰트 파일 위치

### 물리적 파일 경로
```
/home/kang/dev/english/fonts/
├── NotoSansKR-Bold.otf
└── (기타 폰트 파일들)
```

### FFmpeg에서 사용하는 상대 경로
```bash
fontsdir=fonts
```

## MP4 생성 방식별 폰트 설정

### 1. 개별 문장 MP4 추출 (SRT 방식)

**파일 위치**: `/home/kang/dev/english/app.py:406-536`  
**함수**: `extract_mp4(media_id, sentence_id)`  
**API 엔드포인트**: `/api/sentence/<media_id>/<int:sentence_id>/extract-mp4`

#### SRT + force_style 방식

**비디오 파일용 FFmpeg 명령어**:
```bash
-vf "subtitles={srt_path}:fontsdir=fonts:force_style='FontName=\"Noto Sans KR\",FontSize=38,PrimaryColour=&Hffffff,Bold=1,Alignment=2,MarginV=50'"
```

**오디오 파일용 FFmpeg 명령어**:
```bash
-filter_complex "[0:v]subtitles={srt_path}:fontsdir=fonts:force_style='FontName=\"Noto Sans KR\",FontSize=38,PrimaryColour=&Hffffff,Bold=1,Alignment=2,MarginV=50'[v]"
```

#### 폰트 설정 상세
- **FontName**: "Noto Sans KR"
- **FontSize**: 38 (상대 크기, 영상 해상도 기준)
- **PrimaryColour**: &Hffffff (흰색, BGR 형식)
- **Bold**: 1 (볼드체 활성화)
- **Alignment**: 2 (하단 중앙 정렬)
- **MarginV**: 50 (하단에서 50픽셀 마진)

#### 텍스트 처리
```python
# Python으로 줄바꿈 처리
wrapped_text = wrap_text(sentence['english'], max_chars_per_line=40)

# SRT 파일 생성
with open(srt_path, 'w', encoding='utf-8') as f:
    f.write(f"1\n00:00:00,000 --> {duration_formatted}\n{wrapped_text}\n\n")
```

### 2. 전체/북마크 문장 MP4 추출 (ASS 방식)

**파일 위치**: `/home/kang/dev/english/app.py:287-385`  
**함수**: `create_ass_subtitle_file(english_text, korean_text, duration, output_path)`  
**사용하는 함수들**:
- `extract_all_sentences_mp4()` - 전체 문장 추출
- `extract_bookmarked_mp4()` - 북마크 문장 추출
- `extract_all_mp4()` - 전체 미디어 추출

#### ASS 내장 스타일 방식

**FFmpeg 명령어**:
```bash
-vf "subtitles={ass_path}:fontsdir=fonts"
```

**비디오용 filter_complex**:
```bash
-filter_complex "[0:v]subtitles={ass_path}:fontsdir=fonts[v]"
```

#### ASS 파일 구조

**헤더 섹션**:
```ass
[Script Info]
Title: Subtitle
ScriptType: v4.00+
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
```

**영어 스타일**:
```ass
Style: English,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,1,0,0,0,100,100,0,0,1,2,0,2,3,3,60,1
```

**한글 스타일**:
```ass
Style: Korean,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,16,1
```

#### ASS 스타일 설정 상세

**영어 스타일 (English)**:
- **Fontname**: Noto Sans KR
- **Fontsize**: 24 (상대값)
- **Bold**: 1 (볼드체)
- **MarginL/R**: 3 (좌우 마진)
- **MarginV**: 60 (하단에서 60픽셀)

**한글 스타일 (Korean)**:
- **Fontname**: Noto Sans KR
- **Fontsize**: 24 (상대값)
- **Bold**: 0 (일반체)
- **MarginL/R**: 10 (좌우 마진)
- **MarginV**: 16 (하단에서 16픽셀)

#### 자동 줄바꿈
```ass
WrapStyle: 0  # 스마트 래핑 (줄 길이 균등화)
```

## 방식별 비교표

| 항목 | 개별 문장 (SRT) | 전체/북마크 (ASS) |
|------|-----------------|-------------------|
| **파일 형식** | SRT | ASS |
| **폰트 적용** | FFmpeg force_style | ASS 내장 스타일 |
| **폰트 크기** | 38 (1080 기준 상대값) | 24 (기본 PlayRes 기준) |
| **실제 표시 크기** | ~38-40픽셀 | ~90픽셀 (3.75배 확대) |
| **PlayRes 설정** | 영상 해상도 직접 사용 | 설정 없음 (기본값 사용) |
| **볼드체** | 영어만 볼드 | 영어 볼드, 한글 일반 |
| **마진 설정** | MarginV=50 | 영어=60, 한글=16 |
| **줄바꿈 처리** | Python wrap_text() | ASS WrapStyle=0 |
| **다중 언어** | 불가능 | 영어/한글 별도 스타일 |
| **텍스트 제한** | 12줄 (Python 처리) | 무제한 (ASS 처리) |

## 중요: 폰트 크기 단위 해석

### SRT와 ASS 모두 상대 크기 사용

**핵심 사실**: SRT 자막도 ASS와 동일하게 **상대 크기**를 사용합니다.

#### SRT 자막의 크기 처리 과정
1. **SRT 파일 자체**: 폰트 크기 정보 없음 (시간 + 텍스트만)
2. **FFmpeg 내부 변환**: SRT → ASS 자동 변환
3. **기본 스타일 적용**: 설정 없으면 FontSize=20 기준
4. **force_style 적용**: `FontSize=38`은 상대값으로 처리
5. **최종 렌더링**: 영상 해상도(1920x1080) 기준으로 스케일링

#### 실제 크기 계산의 핵심: PlayRes 설정

**SRT와 ASS의 근본적 차이점 발견!**

##### SRT 처리 방식
- FFmpeg가 영상 해상도(1920x1080)를 직접 기준으로 사용
- `FontSize=38` = 1080 기준 상대값으로 처리

##### ASS 처리 방식 (현재 구현)
- **PlayResX/PlayResY 설정 없음** (이것이 핵심!)
- libass가 **기본 해상도**(보통 PlayResY=288 등)를 사용
- FontSize=24가 작은 기준 해상도에서 계산됨
- 1920x1080으로 렌더링시 **대폭 확대**됨

##### 실제 스케일링 계산
```
기본 PlayResY ≈ 288 (libass 기본값)
실제 영상 해상도 = 1080

스케일링 비율 = 1080 ÷ 288 ≈ 3.75배
따라서 ASS FontSize=24 ≈ 24 × 3.75 = 90픽셀 상당!
```

#### 이것이 ASS 24가 SRT 38보다 크게 보이는 이유!

**현재 상황**:
- ASS FontSize=24 → 약 90픽셀 상당 (기본 PlayRes에서 확대)
- SRT FontSize=38 → 약 38-40픽셀 상당 (1080 직접 기준)

**결과**: ASS가 SRT보다 2배 이상 크게 표시됨

### drawtext 필터와의 차이점
```bash
# 절대 픽셀 크기 (drawtext)
-vf "drawtext=fontsize=38"  # 정확히 38픽셀

# 상대 크기 (subtitles with SRT/ASS)
-vf "subtitles=file.srt:force_style='FontSize=38'"  # 해상도 기준 상대값
```

## 폰트 디렉토리 설정

### 상대 경로 사용
모든 FFmpeg 명령어에서 `fontsdir=fonts` 사용

### 실제 폰트 파일
- **파일명**: `NotoSansKR-Bold.otf`
- **FFmpeg 참조명**: `"Noto Sans KR"`
- **지원 언어**: 한글, 영어, 기본 라틴 문자

## 색상 및 스타일 공통 설정

### 색상 설정
- **PrimaryColour**: &Hffffff (흰색)
- **OutlineColour**: &H0 (검은색 테두리)
- **BackColour**: &H80000000 (투명한 배경)

### 정렬 설정
- **Alignment**: 2 (하단 중앙 정렬)

### 테두리 설정
- **BorderStyle**: 1 (테두리 활성화)
- **Outline**: 2 (테두리 두께)
- **Shadow**: 0 (그림자 없음)

## 사용 시나리오별 추천

### 개별 문장 추출
- **현재 방식**: SRT + force_style
- **장점**: 간단한 구현, 빠른 처리
- **단점**: 스타일 제한, 다중 언어 불가

### 대량 문장 추출
- **현재 방식**: ASS 내장 스타일
- **장점**: 정밀한 제어, 다중 언어 지원
- **단점**: 복잡한 구현

## 개선 방안

### 1. PlayRes 설정으로 ASS 폰트 크기 정규화

**현재 문제**: ASS FontSize=24가 SRT FontSize=38보다 2배 이상 크게 표시됨

**해결 방법**: ASS 헤더에 PlayRes 명시적 설정
```ass
[Script Info]
Title: Subtitle
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
```

**효과**: 
- ASS FontSize=24 ≈ 실제 24픽셀에 근접
- SRT와 ASS 크기 일관성 확보

### 2. 폰트 크기 표준화 옵션

#### 옵션 A: PlayRes 설정 + ASS 크기 조정
- ASS에 PlayResX=1920, PlayResY=1080 추가
- ASS FontSize를 38로 조정하여 SRT와 동일하게

#### 옵션 B: 현재 스케일링 활용
- PlayRes 설정 없이 현재 상태 유지
- ASS FontSize를 10-12로 줄여서 실제 크기 맞춤

### 3. 마진 설정 통일
현재 개별 문장(50px)과 전체 문장(60px/16px)의 마진이 다름

## 문제 해결 가이드

### 폰트가 적용되지 않는 경우
1. `/home/kang/dev/english/fonts/` 디렉토리 확인
2. `NotoSansKR-Bold.otf` 파일 존재 확인
3. FFmpeg fontsdir 경로 확인

### 한글이 깨지는 경우
1. UTF-8 인코딩 확인
2. Noto Sans KR 폰트 지원 언어 확인
3. ASS 파일의 인코딩 설정 확인

### 폰트 크기가 이상한 경우

#### ASS 폰트가 예상보다 큰 경우
1. **PlayRes 설정 확인**: Script Info에 PlayResX/Y 있는지 확인
2. **기본 해상도 스케일링**: 설정 없으면 288→1080 확대 (3.75배)
3. **해결책**: PlayResX=1920, PlayResY=1080 추가

#### SRT 폰트가 예상과 다른 경우
1. **영상 해상도 기준**: 1920x1080을 직접 기준으로 사용
2. **force_style 확인**: FontSize 파라미터 정확한지 확인
3. **drawtext와 혼동 주의**: drawtext는 절대 픽셀

#### 크기 일관성 문제
- **근본 원인**: SRT(1080 기준) vs ASS(기본 PlayRes 기준)
- **해결책**: ASS에 PlayRes 설정 또는 FontSize 비율 조정

## 버전 히스토리

### 현재 버전
- **개별 문장**: SRT + force_style (FontSize=38)
- **전체/북마크**: ASS 내장 스타일 (FontSize=24)
- **폰트**: Noto Sans KR
- **해상도**: 1920x1080 고정

### 이전 문제점들
1. **텍스트 잘림**: Python wrap_text 4줄 제한 → 12줄 → ASS 자동 처리
2. **폰트 크기 불일치**: 다양한 크기 시도 → 현재 24/38 표준화
3. **이중 줄바꿈**: Python + ASS 동시 처리 → ASS만 사용
4. **스타일 불일치**: SRT force_style 문제 → ASS 안정성

### 최신 발견 (PlayRes 문제)
5. **ASS 폰트 크기 예상 외 확대**: PlayResX/Y 설정 없음으로 인한 스케일링
   - 원인: 기본 PlayRes(~288) → 1080 확대 (3.75배)
   - 결과: ASS FontSize=24가 SRT FontSize=38보다 2배 이상 크게 표시
   - 해결책: PlayRes 명시적 설정 또는 FontSize 비율 조정

## 결론

이 문서는 현재 구현된 FFmpeg 폰트 설정을 정확히 반영하며, **PlayRes 스케일링 문제**라는 근본 원인을 발견함으로써 모든 폰트 크기 불일치 현상을 설명합니다. 향후 개선 작업의 기준점으로 활용됩니다.