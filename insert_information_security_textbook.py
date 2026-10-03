import sqlite3
from database import get_textbook_db_connection, init_textbook_db


# ============================================================
# 정보 보안 개론 교재 목차 삽입 스크립트
# 위치: main.py, database.py와 같은 폴더
# 실행: python insert_information_security_textbook.py
# ============================================================


BOOK_SUBJECT = "정보보호"
BOOK_TITLE = "IT CookBook, 정보 보안 개론(4판)"
BOOK_DESCRIPTION = "정보 보안 개론 4판 교재 목차 기반 학습 추천용 데이터"


def insert_chapter(
    cursor,
    textbook_id,
    parent_id,
    depth,
    chapter_order,
    title,
    page=None,
    importance=3,
    description=None
):
    """
    목차 항목을 textbook_chapters 테이블에 추가한다.
    parent_id가 None이면 대목차, 값이 있으면 하위 목차이다.
    """
    cursor.execute(
        """
        INSERT INTO textbook_chapters
        (textbook_id, parent_id, depth, chapter_order, title, page, importance, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            textbook_id,
            parent_id,
            depth,
            chapter_order,
            title,
            page,
            importance,
            description
        )
    )

    return cursor.lastrowid


def insert_child_items(cursor, textbook_id, parent_id, depth, items):
    """
    중목차 또는 소목차 목록을 반복 삽입한다.
    items는 (order, title, page, importance, children) 구조를 사용한다.
    """
    for item in items:
        chapter_order = item["order"]
        title = item["title"]
        page = item.get("page")
        importance = item.get("importance", 3)
        children = item.get("children", [])

        inserted_id = insert_chapter(
            cursor=cursor,
            textbook_id=textbook_id,
            parent_id=parent_id,
            depth=depth,
            chapter_order=chapter_order,
            title=title,
            page=page,
            importance=importance
        )

        if children:
            insert_child_items(
                cursor=cursor,
                textbook_id=textbook_id,
                parent_id=inserted_id,
                depth=depth + 1,
                items=children
            )


def main():
    # textbook.db와 테이블이 없으면 생성한다.
    init_textbook_db()

    conn = get_textbook_db_connection()
    cursor = conn.cursor()

    try:
        # 같은 교재가 이미 있으면 삭제 후 다시 삽입한다.
        # 이렇게 해야 중복 삽입을 막고, 목차를 수정했을 때 다시 반영하기 쉽다.
        cursor.execute(
            """
            SELECT id FROM textbooks
            WHERE subject = ? AND book_title = ?
            """,
            (BOOK_SUBJECT, BOOK_TITLE)
        )
        existing = cursor.fetchone()

        if existing:
            old_textbook_id = existing["id"]
            cursor.execute(
                "DELETE FROM textbooks WHERE id = ?",
                (old_textbook_id,)
            )
            print(f"기존 교재 데이터 삭제 완료: textbook_id={old_textbook_id}")

        # 교재 기본 정보 삽입
        cursor.execute(
            """
            INSERT INTO textbooks
            (subject, book_title, publisher, author, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                BOOK_SUBJECT,
                BOOK_TITLE,
                "한빛아카데미",
                None,
                BOOK_DESCRIPTION
            )
        )

        textbook_id = cursor.lastrowid

        chapters = [
            {
                "order": 1,
                "title": "정보 보안의 세계",
                "page": 18,
                "importance": 4,
                "children": [
                    {"order": 1, "title": "정보 보안의 역사", "page": 18, "importance": 3},
                    {
                        "order": 2,
                        "title": "정보 보안의 이해",
                        "page": 34,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "보안의 3대 요소", "page": 34, "importance": 5},
                            {"order": 2, "title": "보안 전문가의 자격 요건", "page": 35, "importance": 3},
                        ]
                    },
                    {"order": 98, "title": "요약", "page": 43, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 44, "importance": 5},
                ]
            },
            {
                "order": 2,
                "title": "시스템 보안",
                "page": 46,
                "importance": 5,
                "children": [
                    {"order": 1, "title": "시스템 보안의 이해", "page": 46, "importance": 4},
                    {
                        "order": 2,
                        "title": "계정 관리",
                        "page": 48,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "운영체제의 계정 관리", "page": 48, "importance": 5},
                            {"order": 2, "title": "데이터베이스의 계정 관리", "page": 53, "importance": 4},
                            {"order": 3, "title": "응용 프로그램의 계정 관리", "page": 53, "importance": 4},
                            {"order": 4, "title": "네트워크 장비의 계정 관리", "page": 54, "importance": 4},
                        ]
                    },
                    {"order": 3, "title": "세션 관리", "page": 55, "importance": 4},
                    {
                        "order": 4,
                        "title": "접근 제어",
                        "page": 58,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "운영체제의 접근 제어", "page": 58, "importance": 5},
                            {"order": 2, "title": "데이터베이스의 접근 제어", "page": 60, "importance": 5},
                            {"order": 3, "title": "응용 프로그램의 접근 제어", "page": 61, "importance": 4},
                            {"order": 4, "title": "네트워크 장비의 접근 제어", "page": 62, "importance": 4},
                        ]
                    },
                    {
                        "order": 5,
                        "title": "권한 관리",
                        "page": 63,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "운영체제의 권한 관리", "page": 63, "importance": 5},
                            {"order": 2, "title": "데이터베이스의 권한 관리", "page": 66, "importance": 5},
                            {"order": 3, "title": "응용 프로그램의 권한 관리", "page": 68, "importance": 4},
                        ]
                    },
                    {
                        "order": 6,
                        "title": "로그 관리",
                        "page": 69,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "운영체제의 로그 관리", "page": 70, "importance": 5},
                            {"order": 2, "title": "데이터베이스의 로그 관리", "page": 75, "importance": 5},
                            {"order": 3, "title": "응용 프로그램의 로그 관리", "page": 80, "importance": 4},
                            {"order": 4, "title": "네트워크 장비의 로그 관리", "page": 84, "importance": 4},
                        ]
                    },
                    {
                        "order": 7,
                        "title": "취약점 관리",
                        "page": 86,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "패치 관리", "page": 86, "importance": 5},
                            {"order": 2, "title": "응용 프로그램별 고유 위험 관리", "page": 87, "importance": 4},
                            {"order": 3, "title": "응용 프로그램의 정보 수집 제한", "page": 87, "importance": 4},
                        ]
                    },
                    {
                        "order": 8,
                        "title": "모바일 보안",
                        "page": 89,
                        "importance": 4,
                        "children": [
                            {"order": 1, "title": "모바일 운영체제 보안", "page": 89, "importance": 4},
                            {"order": 2, "title": "모바일 기기 보안", "page": 97, "importance": 4},
                        ]
                    },
                    {"order": 98, "title": "요약", "page": 100, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 106, "importance": 5},
                ]
            },
            {
                "order": 3,
                "title": "네트워크 보안",
                "page": 112,
                "importance": 5,
                "children": [
                    {"order": 1, "title": "네트워크의 이해", "page": 112, "importance": 4},
                    {
                        "order": 2,
                        "title": "서비스 거부 공격: DoS와 DDoS",
                        "page": 130,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "서비스 거부 공격(DoS)", "page": 130, "importance": 5},
                            {"order": 2, "title": "분산 서비스 거부 공격(DDoS)", "page": 140, "importance": 5},
                        ]
                    },
                    {
                        "order": 3,
                        "title": "스니핑 공격",
                        "page": 143,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "스니핑 공격의 원리", "page": 143, "importance": 5},
                            {"order": 2, "title": "스니핑 공격의 종류", "page": 145, "importance": 5},
                            {"order": 3, "title": "스니핑 공격의 탐지", "page": 145, "importance": 4},
                        ]
                    },
                    {
                        "order": 4,
                        "title": "스푸핑 공격",
                        "page": 148,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "ARP 스푸핑 공격", "page": 148, "importance": 5},
                            {"order": 2, "title": "IP 스푸핑 공격", "page": 151, "importance": 5},
                            {"order": 3, "title": "ICMP 리다이렉트 공격", "page": 152, "importance": 4},
                            {"order": 4, "title": "DNS 스푸핑 공격", "page": 154, "importance": 5},
                        ]
                    },
                    {"order": 5, "title": "세션 하이재킹 공격", "page": 158, "importance": 5},
                    {
                        "order": 6,
                        "title": "무선 네트워크 공격과 보안",
                        "page": 160,
                        "importance": 4,
                        "children": [
                            {"order": 1, "title": "AP 보안", "page": 162, "importance": 4},
                            {"order": 2, "title": "무선 랜 통신의 암호화", "page": 163, "importance": 4},
                        ]
                    },
                    {"order": 98, "title": "요약", "page": 168, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 172, "importance": 5},
                ]
            },
            {
                "order": 4,
                "title": "웹 보안",
                "page": 176,
                "importance": 5,
                "children": [
                    {"order": 1, "title": "웹과 HTTP의 이해", "page": 176, "importance": 4},
                    {
                        "order": 2,
                        "title": "웹 서비스의 이해",
                        "page": 181,
                        "importance": 4,
                        "children": [
                            {"order": 1, "title": "프론트 엔드", "page": 181, "importance": 3},
                            {"order": 2, "title": "백 엔드", "page": 182, "importance": 3},
                        ]
                    },
                    {
                        "order": 3,
                        "title": "웹 해킹",
                        "page": 183,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "웹 취약점 스캐너를 통한 정보 수집", "page": 183, "importance": 4},
                            {"order": 2, "title": "웹 프록시를 통한 취약점 분석", "page": 184, "importance": 5},
                            {"order": 3, "title": "구글 해킹을 통한 정보 수집", "page": 192, "importance": 4},
                        ]
                    },
                    {
                        "order": 4,
                        "title": "웹의 취약점과 보안",
                        "page": 196,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "웹의 주요 취약점", "page": 196, "importance": 5},
                            {"order": 2, "title": "웹의 취약점 보안", "page": 214, "importance": 5},
                        ]
                    },
                    {"order": 98, "title": "요약", "page": 216, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 219, "importance": 5},
                ]
            },
            {
                "order": 5,
                "title": "코드 보안",
                "page": 224,
                "importance": 5,
                "children": [
                    {
                        "order": 1,
                        "title": "시스템 구성과 프로그램 동작",
                        "page": 224,
                        "importance": 4,
                        "children": [
                            {"order": 1, "title": "프로그램과 코드 보안", "page": 224, "importance": 4},
                            {"order": 2, "title": "시스템 메모리와 구조", "page": 226, "importance": 4},
                            {"order": 3, "title": "프로그램 실행 구조", "page": 228, "importance": 4},
                            {"order": 4, "title": "셸", "page": 236, "importance": 4},
                            {"order": 5, "title": "프로세스 권한과 SetUID", "page": 238, "importance": 5},
                        ]
                    },
                    {
                        "order": 2,
                        "title": "버퍼 오버플로 공격",
                        "page": 241,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "버퍼 오버플로 공격의 개념", "page": 241, "importance": 5},
                            {"order": 2, "title": "버퍼 오버플로 공격의 원리", "page": 242, "importance": 5},
                            {"order": 3, "title": "버퍼 오버플로 공격의 대응책", "page": 249, "importance": 5},
                        ]
                    },
                    {
                        "order": 3,
                        "title": "포맷 스트링 공격",
                        "page": 251,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "포맷 스트링 공격의 개념", "page": 251, "importance": 5},
                            {"order": 2, "title": "포맷 스트링 공격의 원리", "page": 252, "importance": 5},
                        ]
                    },
                    {
                        "order": 4,
                        "title": "메모리 해킹",
                        "page": 256,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "메모리 해킹의 개념", "page": 256, "importance": 5},
                            {"order": 2, "title": "메모리 해킹의 원리", "page": 256, "importance": 5},
                        ]
                    },
                    {"order": 98, "title": "요약", "page": 261, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 264, "importance": 5},
                ]
            },
            {
                "order": 6,
                "title": "악성 코드",
                "page": 268,
                "importance": 5,
                "children": [
                    {
                        "order": 1,
                        "title": "악성 코드",
                        "page": 268,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "악성 코드의 역사", "page": 268, "importance": 4},
                            {"order": 2, "title": "악성 코드의 분류", "page": 271, "importance": 5},
                        ]
                    },
                    {"order": 2, "title": "바이러스", "page": 274, "importance": 5},
                    {
                        "order": 3,
                        "title": "웜",
                        "page": 281,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "매스메일러형 웜", "page": 281, "importance": 4},
                            {"order": 2, "title": "시스템 공격형 웜", "page": 282, "importance": 4},
                            {"order": 3, "title": "네트워크 공격형 웜", "page": 283, "importance": 4},
                        ]
                    },
                    {"order": 4, "title": "트로이 목마", "page": 285, "importance": 5},
                    {"order": 5, "title": "PUP", "page": 286, "importance": 4},
                    {
                        "order": 6,
                        "title": "악성 코드 탐지 및 대응책",
                        "page": 287,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "네트워크 상태 점검하기", "page": 288, "importance": 4},
                            {"order": 2, "title": "정상적인 프로세스와 비교하기", "page": 290, "importance": 4},
                            {"order": 3, "title": "악성 코드의 실제 파일 확인하기", "page": 294, "importance": 5},
                            {"order": 4, "title": "시작 프로그램과 레지스트리 확인하기", "page": 296, "importance": 4},
                            {"order": 5, "title": "악성 코드 제거하기", "page": 297, "importance": 5},
                        ]
                    },
                    {"order": 98, "title": "요약", "page": 298, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 300, "importance": 5},
                ]
            },
            {
                "order": 7,
                "title": "암호의 이해",
                "page": 304,
                "importance": 5,
                "children": [
                    {
                        "order": 1,
                        "title": "암호의 개념과 원리",
                        "page": 304,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "암호화와 복호화", "page": 304, "importance": 5},
                            {"order": 2, "title": "단일 치환 암호화", "page": 306, "importance": 4},
                            {"order": 3, "title": "다중 치환 암호화", "page": 308, "importance": 4},
                        ]
                    },
                    {
                        "order": 2,
                        "title": "대칭 암호화 방식",
                        "page": 313,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "DES 알고리즘", "page": 313, "importance": 5},
                            {"order": 2, "title": "트리플 DES 알고리즘", "page": 315, "importance": 4},
                            {"order": 3, "title": "AES 알고리즘", "page": 316, "importance": 5},
                            {"order": 4, "title": "SEED 알고리즘", "page": 316, "importance": 4},
                            {"order": 5, "title": "ARIA 알고리즘", "page": 317, "importance": 4},
                            {"order": 6, "title": "양자 암호", "page": 317, "importance": 4},
                            {"order": 7, "title": "기타 대칭형 알고리즘", "page": 318, "importance": 3},
                        ]
                    },
                    {
                        "order": 3,
                        "title": "비대칭 암호화 방식",
                        "page": 319,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "비대칭 암호화 방식의 발견", "page": 319, "importance": 4},
                            {"order": 2, "title": "RSA 알고리즘", "page": 321, "importance": 5},
                            {"order": 3, "title": "비대칭 암호화의 구조", "page": 322, "importance": 5},
                            {"order": 4, "title": "비대칭 암호화의 기능", "page": 323, "importance": 4},
                        ]
                    },
                    {"order": 4, "title": "해시", "page": 327, "importance": 5},
                    {"order": 98, "title": "요약", "page": 333, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 336, "importance": 5},
                ]
            },
            {
                "order": 8,
                "title": "전자 상거래 보안",
                "page": 340,
                "importance": 4,
                "children": [
                    {"order": 1, "title": "전자 상거래의 이해", "page": 340, "importance": 4},
                    {
                        "order": 2,
                        "title": "공개 키 기반 구조",
                        "page": 344,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "공개 키 기반 구조의 개념", "page": 344, "importance": 5},
                            {"order": 2, "title": "공인 인증서", "page": 346, "importance": 4},
                        ]
                    },
                    {
                        "order": 3,
                        "title": "전자 서명과 전자 봉투",
                        "page": 349,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "전자 서명", "page": 349, "importance": 5},
                            {"order": 2, "title": "전자 봉투", "page": 352, "importance": 4},
                        ]
                    },
                    {
                        "order": 4,
                        "title": "전자 결제와 가상 화폐",
                        "page": 354,
                        "importance": 4,
                        "children": [
                            {"order": 1, "title": "SET", "page": 354, "importance": 4},
                            {"order": 2, "title": "간편 결제", "page": 358, "importance": 3},
                            {"order": 3, "title": "전자 화폐", "page": 359, "importance": 3},
                            {"order": 4, "title": "스마트카드의 구조", "page": 360, "importance": 4},
                            {"order": 5, "title": "스마트카드 인증", "page": 362, "importance": 4},
                            {"order": 6, "title": "가상 화폐(비트코인)", "page": 366, "importance": 3},
                        ]
                    },
                    {
                        "order": 5,
                        "title": "암호화 통신",
                        "page": 374,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "네트워크 암호화", "page": 374, "importance": 5},
                            {"order": 2, "title": "전자 우편 암호화", "page": 377, "importance": 4},
                        ]
                    },
                    {
                        "order": 6,
                        "title": "콘텐츠 보안",
                        "page": 379,
                        "importance": 4,
                        "children": [
                            {"order": 1, "title": "스테가노그래피", "page": 379, "importance": 4},
                            {"order": 2, "title": "워터마크", "page": 379, "importance": 4},
                        ]
                    },
                    {"order": 98, "title": "요약", "page": 381, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 386, "importance": 5},
                ]
            },
            {
                "order": 9,
                "title": "보안 시스템",
                "page": 390,
                "importance": 5,
                "children": [
                    {
                        "order": 1,
                        "title": "인증 시스템",
                        "page": 390,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "인증 수단", "page": 390, "importance": 5},
                            {"order": 2, "title": "SSO", "page": 395, "importance": 4},
                        ]
                    },
                    {"order": 2, "title": "방화벽", "page": 397, "importance": 5},
                    {
                        "order": 3,
                        "title": "침입 탐지 시스템",
                        "page": 400,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "침입 탐지 시스템의 주요 기능", "page": 401, "importance": 5},
                            {"order": 2, "title": "설치 위치", "page": 403, "importance": 4},
                        ]
                    },
                    {
                        "order": 4,
                        "title": "침입 방지 시스템",
                        "page": 406,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "침입 방지 시스템의 개발 과정", "page": 406, "importance": 4},
                            {"order": 2, "title": "침입 방지 시스템의 동작 원리", "page": 406, "importance": 5},
                            {"order": 3, "title": "침입 방지 시스템의 설치", "page": 408, "importance": 4},
                        ]
                    },
                    {"order": 5, "title": "통제 및 감시 장비", "page": 409, "importance": 4},
                    {
                        "order": 6,
                        "title": "기타 보안 솔루션",
                        "page": 411,
                        "importance": 4,
                        "children": [
                            {"order": 1, "title": "VPN", "page": 411, "importance": 5},
                            {"order": 2, "title": "VLAN", "page": 413, "importance": 4},
                            {"order": 3, "title": "NAC", "page": 415, "importance": 4},
                            {"order": 4, "title": "보안 운영체제", "page": 420, "importance": 4},
                            {"order": 5, "title": "백신", "page": 421, "importance": 4},
                            {"order": 6, "title": "PC 방화벽", "page": 421, "importance": 4},
                            {"order": 7, "title": "스팸 필터 솔루션", "page": 422, "importance": 3},
                            {"order": 8, "title": "DRM", "page": 424, "importance": 3},
                            {"order": 9, "title": "DLP", "page": 426, "importance": 4},
                        ]
                    },
                    {"order": 98, "title": "요약", "page": 428, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 430, "importance": 5},
                ]
            },
            {
                "order": 10,
                "title": "IoT 보안과 AI 보안",
                "page": 434,
                "importance": 4,
                "children": [
                    {"order": 1, "title": "IoT 보안", "page": 434, "importance": 4},
                    {
                        "order": 2,
                        "title": "AI에 대한 이해",
                        "page": 439,
                        "importance": 4,
                        "children": [
                            {"order": 1, "title": "AI의 역사", "page": 439, "importance": 3},
                            {"order": 2, "title": "AI 기술의 분류", "page": 443, "importance": 4},
                        ]
                    },
                    {
                        "order": 3,
                        "title": "AI의 취약점 유형과 대안",
                        "page": 447,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "데이터 변조 공격과 대안", "page": 447, "importance": 5},
                            {"order": 2, "title": "악의적 데이터 주입 공격", "page": 448, "importance": 5},
                            {"order": 3, "title": "데이터 추출 공격", "page": 449, "importance": 5},
                        ]
                    },
                    {
                        "order": 4,
                        "title": "AI를 이용한 보안",
                        "page": 450,
                        "importance": 4,
                        "children": [
                            {"order": 1, "title": "스팸 메일 탐지", "page": 450, "importance": 4},
                            {"order": 2, "title": "네트워크 침입 탐지", "page": 453, "importance": 4},
                            {"order": 3, "title": "악성 코드 탐지", "page": 453, "importance": 4},
                            {"order": 4, "title": "CCTV", "page": 455, "importance": 3},
                        ]
                    },
                    {"order": 98, "title": "요약", "page": 456, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 457, "importance": 5},
                ]
            },
            {
                "order": 11,
                "title": "침해 대응과 디지털 포렌식",
                "page": 460,
                "importance": 5,
                "children": [
                    {
                        "order": 1,
                        "title": "침해 대응",
                        "page": 460,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "사전 대응", "page": 461, "importance": 4},
                            {"order": 2, "title": "사고 탐지", "page": 463, "importance": 5},
                            {"order": 3, "title": "대응", "page": 465, "importance": 5},
                            {"order": 4, "title": "제거 및 복구", "page": 466, "importance": 5},
                            {"order": 5, "title": "후속 조치 및 보고", "page": 466, "importance": 4},
                        ]
                    },
                    {
                        "order": 2,
                        "title": "디지털 포렌식의 개념과 절차",
                        "page": 467,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "디지털 포렌식의 증거", "page": 468, "importance": 5},
                            {"order": 2, "title": "디지털 포렌식 기본 원칙", "page": 469, "importance": 5},
                            {"order": 3, "title": "포렌식 수행 절차", "page": 471, "importance": 5},
                            {"order": 4, "title": "사이버 수사 기구", "page": 473, "importance": 3},
                        ]
                    },
                    {
                        "order": 3,
                        "title": "디지털 포렌식의 증거 수집",
                        "page": 476,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "네트워크 증거 수집", "page": 476, "importance": 4},
                            {"order": 2, "title": "시스템 증거 수집", "page": 477, "importance": 5},
                            {"order": 3, "title": "데이터 및 응용 프로그램 증거 수집", "page": 484, "importance": 4},
                        ]
                    },
                    {"order": 98, "title": "요약", "page": 485, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 487, "importance": 5},
                ]
            },
            {
                "order": 12,
                "title": "사회공학",
                "page": 490,
                "importance": 5,
                "children": [
                    {"order": 1, "title": "사회공학의 이해", "page": 490, "importance": 5},
                    {
                        "order": 2,
                        "title": "사회공학 기법",
                        "page": 494,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "인간 기반 사회공학 기법", "page": 494, "importance": 5},
                            {"order": 2, "title": "컴퓨터 기반 사회공학 기법", "page": 497, "importance": 5},
                        ]
                    },
                    {"order": 3, "title": "사회공학 사례와 대응책", "page": 502, "importance": 5},
                    {"order": 98, "title": "요약", "page": 503, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 505, "importance": 5},
                ]
            },
            {
                "order": 13,
                "title": "보안 관리",
                "page": 508,
                "importance": 5,
                "children": [
                    {"order": 1, "title": "보안 거버넌스", "page": 508, "importance": 5},
                    {
                        "order": 2,
                        "title": "보안 프레임워크",
                        "page": 512,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "ISMS와 PDCA 모델", "page": 512, "importance": 5},
                            {"order": 2, "title": "ISO 27001의 보안 관리 항목", "page": 514, "importance": 5},
                            {"order": 3, "title": "ISO 27001의 보안 통제 분야", "page": 515, "importance": 5},
                            {"order": 4, "title": "K-ISMS", "page": 516, "importance": 5},
                        ]
                    },
                    {"order": 3, "title": "보안 조직", "page": 526, "importance": 4},
                    {"order": 4, "title": "보안 정책과 절차", "page": 531, "importance": 5},
                    {"order": 5, "title": "접근 제어 모델", "page": 538, "importance": 5},
                    {
                        "order": 6,
                        "title": "내부 통제",
                        "page": 542,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "최소 권한", "page": 542, "importance": 5},
                            {"order": 2, "title": "직무 분리", "page": 543, "importance": 5},
                        ]
                    },
                    {
                        "order": 7,
                        "title": "보안 인증",
                        "page": 544,
                        "importance": 5,
                        "children": [
                            {"order": 1, "title": "TCSEC", "page": 544, "importance": 4},
                            {"order": 2, "title": "ITSEC", "page": 546, "importance": 4},
                            {"order": 3, "title": "CC", "page": 547, "importance": 4},
                        ]
                    },
                    {"order": 8, "title": "개인 정보 보호", "page": 548, "importance": 5},
                    {"order": 98, "title": "요약", "page": 551, "importance": 4},
                    {"order": 99, "title": "연습문제", "page": 554, "importance": 5},
                ]
            },
            {
                "order": 14,
                "title": "부록: 실습 환경 구축하기",
                "page": 558,
                "importance": 3,
                "children": [
                    {
                        "order": 1,
                        "title": "웹 해킹 실습 환경 구성",
                        "page": 558,
                        "importance": 4,
                        "children": [
                            {"order": 1, "title": "Node.js 설치하기", "page": 558, "importance": 3},
                            {"order": 2, "title": "웹 응용 프로그램 설치하기", "page": 559, "importance": 4},
                            {"order": 3, "title": "웹 응용 프로그램 데이터베이스", "page": 562, "importance": 4},
                        ]
                    },
                    {"order": 99, "title": "찾아보기", "page": 563, "importance": 2},
                ]
            },
        ]

        # 전체 목차 삽입
        for chapter in chapters:
            chapter_id = insert_chapter(
                cursor=cursor,
                textbook_id=textbook_id,
                parent_id=None,
                depth=1,
                chapter_order=chapter["order"],
                title=chapter["title"],
                page=chapter.get("page"),
                importance=chapter.get("importance", 3)
            )

            insert_child_items(
                cursor=cursor,
                textbook_id=textbook_id,
                parent_id=chapter_id,
                depth=2,
                items=chapter.get("children", [])
            )

        conn.commit()

        print("정보보안 교재 목차 삽입 완료")
        print(f"textbook_id: {textbook_id}")
        print(f"총 Chapter 수: {len(chapters)}")

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM textbook_chapters
            WHERE textbook_id = ?
            """,
            (textbook_id,)
        )
        count_row = cursor.fetchone()
        print(f"총 목차 항목 수: {count_row['count']}")

    except Exception as e:
        conn.rollback()
        print("삽입 중 오류 발생")
        print(e)

    finally:
        conn.close()


if __name__ == "__main__":
    main()