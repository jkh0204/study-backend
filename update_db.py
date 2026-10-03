# update_db.py
import sqlite3
import os

# 유저별 데이터가 저장되는 폴더 경로 (프로젝트 구조에 맞게 설정)
data_dir = "./data"

print("🚀 데이터베이스 업데이트를 시작합니다...")

if os.path.exists(data_dir):
    # data 폴더 안에 있는 모든 유저 폴더를 찾습니다.
    for folder_name in os.listdir(data_dir):
        if folder_name.startswith("user_"):
            db_path = os.path.join(data_dir, folder_name, "schedule.db")
            
            # schedule.db 파일이 존재하면 업데이트 실행
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                try:
                    # 휴지통 기능을 위한 deleted_at 컬럼 추가!
                    cursor.execute("ALTER TABLE schedules ADD COLUMN deleted_at DATETIME DEFAULT NULL;")
                    conn.commit()
                    print(f"✅ 성공: {db_path} 에 컬럼 추가 완료!")
                except sqlite3.OperationalError as e:
                    # 이미 컬럼을 추가했거나 다른 에러가 있는 경우
                    print(f"⚠️ 건너뜀: {db_path} - {str(e)} (이미 컬럼이 존재할 수 있습니다)")
                finally:
                    conn.close()

print("🎉 모든 데이터베이스 업데이트 작업이 끝났습니다!")