#!/usr/bin/env python3
"""
YouTube URL에서 자막을 다운로드하고 SRT 파일로 저장
"""

import yt_dlp
import os
import re
from datetime import datetime

def download_subtitles_from_urls(url_file_path, output_dir="subtitles"):
    """
    URL 파일에서 YouTube 자막을 다운로드
    
    Args:
        url_file_path: YouTube URL이 담긴 텍스트 파일 경로
        output_dir: 자막 파일을 저장할 디렉토리
    """
    
    # 출력 디렉토리 생성
    os.makedirs(output_dir, exist_ok=True)
    
    # URL 파일 읽기
    try:
        with open(url_file_path, 'r', encoding='utf-8') as f:
            urls = [url.strip() for url in f.readlines() if url.strip()]
    except FileNotFoundError:
        print(f"❌ 파일을 찾을 수 없습니다: {url_file_path}")
        return
    
    print(f"📥 총 {len(urls)}개의 YouTube URL에서 자막 다운로드를 시작합니다...")
    print(f"📁 저장 위치: {output_dir}/")
    print("-" * 50)
    
    # yt-dlp 설정
    ydl_opts = {
        'writesubtitles': True,          # 자막 다운로드
        'writeautomaticsub': True,       # 자동생성 자막도 다운로드
        'subtitleslangs': ['en', 'ko'],  # 영어, 한국어 자막
        'subtitlesformat': 'srt',        # SRT 형식
        'skip_download': True,           # 비디오는 다운로드하지 않음
        'outtmpl': f'{output_dir}/%(title)s [%(id)s].%(ext)s',  # 출력 파일명 형식
        'ignoreerrors': True,            # 오류 시 계속 진행
    }
    
    success_count = 0
    error_count = 0
    downloaded_files = []
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for i, url in enumerate(urls, 1):
            try:
                print(f"\n[{i}/{len(urls)}] 처리 중: {url}")
                
                # 비디오 정보 가져오기
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown')
                video_id = info.get('id', 'unknown')
                duration = info.get('duration', 0)
                
                # 지속시간을 분:초 형식으로 변환
                duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Unknown"
                
                print(f"  📹 제목: {title}")
                print(f"  🕒 길이: {duration_str}")
                print(f"  🆔 ID: {video_id}")
                
                # 사용 가능한 자막 확인
                subtitles = info.get('subtitles', {})
                automatic_captions = info.get('automatic_captions', {})
                
                available_subs = []
                if 'en' in subtitles:
                    available_subs.append('en (manual)')
                elif 'en' in automatic_captions:
                    available_subs.append('en (auto)')
                    
                if 'ko' in subtitles:
                    available_subs.append('ko (manual)')
                elif 'ko' in automatic_captions:
                    available_subs.append('ko (auto)')
                
                print(f"  🎯 사용 가능한 자막: {', '.join(available_subs) if available_subs else 'None'}")
                
                if not available_subs:
                    print(f"  ⚠️  영어/한국어 자막이 없습니다.")
                    error_count += 1
                    continue
                
                # 자막 다운로드
                ydl.download([url])
                
                # 다운로드된 파일 확인
                safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)  # 파일명에 사용할 수 없는 문자 제거
                
                for lang in ['en', 'ko']:
                    possible_files = [
                        f"{output_dir}/{safe_title} [{video_id}].{lang}.srt",
                        f"{output_dir}/{title} [{video_id}].{lang}.srt"
                    ]
                    
                    for file_path in possible_files:
                        if os.path.exists(file_path):
                            file_size = os.path.getsize(file_path)
                            print(f"  ✅ {lang.upper()} 자막 다운로드 완료: {os.path.basename(file_path)} ({file_size} bytes)")
                            downloaded_files.append(file_path)
                            break
                
                success_count += 1
                
            except Exception as e:
                print(f"  ❌ 오류 발생: {str(e)}")
                error_count += 1
                continue
    
    # 결과 요약
    print("\n" + "=" * 50)
    print(f"📊 다운로드 완료!")
    print(f"✅ 성공: {success_count}개")
    print(f"❌ 실패: {error_count}개")
    print(f"📁 다운로드된 파일: {len(downloaded_files)}개")
    
    if downloaded_files:
        print(f"\n📋 다운로드된 자막 파일:")
        for file_path in downloaded_files:
            print(f"  - {os.path.basename(file_path)}")
    
    return downloaded_files

def process_subtitle_file(srt_file_path):
    """
    SRT 파일을 분석하여 기본 정보 출력
    """
    try:
        with open(srt_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 자막 블록 개수 세기
        blocks = content.strip().split('\n\n')
        subtitle_count = len([block for block in blocks if block.strip()])
        
        # 첫 번째와 마지막 타임스탬프 찾기
        time_pattern = r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})'
        times = re.findall(time_pattern, content)
        
        if times:
            start_time = times[0][0]
            end_time = times[-1][1]
            print(f"  📊 자막 정보: {subtitle_count}개 블록, {start_time} ~ {end_time}")
        
        return subtitle_count
        
    except Exception as e:
        print(f"  ⚠️  파일 분석 오류: {e}")
        return 0

if __name__ == "__main__":
    import sys
    
    # 기본 URL 파일 경로
    url_file = "youtubeurl.txt"
    
    # 명령행 인자로 파일 경로 지정 가능
    if len(sys.argv) > 1:
        url_file = sys.argv[1]
    
    print(f"🎬 YouTube 자막 다운로더")
    print(f"📂 URL 파일: {url_file}")
    print(f"🕒 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    downloaded_files = download_subtitles_from_urls(url_file)
    
    # 다운로드된 파일들 분석
    if downloaded_files:
        print(f"\n🔍 자막 파일 분석:")
        for file_path in downloaded_files:
            print(f"\n📄 {os.path.basename(file_path)}")
            process_subtitle_file(file_path)