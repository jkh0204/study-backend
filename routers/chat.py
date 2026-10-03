import json
import os
import re
import sqlite3
import traceback
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from models import ChatRequest, ChatResponse
from database import (
    get_chat_db_connection,
    get_study_db_connection,
    get_schedule_db_connection,
    get_textbook_db_connection
)
from security import get_current_user
from ollama import AsyncClient


router = APIRouter(tags=["Chat"])
ollama_client = AsyncClient()

DEFAULT_TASK_SECONDS = 3600
DEFAULT_TASK_TIME_TEXT = "1시간"


# =========================================================
# 과목명 처리
# =========================================================

def normalize_subject_korean(subject: str) -> str:
    if subject is None:
        return "기타"

    raw = str(subject).strip()

    if not raw:
        return "기타"

    compact = raw.lower().replace(" ", "")

    subject_map = {
        "파ㅓ이썬": "파이썬",
        "파ㅣ썬": "파이썬",
        "파이선": "파이썬",
        "python": "파이썬",
        "py": "파이썬",

        "linux": "리눅스",
        "리눅스": "리눅스",

        "algorithm": "알고리즘",
        "algorithms": "알고리즘",
        "알고리즘": "알고리즘",

        "logiccircuit": "논리회로",
        "logiccircuits": "논리회로",
        "논리회로": "논리회로",

        "datastructure": "자료구조",
        "datastructures": "자료구조",
        "자료구조": "자료구조",

        "operatingsystem": "운영체제",
        "os": "운영체제",
        "운영체제": "운영체제",

        "database": "데이터베이스",
        "db": "데이터베이스",
        "데이터베이스": "데이터베이스",

        "math": "수학",
        "mathematics": "수학",
        "수학": "수학",

        "english": "영어",
        "영어": "영어",

        "korean": "국어",
        "국어": "국어",

        "java": "자바",
        "자바": "자바",

        "javascript": "자바스크립트",
        "js": "자바스크립트",
        "자바스크립트": "자바스크립트",

        "computer": "컴퓨터",
        "컴퓨터": "컴퓨터",

        "사회탐구": "사회탐구",
        "사탐": "사회탐구",

        "윤리": "윤리",
        "윤리공부": "윤리",

        "정보보호": "정보보호",
        "정보보안": "정보보호",
        "보안": "정보보호",
        "informationsecurity": "정보보호",
        "security": "정보보호",
    }

    return subject_map.get(compact, raw)


def detect_subject_from_user_message(user_msg: str, current_subject: str = "기타") -> str:
    current_subject = normalize_subject_korean(current_subject)

    if current_subject != "기타":
        return current_subject

    if not user_msg:
        return "기타"

    compact = user_msg.lower().replace(" ", "")

    subject_keywords = [
        ("정보보호", ["정보보호", "정보보안", "보안", "informationsecurity", "security"]),
        ("파이썬", ["파이썬", "파ㅓ이썬", "파ㅣ썬", "파이선", "python", "py"]),
        ("리눅스", ["리눅스", "linux"]),
        ("알고리즘", ["알고리즘", "algorithm", "algorithms"]),
        ("논리회로", ["논리회로", "logiccircuit", "logiccircuits"]),
        ("자료구조", ["자료구조", "datastructure", "datastructures"]),
        ("운영체제", ["운영체제", "operatingsystem", "os"]),
        ("데이터베이스", ["데이터베이스", "database", "db"]),
        ("수학", ["수학", "math", "mathematics"]),
        ("영어", ["영어", "english"]),
        ("국어", ["국어", "korean"]),
        ("자바스크립트", ["자바스크립트", "javascript", "js"]),
        ("자바", ["자바", "java"]),
        ("컴퓨터", ["컴퓨터", "computer"]),
        ("사회탐구", ["사회탐구", "사탐"]),
        ("윤리", ["윤리"]),
        ("과제", ["과제"]),
        ("시험공부", ["시험공부"])
    ]

    for subject, keywords in subject_keywords:
        if any(keyword in compact for keyword in keywords):
            return subject

    match = re.search(r'([가-힣A-Za-z0-9+#]+)\s*공부', user_msg)
    if match:
        return normalize_subject_korean(match.group(1))

    match = re.search(r'([가-힣A-Za-z0-9+#]+)\s*(추천|계획|스케줄|스케쥴|일정)', user_msg)
    if match:
        return normalize_subject_korean(match.group(1))

    return "기타"


# =========================================================
# 날짜 처리
# =========================================================

def parse_target_date_from_text(text: str) -> str:
    today = datetime.now()

    if not text:
        return today.strftime("%Y-%m-%d")

    compact = text.replace(" ", "")

    if "오늘" in compact:
        return today.strftime("%Y-%m-%d")

    if "내일" in compact:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    if "모레" in compact:
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")

    match = re.search(r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일', text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    match = re.search(r'(\d{4})[-./](\d{1,2})[-./](\d{1,2})', text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    match = re.search(r'(\d{1,2})\s*월\s*(\d{1,2})\s*일', text)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        return f"{today.year:04d}-{month:02d}-{day:02d}"

    return today.strftime("%Y-%m-%d")

def has_concrete_schedule_content(user_msg: str) -> bool:
    """
    사용자가 직접 스케줄 내용을 말했는지 검사한다.
    예:
    - 오늘 파이썬 3시간 공부 추가해줘
    - 내일 수학 공부 추가해줘
    - 5월 28일부터 30일까지 영어 공부 추가해줘
    이런 문장은 직전 추천 수락이 아니라 직접 스케줄 추가로 처리해야 한다.
    """
    if not user_msg:
        return False

    text = user_msg.replace(" ", "")

    # 날짜 표현이 있는 경우
    date_keywords = [
        "오늘",
        "내일",
        "모레",
        "이번주",
        "다음주",
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "토요일",
        "일요일",
    ]

    if any(word in user_msg for word in date_keywords):
        return True

    # 5월 28일, 2026년 6월 15일 같은 날짜 표현
    if re.search(r'\d{1,2}\s*월\s*\d{1,2}\s*일', user_msg):
        return True

    if re.search(r'\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일', user_msg):
        return True

    # 시간 표현이 있는 경우
    if re.search(r'\d+\s*시간|\d+\s*분|\d+\s*초', user_msg):
        return True

    # 공부할 과목/내용이 직접 들어간 경우
    if "공부" in user_msg:
        return True

    return False


def is_accepting_previous_recommendation(text: str) -> bool:
    """
    직전 추천을 그대로 추가하겠다는 짧은 수락 문장만 True로 처리한다.

    예:
    - 추가해줘
    - 그대로 추가해줘
    - 이대로 추가해줘

    반대로 아래처럼 날짜/과목/기간/공부 내용이 들어간 문장은
    새 스케줄 추가로 봐야 하므로 False를 반환한다.
    - 오늘부터 일주일동안 파이썬 공부할거야. 스케줄 추가해줘
    - 오늘 운영체제 공부하고 내일 정보보호 공부할거야. 스케줄 추가해줘
    """

    if not text:
        return False

    compact = text.strip().replace(" ", "")

    # 사용자가 직접 새 스케줄 내용을 말한 경우는 직전 추천 수락이 아님
    direct_keywords = [
        "오늘",
        "내일",
        "모레",
        "이번주",
        "다음주",
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "토요일",
        "일요일",
        "부터",
        "까지",
        "동안",
        "일주일",
        "1주일",
        "한주",
        "공부",
        "학습",
        "복습",
        "예습",
        "문제",
        "풀이",
    ]

    if any(keyword in compact for keyword in direct_keywords):
        return False

    # 날짜 표현이 있으면 직접 스케줄 추가
    if re.search(r'\d{1,2}월\d{1,2}일', compact):
        return False

    if re.search(r'\d{4}년\d{1,2}월\d{1,2}일', compact):
        return False

    # 시간 표현이 있으면 직접 스케줄 추가
    if re.search(r'\d+(시간|분|초)', compact):
        return False

    accept_exact_patterns = [
        "응",
        "ㅇㅇ",
        "그래",
        "좋아",
        "추가해줘",
        "추가해",
        "등록해줘",
        "등록해",
        "저장해줘",
        "저장해",
        "넣어줘",
        "넣어",
        "그거추가해줘",
        "그대로추가해줘",
        "이대로추가해줘",
        "이일정대로추가해줘",
        "이계획대로추가해줘",
        "추천한대로추가해줘",
        "스케줄에추가해줘",
        "스케쥴에추가해줘",
        "일정에추가해줘",
    ]

    return compact in accept_exact_patterns

def date_word_to_date(date_word: str) -> str:
    today = datetime.now()
    compact = date_word.replace(" ", "")

    if "오늘" in compact:
        return today.strftime("%Y-%m-%d")

    if "내일" in compact:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    if "모레" in compact:
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")

    return parse_target_date_from_text(date_word)


# =========================================================
# 시간 처리
# =========================================================

def parse_duration_from_text(text: str, default_seconds: int = DEFAULT_TASK_SECONDS) -> int:
    if not text:
        return default_seconds

    match = re.search(
        r'(?:(\d+(?:\.\d+)?)\s*시간)?\s*'
        r'(?:(\d+(?:\.\d+)?)\s*분)?\s*'
        r'(?:(\d+(?:\.\d+)?)\s*초)?',
        text
    )

    if match and (match.group(1) or match.group(2) or match.group(3)):
        h = float(match.group(1)) if match.group(1) else 0
        m = float(match.group(2)) if match.group(2) else 0
        s = float(match.group(3)) if match.group(3) else 0

        total = int(h * 3600 + m * 60 + s)

        if total > 0:
            return total

    return default_seconds


def seconds_to_korean_time(seconds: int) -> str:
    if seconds <= 0:
        seconds = DEFAULT_TASK_SECONDS

    if seconds % 3600 == 0:
        return f"{seconds // 3600}시간"

    if seconds % 60 == 0:
        return f"{seconds // 60}분"

    return f"{seconds}초"



def parse_task_time(content: str, default_subject: str = "기타"):
    content = str(content).strip()

    time_match = re.search(
        r'외\s*(?:(\d+(?:\.\d+)?)\s*시간)?\s*'
        r'(?:(\d+(?:\.\d+)?)\s*분)?\s*'
        r'(?:(\d+(?:\.\d+)?)\s*초)?',
        content
    )

    if not time_match:
        time_match = re.search(
            r'(?:(\d+(?:\.\d+)?)\s*시간)?\s*'
            r'(?:(\d+(?:\.\d+)?)\s*분)?\s*'
            r'(?:(\d+(?:\.\d+)?)\s*초)?$',
            content
        )

    if time_match and (time_match.group(1) or time_match.group(2) or time_match.group(3)):
        h = float(time_match.group(1)) if time_match.group(1) else 0
        m = float(time_match.group(2)) if time_match.group(2) else 0
        s = float(time_match.group(3)) if time_match.group(3) else 0

        total_seconds = int(h * 3600 + m * 60 + s)
        subject_part = content[:time_match.start()].strip()
    else:
        total_seconds = DEFAULT_TASK_SECONDS
        subject_part = content

    default_subject = normalize_subject_korean(default_subject)

    if default_subject != "기타":
        return default_subject, total_seconds

    subject_part = subject_part.replace("외", "").strip()

    if "-" in subject_part:
        subject = subject_part.split("-")[0].strip()
    else:
        subject = subject_part.split(" ")[0].strip()

    subject = normalize_subject_korean(subject)

    if not subject:
        subject = "기타"

    return subject, total_seconds


# =========================================================
# 의도 판단
# =========================================================

def is_clear_history_request(text: str) -> bool:
    if not text:
        return False    

    compact = text.replace(" ", "")

    keywords = [
        "대화기록초기화",
        "기록초기화",
        "대화초기화",
        "이전대화무시",
        "이전내용무시",
        "새로시작",
        "처음부터",
        "기록삭제",
        "대화삭제"
    ]

    return any(keyword in compact for keyword in keywords)


def is_schedule_add_request(text: str) -> bool:
    if not text:
        return False

    compact = text.replace(" ", "")

    keywords = [
        "추가해줘",
        "추가해",
        "추가",
        "등록해줘",
        "등록해",
        "등록",
        "넣어줘",
        "넣어",
        "저장해줘",
        "저장해",
        "스케줄에추가",
        "스케쥴에추가",
        "일정에추가",
        "스케줄추가",
        "스케쥴추가",
        "일정추가"
    ]

    return any(keyword in compact for keyword in keywords)


def is_accepting_previous_recommendation(text: str) -> bool:
    """
    직전 추천을 그대로 추가하겠다는 짧은 수락 문장만 True로 처리한다.

    예:
    - 추가해줘
    - 그대로 추가해줘
    - 이대로 추가해줘

    반대로 아래처럼 날짜/과목/기간/공부 내용이 들어간 문장은
    새 스케줄 추가로 봐야 하므로 False를 반환한다.
    - 오늘부터 일주일동안 파이썬 공부할거야. 스케줄 추가해줘
    - 오늘 운영체제 공부하고 내일 정보보호 공부할거야. 스케줄 추가해줘
    """

    if not text:
        return False

    compact = text.strip().replace(" ", "")

    # 사용자가 직접 새 스케줄 내용을 말한 경우는 직전 추천 수락이 아님
    direct_keywords = [
        "오늘",
        "내일",
        "모레",
        "이번주",
        "다음주",
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "토요일",
        "일요일",
        "부터",
        "까지",
        "동안",
        "일주일",
        "1주일",
        "한주",
        "공부",
        "학습",
        "복습",
        "예습",
        "문제",
        "풀이",
    ]

    if any(keyword in compact for keyword in direct_keywords):
        return False

    # 날짜 표현이 있으면 직접 스케줄 추가
    if re.search(r'\d{1,2}월\d{1,2}일', compact):
        return False

    if re.search(r'\d{4}년\d{1,2}월\d{1,2}일', compact):
        return False

    # 시간 표현이 있으면 직접 스케줄 추가
    if re.search(r'\d+(시간|분|초)', compact):
        return False

    accept_exact_patterns = [
        "응",
        "ㅇㅇ",
        "그래",
        "좋아",
        "추가해줘",
        "추가해",
        "등록해줘",
        "등록해",
        "저장해줘",
        "저장해",
        "넣어줘",
        "넣어",
        "그거추가해줘",
        "그대로추가해줘",
        "이대로추가해줘",
        "이일정대로추가해줘",
        "이계획대로추가해줘",
        "추천한대로추가해줘",
        "스케줄에추가해줘",
        "스케쥴에추가해줘",
        "일정에추가해줘",
    ]

    return compact in accept_exact_patterns

def is_direct_schedule_request(text: str) -> bool:
    """
    사용자가 직접 스케줄 내용을 말한 경우인지 확인한다.

    예:
    - 오늘 파이썬 3시간 공부할거라고 스케줄에 추가해줘
    - 내일 리눅스 2시간 공부 추가해줘
    - 5월 30일 수학 1시간 추가해줘

    이런 경우는 직전 추천 저장이 아니라 새 스케줄 추가로 처리해야 한다.
    """

    if not text:
        return False

    has_add_word = any(word in text for word in ["추가", "등록", "저장", "스케줄", "스케쥴", "일정"])
    has_date_word = any(word in text for word in ["오늘", "내일", "모레", "이번", "다음", "월", "일"])
    has_time_word = bool(re.search(r'\d+\s*(시간|분)', text))
    has_study_word = any(word in text for word in ["공부", "학습", "복습", "예습", "문제", "풀이"])

    return has_add_word and has_date_word and has_time_word and has_study_word

def last_ai_asks_to_add_schedule(last_ai_msg: str) -> bool:
    """
    직전 AI 답변이 '이 일정대로 스케줄에 추가해 드릴까요?' 형태인지 확인한다.
    사용자가 '추가해줘'라고만 말해도 직전 추천 수락으로 처리하기 위함.
    """

    if not last_ai_msg:
        return False

    compact = last_ai_msg.replace(" ", "")

    keywords = [
        "이일정대로스케줄에추가",
        "이일정대로스케쥴에추가",
        "이일정대로일정에추가",
        "이계획대로스케줄에추가",
        "이계획대로스케쥴에추가",
        "스케줄에추가해드릴까요",
        "스케쥴에추가해드릴까요",
        "일정에추가해드릴까요",
        "추가해드릴까요",
        "추가할까요"
    ]

    return any(keyword in compact for keyword in keywords)


def has_long_term_period(text: str) -> bool:
    if not text:
        return False

    compact = text.replace(" ", "")

    keywords = [
        "일주일",
        "1주일",
        "한주",
        "1주간",
        "2주",
        "3주",
        "4주",
        "한달",
        "1개월",
        "장기계획",
        "장기스케줄",
        "장기스케쥴"
    ]

    if any(keyword in compact for keyword in keywords):
        return True

    if re.search(r'\d+\s*주\s*(동안|간)?', text):
        return True

    if re.search(r'\d+\s*개월\s*(동안|간)?', text):
        return True

    if re.search(r'\d+\s*일\s*(동안|간)', text):
        return True

    return False


def extract_period_text(text: str) -> str:
    if not text:
        return "일주일"

    compact = text.replace(" ", "")

    if "일주일" in compact or "1주일" in compact or "한주" in compact:
        return "일주일"

    if "한달" in compact or "1개월" in compact:
        return "한 달"

    match = re.search(r'(\d+)\s*주', text)
    if match:
        return f"{match.group(1)}주"

    match = re.search(r'(\d+)\s*개월', text)
    if match:
        return f"{match.group(1)}개월"

    match = re.search(r'(\d+)\s*일\s*(동안|간)', text)
    if match:
        return f"{match.group(1)}일"

    return "일주일"


def get_period_days(period: str) -> int:
    if not period:
        return 7

    compact = period.replace(" ", "")

    if "일주일" in compact or "1주일" in compact or "한주" in compact:
        return 7

    if "한달" in compact or "1개월" in compact:
        return 30

    match = re.search(r'(\d+)주', compact)
    if match:
        return int(match.group(1)) * 7

    match = re.search(r'(\d+)개월', compact)
    if match:
        return int(match.group(1)) * 30

    match = re.search(r'(\d+)일', compact)
    if match:
        return int(match.group(1))

    return 7


# =========================================================
# 벼락치기 / 시험 계획 처리
# =========================================================

def is_exam_cram_context(text: str) -> bool:
    if not text:
        return False

    compact = text.replace(" ", "")

    has_exam = "시험" in compact
    has_cram = "벼락치기" in compact or "시험공부" in compact or "시험대비" in compact
    has_plan = (
        "계획" in compact
        or "스케줄" in compact
        or "스케쥴" in compact
        or "짜줘" in compact
        or "추천" in compact
    )

    return has_exam and (has_cram or has_plan)

def is_current_exam_cram_request(text: str) -> bool:
    """
    현재 사용자 메시지 자체가 시험/벼락치기 계획 요청인지 확인한다.
    이전 대화 내용 때문에 벼락치기 추천이 반복되는 것을 막기 위해 사용한다.
    """
    if not text:
        return False

    compact = text.replace(" ", "")

    has_exam_word = (
        "시험" in compact
        or "벼락치기" in compact
        or "시험공부" in compact
        or "시험대비" in compact
    )

    has_plan_word = (
        "계획" in compact
        or "스케줄" in compact
        or "스케쥴" in compact
        or "일정" in compact
        or "짜줘" in compact
        or "추천" in compact
    )

    has_exam_info = (
        "시험범위" in compact
        or "범위" in compact
        or re.search(r'\d{1,2}\s*장', text) is not None
        or re.search(r'\d{1,2}\s*월\s*\d{1,2}\s*일', text) is not None
    )

    return has_exam_word and (has_plan_word or has_exam_info)

def is_cram_schedule_request(text: str) -> bool:
    """
    벼락치기 스케줄 요청인지 판단한다.
    일반적인 '일주일동안 공부하겠다'는 벼락치기로 보지 않는다.
    """

    if not text:
        return False

    compact = text.replace(" ", "")

    cram_keywords = [
        "벼락치기",
        "시험",
        "시험범위",
        "중간고사",
        "기말고사",
        "고사",
        "시험공부"
    ]

    return any(keyword in compact for keyword in cram_keywords)


def is_answering_cram_missing_info(last_ai_msg: str, user_msg: str) -> bool:
    """
    AI가 직전에 시험 날짜/시험범위를 물어봤고,
    사용자가 그 정보만 답한 경우에는 이전 대화와 합쳐서 벼락치기 계획을 완성한다.
    """
    if not last_ai_msg or not user_msg:
        return False

    last_compact = last_ai_msg.replace(" ", "")
    user_compact = user_msg.replace(" ", "")

    ai_asked_exam_date = "시험날짜" in last_compact or "시험일" in last_compact
    ai_asked_chapters = "시험범위" in last_compact or "범위" in last_compact

    user_gave_date = re.search(r'\d{1,2}\s*월\s*\d{1,2}\s*일', user_msg) is not None
    user_gave_chapters = (
        "시험범위" in user_compact
        or "범위" in user_compact
        or re.search(r'\d{1,2}\s*장', user_msg) is not None
    )

    return (ai_asked_exam_date and user_gave_date) or (ai_asked_chapters and user_gave_chapters)


def extract_exam_date_from_text(text: str) -> Optional[str]:
    if not text:
        return None

    today = datetime.now()

    match = re.search(r'(\d{4})[-./](\d{1,2})[-./](\d{1,2})', text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    match = re.search(r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일', text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    match = re.search(r'(\d{1,2})\s*월\s*(\d{1,2})\s*일', text)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        return f"{today.year:04d}-{month:02d}-{day:02d}"

    return None


def extract_exam_chapters_from_text(text: str) -> list[int]:
    if not text:
        return []

    chapters = set()

    # 9장, 10장, 11장, 13장
    for n in re.findall(r'(\d{1,2})\s*장', text):
        chapters.add(int(n))

    # 시험범위는 9,10,11,13장이야
    scope_patterns = [
        r'(?:시험\s*범위|시험범위|범위)\s*(?:는|가|은)?\s*([0-9,\s]+)\s*장',
        r'(?:시험\s*범위|시험범위|범위)[^\n]*?([0-9,\s]+)\s*장'
    ]

    for pattern in scope_patterns:
        match = re.search(pattern, text)
        if match:
            nums = re.findall(r'\d{1,2}', match.group(1))
            for n in nums:
                chapters.add(int(n))

    # 9~13장, 9-13장
    range_match = re.search(r'(\d{1,2})\s*[~-]\s*(\d{1,2})\s*장', text)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))

        if start <= end:
            for n in range(start, end + 1):
                chapters.add(n)

    return sorted(chapters)


def extract_cram_days(text: str) -> int:
    if not text:
        return 7

    compact = text.replace(" ", "")

    if "일주일" in compact or "1주일" in compact or "한주" in compact:
        return 7

    match = re.search(r'(\d+)\s*주', text)
    if match:
        return int(match.group(1)) * 7

    match = re.search(r'(\d+)\s*일\s*(동안|간)', text)
    if match:
        return int(match.group(1))

    return 7


def get_cram_dates(exam_date: str, days: int) -> list[str]:
    exam_dt = datetime.strptime(exam_date, "%Y-%m-%d")
    start_dt = exam_dt - timedelta(days=days)

    return [
        (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(days)
    ]


def fetch_information_security_chapter_items(chapter_numbers: list[int]) -> list[dict]:
    """
    현재 textbook.db 구조 기준.

    textbooks:
    - id
    - subject
    - book_title

    textbook_chapters:
    - id
    - textbook_id
    - parent_id
    - depth
    - chapter_order
    - title
    - page
    - importance
    """

    if not chapter_numbers:
        return []

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
            ("%정보보호%",)
        )

        textbook = cursor.fetchone()

        if textbook is None:
            return []

        textbook_id = textbook["id"]

        placeholders = ",".join(["?"] * len(chapter_numbers))

        cursor.execute(
            f"""
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
              AND depth = 1
              AND chapter_order IN ({placeholders})
            ORDER BY chapter_order ASC, id ASC
            """,
            [textbook_id] + chapter_numbers
        )

        chapter_rows = cursor.fetchall()

        result = []

        for chapter in chapter_rows:
            chapter_id = chapter["id"]
            chapter_no = chapter["chapter_order"]
            chapter_title = chapter["title"]

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
                  AND parent_id = ?
                ORDER BY depth ASC, chapter_order ASC, id ASC
                """,
                (textbook_id, chapter_id)
            )

            child_rows = cursor.fetchall()

            if child_rows:
                for child in child_rows:
                    child_title = child["title"]
                    page_text = f" p.{child['page']}" if child["page"] is not None else ""

                    result.append({
                        "chapter_number": chapter_no,
                        "content": f"{chapter_no}장 {chapter_title} - {child_title}{page_text}"
                    })
            else:
                result.append({
                    "chapter_number": chapter_no,
                    "content": f"{chapter_no}장 {chapter_title}"
                })

        found_chapters = {item["chapter_number"] for item in result}

        # DB에 일부 장이 빠져 있어도 시험범위 장 번호는 반드시 포함
        for chapter_no in chapter_numbers:
            if chapter_no not in found_chapters:
                result.append({
                    "chapter_number": chapter_no,
                    "content": f"{chapter_no}장 핵심 개념 정리"
                })

        result.sort(key=lambda x: x["chapter_number"])

        return result

    except Exception:
        traceback.print_exc()

        return [
            {
                "chapter_number": chapter_no,
                "content": f"{chapter_no}장 핵심 개념 정리"
            }
            for chapter_no in chapter_numbers
        ]

    finally:
        conn.close()


def build_information_security_cram_plan(
    exam_date: str,
    chapter_numbers: list[int],
    days: int
) -> list[dict]:
    """
    시험범위 장들을 days일에 빠짐없이 분배한다.
    각 날짜마다 task를 1개로 합치지 않고, 장/소목차별로 task를 나누어 생성한다.
    """

    dates = get_cram_dates(exam_date, days)
    items = fetch_information_security_chapter_items(chapter_numbers)

    if not items:
        items = [
            {
                "chapter_number": chapter_no,
                "content": f"{chapter_no}장 핵심 개념 정리"
            }
            for chapter_no in chapter_numbers
        ]

    plan = []

    grouped_items = [[] for _ in dates]

    # 목차 항목을 날짜별로 순서대로 분배
    for index, item in enumerate(items):
        day_index = index % len(dates)
        grouped_items[day_index].append(item)

    for index, target_date in enumerate(dates):
        day_items = grouped_items[index]

        tasks = []

        if day_items:
            for item in day_items:
                content = item["content"]

                # 이미 "9장"이 포함되어 있으므로 그대로 사용
                tasks.append(f"정보보호 {content} 외 1시간")
        else:
            all_chapters = ", ".join(f"{chapter_no}장" for chapter_no in chapter_numbers)
            tasks.append(f"정보보호 {all_chapters} 복습 및 기출문제 풀이 외 1시간")

        # 시험 전날은 전체 복습 task를 별도로 추가
        if index == len(dates) - 1:
            all_chapters = ", ".join(f"{chapter_no}장" for chapter_no in chapter_numbers)
            tasks.append(f"정보보호 {all_chapters} 전체 복습 및 약점 정리 외 1시간")

        plan.append({
            "target_date": target_date,
            "title": "정보보호 벼락치기 계획",
            "subject": "정보보호",
            "tasks": tasks
        })

    # 안전장치: 모든 시험범위 장이 최소 1번 이상 task에 들어갔는지 확인
    plan_text = "\n".join(
        task
        for day in plan
        for task in day["tasks"]
    )

    missing_chapters = [
        chapter_no
        for chapter_no in chapter_numbers
        if f"{chapter_no}장" not in plan_text
    ]

    if missing_chapters:
        for index, chapter_no in enumerate(missing_chapters):
            target_index = index % len(plan)
            plan[target_index]["tasks"].append(
                f"정보보호 {chapter_no}장 핵심 개념 정리 외 1시간"
            )

    return plan

def format_cram_plan_message(
    exam_date: str,
    chapter_numbers: list[int],
    plan: list[dict]
) -> str:
    lines = []

    lines.append("정보보호 시험 대비 벼락치기 학습 계획입니다.")
    lines.append(f"시험일: {exam_date}")
    lines.append(f"시험범위: {', '.join(f'{chapter_no}장' for chapter_no in chapter_numbers)}")
    lines.append("")

    for index, item in enumerate(plan, start=1):
        lines.append(f"{index}일차 ({item['target_date']})")

        for task in item["tasks"]:
            lines.append(f"- {task}")

        lines.append("- 공부 방법: 핵심 개념을 먼저 정리한 뒤, 헷갈리는 용어와 차이점을 따로 표시하세요.")
        lines.append("")

    lines.append("이 일정대로 스케줄에 추가해 드릴까요?")

    return "\n".join(lines).strip()


def try_build_cram_plan_from_context(combined_text: str):
    if not is_exam_cram_context(combined_text):
        return None

    exam_date = extract_exam_date_from_text(combined_text)
    chapter_numbers = extract_exam_chapters_from_text(combined_text)
    days = extract_cram_days(combined_text)

    subject = detect_subject_from_user_message(combined_text, "정보보호")

    if subject == "기타":
        subject = "정보보호"

    if subject != "정보보호":
        return None

    if not exam_date and not chapter_numbers:
        return {
            "need_more_info": True,
            "message": "시험 날짜와 시험범위를 알려주세요. 예: 시험은 6월 15일이고 시험범위는 9장, 10장, 11장, 13장이야"
        }

    if not exam_date:
        return {
            "need_more_info": True,
            "message": "시험 날짜를 알려주세요. 예: 시험은 6월 15일이야"
        }

    if not chapter_numbers:
        return {
            "need_more_info": True,
            "message": "시험범위를 알려주세요. 예: 시험범위는 9장, 10장, 11장, 13장이야"
        }

    plan = build_information_security_cram_plan(
        exam_date=exam_date,
        chapter_numbers=chapter_numbers,
        days=days
    )

    ai_response = format_cram_plan_message(
        exam_date=exam_date,
        chapter_numbers=chapter_numbers,
        plan=plan
    )

    return {
        "need_more_info": False,
        "message": ai_response,
        "plan": plan
    }


# =========================================================
# 여러 날짜 스케줄 추출
# =========================================================

def clean_schedule_task_text(text: str) -> str:
    text = str(text).strip()

    remove_words = [
        "추가해주고",
        "추가해줘",
        "추가하고",
        "추가해",
        "등록해주고",
        "등록해줘",
        "등록하고",
        "등록해",
        "넣어주고",
        "넣어줘",
        "저장해주고",
        "저장해줘",
        "스케줄에",
        "스케쥴에",
        "일정에",
        "해줘",
        "하고",
        "그리고",
        "랑",
        "이랑",
        "도"
    ]

    for word in remove_words:
        text = text.replace(word, " ")

    text = re.sub(r'\s+', ' ', text).strip()

    return text


def make_task_content_from_piece(piece: str):
    piece = clean_schedule_task_text(piece)

    duration_seconds = parse_duration_from_text(piece, DEFAULT_TASK_SECONDS)
    time_text = seconds_to_korean_time(duration_seconds)

    subject = detect_subject_from_user_message(piece, "기타")

    if subject == "기타":
        match = re.search(r'([가-힣A-Za-z0-9+#]+)\s*공부', piece)

        if match:
            subject = normalize_subject_korean(match.group(1))

    if subject == "기타":
        temp = piece.replace("공부", "").strip()
        subject = normalize_subject_korean(temp) if temp else "학습"

    return subject, f"{subject} 공부 외 {time_text}"


def extract_multiple_schedule_items(user_msg: str):
    """
    한 문장 안에 오늘/내일/모레 등 여러 날짜의 공부 계획이 들어있을 때 분리한다.

    예:
    오늘 운영체제 공부하고 내일 정보보호 공부할거야
    -> 오늘: 운영체제 공부 외 1시간
    -> 내일: 정보보호 공부 외 1시간
    """

    items = []

    if not user_msg:
        return items

    today = datetime.now()

    date_keywords = [
        ("오늘", today),
        ("내일", today + timedelta(days=1)),
        ("모레", today + timedelta(days=2)),
    ]

    found_dates = []

    for keyword, date_value in date_keywords:
        for match in re.finditer(keyword, user_msg):
            found_dates.append({
                "keyword": keyword,
                "start": match.start(),
                "end": match.end(),
                "date": date_value.strftime("%Y-%m-%d")
            })

    found_dates.sort(key=lambda x: x["start"])

    if len(found_dates) < 2:
        return items

    for i, date_info in enumerate(found_dates):
        start_index = date_info["end"]

        if i + 1 < len(found_dates):
            end_index = found_dates[i + 1]["start"]
        else:
            end_index = len(user_msg)

        part = user_msg[start_index:end_index].strip()

        # 불필요한 표현 제거
        remove_words = [
            "하고",
            "그리고",
            "에는",
            "은",
            "는",
            "을",
            "를",
            "할거야",
            "할 거야",
            "할거라고",
            "할 거라고",
            "하겠다",
            "스케줄",
            "스케쥴",
            "일정",
            "추가해줘",
            "추가해",
            "추가",
            "등록해줘",
            "저장해줘",
            ".",
            ","
        ]

        for word in remove_words:
            part = part.replace(word, " ")

        part = re.sub(r"\s+", " ", part).strip()

        if not part:
            continue

        subject = detect_subject_from_user_message(part, "기타")

        if subject == "기타":
            subject_match = re.search(r"([가-힣A-Za-z0-9+#]+)\s*공부", part)

            if subject_match:
                subject = subject_match.group(1).strip()

        if subject == "기타":
            subject_match = re.search(r"([가-힣A-Za-z0-9+#]+)\s*학습", part)

            if subject_match:
                subject = subject_match.group(1).strip()

        if subject == "기타":
            words = part.split()

            if words:
                subject = words[0].strip()

        if not subject or subject == "기타":
            subject = "학습"

        duration_seconds = parse_duration_from_text(part, DEFAULT_TASK_SECONDS)
        time_text = seconds_to_korean_time(duration_seconds)

        if "공부" in user_msg:
            task = f"{subject} 공부 외 {time_text}"
        else:
            task = f"{subject} 학습 외 {time_text}"

        items.append({
            "target_date": date_info["date"],
            "subject": subject,
            "task": task
        })

    return items

def extract_period_schedule_items(user_msg: str):
    """
    기간형 스케줄을 날짜별로 분리한다.

    예:
    오늘부터 일주일동안 파이썬 공부
    내일부터 3일동안 정보보호 공부
    5월 28일부터 30일까지 수학 공부
    """

    items = []

    if not user_msg:
        return items

    today = datetime.now()
    compact = user_msg.replace(" ", "")

    start_date = None
    days_count = None

    # -----------------------------
    # 1. 시작일 찾기
    # -----------------------------
    if "오늘부터" in compact:
        start_date = today

    elif "내일부터" in compact:
        start_date = today + timedelta(days=1)

    elif "모레부터" in compact:
        start_date = today + timedelta(days=2)

    else:
        start_match = re.search(r'(\d{1,2})월(\d{1,2})일부터', compact)

        if start_match:
            month = int(start_match.group(1))
            day = int(start_match.group(2))
            start_date = datetime(today.year, month, day)

    if start_date is None:
        return items

    # -----------------------------
    # 2. 기간 찾기
    # -----------------------------
    if "일주일동안" in compact or "일주일간" in compact or "일주일치" in compact or "1주일동안" in compact or "1주일간" in compact or "1주일치" in compact or "한주동안" in compact:
        days_count = 7

    else:
        day_count_match = re.search(r'(\d+)일(?:동안|간|치)', compact)

        if day_count_match:
            days_count = int(day_count_match.group(1))

    # 예: 5월 28일부터 30일까지
    if days_count is None:
        range_match = re.search(r'(\d{1,2})월(\d{1,2})일부터(\d{1,2})일까지', compact)

        if range_match:
            month = int(range_match.group(1))
            start_day = int(range_match.group(2))
            end_day = int(range_match.group(3))

            start_date = datetime(today.year, month, start_day)
            end_date = datetime(today.year, month, end_day)

            days_count = (end_date - start_date).days + 1

    # 예: 5월 28일부터 5월 30일까지
    if days_count is None:
        full_range_match = re.search(
            r'(\d{1,2})월(\d{1,2})일부터(\d{1,2})월(\d{1,2})일까지',
            compact
        )

        if full_range_match:
            start_month = int(full_range_match.group(1))
            start_day = int(full_range_match.group(2))
            end_month = int(full_range_match.group(3))
            end_day = int(full_range_match.group(4))

            start_date = datetime(today.year, start_month, start_day)
            end_date = datetime(today.year, end_month, end_day)

            days_count = (end_date - start_date).days + 1

    if days_count is None or days_count <= 0:
        return items

    if days_count > 60:
        days_count = 60

    # -----------------------------
    # 3. 과목 / 시간 찾기
    # -----------------------------
    subject = detect_subject_from_user_message(user_msg, "기타")

    if subject == "기타":
        subject_match = re.search(r'([가-힣A-Za-z0-9+#]+)\s*공부', user_msg)

        if subject_match:
            subject = subject_match.group(1).strip()

    if subject == "기타":
        subject = "학습"

    duration_seconds = parse_duration_from_text(user_msg, DEFAULT_TASK_SECONDS)
    time_text = seconds_to_korean_time(duration_seconds)

    # -----------------------------
    # 4. 날짜별 item 생성
    # -----------------------------
    for i in range(days_count):
        target_date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")

        if "공부" in user_msg:
            task = f"{subject} 공부 외 {time_text}"
        else:
            task = f"{subject} 학습 외 {time_text}"

        items.append({
            "target_date": target_date,
            "subject": subject,
            "task": task
        })

    return items

def make_range_schedule_items(start_date: datetime, end_date: datetime, task_piece: str):
    if end_date < start_date:
        return []

    day_count = (end_date - start_date).days + 1

    if day_count > 60:
        return []

    subject, task_content = make_task_content_from_piece(task_piece)

    result = []

    for i in range(day_count):
        target_date = start_date + timedelta(days=i)

        result.append({
            "target_date": target_date.strftime("%Y-%m-%d"),
            "subject": subject,
            "task": task_content
        })

    return result


def extract_date_range_schedule_items(user_msg: str):
    if not user_msg:
        return []

    today = datetime.now()

    match = re.search(
        r'(\d{1,2})\s*월\s*(\d{1,2})\s*일?\s*부터\s*(\d{1,2})\s*일?\s*까지\s*(.+)',
        user_msg
    )

    if match:
        start_month = int(match.group(1))
        start_day = int(match.group(2))
        end_month = start_month
        end_day = int(match.group(3))
        task_piece = match.group(4).strip()

        start_date = datetime(today.year, start_month, start_day)
        end_date = datetime(today.year, end_month, end_day)

        return make_range_schedule_items(start_date, end_date, task_piece)

    match = re.search(
        r'(\d{1,2})\s*월\s*(\d{1,2})\s*일?\s*부터\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일?\s*까지\s*(.+)',
        user_msg
    )

    if match:
        start_month = int(match.group(1))
        start_day = int(match.group(2))
        end_month = int(match.group(3))
        end_day = int(match.group(4))
        task_piece = match.group(5).strip()

        start_date = datetime(today.year, start_month, start_day)
        end_date = datetime(today.year, end_month, end_day)

        return make_range_schedule_items(start_date, end_date, task_piece)

    return []


# =========================================================
# AI 응답 파싱
# =========================================================

def parse_long_term_schedule(ai_message: str):
    """
    AI가 추천한 장기/벼락치기 계획을 스케줄 저장용 데이터로 파싱한다.

    지원 형식:

    1일차 (2026-06-08)
    - 정보보호 9장 인증 시스템 p.390 외 1시간
    - 정보보호 9장 방화벽 p.397 외 1시간

    2일차 (2026-06-09)
    - 정보보호 10장 IoT 보안 p.434 외 1시간

    또는:

    6월 8일: 정보보호 9장 인증 시스템 외 1시간
    2026년 6월 8일: 정보보호 9장 인증 시스템 외 1시간
    1일차: 정보보호 9장 인증 시스템 외 1시간
    """

    days_data = []

    if not ai_message:
        return days_data

    today = datetime.now()
    current_date = None

    for line in ai_message.split("\n"):
        original_line = line.strip()
        clean_line = original_line.replace("*", "").strip()

        if not clean_line:
            continue

        # 안내 문구는 제외
        if "스케줄에 추가해 드릴까요" in clean_line:
            continue

        if "추가해 드릴까요" in clean_line:
            continue

        if "공부 방법" in clean_line:
            continue

        if "학습 방법" in clean_line:
            continue

        if "핵심 개념을 먼저 정리" in clean_line:
            continue

        if "헷갈리는 용어" in clean_line:
            continue

        # -------------------------------------------------
        # 1. 1일차 (2026-06-08)
        # -------------------------------------------------
        match_day_header_with_date = re.search(
            r'(\d+)\s*일차\s*\((\d{4}-\d{2}-\d{2})\)',
            clean_line
        )

        if match_day_header_with_date:
            current_date = match_day_header_with_date.group(2)
            continue

        # -------------------------------------------------
        # 2. 1일차: 정보보호 ... 외 1시간
        # -------------------------------------------------
        match_day_inline = re.search(
            r'(\d+)\s*일차\s*[:：]\s*(.+)',
            clean_line
        )

        if match_day_inline:
            day_num = int(match_day_inline.group(1))
            task_content = match_day_inline.group(2).strip()

            current_date = (today + timedelta(days=day_num - 1)).strftime("%Y-%m-%d")

            if task_content and "외" in task_content:
                days_data.append({
                    "date": current_date,
                    "task": task_content
                })

            continue

        # -------------------------------------------------
        # 3. 2026년 6월 8일: 정보보호 ... 외 1시간
        # -------------------------------------------------
        match_full_date = re.search(
            r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*[:：]\s*(.+)',
            clean_line
        )

        if match_full_date:
            year = int(match_full_date.group(1))
            month = int(match_full_date.group(2))
            day = int(match_full_date.group(3))
            task_content = match_full_date.group(4).strip()

            current_date = f"{year:04d}-{month:02d}-{day:02d}"

            if task_content and "외" in task_content:
                days_data.append({
                    "date": current_date,
                    "task": task_content
                })

            continue

        # -------------------------------------------------
        # 4. 6월 8일: 정보보호 ... 외 1시간
        # -------------------------------------------------
        match_month_day = re.search(
            r'(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*[:：]\s*(.+)',
            clean_line
        )

        if match_month_day:
            month = int(match_month_day.group(1))
            day = int(match_month_day.group(2))
            task_content = match_month_day.group(3).strip()

            current_date = f"{today.year:04d}-{month:02d}-{day:02d}"

            if task_content and "외" in task_content:
                days_data.append({
                    "date": current_date,
                    "task": task_content
                })

            continue

        # -------------------------------------------------
        # 5. 날짜 헤더 아래의 task 줄
        # 예:
        # - 정보보호 9장 인증 시스템 p.390 외 1시간
        # -------------------------------------------------
        if current_date and clean_line.startswith("-"):
            task_content = clean_line[1:].strip()

            if not task_content:
                continue

            # task 시간 정보가 있는 줄만 저장
            if "외" not in task_content:
                continue

            days_data.append({
                "date": current_date,
                "task": task_content
            })

            continue

    return days_data

def parse_today_recommendation(ai_message: str):
    """
    오늘 추천 학습 계획을 파싱한다.

    예:
    파이썬 - 핵심 개념 정리 외 30분
    파이썬 - 예제 실습 외 40분

    장기 계획의 '1일차', '2일차' 형식이나
    '- 공부 내용', '- 학습 방법' 같은 설명 줄은 제외한다.
    """

    tasks = []

    if not ai_message:
        return tasks

    for line in ai_message.split("\n"):
        clean_line = line.replace("*", "").strip()

        if not clean_line:
            continue

        # 설명 줄 제외
        if clean_line.startswith("-"):
            continue

        # 장기 계획/벼락치기 날짜 줄 제외
        if re.search(r'\d+일차', clean_line):
            continue

        # 오늘 추천 항목만 수집
        if " - " in clean_line and "외" in clean_line:
            tasks.append(clean_line)

    return tasks

def make_single_schedule_task_from_user_message(user_msg: str, subject: str) -> str:
    duration_seconds = parse_duration_from_text(user_msg, DEFAULT_TASK_SECONDS)
    time_text = seconds_to_korean_time(duration_seconds)

    if subject == "기타":
        subject = detect_subject_from_user_message(user_msg, "기타")

    if subject == "기타":
        subject = "학습"

    return f"{subject} 공부 외 {time_text}"


# =========================================================
# Ollama 의도 추출
# =========================================================

async def extract_intent_data(user_msg: str):
    today_str = datetime.now().strftime("%Y-%m-%d")

    extraction_prompt = f"""
당신은 학습 스케줄러입니다. 오늘 날짜는 {today_str}입니다.
사용자의 마지막 메시지만 보고 JSON만 출력하세요.

[분류 규칙]

1. recommend_request
오늘 하루 공부 추천을 원할 때.
출력:
{{"type":"recommend_request","subject":"과목명"}}

2. long_term_request
일주일, 한 달, 2주, 7일 동안 같은 기간 계획을 원할 때.
단, 시험/벼락치기 계획은 exam_cram_request로 분류하세요.
출력:
{{"type":"long_term_request","subject":"과목명","period":"기간"}}

3. exam_cram_request
시험 날짜와 시험 범위를 바탕으로 벼락치기 계획을 원할 때.
출력:
{{"type":"exam_cram_request","subject":"정보보호"}}

4. schedule
사용자가 직접 일정 추가, 스케줄 추가, 등록, 저장을 요청할 때.
출력:
{{"type":"schedule","subject":"과목명","target_date":"YYYY-MM-DD","tasks":["과목명 공부 외 1시간"]}}

5. accept_recommendation
직전 추천을 수락할 때.
출력:
{{"type":"accept_recommendation","subject":"기타"}}

6. study
이미 공부한 시간을 기록할 때.
출력:
{{"type":"study","subject":"과목명","duration":7200}}

7. none
그 외 일반 대화.
출력:
{{"type":"none","subject":"기타"}}

[중요 규칙]
- 반드시 JSON만 출력하세요.
- 설명, 마크다운, 코드블록을 쓰지 마세요.
- subject는 반드시 한국어로 쓰세요.
- 시간이 없으면 기본 1시간입니다.
"""

    try:
        response = await ollama_client.chat(
            model="llama3",
            messages=[
                {"role": "system", "content": extraction_prompt},
                {"role": "user", "content": user_msg}
            ],
            format="json",
            options={"temperature": 0.0}
        )

        data = json.loads(response["message"]["content"])

        if "type" not in data:
            data["type"] = "none"

        if "subject" not in data:
            data["subject"] = "기타"

        data["subject"] = normalize_subject_korean(data.get("subject", "기타"))

        return data

    except Exception:
        return {
            "type": "none",
            "subject": "기타"
        }


# =========================================================
# Ollama 일반 응답
# =========================================================

async def ask_ollama(user_msg: str, history: list, system_hint: str, use_history: bool = False):
    system_prompt = f"""
당신은 사용자의 학습을 돕는 AI 비서입니다.

[절대 규칙]
1. 모든 답변은 반드시 한국어로만 작성하세요.
2. 영어 제목, 영어 목차, 영어 설명을 쓰지 마세요.
3. 과목명이 파이썬이면 Python이라고 쓰지 말고 "파이썬"이라고 쓰세요.
4. 과목명이 정보보호이면 Information Security라고 쓰지 말고 "정보보호"라고 쓰세요.
5. 가능한 한 모든 개념명을 한국어로 쓰세요.
6. 사용자가 스케줄 추가를 요청했고 시스템 명령이 있다면, 시스템 명령의 문장만 답하세요.
7. "Syntax", "Variables", "Data Types", "Control Structures", "Functions", "Modules" 같은 영어 표현을 쓰지 마세요.
8. 답변에 초 단위 숫자를 쓰지 마세요.
9. 오늘 계획에는 "1일차", "2일차"를 쓰지 마세요.
10. 장기 계획에는 "1일차", "2일차"를 사용해도 됩니다.

{system_hint}
"""

    messages = [{"role": "system", "content": system_prompt}]

    if use_history:
        for role, msg in history:
            messages.append({
                "role": role,
                "content": msg
            })

    messages.append({
        "role": "user",
        "content": user_msg
    })

    try:
        response = await ollama_client.chat(
            model="llama3",
            messages=messages,
            options={"temperature": 0.0}
        )

        return response["message"]["content"]

    except Exception:
        traceback.print_exc()
        return "응답 생성 중 오류가 발생했습니다."


# =========================================================
# schedule.db 저장
# =========================================================

def save_schedule_task(
    conn_sch,
    target_date: str,
    title: str,
    task_content: str,
    subject: str,
    merge_same_day: bool = False
):
    """
    schedule.db에 스케줄 1개와 task 1개를 저장한다.

    merge_same_day=False:
        같은 날짜에 기존 스케줄이 있어도 새 스케줄을 따로 만든다.
        예: 사용자가 직접 추가한 단일 스케줄

    merge_same_day=True:
        같은 날짜 + 같은 제목의 스케줄이 이미 있으면 기존 스케줄에 task만 추가한다.
        예: AI가 추천한 벼락치기/장기 계획
    """

    cursor_sch = conn_sch.cursor()

    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")

    if not title:
        title = "학습 계획"

    if not task_content:
        if subject and subject != "기타":
            task_content = f"{subject} 공부 외 1시간"
        else:
            task_content = "공부 외 1시간"

    parsed_subject, parsed_seconds = parse_task_time(task_content, subject)
    parsed_subject = normalize_subject_korean(parsed_subject)

    schedule_id = None

    # merge_same_day=True일 때만 기존 스케줄을 찾아서 재사용한다.
    if merge_same_day:
        cursor_sch.execute(
            """
            SELECT id
            FROM schedules
            WHERE target_date = ?
              AND title = ?
              AND deleted_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (target_date, title)
        )

        row = cursor_sch.fetchone()

        if row:
            try:
                schedule_id = row["id"]
            except Exception:
                schedule_id = row[0]

    # 기존 스케줄을 재사용하지 않거나, 찾지 못했으면 새 스케줄 생성
    if schedule_id is None:
        cursor_sch.execute(
            """
            INSERT INTO schedules (
                target_date,
                title
            )
            VALUES (?, ?)
            """,
            (target_date, title)
        )

        schedule_id = cursor_sch.lastrowid

    # 해당 스케줄에 task 추가
    cursor_sch.execute(
        """
        INSERT INTO tasks (
            schedule_id,
            content,
            subject,
            target_seconds,
            is_completed
        )
        VALUES (?, ?, ?, ?, 0)
        """,
        (
            schedule_id,
            task_content,
            parsed_subject,
            parsed_seconds
        )
    )

    return schedule_id

def verify_schedule_saved(conn_sch, schedule_id: int) -> bool:
    """
    스케줄과 task가 실제로 저장되었는지 확인한다.
    """

    cursor_sch = conn_sch.cursor()

    cursor_sch.execute(
        """
        SELECT COUNT(*)
        FROM schedules s
        JOIN tasks t ON t.schedule_id = s.id
        WHERE s.id = ?
          AND s.deleted_at IS NULL
        """,
        (schedule_id,)
    )

    count = cursor_sch.fetchone()[0]

    return count > 0

def save_schedule_with_tasks(conn_sch, target_date: str, title: str, tasks: list, subject: str, merge_same_day: bool = False):
    """
    한 날짜에 여러 task가 있을 때 schedule 1개에 여러 task를 저장한다.

    merge_same_day=False:
        같은 날짜에 기존 스케줄이 있어도 새 schedule을 만든다.
        단일 공부 추가가 기존 날짜 스케줄에 합쳐지는 문제를 막는다.

    merge_same_day=True:
        같은 날짜 + 같은 title의 기존 schedule이 있으면 그 schedule에 task만 추가한다.
    """

    if not tasks:
        return None

    cursor_sch = conn_sch.cursor()
    schedule_id = None

    if merge_same_day:
        cursor_sch.execute(
            """
            SELECT id
            FROM schedules
            WHERE target_date = ?
              AND title = ?
              AND deleted_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (target_date, title)
        )
        row = cursor_sch.fetchone()
        if row:
            try:
                schedule_id = row["id"]
            except Exception:
                schedule_id = row[0]

    if schedule_id is None:
        cursor_sch.execute(
            """
            INSERT INTO schedules (target_date, title)
            VALUES (?, ?)
            """,
            (target_date, title)
        )
        schedule_id = cursor_sch.lastrowid

    for task_content in tasks:
        task_content = str(task_content).strip()

        if not task_content:
            continue

        parsed_subject, parsed_seconds = parse_task_time(task_content, subject)
        parsed_subject = normalize_subject_korean(parsed_subject)

        cursor_sch.execute(
            """
            INSERT INTO tasks (
                schedule_id,
                content,
                subject,
                target_seconds,
                is_completed
            )
            VALUES (?, ?, ?, ?, 0)
            """,
            (
                schedule_id,
                task_content,
                parsed_subject,
                parsed_seconds
            )
        )

    return schedule_id

def get_last_assistant_message(history: list):
    for role, msg in reversed(history):
        if role == "assistant":
            return msg

    return ""


def save_chat_message(conn_chat, role: str, message: str):
    cursor_chat = conn_chat.cursor()

    cursor_chat.execute(
        """
        INSERT INTO chat_history (role, message)
        VALUES (?, ?)
        """,
        (role, message)
    )


# =========================================================
# 메인 채팅 엔드포인트
# =========================================================

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    user_msg = request.user_message

    conn_chat = get_chat_db_connection(user_id)
    conn_study = get_study_db_connection(user_id)
    conn_sch = get_schedule_db_connection(user_id)

    try:
        cursor_chat = conn_chat.cursor()

        cursor_chat.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn_chat.commit()

        if is_clear_history_request(user_msg):
            cursor_chat.execute("DELETE FROM chat_history")
            conn_chat.commit()

            return ChatResponse(ai_response="이전 대화 기록을 초기화했습니다.")

        cursor_chat.execute(
            """
            SELECT role, message
            FROM chat_history
            ORDER BY id DESC
            LIMIT 20
            """
        )

        raw_history = cursor_chat.fetchall()
        history = [[row[0], row[1]] for row in reversed(raw_history)]

        user_history_text = "\n".join(
            msg
            for role, msg in history
            if role == "user"
        )

        combined_text = user_history_text + "\n" + user_msg

        extracted = await extract_intent_data(user_msg)

        # 직전 AI 답변 확인
        last_ai_msg = get_last_assistant_message(history)

        # -------------------------------------------------
        # 현재 메시지 기준 의도 보정
        # 중요:
        # "추가해줘"는 새 스케줄 생성 요청이 아니라,
        # 직전 추천 계획을 저장하는 요청일 수 있다.
        # -------------------------------------------------

        # -------------------------------------------------
        # 현재 메시지 기준 의도 보정
        # 중요:
        # 1. 사용자가 날짜/기간/과목/공부 내용을 직접 말했으면 무조건 새 스케줄 추가
        # 2. "추가해줘", "그대로 추가해줘"처럼 짧은 말만 직전 추천 수락
        # -------------------------------------------------

        # 날짜/기간/공부 내용이 있는 직접 스케줄 요청인지 먼저 확인
        period_items_preview = extract_period_schedule_items(user_msg)
        multiple_items_preview = extract_multiple_schedule_items(user_msg)

        if period_items_preview or multiple_items_preview:
            # 예:
            # 오늘부터 일주일동안 파이썬 공부할거야. 스케줄 추가해줘
            # 오늘 운영체제 공부하고 내일 정보보호 공부할거야. 스케줄 추가해줘
            extracted["type"] = "schedule"

        elif is_schedule_add_request(user_msg) and has_concrete_schedule_content(user_msg):
            # 예:
            # 오늘 파이썬 3시간 공부할거라고 스케줄에 추가해줘
            # 내일 수학 공부 추가해줘
            extracted["type"] = "schedule"

        elif is_accepting_previous_recommendation(user_msg):
            # 예:
            # 추가해줘
            # 그대로 추가해줘
            # 이대로 추가해줘
            extracted["type"] = "accept_recommendation"

        elif is_schedule_add_request(user_msg) and last_ai_asks_to_add_schedule(last_ai_msg):
            # 직전 AI가 "추가해드릴까요?"라고 했고,
            # 사용자가 구체적인 새 내용을 말하지 않은 경우만 추천 수락
            extracted["type"] = "accept_recommendation"

        elif is_schedule_add_request(user_msg):
            extracted["type"] = "schedule"

        elif has_long_term_period(user_msg):
            extracted["type"] = "long_term_request"
            extracted["period"] = extract_period_text(user_msg)

        intent_type = extracted.get("type", "none")
       # -------------------------------------------------
        # 정보보호 시험/벼락치기 계획 생성
        # 중요:
        # 현재 메시지가 벼락치기 요청일 때만 실행한다.
        # 이전 대화에 벼락치기 내용이 남아 있어도,
        # 사용자가 "다른 거 추천해줘"라고 하면 다시 벼락치기로 들어가면 안 된다.
        # -------------------------------------------------

        period_items_preview = extract_period_schedule_items(user_msg)
        multiple_items_preview = extract_multiple_schedule_items(user_msg)

        if period_items_preview or multiple_items_preview:
            intent_type = "schedule"
            extracted["type"] = "schedule"

        should_try_cram_plan = (
            intent_type not in ["accept_recommendation", "schedule"]
            and (
                is_current_exam_cram_request(user_msg)
                or is_answering_cram_missing_info(last_ai_msg, user_msg)
            )
        )

        if should_try_cram_plan:
            cram_result = try_build_cram_plan_from_context(combined_text)

            if cram_result is not None:
                ai_response = cram_result["message"]

                save_chat_message(conn_chat, "user", user_msg)
                save_chat_message(conn_chat, "assistant", ai_response)
                conn_chat.commit()

                return ChatResponse(ai_response=ai_response)
        elif has_long_term_period(user_msg):
            extracted["type"] = "long_term_request"
            extracted["period"] = extract_period_text(user_msg)

        intent_type = extracted.get("type", "none")

        core_subject = detect_subject_from_user_message(
            user_msg,
            extracted.get("subject", "기타")
        )

        fixed_ai_response = None
        system_hint = ""
        use_history_for_answer = False

        # -------------------------------------------------
        # 직전 추천 수락
        # -------------------------------------------------

        if intent_type == "accept_recommendation":
            # 안전장치:
            # 현재 사용자 메시지 자체가 기간형/여러 날짜 스케줄이면
            # 직전 추천 수락이 아니라 직접 스케줄 추가로 돌린다.
            period_items_now = extract_period_schedule_items(user_msg)
            multiple_items_now = extract_multiple_schedule_items(user_msg)

            if period_items_now or multiple_items_now:
                intent_type = "schedule"
            
            last_ai_msg = get_last_assistant_message(history)

            parsed_long_term = parse_long_term_schedule(last_ai_msg)
            parsed_today = parse_today_recommendation(last_ai_msg)

            if parsed_long_term:
                inferred_subject = core_subject

                if inferred_subject == "기타":
                    for day_info in parsed_long_term:
                        inferred_subject, _ = parse_task_time(day_info["task"], "기타")
                        if inferred_subject != "기타":
                            break

                # 날짜별로 task 묶기
                grouped_by_date = {}

                for day_info in parsed_long_term:
                    target_date = day_info["date"]
                    task_content = day_info["task"]

                    grouped_by_date.setdefault(target_date, [])
                    grouped_by_date[target_date].append(task_content)

                # 같은 날짜는 schedule 1개, task 여러 개로 저장
                for target_date, task_list in grouped_by_date.items():
                    save_schedule_with_tasks(
                        conn_sch=conn_sch,
                        target_date=target_date,
                        title="학습 계획",
                        tasks=task_list,
                        subject=inferred_subject,
                        merge_same_day=True
                    )

                conn_sch.commit()
                if is_cram_schedule_request(user_msg):
                    fixed_ai_response = "스케줄을 추가했습니다."
                else:
                    fixed_ai_response = "기간 학습 계획을 날짜별로 추가했습니다."

            elif parsed_today:
                target_date = parse_target_date_from_text(user_msg)

                inferred_subject = core_subject

                if inferred_subject == "기타":
                    for task_content in parsed_today:
                        inferred_subject, _ = parse_task_time(task_content, "기타")
                        if inferred_subject != "기타":
                            break

                save_schedule_with_tasks(
                    conn_sch=conn_sch,
                    target_date=target_date,
                    title="오늘의 추천 학습 계획",
                    tasks=parsed_today,
                    subject=inferred_subject
                )

                conn_sch.commit()
                fixed_ai_response = "오늘 추천 학습 계획이 스케줄에 추가되었습니다."

            else:
                # 직전 추천을 찾지 못했지만,
                # 현재 메시지 자체에 날짜/과목/시간/공부 내용이 있으면 직접 스케줄로 저장한다.
                if has_concrete_schedule_content(user_msg):
                    target_date = parse_target_date_from_text(user_msg)
                    task_content = make_single_schedule_task_from_user_message(user_msg, core_subject)

                    save_schedule_task(
                        conn_sch=conn_sch,
                        target_date=target_date,
                        title="학습 계획",
                        task_content=task_content,
                        subject=core_subject
                    )

                    conn_sch.commit()
                    fixed_ai_response = "스케줄에 추가되었습니다."

                else:
                    fixed_ai_response = "추가할 수 있는 직전 추천 계획을 찾지 못했습니다. 먼저 학습 계획을 추천받은 뒤 다시 추가해 주세요."
        # -------------------------------------------------
        # 직접 스케줄 추가
        # -------------------------------------------------

        elif intent_type == "schedule":
            saved_ids = []

            # 1. 오늘부터 일주일동안 같은 기간형 먼저 처리
            period_items = extract_period_schedule_items(user_msg)

            print("DEBUG period_items =", period_items, flush=True)

            if period_items:
                for item in period_items:
                    schedule_id = save_schedule_task(
                        conn_sch=conn_sch,
                        target_date=item["target_date"],
                        title="학습 계획",
                        task_content=item["task"],
                        subject=item["subject"],
                        merge_same_day=False
                    )

                    saved_ids.append(schedule_id)

                conn_sch.commit()

                if all(verify_schedule_saved(conn_sch, sid) for sid in saved_ids):
                    fixed_ai_response = f"스케줄에 {len(period_items)}일치 계획을 추가했습니다."
                else:
                    fixed_ai_response = "스케줄 저장 중 문제가 발생했습니다. 다시 시도해 주세요."

            else:
                # 2. 오늘 A, 내일 B 같은 여러 날짜 스케줄 처리
                multiple_items = extract_multiple_schedule_items(user_msg)

                print("DEBUG multiple_items =", multiple_items, flush=True)

                if multiple_items:
                    for item in multiple_items:
                        schedule_id = save_schedule_task(
                            conn_sch=conn_sch,
                            target_date=item["target_date"],
                            title="학습 계획",
                            task_content=item["task"],
                            subject=item["subject"],
                            merge_same_day=False
                        )

                        saved_ids.append(schedule_id)

                    conn_sch.commit()

                    if all(verify_schedule_saved(conn_sch, sid) for sid in saved_ids):
                        fixed_ai_response = f"스케줄에 {len(multiple_items)}개 추가되었습니다."
                    else:
                        fixed_ai_response = "스케줄 저장 중 문제가 발생했습니다. 다시 시도해 주세요."

                else:
                    # 3. 단일 스케줄 처리
                    target_date = extracted.get("target_date") or parse_target_date_from_text(user_msg)

                    subject = core_subject

                    if subject == "기타":
                        subject = detect_subject_from_user_message(user_msg, "기타")

                    if subject == "기타":
                        subject = "학습"

                    task_content = make_single_schedule_task_from_user_message(user_msg, subject)

                    schedule_id = save_schedule_task(
                        conn_sch=conn_sch,
                        target_date=target_date,
                        title="학습 계획",
                        task_content=task_content,
                        subject=subject,
                        merge_same_day=False
                    )

                    saved_ids.append(schedule_id)

                    conn_sch.commit()

                    if all(verify_schedule_saved(conn_sch, sid) for sid in saved_ids):
                        fixed_ai_response = "스케줄에 추가되었습니다."
                    else:
                        fixed_ai_response = "스케줄 저장 중 문제가 발생했습니다. 다시 시도해 주세요."
        # -------------------------------------------------
        # 공부 기록 저장
        # -------------------------------------------------

        elif intent_type == "study":
            duration = extracted.get("duration")

            try:
                duration = int(duration)
            except Exception:
                duration = 0

            if duration <= 0:
                duration = parse_duration_from_text(user_msg, DEFAULT_TASK_SECONDS)

            cursor_study = conn_study.cursor()

            cursor_study.execute(
                """
                INSERT INTO study_logs (
                    subject,
                    duration,
                    raw_message
                )
                VALUES (?, ?, ?)
                """,
                (
                    core_subject,
                    duration,
                    user_msg
                )
            )

            conn_study.commit()
            fixed_ai_response = "공부 기록이 성공적으로 저장되었습니다."

        # -------------------------------------------------
        # 장기 학습 계획 추천
        # -------------------------------------------------

        elif intent_type == "long_term_request":
            period = str(extracted.get("period", extract_period_text(user_msg))).strip()
            period_days = get_period_days(period)

            if core_subject != "기타":
                system_hint = f"""
[명령]: 사용자가 '{core_subject}' 과목을 '{period}' 동안 공부하려고 합니다.
총 {period_days}일짜리 장기 학습 계획을 추천하세요.

반드시 한국어로만 답하세요.
영어 제목, 영어 목차, 영어 설명은 절대 쓰지 마세요.
과목명은 반드시 '{core_subject}'라고 쓰세요.

아래 형식을 반드시 지키세요.

1일차: {core_subject} - 핵심 개념 학습 외 2시간
- 공부 내용: {core_subject}의 가장 기본이 되는 핵심 개념을 정리하기
- 학습 방법: 개념을 읽은 뒤 짧은 예제를 직접 따라 작성하기

2일차: {core_subject} - 기본 예제 실습 외 2시간
- 공부 내용: 전날 배운 개념을 활용한 기본 예제를 풀어보기
- 학습 방법: 정답을 바로 보지 말고 직접 작성한 뒤 비교하기

중요:
- 반드시 1일차부터 {period_days}일차까지 작성하세요.
- 각 일차 첫 줄은 반드시 "{core_subject} - 학습내용 외 2시간" 형태로 작성하세요.
- 각 일차마다 공부 내용과 학습 방법을 한국어로 작성하세요.
- 영어 단어를 쓰지 마세요.
- 마지막 문장은 반드시 '이 일정대로 스케줄에 추가해 드릴까요?' 로만 끝내세요.
- 부연 설명은 쓰지 마세요.
"""
            else:
                fixed_ai_response = "장기 스케줄을 짜기 위해 어떤 과목을 공부하고 싶으신가요?"

        # -------------------------------------------------
        # 오늘 학습 추천
        # -------------------------------------------------

        elif intent_type == "recommend_request":
            if core_subject != "기타":
                system_hint = f"""
[명령]: 사용자가 '{core_subject}' 공부 추천을 요청했습니다.
오늘 하루 안에 실천할 수 있는 구체적인 학습 계획을 추천하세요.

반드시 한국어로만 답하세요.
영어 제목, 영어 목차, 영어 설명은 절대 쓰지 마세요.
과목명은 반드시 '{core_subject}'라고 쓰세요.

반드시 아래 형식을 지키세요.

오늘의 추천 학습 계획입니다.

{core_subject} - 핵심 개념 정리 외 30분
- 공부 내용: 오늘 공부할 핵심 개념을 정리하고 중요한 용어를 노트에 적기
- 학습 방법: 교재, 강의, 공식 문서 중 하나를 선택해서 개념을 먼저 이해하기

{core_subject} - 예제 실습 외 40분
- 공부 내용: 배운 개념을 활용한 기본 예제를 직접 풀어보기
- 학습 방법: 정답을 바로 보지 말고 먼저 직접 작성해보기

{core_subject} - 복습 및 정리 외 30분
- 공부 내용: 오늘 배운 내용을 짧게 요약하고 헷갈린 부분 표시하기
- 학습 방법: 틀리거나 막힌 부분을 따로 적고 다시 확인하기

마지막 문장은 반드시 아래 문장으로 끝내세요.
'이 일정대로 스케줄에 추가해 드릴까요?'

주의:
- "1일차", "2일차", "3일차" 표현은 절대 쓰지 마세요.
- 오늘 하루 계획만 작성하세요.
- 영어 단어를 쓰지 마세요.
- 각 항목에는 반드시 "외 N분" 형태의 시간을 포함하세요.
"""
            else:
                fixed_ai_response = "오늘은 어떤 과목을 집중적으로 공부하고 싶으신가요?"

        # -------------------------------------------------
        # 일반 대화
        # -------------------------------------------------

        else:
            use_history_for_answer = True

        if fixed_ai_response is not None:
            ai_response = fixed_ai_response
        else:
            ai_response = await ask_ollama(
                user_msg=user_msg,
                history=history,
                system_hint=system_hint,
                use_history=use_history_for_answer
            )

        save_chat_message(conn_chat, "user", user_msg)
        save_chat_message(conn_chat, "assistant", ai_response)
        conn_chat.commit()

        return ChatResponse(ai_response=ai_response)

    except Exception:
        traceback.print_exc()

        return ChatResponse(ai_response="오류가 발생했습니다.")

    finally:
        conn_chat.close()
        conn_study.close()
        conn_sch.close()


# =========================================================
# 채팅 기록 초기화 API
# =========================================================

@router.delete("/chat/history")
async def clear_chat_history(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    conn_chat = get_chat_db_connection(user_id)

    try:
        cursor = conn_chat.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute("DELETE FROM chat_history")
        conn_chat.commit()

        return {"message": "채팅 기록이 초기화되었습니다."}

    finally:
        conn_chat.close()

def make_schedule_task_content(user_msg: str, subject: str, target_seconds: int) -> str:
    """
    사용자가 직접 말한 스케줄 문장을 task content로 정리한다.
    """

    hours = target_seconds // 3600
    minutes = (target_seconds % 3600) // 60

    if hours > 0 and minutes > 0:
        time_text = f"{hours}시간 {minutes}분"
    elif hours > 0:
        time_text = f"{hours}시간"
    elif minutes > 0:
        time_text = f"{minutes}분"
    else:
        time_text = "1시간"

    # 너무 긴 문장을 그대로 저장하지 않도록 간단히 정리
    if "공부" in user_msg:
        content = f"{subject} 공부 외 {time_text}"
    else:
        content = f"{subject} 학습 외 {time_text}"

    return content