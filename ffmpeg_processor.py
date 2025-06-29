"""
FFmpeg processing utilities for audio/video extraction and subtitle handling
"""
import os
import subprocess
import uuid
import logging
from typing import Dict, List, Optional, Tuple, Union
from pathlib import Path

logger = logging.getLogger(__name__)

class FFmpegProcessor:
    """Centralized FFmpeg operations processor"""
    
    def __init__(self, fonts_dir: str = "fonts"):
        self.fonts_dir = fonts_dir
        self.default_timeout = 120  # seconds
        self.chapter_timeout = 900  # seconds for longer operations
    
    def extract_audio_segment(self, input_file: str, output_file: str, 
                            start_time: float, duration: float, 
                            volume: float = 3.0, timeout: int = None) -> bool:
        """Extract audio segment from media file"""
        try:
            cmd = [
                'ffmpeg',
                '-ss', str(start_time),
                '-i', input_file,
                '-t', str(duration),
                '-af', f'volume={volume}',
                '-c:a', 'mp3',
                '-b:a', '128k',
                '-y',
                output_file
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=timeout or self.default_timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Audio segment extracted: {output_file}")
                return True
            else:
                logger.error(f"FFmpeg error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout extracting audio segment")
            return False
        except Exception as e:
            logger.error(f"Error extracting audio segment: {e}")
            return False
    
    def extract_video_segment(self, input_file: str, output_file: str,
                            start_time: float, duration: float,
                            subtitle_file: Optional[str] = None,
                            volume: float = 3.0, timeout: int = None) -> bool:
        """Extract video segment with optional subtitles"""
        try:
            cmd = [
                'ffmpeg',
                '-ss', str(start_time),
                '-i', input_file,
                '-t', str(duration)
            ]
            
            # Add subtitle filter if provided
            if subtitle_file:
                cmd.extend(['-vf', f"subtitles={subtitle_file}:fontsdir={self.fonts_dir}"])
            
            cmd.extend([
                '-af', f'volume={volume}',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-y',
                output_file
            ])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self.default_timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Video segment extracted: {output_file}")
                return True
            else:
                logger.error(f"FFmpeg error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout extracting video segment")
            return False
        except Exception as e:
            logger.error(f"Error extracting video segment: {e}")
            return False
    
    def create_video_from_audio(self, audio_file: str, output_file: str,
                              start_time: float, duration: float,
                              subtitle_file: Optional[str] = None,
                              volume: float = 3.0, timeout: int = None) -> bool:
        """Create video with black background from audio file"""
        try:
            cmd = [
                'ffmpeg',
                '-f', 'lavfi',
                '-i', f'color=black:size=1920x1080:duration={duration}:rate=30',
                '-ss', str(start_time),
                '-i', audio_file,
                '-t', str(duration)
            ]
            
            if subtitle_file:
                cmd.extend([
                    '-filter_complex',
                    f"[0:v]subtitles={subtitle_file}:fontsdir={self.fonts_dir}[v]",
                    '-map', '[v]',
                    '-map', '1:a'
                ])
            else:
                cmd.extend(['-map', '0:v', '-map', '1:a'])
            
            cmd.extend([
                '-af', f'volume={volume}',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-shortest',
                '-y',
                output_file
            ])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self.default_timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Video from audio created: {output_file}")
                return True
            else:
                logger.error(f"FFmpeg error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout creating video from audio")
            return False
        except Exception as e:
            logger.error(f"Error creating video from audio: {e}")
            return False
    
    def extract_audio_from_video(self, video_file: str, audio_file: str) -> bool:
        """Extract audio track from video file"""
        try:
            cmd = [
                'ffmpeg',
                '-i', video_file,
                '-vn',  # No video
                '-acodec', 'mp3',
                '-ab', '128k',
                '-ar', '44100',
                '-y',
                audio_file
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.default_timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Audio extracted from video: {audio_file}")
                return True
            else:
                logger.error(f"FFmpeg error extracting audio: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout extracting audio from video")
            return False
        except Exception as e:
            logger.error(f"Error extracting audio from video: {e}")
            return False
    
    def get_media_duration(self, media_file: str) -> Optional[float]:
        """Get duration of media file"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                media_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                return float(data['format']['duration'])
            else:
                logger.error(f"FFprobe error: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting media duration: {e}")
            return None

class SubtitleProcessor:
    """Handles subtitle file creation and management"""
    
    @staticmethod
    def wrap_text(text: str, max_chars_per_line: int = 40, max_lines: int = 12, for_ass: bool = False) -> str:
        """Wrap text for subtitles"""
        import textwrap
        
        if not text:
            return ""
        
        # Split by existing line breaks first
        paragraphs = text.split('\n')
        wrapped_paragraphs = []
        
        for paragraph in paragraphs:
            if not paragraph.strip():
                wrapped_paragraphs.append('')
                continue
            
            # Wrap each paragraph
            wrapped_lines = textwrap.wrap(
                paragraph, 
                width=max_chars_per_line,
                break_long_words=False,
                break_on_hyphens=False
            )
            wrapped_paragraphs.extend(wrapped_lines)
        
        # Limit total lines
        if len(wrapped_paragraphs) > max_lines:
            wrapped_paragraphs = wrapped_paragraphs[:max_lines]
        
        # Join with appropriate line break character
        line_break = '\\N' if for_ass else '\n'
        return line_break.join(wrapped_paragraphs)
    
    @staticmethod
    def create_ass_subtitle_file(english_text: Optional[str], korean_text: Optional[str], 
                               duration: float, output_path: str) -> str:
        """Create ASS format subtitle file with English and Korean support"""
        
        def seconds_to_ass_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours}:{minutes:02d}:{secs:05.2f}"
        
        # ASS header with updated settings
        ass_content = """[Script Info]
Title: Subtitle
ScriptType: v4.00+
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: English,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,1,0,0,0,100,100,0,0,1,2,0,2,3,3,60,1
Style: Korean,Noto Sans KR,24,&Hffffff,&Hffffff,&H0,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,16,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        start_time = "0:00:00.00"
        end_time = seconds_to_ass_time(duration)
        
        # Add dialogue lines based on available text
        if english_text and korean_text:
            ass_content += f"Dialogue: 0,{start_time},{end_time},English,,0,0,0,,{english_text}\n"
            ass_content += f"Dialogue: 1,{start_time},{end_time},Korean,,0,0,0,,{korean_text}\n"
        elif english_text:
            ass_content += f"Dialogue: 0,{start_time},{end_time},English,,0,0,0,,{english_text}\n"
        elif korean_text:
            ass_content += f"Dialogue: 0,{start_time},{end_time},Korean,,0,0,0,,{korean_text}\n"
        
        # Write file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        return output_path
    
    @staticmethod
    def create_srt_subtitle_file(text: str, duration: float, output_path: str) -> str:
        """Create SRT format subtitle file"""
        wrapped_text = SubtitleProcessor.wrap_text(text, max_chars_per_line=40)
        
        duration_formatted = f"{int(duration//3600):02d}:{int((duration%3600)//60):02d}:{duration%60:06.3f}"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"1\n00:00:00,000 --> {duration_formatted}\n{wrapped_text}\n\n")
        
        return output_path

class MediaExtractor:
    """High-level media extraction operations"""
    
    def __init__(self, ffmpeg_processor: FFmpegProcessor, subtitle_processor: SubtitleProcessor):
        self.ffmpeg = ffmpeg_processor
        self.subtitle = subtitle_processor
    
    def extract_sentence_with_subtitles(self, input_file: str, output_file: str,
                                      sentence_data: Dict, subtitle_options: Dict,
                                      is_video_file: bool = True) -> bool:
        """Extract single sentence with subtitle options"""
        start_time = sentence_data['startTime']
        end_time = sentence_data['endTime'] 
        duration = end_time - start_time
        
        # Create subtitle file if needed
        subtitle_file = None
        if any(subtitle_options.values()):
            subtitle_file = self._create_subtitle_file(sentence_data, duration, subtitle_options)
        
        try:
            # Extract based on file type
            if is_video_file:
                success = self.ffmpeg.extract_video_segment(
                    input_file, output_file, start_time, duration, subtitle_file
                )
            else:
                success = self.ffmpeg.create_video_from_audio(
                    input_file, output_file, start_time, duration, subtitle_file
                )
            
            return success
            
        finally:
            # Clean up subtitle file
            if subtitle_file and os.path.exists(subtitle_file):
                try:
                    os.remove(subtitle_file)
                except Exception as e:
                    logger.warning(f"Failed to remove subtitle file {subtitle_file}: {e}")
    
    def _create_subtitle_file(self, sentence_data: Dict, duration: float, 
                            subtitle_options: Dict) -> Optional[str]:
        """Create appropriate subtitle file based on options"""
        english_text = sentence_data.get('english') if subtitle_options.get('english') else None
        korean_text = sentence_data.get('korean') if subtitle_options.get('korean') else None
        
        if not english_text and not korean_text:
            return None
        
        # Generate unique filename
        subtitle_filename = f'temp_subtitle_{uuid.uuid4().hex}.ass'
        subtitle_path = os.path.join(os.path.dirname(sentence_data.get('output_dir', '.')), subtitle_filename)
        
        return self.subtitle.create_ass_subtitle_file(
            english_text, korean_text, duration, subtitle_path
        )

# Singleton instances
ffmpeg_processor = FFmpegProcessor()
subtitle_processor = SubtitleProcessor()
media_extractor = MediaExtractor(ffmpeg_processor, subtitle_processor)