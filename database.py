"""
Database operations and models for English Learning Player
"""
import sqlite3
import logging
from contextlib import contextmanager
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Centralized database operations manager"""
    
    def __init__(self, db_path: str = 'dev.db'):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            logger.error(f"Database operation failed: {e}")
            raise
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database with required tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Media table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Media (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    originalFilename TEXT,
                    fileSize INTEGER,
                    fileType TEXT,
                    duration REAL,
                    status TEXT DEFAULT 'uploaded',
                    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            ''')
            
            # Chapter table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Chapter (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mediaId TEXT NOT NULL,
                    title TEXT NOT NULL,
                    startTime REAL NOT NULL,
                    endTime REAL NOT NULL,
                    `order` INTEGER NOT NULL,
                    FOREIGN KEY (mediaId) REFERENCES Media (id) ON DELETE CASCADE
                )
            ''')
            
            # Scene table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Scene (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapterId INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    startTime REAL NOT NULL,
                    endTime REAL NOT NULL,
                    `order` INTEGER NOT NULL,
                    FOREIGN KEY (chapterId) REFERENCES Chapter (id) ON DELETE CASCADE
                )
            ''')
            
            # Sentence table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Sentence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sceneId INTEGER NOT NULL,
                    english TEXT NOT NULL,
                    korean TEXT,
                    startTime REAL NOT NULL,
                    endTime REAL NOT NULL,
                    `order` INTEGER NOT NULL,
                    isBookmarked BOOLEAN DEFAULT 0,
                    confidence REAL,
                    detectedVerbs TEXT,
                    FOREIGN KEY (sceneId) REFERENCES Scene (id) ON DELETE CASCADE
                )
            ''')
            
            # Add detectedVerbs column if it doesn't exist (migration)
            try:
                cursor.execute('ALTER TABLE Sentence ADD COLUMN detectedVerbs TEXT')
                conn.commit()
            except Exception:
                # Column already exists or other error - ignore
                pass
            
            conn.commit()
            logger.info("Database initialized successfully")

class MediaRepository:
    """Repository for Media operations"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def get_all(self) -> List[Dict]:
        """Get all media files"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Media ORDER BY createdAt DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_by_id(self, media_id: str) -> Optional[Dict]:
        """Get media by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Media WHERE id = ?", (media_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create(self, media_data: Dict) -> str:
        """Create new media entry"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO Media (id, filename, originalFilename, fileSize, fileType, duration, status, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                media_data['id'], media_data['filename'], media_data.get('originalFilename'),
                media_data.get('fileSize'), media_data.get('fileType'), media_data.get('duration'),
                media_data.get('status', 'uploaded'), media_data.get('metadata')
            ))
            conn.commit()
            return media_data['id']
    
    def update_status(self, media_id: str, status: str) -> bool:
        """Update media status"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Media SET status = ? WHERE id = ?", (status, media_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete(self, media_id: str) -> bool:
        """Delete media and all related data"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Media WHERE id = ?", (media_id,))
            conn.commit()
            return cursor.rowcount > 0

class ChapterRepository:
    """Repository for Chapter operations"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def get_by_media_id(self, media_id: str) -> List[Dict]:
        """Get chapters with scene counts"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.*, 
                       (SELECT COUNT(*) FROM Scene WHERE chapterId = c.id) as scene_count
                FROM Chapter c
                WHERE c.mediaId = ?
                ORDER BY c.`order`
            ''', (media_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_by_id(self, chapter_id: int) -> Optional[Dict]:
        """Get chapter by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Chapter WHERE id = ?", (chapter_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create_batch(self, chapters: List[Dict]) -> List[int]:
        """Create multiple chapters"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            chapter_ids = []
            for chapter in chapters:
                cursor.execute('''
                    INSERT INTO Chapter (mediaId, title, startTime, endTime, `order`)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    chapter['mediaId'], chapter['title'], chapter['startTime'],
                    chapter['endTime'], chapter['order']
                ))
                chapter_ids.append(cursor.lastrowid)
            conn.commit()
            return chapter_ids

class SceneRepository:
    """Repository for Scene operations"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def get_by_chapter_id(self, chapter_id: int) -> List[Dict]:
        """Get scenes with sentence counts"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT sc.*, 
                       (SELECT COUNT(*) FROM Sentence WHERE sceneId = sc.id) as sentence_count
                FROM Scene sc
                WHERE sc.chapterId = ?
                ORDER BY sc.`order`
            ''', (chapter_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_by_id(self, scene_id: int) -> Optional[Dict]:
        """Get scene by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Scene WHERE id = ?", (scene_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create_batch(self, scenes: List[Dict]) -> List[int]:
        """Create multiple scenes"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            scene_ids = []
            for scene in scenes:
                cursor.execute('''
                    INSERT INTO Scene (chapterId, title, startTime, endTime, `order`)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    scene['chapterId'], scene['title'], scene['startTime'],
                    scene['endTime'], scene['order']
                ))
                scene_ids.append(cursor.lastrowid)
            conn.commit()
            return scene_ids

class SentenceRepository:
    """Repository for Sentence operations"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def get_by_media_id(self, media_id: str) -> List[Dict]:
        """Get all sentences for a media"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.*, sc.chapterId, sc.title as sceneTitle, c.title as chapterTitle
                FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                JOIN Chapter c ON sc.chapterId = c.id
                WHERE c.mediaId = ?
                ORDER BY s.`order`
            ''', (media_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_by_id(self, sentence_id: int) -> Optional[Dict]:
        """Get sentence by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Sentence WHERE id = ?", (sentence_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_by_scene_id(self, scene_id: int) -> List[Dict]:
        """Get sentences by scene ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM Sentence 
                WHERE sceneId = ? 
                ORDER BY `order`
            ''', (scene_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_by_chapter_id(self, chapter_id: int) -> List[Dict]:
        """Get sentences by chapter ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.* FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                WHERE sc.chapterId = ? 
                ORDER BY s.`order`
            ''', (chapter_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_bookmarked_by_media_id(self, media_id: str) -> List[Dict]:
        """Get bookmarked sentences for a media"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.*, sc.chapterId, sc.title as sceneTitle, c.title as chapterTitle
                FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                JOIN Chapter c ON sc.chapterId = c.id
                WHERE c.mediaId = ? AND s.isBookmarked = 1
                ORDER BY s.`order`
            ''', (media_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def toggle_bookmark(self, sentence_id: int) -> Dict:
        """Toggle bookmark status"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get current status
            cursor.execute("SELECT isBookmarked FROM Sentence WHERE id = ?", (sentence_id,))
            current = cursor.fetchone()
            if not current:
                raise ValueError(f"Sentence {sentence_id} not found")
            
            new_status = not bool(current[0])
            cursor.execute("UPDATE Sentence SET isBookmarked = ? WHERE id = ?", (new_status, sentence_id))
            conn.commit()
            
            return {'bookmarked': new_status}
    
    def update_translation(self, sentence_id: int, korean_text: str) -> bool:
        """Update Korean translation"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Sentence SET korean = ? WHERE id = ?", (korean_text, sentence_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def update_verbs(self, sentence_id: int, verbs_json: str) -> bool:
        """Update detected verbs"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Sentence SET detectedVerbs = ? WHERE id = ?", (verbs_json, sentence_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_sentences_without_verbs(self, media_id: str) -> List[Dict]:
        """Get sentences that need verb analysis"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.* FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                JOIN Chapter c ON sc.chapterId = c.id
                WHERE c.mediaId = ? AND (s.detectedVerbs IS NULL OR s.detectedVerbs = '')
                ORDER BY s.`order`
            ''', (media_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def create_batch(self, sentences: List[Dict]) -> List[int]:
        """Create multiple sentences"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            sentence_ids = []
            for sentence in sentences:
                cursor.execute('''
                    INSERT INTO Sentence (sceneId, english, korean, startTime, endTime, `order`, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    sentence['sceneId'], sentence['english'], sentence.get('korean'),
                    sentence['startTime'], sentence['endTime'], sentence['order'],
                    sentence.get('confidence')
                ))
                sentence_ids.append(cursor.lastrowid)
            conn.commit()
            return sentence_ids
    
    def delete_by_media_id(self, media_id: str) -> bool:
        """Delete all sentences for a media"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM Sentence 
                WHERE sceneId IN (
                    SELECT sc.id FROM Scene sc
                    JOIN Chapter c ON sc.chapterId = c.id
                    WHERE c.mediaId = ?
                )
            ''', (media_id,))
            conn.commit()
            return cursor.rowcount > 0

# Singleton instances
db_manager = DatabaseManager()
media_repo = MediaRepository(db_manager)
chapter_repo = ChapterRepository(db_manager)
scene_repo = SceneRepository(db_manager)
sentence_repo = SentenceRepository(db_manager)