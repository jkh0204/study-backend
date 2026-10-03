import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def get_user_db_connection():
    conn = sqlite3.connect(os.path.join(DATA_DIR, "users.db"))
    conn.row_factory = sqlite3.Row
    return conn

def init_user_db():
    conn = get_user_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            hashed_password TEXT NOT NULL,
            provider TEXT DEFAULT 'local',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def init_personal_tables(user_dir: str):
    with sqlite3.connect(os.path.join(user_dir, "chat.db")) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        
    with sqlite3.connect(os.path.join(user_dir, "study.db")) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS study_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT, duration INTEGER, content TEXT, raw_message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        
    with sqlite3.connect(os.path.join(user_dir, "schedule.db")) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute('''CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            target_date TEXT NOT NULL, 
            title TEXT NOT NULL,
            deleted_at TEXT DEFAULT NULL 
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            schedule_id INTEGER NOT NULL, 
            content TEXT NOT NULL,
            target_time TEXT, 
            is_completed INTEGER DEFAULT 0,
            FOREIGN KEY(schedule_id) REFERENCES schedules(id) ON DELETE CASCADE
        )''')
        
    with sqlite3.connect(os.path.join(user_dir, "memo.db")) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

    with sqlite3.connect(os.path.join(user_dir, "diary.db")) as conn: 
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_diaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_date TEXT NOT NULL,
            content TEXT,
            mood_id INTEGER,
            UNIQUE(target_date)
        )''')

def get_user_folder(user_id: int):
    user_dir = os.path.join(DATA_DIR, f"user_{user_id}")
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
        init_personal_tables(user_dir)
    return user_dir

def get_chat_db_connection(user_id: int):
    conn = sqlite3.connect(os.path.join(get_user_folder(user_id), "chat.db"))
    conn.row_factory = sqlite3.Row
    return conn

def get_study_db_connection(user_id: int):
    conn = sqlite3.connect(os.path.join(get_user_folder(user_id), "study.db"))
    conn.row_factory = sqlite3.Row
    return conn

def get_schedule_db_connection(user_id: int):
    user_folder = get_user_folder(user_id) 
    db_path = os.path.join(user_folder, "schedule.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_date TEXT NOT NULL,
        title TEXT NOT NULL,
        deleted_at TEXT DEFAULT NULL
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        schedule_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        subject TEXT,               
        target_seconds INTEGER,
        is_completed INTEGER DEFAULT 0,
        target_time TEXT,
        FOREIGN KEY (schedule_id) REFERENCES schedules (id) ON DELETE CASCADE
    )''')
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN subject TEXT")
        conn.execute("ALTER TABLE tasks ADD COLUMN target_seconds INTEGER")
    except sqlite3.OperationalError:
        pass # 이미 컬럼이 존재하면 넘어감
    conn.commit()
    return conn

def get_memo_db_connection(user_id: int):
    conn = sqlite3.connect(os.path.join(get_user_folder(user_id), "memo.db"))
    conn.row_factory = sqlite3.Row
    return conn

def get_diary_db_connection(user_id: int):
    conn = sqlite3.connect(os.path.join(get_user_folder(user_id), "diary.db"))
    conn.row_factory = sqlite3.Row

    conn.execute('''CREATE TABLE IF NOT EXISTS daily_diaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_date TEXT NOT NULL,
        content TEXT,
        mood_id INTEGER DEFAULT 2,
        UNIQUE(target_date)
    )''')
    conn.commit()

    return conn

def get_textbook_db_connection():
    """
    모든 유저가 공통으로 사용하는 textbook.db 연결 함수.
    textbook.db는 data/textbook.db 위치에 생성된다.
    """
    db_path = os.path.join(DATA_DIR, "textbook.db")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    return conn


def init_textbook_db():
    """
    모든 유저가 공통으로 참조하는 textbook.db 테이블 생성 함수.
    """

    conn = get_textbook_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS textbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            book_title TEXT NOT NULL,
            publisher TEXT,
            author TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS textbook_chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            textbook_id INTEGER NOT NULL,
            parent_id INTEGER,
            depth INTEGER NOT NULL,
            chapter_order INTEGER NOT NULL,
            title TEXT NOT NULL,
            page INTEGER,
            importance INTEGER DEFAULT 3,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(textbook_id) REFERENCES textbooks(id) ON DELETE CASCADE,
            FOREIGN KEY(parent_id) REFERENCES textbook_chapters(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_textbooks_subject
        ON textbooks(subject)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_textbook_chapters_textbook_id
        ON textbook_chapters(textbook_id)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_textbook_chapters_parent_id
        ON textbook_chapters(parent_id)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_textbook_chapters_depth
        ON textbook_chapters(depth)
    ''')

    conn.commit()
    conn.close()

def get_textbook_outline_by_subject(subject: str, limit: int = 120):
    """
    textbook.db에서 특정 과목의 교재 목차를 조회한다.
    채팅 AI가 벼락치기/학습 계획 추천을 할 때 참고할 목차 데이터로 사용한다.
    """

    conn = get_textbook_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, subject, book_title
            FROM textbooks
            WHERE subject LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (f"%{subject}%",)
        )

        textbook = cursor.fetchone()

        if textbook is None:
            return None

        textbook_id = textbook["id"]

        cursor.execute(
            """
            SELECT
                id,
                parent_id,
                depth,
                chapter_order,
                title,
                page,
                importance
            FROM textbook_chapters
            WHERE textbook_id = ?
            ORDER BY
                CASE WHEN parent_id IS NULL THEN id ELSE parent_id END,
                depth,
                chapter_order,
                id
            LIMIT ?
            """,
            (textbook_id, limit)
        )

        rows = cursor.fetchall()

        outline_lines = []

        for row in rows:
            depth = row["depth"]
            indent = "  " * (depth - 1)
            page_text = f" p.{row['page']}" if row["page"] is not None else ""
            importance_text = f" 중요도:{row['importance']}" if row["importance"] is not None else ""

            outline_lines.append(
                f"{indent}- {row['title']}{page_text}{importance_text}"
            )

        return {
            "textbook_id": textbook["id"],
            "subject": textbook["subject"],
            "book_title": textbook["book_title"],
            "outline": "\n".join(outline_lines)
        }

    finally:
        conn.close()

