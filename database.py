"""
Database operations and models for English Learning Player
"""
import sqlite3
import logging
import threading
from contextlib import contextmanager
from typing import Dict, List, Optional, Any
from queue import Queue, Empty

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Centralized database operations manager with connection pooling"""
    
    def __init__(self, db_path: str = 'dev.db', pool_size: int = 10):
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool = Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._initialize_pool()
        self.init_database()
    
    def _initialize_pool(self):
        """Initialize connection pool"""
        for _ in range(self.pool_size):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            conn.execute('PRAGMA journal_mode=WAL')
            # Enable foreign key constraints
            conn.execute('PRAGMA foreign_keys=ON')
            self._pool.put(conn)
        logger.info(f"Database connection pool initialized with {self.pool_size} connections")
    
    def _get_connection_from_pool(self):
        """Get connection from pool"""
        try:
            return self._pool.get(timeout=5.0)  # 5 second timeout
        except Empty:
            # Pool exhausted, create temporary connection
            logger.warning("Connection pool exhausted, creating temporary connection")
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA foreign_keys=ON')
            return conn
    
    def _return_connection_to_pool(self, conn):
        """Return connection to pool"""
        try:
            self._pool.put_nowait(conn)
        except:
            # Pool is full, close the connection
            conn.close()
    
    @contextmanager
    def get_connection(self):
        """Context manager for pooled database connections"""
        conn = self._get_connection_from_pool()
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            logger.error(f"Database operation failed: {e}")
            raise
        finally:
            self._return_connection_to_pool(conn)
    
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
            
            # Add isBookmarked column if it doesn't exist (migration)
            try:
                cursor.execute('ALTER TABLE Sentence ADD COLUMN isBookmarked BOOLEAN DEFAULT 0')
                conn.commit()
            except Exception:
                # Column already exists or other error - ignore
                pass
            
            # Create WordDifficulty cache table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS WordDifficulty (
                    word TEXT PRIMARY KEY,
                    difficulty TEXT NOT NULL,
                    level TEXT NOT NULL,
                    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create Words database table for phrase matching
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phrase TEXT NOT NULL UNIQUE,
                    meaning TEXT NOT NULL,
                    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create performance indexes
            self._create_indexes(cursor)
            
            conn.commit()
            logger.info("Database initialized successfully")
    
    def _create_indexes(self, cursor):
        """Create indexes for performance optimization"""
        indexes = [
            # High-impact indexes for frequent queries
            "CREATE INDEX IF NOT EXISTS idx_chapter_media_id ON Chapter(mediaId)",
            "CREATE INDEX IF NOT EXISTS idx_scene_chapter_id ON Scene(chapterId)", 
            "CREATE INDEX IF NOT EXISTS idx_sentence_scene_id ON Sentence(sceneId)",
            "CREATE INDEX IF NOT EXISTS idx_sentence_media_order ON Sentence(sceneId, `order`)",
            
            # Bookmark queries optimization
            "CREATE INDEX IF NOT EXISTS idx_sentence_bookmarked ON Sentence(sceneId) WHERE isBookmarked = 1",
            
            # Media status queries
            "CREATE INDEX IF NOT EXISTS idx_media_status ON Media(status)",
            
            # Word difficulty lookup optimization
            "CREATE INDEX IF NOT EXISTS idx_word_difficulty_lookup ON WordDifficulty(word)",
            
            # Words phrase lookup optimization
            "CREATE INDEX IF NOT EXISTS idx_words_phrase ON Words(phrase)",
            
            # Chapter and Scene ordering
            "CREATE INDEX IF NOT EXISTS idx_chapter_order ON Chapter(mediaId, `order`)",
            "CREATE INDEX IF NOT EXISTS idx_scene_order ON Scene(chapterId, `order`)",
            
            # Time-based queries
            "CREATE INDEX IF NOT EXISTS idx_sentence_time ON Sentence(startTime, endTime)",
            "CREATE INDEX IF NOT EXISTS idx_media_created ON Media(createdAt)"
        ]
        
        for index_sql in indexes:
            try:
                cursor.execute(index_sql)
                logger.debug(f"Created index: {index_sql}")
            except Exception as e:
                logger.warning(f"Failed to create index: {index_sql}, Error: {e}")
        
        logger.info("Database indexes created successfully")

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
    
    def update_highlighted_english(self, sentence_id: int, highlighted_english: str) -> bool:
        """Update highlighted_english for a sentence"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE Sentence SET highlighted_english = ? WHERE id = ?",
                (highlighted_english, sentence_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def get_sentences_without_highlights(self, media_id: str) -> List[Dict]:
        """Get sentences that don't have highlighted_english yet"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.*, sc.chapterId, sc.title as sceneTitle, c.title as chapterTitle
                FROM Sentence s
                JOIN Scene sc ON s.sceneId = sc.id
                JOIN Chapter c ON sc.chapterId = c.id
                WHERE c.mediaId = ? AND (s.highlighted_english IS NULL OR s.highlighted_english = '')
                ORDER BY s.`order`
            ''', (media_id,))
            return [dict(row) for row in cursor.fetchall()]

class WordsRepository:
    """Repository for Words operations"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def get_all_phrases(self) -> List[Dict]:
        """Get all phrases for matching"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT phrase, meaning FROM Words ORDER BY LENGTH(phrase) DESC")
            return [{'phrase': row[0], 'meaning': row[1]} for row in cursor.fetchall()]
    
    def find_matching_phrases(self, text: str, limit: int = 10) -> List[Dict]:
        """Find phrases that might match the given text using database search"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Split text into words for better matching
            words = text.lower().split()
            matching_phrases = []
            
            # Search for phrases containing key words from the text
            for word in words[:5]:  # Limit to first 5 words to avoid too many queries
                if len(word) >= 3:  # Skip very short words
                    cursor.execute(
                        "SELECT phrase, meaning FROM Words WHERE phrase LIKE ? ORDER BY LENGTH(phrase) DESC LIMIT ?",
                        (f'%{word}%', limit)
                    )
                    results = cursor.fetchall()
                    for row in results:
                        phrase_data = {'phrase': row[0], 'meaning': row[1]}
                        if phrase_data not in matching_phrases:
                            matching_phrases.append(phrase_data)
            
            return matching_phrases[:limit]
    
    def add_phrase(self, phrase: str, meaning: str) -> bool:
        """Add new phrase to database"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO Words (phrase, meaning) VALUES (?, ?)", (phrase.strip(), meaning.strip()))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to add phrase: {e}")
                return False
    
    def load_from_file(self, file_path: str) -> int:
        """Load phrases from words_db.txt file"""
        count = 0
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or ';' not in line:
                        continue
                    
                    parts = line.split(';', 1)
                    if len(parts) == 2:
                        phrase = parts[0].strip()
                        meaning = parts[1].strip()
                        if phrase and meaning:
                            if self.add_phrase(phrase, meaning):
                                count += 1
            
            logger.info(f"Loaded {count} phrases from {file_path}")
            return count
        except Exception as e:
            logger.error(f"Failed to load phrases from file: {e}")
            return 0
    
    def get_phrase_count(self) -> int:
        """Get total phrase count"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Words")
            return cursor.fetchone()[0]

# Singleton instances
db_manager = DatabaseManager()
media_repo = MediaRepository(db_manager)
chapter_repo = ChapterRepository(db_manager)
scene_repo = SceneRepository(db_manager)
sentence_repo = SentenceRepository(db_manager)
words_repo = WordsRepository(db_manager)