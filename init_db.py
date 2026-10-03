from database import get_user_db_connection, get_chat_db_connection, get_study_db_connection

def init_dbs():
    
    # 1. 유저 db 테이블
    conn_user = get_user_db_connection()
    cursor_user = conn_user.cursor()
    cursor_user.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            hashed_password TEXT NOT NULL,
            provider TEXT DEFAULT 'local',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn_user.commit()
    conn_user.close()

    # 2. 채팅 db 테이블
    conn_chat = get_chat_db_connection()
    conn_chat.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,        
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn_chat.commit()
    conn_chat.close()

    # 3. 공부 기록 db 테이블
    conn_study = get_study_db_connection()
    cursor_study = conn_study.cursor()
    cursor_study.execute('''
        CREATE TABLE IF NOT EXISTS study_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject TEXT,
            duration INTEGER,
            content TEXT,
            raw_message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn_study.commit()
    conn_study.close()

if __name__ == "__main__":
    init_dbs()
