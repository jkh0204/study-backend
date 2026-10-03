from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from database import get_memo_db_connection
from security import get_current_user
from datetime import datetime

router = APIRouter()

class MemoCreate(BaseModel):
    title: Optional[str] = ""
    content: str

class MemoUpdate(BaseModel):
    title: Optional[str] = ""
    content: str

@router.post("/memos")
async def create_memo(data: MemoCreate, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = get_memo_db_connection(user_id)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO memos (title, content) VALUES (?, ?)", (data.title, data.content))
        conn.commit()
        return {"message": "메모가 성공적으로 저장되었습니다.", "memo_id": cursor.lastrowid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/memos")
async def get_memos(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = get_memo_db_connection(user_id)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM memos ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

@router.get("/memos/{memo_id}")
async def get_memo_detail(memo_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = get_memo_db_connection(user_id)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM memos WHERE id = ?", (memo_id,))
        memo = cursor.fetchone()
        if not memo:
            raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다.")
        return dict(memo)
    finally:
        conn.close()

@router.put("/memos/{memo_id}")
async def update_memo(memo_id: int, data: MemoUpdate, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = get_memo_db_connection(user_id)
    cursor = conn.cursor()
    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE memos SET title = ?, content = ?, updated_at = ? WHERE id = ?", 
            (data.title, data.content, current_time, memo_id)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="수정할 메모가 없습니다.")
        conn.commit()
        return {"message": "메모가 수정되었습니다."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.delete("/memos/{memo_id}")
async def delete_memo(memo_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = get_memo_db_connection(user_id)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM memos WHERE id = ?", (memo_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="삭제할 메모가 없습니다.")
        conn.commit()
        return {"message": "메모가 삭제되었습니다."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()