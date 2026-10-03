from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from database import get_diary_db_connection
from security import get_current_user

router = APIRouter(prefix="/api", tags=["diary"])


class DiarySchema(BaseModel):
    target_date: str = Field(..., example="2026-04-14")
    content: Optional[str] = ""
    mood_id: int = Field(2, ge=1, le=5)


@router.get("/diary/mood-summary")
async def get_mood_summary(
    month: str = Query(..., example="2026-05"),
    current_user: dict = Depends(get_current_user)
):
    """
    선택한 달의 감정 기록을 mood_id별 개수로 집계합니다.

    예:
    GET /api/diary/mood-summary?month=2026-05
    """
    conn = get_diary_db_connection(current_user["id"])
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT mood_id,
                   COUNT(*) AS mood_count
            FROM daily_diaries
            WHERE substr(target_date, 1, 7) = ?
              AND mood_id BETWEEN 1 AND 5
            GROUP BY mood_id
            ORDER BY mood_id ASC
            """,
            (month,)
        )

        rows = cursor.fetchall()

        mood_count_map = {
            1: 0,
            2: 0,
            3: 0,
            4: 0,
            5: 0
        }

        for row in rows:
            mood_id = int(row["mood_id"])
            mood_count = int(row["mood_count"])

            if mood_id in mood_count_map:
                mood_count_map[mood_id] = mood_count

        items = [
            {
                "mood_id": mood_id,
                "count": mood_count_map[mood_id]
            }
            for mood_id in range(1, 6)
        ]

        return {
            "month": month,
            "items": items
        }

    except Exception as e:
        print(f"❌ Mood Summary Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        conn.close()


@router.get("/diary/{target_date}")
async def get_diary(
    target_date: str,
    current_user: dict = Depends(get_current_user)
):
    conn = get_diary_db_connection(current_user["id"])
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT content,
                   mood_id
            FROM daily_diaries
            WHERE target_date = ?
            """,
            (target_date,)
        )

        row = cursor.fetchone()

        if row:
            return {
                "content": row["content"],
                "mood_id": row["mood_id"]
            }

        return {
            "content": "",
            "mood_id": 2
        }

    except Exception as e:
        print(f"❌ Diary Get Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        conn.close()


@router.post("/diary")
async def save_diary(
    data: DiarySchema,
    current_user: dict = Depends(get_current_user)
):
    conn = get_diary_db_connection(current_user["id"])
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT OR REPLACE INTO daily_diaries
            (target_date, content, mood_id)
            VALUES (?, ?, ?)
            """,
            (
                data.target_date,
                data.content,
                data.mood_id
            )
        )

        conn.commit()

        return {
            "status": "success"
        }

    except Exception as e:
        conn.rollback()
        print(f"❌ Diary Save Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        conn.close()