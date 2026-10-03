import os
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware 
from dotenv import load_dotenv

from database import init_user_db, init_textbook_db
from routers import auth, auth_social, chat, schedule, memo, timer, diary, account

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 켜질 때 중앙 유저 테이블만 세팅. 나머지는 로그인한 유저별로 알아서 생성됨.
    init_user_db()
    init_textbook_db()
    yield

load_dotenv()

app = FastAPI(lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "your-super-secret-key"), https_only=False)

# 라우터 등록
app.include_router(auth.router) # /auth/login, /auth/signup
app.include_router(auth_social.router) # /auth/login/google, /auth/google/callback 등
app.include_router(chat.router) # /chat
app.include_router(schedule.router, prefix="/api", tags=["Schedules"]) 
app.include_router(memo.router, prefix="/api", tags=["Memos"])
app.include_router(timer.router)
app.include_router(diary.router)
app.include_router(account.router)

@app.get("/login_test_copy")
async def show_login_page():
    return FileResponse("login_test_copy.html")