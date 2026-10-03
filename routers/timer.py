from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_study_db_connection
from security import get_current_user

router = APIRouter(tags=["Study Timer"])


# 안드로이드가 보내는 JSON 데이터 구조
class StudyRecordRequest(BaseModel):
    subject: str
    duration_seconds: int
    content: Optional[str] = "-"  # 사용자가 세부 내용을 적지 않을 경우 기본값


@router.post("/study-records")
async def save_timer_record(
    record: StudyRecordRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    안드로이드 타이머에서 보낸 공부 기록을 개인별 study.db에 저장합니다.
    """
    user_id = current_user["id"]

    conn = get_study_db_connection(user_id)
    cursor = conn.cursor()

    try:
        cursor.execute(
            '''
            INSERT INTO study_logs (subject, duration, content, raw_message)
            VALUES (?, ?, ?, ?)
            ''',
            (
                record.subject,
                record.duration_seconds,
                record.content,
                "App Timer Record"
            )
        )

        conn.commit()
        return {"message": "타이머 기록이 안전하게 저장되었습니다."}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"저장 실패: {str(e)}")

    finally:
        conn.close()


@router.get("/api/study-summary")
async def get_study_summary(current_user: dict = Depends(get_current_user)):
    """
    학습 분석 화면 상단 카드에 표시할 학습 시간 요약을 반환합니다.

    today_total_duration:
    - 오늘 날짜의 study_logs.duration 총합

    month_avg_duration:
    - 이번 달 study_logs.duration 평균
    """
    user_id = current_user["id"]

    conn = get_study_db_connection(user_id)
    cursor = conn.cursor()

    try:
        # 오늘 날짜의 duration 총합
        cursor.execute(
            '''
            SELECT IFNULL(SUM(duration), 0)
            FROM study_logs
            WHERE date(timestamp, 'localtime') = date('now', 'localtime')
            '''
        )
        today_total_duration = cursor.fetchone()[0]

        # 이번 달의 모든 study_logs duration 평균
        cursor.execute(
            '''
            SELECT IFNULL(AVG(duration), 0)
            FROM study_logs
            WHERE strftime('%Y-%m', timestamp, 'localtime') = strftime('%Y-%m', 'now', 'localtime')
            '''
        )
        month_avg_duration = cursor.fetchone()[0]

        return {
            "today_total_duration": int(today_total_duration),
            "month_avg_duration": int(month_avg_duration)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"학습 시간 요약 조회 실패: {str(e)}")

    finally:
        conn.close()