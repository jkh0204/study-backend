import os
import sqlite3

# 1. 이 파일(check_db.py)이 있는 진짜 위치를 찾습니다. (절대 경로)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

print("-" * 50)
print(f"📍 내 프로젝트 위치: {BASE_DIR}")
print(f"📂 데이터 저장소 위치: {DATA_DIR}")
print("-" * 50)

# 2. 폴더가 없으면 만듭니다.
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR)
        print("✅ 'data' 폴더를 새로 만들었습니다.")
    except Exception as e:
        print(f"❌ 폴더 생성 실패: {e}")
else:
    print("✅ 'data' 폴더가 이미 존재합니다.")

# 3. DB 파일 3형제를 확인하고, 없으면 빈 파일을 만듭니다.
db_files = ["users.db", "chat.db", "study.db"]

print("\n[ 파일 상태 확인 ]")
for db_name in db_files:
    db_path = os.path.join(DATA_DIR, db_name)
    
    if os.path.exists(db_path):
        size = os.path.getsize(db_path)
        print(f"🟢 {db_name} : 있음! (크기: {size} bytes)")
    else:
        print(f"🔴 {db_name} : 없음! -> 생성 시도 중...")
        try:
            # 빈 파일 생성 테스트
            conn = sqlite3.connect(db_path)
            conn.close()
            print(f"   -> ✨ {db_name} 생성 성공!")
        except Exception as e:
            print(f"   -> ☠️ 생성 실패 에러: {e}")

print("-" * 50)
print("이제 왼쪽 파일 탐색기에서 'data' 폴더를 열어보세요.")