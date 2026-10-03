import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
from dotenv import load_dotenv
from database import get_user_db_connection

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "9cad9cbb3f78b4e99aba2980dd4e1954") 
ALGORITHM = "HS256" # 토큰 암호화 알고리즘
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 #토큰 유효기간, 현재 24시간으로 설정

# 보안 도구 초기화
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# 비밀번호 일치 확인
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

#비밀번호 암호화
def get_password_hash(password):
    return pwd_context.hash(password)

#토큰 생성 함수
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# [중요] 모든 라우터에서 공통으로 사용할 "로그인 사용자 확인" 함수
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="자격 증명이 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        user_id: int = payload.get("id")
        name: str = payload.get("name")

        if email is None or user_id is None:
            raise credentials_exception
    
    except JWTError:
        raise credentials_exception
    
    conn = get_user_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, email, name, provider FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        
        if user is None:
            raise credentials_exception

        return {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "provider": user["provider"]
        }
    finally:
        conn.close()