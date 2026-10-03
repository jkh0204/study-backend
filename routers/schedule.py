from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
from database import get_schedule_db_connection, get_study_db_connection
from security import get_current_user
from datetime import datetime
import re

router = APIRouter()


class TaskCreate(BaseModel):
    content: str


class ScheduleCreate(BaseModel):
    target_date: str
    title: str
    tasks: List[TaskCreate]


class TaskCheckUpdate(BaseModel):
    is_completed: bool


class TaskUpdate(BaseModel):
    id: Optional[int] = None
    content: str
    is_completed: bool = False


class ScheduleUpdate(BaseModel):
    target_date: str
    title: str
    tasks: List[TaskUpdate]


class TaskUpdateRequest(BaseModel):
    content: Optional[str] = None
    is_completed: Optional[bool] = None
    target_seconds: Optional[int] = None


def parse_task_content(content: str):
    """
    예:
    '수학 2시간' -> subject='수학', target_seconds=7200
    '영어 30분' -> subject='영어', target_seconds=1800
    '컴퓨터' -> subject='컴퓨터', target_seconds=3600
    """
    time_pattern = re.compile(r'(?:(\d+)시간)?\s*(?:(\d+)분)?\s*(?:(\d+)초)?$')
    match = time_pattern.search(content)

    if match and (match.group(1) or match.group(2) or match.group(3)):
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        seconds = int(match.group(3)) if match.group(3) else 0

        target_seconds = hours * 3600 + minutes * 60 + seconds
        subject = content[:match.start()].strip()

        if not subject:
            subject = content.strip()
    else:
        target_seconds = 3600
        subject = content.strip()

    return subject, target_seconds


@router.get("/schedules")
async def get_all_schedules(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = get_schedule_db_connection(user_id)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT *
            FROM schedules
            WHERE deleted_at IS NULL
            ORDER BY target_date ASC
            """
        )

        schedules = [dict(row) for row in cursor.fetchall()]
        result = []

        for sch in schedules:
            schedule_id = sch["id"]

            cursor.execute(
                """
                SELECT *
                FROM tasks
                WHERE schedule_id = ?
                """,
                (schedule_id,)
            )

            tasks = cursor.fetchall()

            result.append({
                "id": schedule_id,
                "title": sch["title"],
                "target_date": sch["target_date"],
                "tasks": [
                    {
                        "id": t["id"],
                        "content": t["content"],
                        "is_completed": bool(t["is_completed"]),
                        "subject": t["subject"],
                        "target_seconds": t["target_seconds"]
                    }
                    for t in tasks
                ]
            })

        return result

    finally:
        conn.close()


@router.get("/schedules/{target_date}")
async def get_schedules(target_date: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = get_schedule_db_connection(user_id)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT *
            FROM schedules
            WHERE target_date = ?
              AND deleted_at IS NULL
            """,
            (target_date,)
        )

        schedules = cursor.fetchall()
        result = []

        for sch in schedules:
            schedule_id = sch["id"]

            cursor.execute(
                """
                SELECT *
                FROM tasks
                WHERE schedule_id = ?
                """,
                (schedule_id,)
            )

            tasks = cursor.fetchall()

            result.append({
                "id": schedule_id,
                "title": sch["title"],
                "target_date": sch["target_date"],
                "tasks": [
                    {
                        "id": t["id"],
                        "content": t["content"],
                        "is_completed": bool(t["is_completed"]),
                        "subject": t["subject"],
                        "target_seconds": t["target_seconds"]
                    }
                    for t in tasks
                ]
            })

        return result

    finally:
        conn.close()


@router.post("/schedules")
async def create_schedule(data: ScheduleCreate, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = get_schedule_db_connection(user_id)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO schedules (target_date, title)
            VALUES (?, ?)
            """,
            (data.target_date, data.title)
        )

        schedule_id = cursor.lastrowid

        for task in data.tasks:
            subject, target_seconds = parse_task_content(task.content)

            cursor.execute(
                """
                INSERT INTO tasks (schedule_id, content, subject, target_seconds)
                VALUES (?, ?, ?, ?)
                """,
                (schedule_id, task.content, subject, target_seconds)
            )

        conn.commit()

        return {
            "message": "일정이 추가되었습니다.",
            "schedule_id": schedule_id
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        conn.close()


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    data: ScheduleUpdate,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    conn = get_schedule_db_connection(user_id)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE schedules
            SET target_date = ?, title = ?
            WHERE id = ?
            """,
            (data.target_date, data.title, schedule_id)
        )

        cursor.execute(
            """
            SELECT id
            FROM tasks
            WHERE schedule_id = ?
            """,
            (schedule_id,)
        )

        existing_task_ids = [row["id"] for row in cursor.fetchall()]
        received_task_ids = []

        for task in data.tasks:
            subject, target_seconds = parse_task_content(task.content)

            if task.id is not None:
                cursor.execute(
                    """
                    UPDATE tasks
                    SET content = ?,
                        subject = ?,
                        target_seconds = ?,
                        is_completed = ?
                    WHERE id = ?
                    """,
                    (
                        task.content,
                        subject,
                        target_seconds,
                        int(task.is_completed),
                        task.id
                    )
                )

                received_task_ids.append(task.id)

            else:
                cursor.execute(
                    """
                    INSERT INTO tasks
                    (schedule_id, content, subject, target_seconds, is_completed)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        schedule_id,
                        task.content,
                        subject,
                        target_seconds,
                        int(task.is_completed)
                    )
                )

        tasks_to_delete = set(existing_task_ids) - set(received_task_ids)

        for del_id in tasks_to_delete:
            cursor.execute(
                """
                DELETE FROM tasks
                WHERE id = ?
                """,
                (del_id,)
            )

        conn.commit()

        return {
            "message": "일정이 성공적으로 수정되었습니다."
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        conn.close()


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: int,
    request: TaskUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    conn = get_schedule_db_connection(current_user["id"])
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id
            FROM tasks
            WHERE id = ?
            """,
            (task_id,)
        )

        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="수정할 할 일을 찾을 수 없습니다.")

        updates = []
        values = []

        if request.content is not None:
            subject, target_seconds = parse_task_content(request.content)

            updates.append("content = ?")
            values.append(request.content)

            updates.append("subject = ?")
            values.append(subject)

            if request.target_seconds is None:
                updates.append("target_seconds = ?")
                values.append(target_seconds)

        if request.is_completed is not None:
            updates.append("is_completed = ?")
            values.append(int(request.is_completed))

        if request.target_seconds is not None:
            updates.append("target_seconds = ?")
            values.append(request.target_seconds)

        if not updates:
            return {
                "message": "수정할 내용이 없습니다.",
                "task_id": task_id
            }

        query = f"""
            UPDATE tasks
            SET {', '.join(updates)}
            WHERE id = ?
        """

        values.append(task_id)
        cursor.execute(query, tuple(values))
        conn.commit()

        return {
            "message": "할 일이 성공적으로 수정되었습니다.",
            "task_id": task_id
        }

    finally:
        conn.close()


@router.patch("/tasks/{task_id}/check")
async def toggle_task_check(
    task_id: int,
    data: TaskCheckUpdate,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    conn = get_schedule_db_connection(user_id)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE tasks
            SET is_completed = ?
            WHERE id = ?
            """,
            (int(data.is_completed), task_id)
        )

        cursor.execute(
            """
            SELECT t.subject,
                   t.target_seconds,
                   s.target_date
            FROM tasks t
            JOIN schedules s ON t.schedule_id = s.id
            WHERE t.id = ?
            """,
            (task_id,)
        )

        task_info = cursor.fetchone()

        if task_info and dict(task_info).get("target_seconds", 0) > 0:
            study_conn = get_study_db_connection(user_id)
            study_cursor = study_conn.cursor()

            try:
                if data.is_completed:
                    study_cursor.execute(
                        """
                        INSERT INTO study_logs
                        (timestamp, subject, duration, raw_message, content)
                        VALUES (?, ?, ?, NULL, NULL)
                        """,
                        (
                            task_info["target_date"],
                            task_info["subject"],
                            task_info["target_seconds"]
                        )
                    )

                else:
                    study_cursor.execute(
                        """
                        DELETE FROM study_logs
                        WHERE rowid = (
                            SELECT rowid
                            FROM study_logs
                            WHERE timestamp = ?
                              AND subject = ?
                              AND duration = ?
                              AND raw_message IS NULL
                              AND content IS NULL
                            ORDER BY rowid DESC
                            LIMIT 1
                        )
                        """,
                        (
                            task_info["target_date"],
                            task_info["subject"],
                            task_info["target_seconds"]
                        )
                    )

                study_conn.commit()

            finally:
                study_conn.close()

        conn.commit()

        return {
            "message": "체크 상태가 변경되었습니다."
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        conn.close()


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_schedule_db_connection(current_user["id"])
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id
            FROM tasks
            WHERE id = ?
            """,
            (task_id,)
        )

        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="삭제하려는 할 일을 찾을 수 없습니다.")

        cursor.execute(
            """
            DELETE FROM tasks
            WHERE id = ?
            """,
            (task_id,)
        )

        conn.commit()

        return {
            "message": "해당 할 일이 성공적으로 삭제되었습니다.",
            "deleted_task_id": task_id
        }

    finally:
        conn.close()


@router.delete("/schedules/{schedule_id}")
async def soft_delete_schedule(schedule_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_schedule_db_connection(current_user["id"])
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE schedules
            SET deleted_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (schedule_id,)
        )

        conn.commit()

        return {
            "message": "일정이 휴지통으로 이동되었습니다.",
            "schedule_id": schedule_id
        }

    finally:
        conn.close()


@router.get("/schedules/trash/list")
async def get_trash_schedules(current_user: dict = Depends(get_current_user)):
    conn = get_schedule_db_connection(current_user["id"])
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM tasks
            WHERE schedule_id IN (
                SELECT id
                FROM schedules
                WHERE deleted_at <= datetime('now', 'localtime', '-30 days')
            )
            """
        )

        cursor.execute(
            """
            DELETE FROM schedules
            WHERE deleted_at <= datetime('now', 'localtime', '-30 days')
            """
        )

        conn.commit()

        cursor.execute(
            """
            SELECT id, title, deleted_at
            FROM schedules
            WHERE deleted_at IS NOT NULL
            ORDER BY deleted_at DESC
            """
        )

        schedules = [dict(row) for row in cursor.fetchall()]

        for sch in schedules:
            cursor.execute(
                """
                SELECT id, content, is_completed
                FROM tasks
                WHERE schedule_id = ?
                """,
                (sch["id"],)
            )

            sch["tasks"] = [dict(row) for row in cursor.fetchall()]

        return schedules

    finally:
        conn.close()


@router.patch("/schedules/{schedule_id}/restore")
async def restore_schedule(schedule_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_schedule_db_connection(current_user["id"])
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE schedules
            SET deleted_at = NULL
            WHERE id = ?
            """,
            (schedule_id,)
        )

        conn.commit()

        return {
            "message": "일정이 성공적으로 복원되었습니다.",
            "schedule_id": schedule_id
        }

    finally:
        conn.close()


@router.delete("/schedules/{schedule_id}/permanent")
async def permanent_delete_schedule(schedule_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_schedule_db_connection(current_user["id"])
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM tasks
            WHERE schedule_id = ?
            """,
            (schedule_id,)
        )

        cursor.execute(
            """
            DELETE FROM schedules
            WHERE id = ?
            """,
            (schedule_id,)
        )

        conn.commit()

        return {
            "message": "일정이 영구적으로 삭제되었습니다."
        }

    finally:
        conn.close()


@router.get("/study-summary")
async def get_study_summary(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = get_study_db_connection(user_id)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT IFNULL(SUM(duration), 0)
            FROM study_logs
            WHERE date(timestamp, 'localtime') = date('now', 'localtime')
            """
        )

        today_total_duration = int(cursor.fetchone()[0] or 0)

        cursor.execute(
            """
            SELECT IFNULL(AVG(daily_total), 0)
            FROM (
                SELECT date(timestamp, 'localtime') AS study_date,
                       SUM(duration) AS daily_total
                FROM study_logs
                WHERE strftime('%Y-%m', timestamp, 'localtime') = strftime('%Y-%m', 'now', 'localtime')
                GROUP BY date(timestamp, 'localtime')
            )
            """
        )

        month_avg_duration = int(cursor.fetchone()[0] or 0)

        return {
            "today_total_duration": today_total_duration,
            "month_avg_duration": month_avg_duration
        }

    finally:
        conn.close()


@router.get("/study/daily-donut")
async def get_daily_donut(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    study_conn = get_study_db_connection(user_id)
    study_cursor = study_conn.cursor()

    schedule_conn = get_schedule_db_connection(user_id)
    schedule_cursor = schedule_conn.cursor()

    try:
        study_cursor.execute(
            """
            SELECT IFNULL(SUM(duration), 0)
            FROM study_logs
            WHERE date(timestamp, 'localtime') = date('now', 'localtime')
            """
        )

        today_study_seconds = int(study_cursor.fetchone()[0] or 0)

        schedule_cursor.execute(
            """
            SELECT IFNULL(SUM(t.target_seconds), 0)
            FROM tasks t
            JOIN schedules s ON t.schedule_id = s.id
            WHERE s.target_date = date('now', 'localtime')
              AND s.deleted_at IS NULL
            """
        )

        today_target_seconds = int(schedule_cursor.fetchone()[0] or 0)

        total_goal_seconds = max(today_target_seconds, today_study_seconds)

        if total_goal_seconds > 0:
            progress = min(today_study_seconds / total_goal_seconds, 1.0)
        else:
            progress = 0.0

        return {
            "today_study_seconds": today_study_seconds,
            "today_target_seconds": today_target_seconds,
            "total_goal_seconds": total_goal_seconds,
            "progress": progress
        }

    finally:
        study_conn.close()
        schedule_conn.close()


@router.get("/study/weekly-chart")
async def get_weekly_chart(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = get_study_db_connection(user_id)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT CAST(strftime('%w', timestamp, 'localtime') AS INTEGER) AS weekday,
                   IFNULL(SUM(duration), 0) AS total_duration
            FROM study_logs
            WHERE date(timestamp, 'localtime') >= date('now', 'weekday 1', '-7 days')
              AND date(timestamp, 'localtime') <= date('now', 'weekday 1', '-1 day', '+6 days')
            GROUP BY weekday
            """
        )

        weekly_seconds = [0, 0, 0, 0, 0, 0, 0]

        for row in cursor.fetchall():
            weekday = int(row[0])
            total_duration = int(row[1] or 0)

            if weekday == 0:
                index = 6
            else:
                index = weekday - 1

            weekly_seconds[index] = total_duration

        return {
            "weekly_seconds": weekly_seconds
        }

    finally:
        conn.close()


@router.get("/study/monthly-chart")
async def get_monthly_chart(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = get_study_db_connection(user_id)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT CAST(strftime('%m', timestamp, 'localtime') AS INTEGER) AS month,
                   IFNULL(SUM(duration), 0) AS total_duration
            FROM study_logs
            WHERE strftime('%Y', timestamp, 'localtime') = strftime('%Y', 'now', 'localtime')
            GROUP BY month
            """
        )

        monthly_seconds = [0 for _ in range(12)]

        for row in cursor.fetchall():
            month = int(row[0])
            total_duration = int(row[1] or 0)

            if 1 <= month <= 12:
                monthly_seconds[month - 1] = total_duration

        return {
            "monthly_seconds": monthly_seconds
        }

    finally:
        conn.close()


@router.get("/study/subject-summary")
async def get_subject_summary(
    date: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    conn = get_study_db_connection(user_id)
    cursor = conn.cursor()

    try:
        if not date:
            cursor.execute("SELECT date('now', 'localtime')")
            date = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT subject,
                   IFNULL(SUM(duration), 0) AS total_duration
            FROM study_logs
            WHERE date(timestamp, 'localtime') = date(?)
            GROUP BY subject
            HAVING total_duration > 0
            ORDER BY total_duration DESC, subject ASC
            """,
            (date,)
        )

        rows = cursor.fetchall()
        total_seconds = sum(int(row[1] or 0) for row in rows)

        items = []
        accumulated_percent = 0

        for index, row in enumerate(rows):
            subject = row[0] if row[0] else "기타"
            duration_seconds = int(row[1] or 0)

            if total_seconds > 0:
                if index == len(rows) - 1:
                    percent = max(0, 100 - accumulated_percent)
                else:
                    percent = round(duration_seconds * 100 / total_seconds)
                    accumulated_percent += percent
            else:
                percent = 0

            items.append({
                "subject": subject,
                "duration_seconds": duration_seconds,
                "percent": percent
            })

        return {
            "date": date,
            "total_seconds": total_seconds,
            "items": items
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"과목별 학습시간 조회 실패: {str(e)}")

    finally:
        conn.close()


@router.get("/study-records")
async def get_study_records_by_date(
    date: str,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    conn = get_study_db_connection(user_id)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id,
                   subject,
                   duration AS duration_seconds,
                   content,
                   raw_message,
                   timestamp
            FROM study_logs
            WHERE date(timestamp, 'localtime') = date(?)
            ORDER BY timestamp DESC
            """,
            (date,)
        )

        return [dict(row) for row in cursor.fetchall()]

    finally:
        conn.close()