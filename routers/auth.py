from fastapi import APIRouter, HTTPException, Depends
from models import SignUpRequest, LoginRequest, Token
from database import get_user_db_connection
from security import get_password_hash, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

# 회원가입 기능 처리
@router.post("/signup", status_code=201)
async def singup(req: SignUpRequest):
    # 비밀번호 일치 확인
    if req.password != req.password_confirm:
        raise HTTPException(status_code=400, detail="비밀번호 불일치")
    
    conn =get_user_db_connection()
    cursor = conn.cursor()
    try:
        # 이메일 중복 확인
        cursor.execute("SELECT id FROM users WHERE email = ?", (req.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다")
        
        # 비밀번호 암호화
        hashed_pw = get_password_hash(req.password)
        cursor.execute("INSERT INTO users (email, name, hashed_password) VALUES (?, ?, ?)",
                       (req.email, req.name, hashed_pw))
        conn.commit()
        return {"message": "회원가입 완료"}
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# 로그인 기능 처리
@router.post("/login", response_model=Token)
async def login(req: LoginRequest):
    conn = get_user_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, hashed_password FROM users WHERE email = ?", (req.email,))
    user = cursor.fetchone()
    conn.close()

    # 이메일 또는 비밀번호 확인
    if not user or not verify_password(req.password, user[2]):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호 오류")
    
    access_token = create_access_token(data={"sub": req.email, "id": user[0], "name": user[1]})
    return {"access_token": access_token, "token_type": "bearer", "user_name": user[1]}

@router.post("/logout")
async def logout(current_user: str = Depends(get_current_user)):
    """
    로그아웃을 처리합니다.
    실제 토큰 삭제는 클라이언트(안드로이드)에서 수행해야 합니다.
    """
    # 백엔드에서는 요청한 유저가 정상적인 토큰을 가지고 있는지 확인만 하고,
    # 성공 메시지를 반환합니다.
    return {"message": "성공적으로 로그아웃 되었습니다."}