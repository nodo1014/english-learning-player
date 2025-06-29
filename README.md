# English Learning Player

영어 학습을 위한 미디어 플레이어 웹 애플리케이션입니다.

## 주요 기능

- 🎵 오디오/비디오 파일 업로드 및 관리
- 🎬 자동 자막 생성 (Whisper AI)
- 📝 SRT 자막 파일 업로드
- 🔖 북마크 기능
- 🎯 구간별 반복 재생
- 📤 MP3/MP4 추출 (개별, 씬별, 북마크, 전체)
- 🌐 자동 번역 (Google Translate)
- 📂 챕터/씬 자동 구성

## 설치 방법

### 1. 필수 요구사항

- Python 3.8+
- FFmpeg
- Redis (Celery용)

### 2. 설치

```bash
# 저장소 클론
git clone https://github.com/yourusername/english-learning-player.git
cd english-learning-player

# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 폰트 설정
mkdir fonts
# Noto Sans KR 폰트를 fonts 디렉토리에 복사

# 데이터베이스 초기화
python app.py  # 첫 실행 시 자동 생성
```

### 3. 실행

```bash
# Flask 서버 실행
python app.py

# 브라우저에서 http://localhost:8000 접속
```

## 사용 방법

1. **파일 업로드**: MP3, MP4 등 미디어 파일 업로드
2. **자막 생성**: Whisper AI로 자동 생성 또는 SRT 파일 업로드
3. **학습**: 구간 반복, 북마크, 번역 기능 활용
4. **추출**: 필요한 구간만 MP3/MP4로 추출

## 기술 스택

- Backend: Flask, SQLite, Celery
- Frontend: Vanilla JavaScript, HTML5, CSS3
- AI: OpenAI Whisper, Google Translate
- Media: FFmpeg

## 라이선스

MIT License