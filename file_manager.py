"""
File management utilities for uploads, downloads, and path handling
"""
import os
import uuid
import shutil
import logging
from pathlib import Path
from typing import Optional, Tuple, List
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage

logger = logging.getLogger(__name__)

class FileManager:
    """Centralized file operations manager"""
    
    def __init__(self, upload_folder: str = 'upload', output_folder: str = 'output'):
        self.upload_folder = Path(upload_folder)
        self.output_folder = Path(output_folder)
        self.allowed_extensions = {
            'mp3', 'wav', 'mp4', 'm4a', 'ogg', 'avi', 'mov', 'mkv', 'webm', 'flv'
        }
        
        # Ensure directories exist
        self.upload_folder.mkdir(exist_ok=True)
        self.output_folder.mkdir(exist_ok=True)
    
    def is_allowed_file(self, filename: str) -> bool:
        """Check if file extension is allowed"""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in self.allowed_extensions
    
    def is_video_file(self, filename: str) -> bool:
        """Check if file is a video file"""
        if not self.is_allowed_file(filename):
            return False
        
        video_extensions = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv'}
        extension = filename.rsplit('.', 1)[1].lower()
        return extension in video_extensions
    
    def generate_unique_filename(self, original_filename: str) -> Tuple[str, str]:
        """Generate unique filename and media ID"""
        media_id = str(uuid.uuid4())
        extension = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
        filename = f"{media_id}.{extension}" if extension else media_id
        return filename, media_id
    
    def save_uploaded_file(self, file: FileStorage) -> Tuple[str, str, dict]:
        """Save uploaded file and return file info"""
        if not file or not file.filename:
            raise ValueError("No file provided")
        
        if not self.is_allowed_file(file.filename):
            raise ValueError(f"File type not allowed: {file.filename}")
        
        # Generate unique filename
        filename, media_id = self.generate_unique_filename(file.filename)
        file_path = self.upload_folder / filename
        
        # Save file
        file.save(str(file_path))
        
        # Get file info
        file_info = {
            'id': media_id,
            'filename': filename,
            'original_filename': file.filename,
            'file_size': file_path.stat().st_size,
            'file_type': 'video' if self.is_video_file(file.filename) else 'audio',
            'file_path': str(file_path)
        }
        
        logger.info(f"File uploaded: {filename} ({file_info['file_size']} bytes)")
        return filename, media_id, file_info
    
    def get_media_path(self, filename: str) -> Optional[str]:
        """Get full path to media file"""
        file_path = self.upload_folder / filename
        return str(file_path) if file_path.exists() else None
    
    def delete_media_file(self, filename: str) -> bool:
        """Delete media file"""
        try:
            file_path = self.upload_folder / filename
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Media file deleted: {filename}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting media file {filename}: {e}")
            return False
    
    def create_output_directory(self, media_id: str, media_filename: str) -> str:
        """Create and return output directory for media"""
        # Clean media name for directory
        media_name = self.get_clean_media_name(media_filename)
        dir_name = f"{media_id}_{media_name}"
        
        output_dir = self.output_folder / dir_name
        output_dir.mkdir(exist_ok=True)
        
        return str(output_dir)
    
    def create_extraction_directory(self, base_dir: str, extraction_type: str, 
                                  subtitle_options: Optional[dict] = None) -> str:
        """Create directory for specific extraction type"""
        if subtitle_options:
            suffix = self._get_subtitle_suffix(subtitle_options)
            dir_name = f"{extraction_type}_{suffix}" if suffix else extraction_type
        else:
            dir_name = extraction_type
        
        extraction_dir = Path(base_dir) / dir_name
        extraction_dir.mkdir(exist_ok=True)
        
        return str(extraction_dir)
    
    def _get_subtitle_suffix(self, subtitle_options: dict) -> str:
        """Generate suffix based on subtitle options"""
        english = subtitle_options.get('english', False)
        korean = subtitle_options.get('korean', False)
        
        if english and korean:
            return 'engkor'
        elif english:
            return 'eng'
        elif korean:
            return 'kor'
        else:
            return 'nosub'
    
    @staticmethod
    def get_clean_media_name(filename: str) -> str:
        """Extract clean media name from filename"""
        if not filename:
            return "unknown"
        
        # Remove extension
        name = filename.rsplit('.', 1)[0] if '.' in filename else filename
        
        # Clean up the name
        name = secure_filename(name)
        
        # Remove common unwanted patterns
        unwanted_patterns = ['1080p', '720p', 'BluRay', 'x264', 'YIFY', 'WEB-DL', 'HDRip']
        for pattern in unwanted_patterns:
            name = name.replace(pattern, '')
        
        # Clean up extra dots and spaces
        name = name.replace('.', ' ').replace('_', ' ')
        name = ' '.join(name.split())  # Remove extra spaces
        
        return name or "unknown"
    
    def list_output_files(self, media_id: str) -> List[dict]:
        """List all output files for a media"""
        media_pattern = f"{media_id}_*"
        output_files = []
        
        for dir_path in self.output_folder.glob(media_pattern):
            if dir_path.is_dir():
                for file_path in dir_path.rglob('*'):
                    if file_path.is_file():
                        relative_path = file_path.relative_to(self.output_folder)
                        output_files.append({
                            'filename': file_path.name,
                            'path': str(relative_path),
                            'size': file_path.stat().st_size,
                            'type': self._get_file_type(file_path.suffix)
                        })
        
        return output_files
    
    def _get_file_type(self, extension: str) -> str:
        """Determine file type from extension"""
        ext = extension.lower().lstrip('.')
        
        if ext in {'mp3', 'wav', 'm4a', 'ogg'}:
            return 'audio'
        elif ext in {'mp4', 'avi', 'mov', 'mkv', 'webm'}:
            return 'video'
        elif ext in {'srt', 'ass'}:
            return 'subtitle'
        elif ext in {'txt', 'json'}:
            return 'text'
        else:
            return 'other'
    
    def delete_media_file(self, filename: str) -> bool:
        """Delete a media file from upload folder"""
        try:
            file_path = self.upload_folder / filename
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted media file: {filename}")
                return True
            else:
                logger.warning(f"Media file not found: {filename}")
                return False
        except Exception as e:
            logger.error(f"Error deleting media file {filename}: {e}")
            return False
    
    def cleanup_media_outputs(self, media_id: str) -> bool:
        """Remove all output files for a media"""
        try:
            media_pattern = f"{media_id}_*"
            removed_count = 0
            
            for dir_path in self.output_folder.glob(media_pattern):
                if dir_path.is_dir():
                    shutil.rmtree(dir_path)
                    removed_count += 1
                    logger.info(f"Removed output directory: {dir_path}")
            
            return removed_count > 0
            
        except Exception as e:
            logger.error(f"Error cleaning up outputs for media {media_id}: {e}")
            return False
    
    def get_download_path(self, filename: str) -> Optional[str]:
        """Get path for downloadable file"""
        # Search in output directories
        for file_path in self.output_folder.rglob(filename):
            if file_path.is_file():
                return str(file_path)
        
        # Search in upload directory
        upload_path = self.upload_folder / filename
        if upload_path.exists():
            return str(upload_path)
        
        return None
    
    def ensure_directory(self, directory: str) -> str:
        """Ensure directory exists and return path"""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        return str(dir_path)

# Singleton instance
file_manager = FileManager()