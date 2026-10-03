import os
import httpx
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from database import get_user_db_connection
from security import create_access_token
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/auth", tags=["Social Auth"])

oauth = OAuth()

# 1. 구글 설정
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# 2. 카카오 설정
oauth.register(
    name='kakao',
    client_id=os.getenv("KAKAO_CLIENT_ID"),
    client_secret=os.getenv("KAKAO_CLIENT_SECRET"),
    authorize_url='https://kauth.kakao.com/oauth/authorize',
    access_token_url='https://kauth.kakao.com/oauth/token',
    userinfo_endpoint='https://kapi.kakao.com/v2/user/me',
    client_kwargs={
        'scope': 'account_email profile_nickname',
        'token_endpoint_auth_method': 'client_secret_post' 
    }
)

# 3. 네이버 설정
oauth.register(
    name='naver',
    client_id=os.getenv("NAVER_CLIENT_ID"),
    client_secret=os.getenv("NAVER_CLIENT_SECRET"),
    authorize_url='https://nid.naver.com/oauth2.0/authorize',
    access_token_url='https://nid.naver.com/oauth2.0/token',
    userinfo_endpoint='https://openapi.naver.com/v1/nid/me',
    client_kwargs={'scope': 'profile'} 
)

from fastapi import HTTPException
# 기존에 사용 중인 의존성(get_user_db_connection, create_access_token)이 import 되어 있어야 합니다.

def process_social_login(email: str, name: str, provider: str):
    """
    이메일과 이름으로 DB 조회/가입 후 JWT 토큰을 생성하여 반환합니다.
    """
    # 1. 소셜 계정에 이메일이 없는 경우 방어 로직
    if not email:
        raise HTTPException(status_code=400, detail=f"{provider} 계정에 이메일 정보가 없습니다. 이메일 제공에 동의해주세요.")

    # 2. 유저 DB 연결
    conn = get_user_db_connection()
    cursor = conn.cursor()
    
    try:
        # 3. 기존 유저 확인
        cursor.execute("SELECT id, name, email FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        
        user_id = None
        
        if user:
            # 이미 가입된 유저
            user_id = user[0]
            print(f"✅ [{provider}] 기존 유저 로그인 성공: {email}")
        else:
            # 신규 유저
            # 비밀번호 컬럼에 소셜 로그인 유저임을 알 수 있는 식별자 저장
            cursor.execute(
                "INSERT INTO users (email, name, hashed_password) VALUES (?, ?, ?)", 
                (email, name, f"{provider}_social_user")
            )
            conn.commit()
            user_id = cursor.lastrowid
            print(f"[{provider}] 신규 유저 가입 완료: {email}")
        
        # 4. JWT 토큰 생성
        access_token = create_access_token(data={
            "sub": email, 
            "id": user_id, 
            "name": name
        })
        
        # 5. 프론트엔드/콜백 라우터로 전달할 최종 데이터 딕셔너리
        return {
            "message": f"{provider} Login successful",
            "access_token": access_token, 
            "token_type": "bearer",
            "user": {
                "email": email, 
                "name": name, 
                "provider": provider
            }
        }
        
    except Exception as e:
        # DB 처리 중 에러가 발생하면 트랜잭션 보호를 위해 안전하게 에러 반환
        raise HTTPException(status_code=500, detail=f"데이터베이스 처리 중 오류 발생: {str(e)}")
        
    finally:
        # 6. 작업이 끝나면 무조건 DB 연결 종료
        conn.close()

# 구글 로그인
@router.get("/login/google")
async def login_google(request: Request):

    redirect_uri = request.url_for('auth_google_callback')
    
    # ngrok 주소일 경우 http를 https로 강제 변환
    if "ngrok-free.app" in str(redirect_uri):
        redirect_uri = str(redirect_uri).replace("http://", "https://")
        
    return await oauth.google.authorize_redirect(request, redirect_uri)

# 카카오 로그인
@router.get("/login/kakao")
async def login_kakao(request: Request):
    redirect_uri = os.getenv("KAKAO_REDIRECT_URI")
    return await oauth.kakao.authorize_redirect(request, redirect_uri, prompt="login")

# 네이버 로그인
@router.get("/login/naver")
async def login_naver(request: Request):
    redirect_uri = os.getenv("NAVER_REDIRECT_URI")
    return await oauth.naver.authorize_redirect(request, redirect_uri)

# 구글 콜백
@router.get("/google/callback", name="auth_google_callback")
async def auth_google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo', {})
        
        # 구글 고유 ID 추출 (sub 키 사용)
        google_id = user_info.get("sub")
        
        email = user_info.get("email")
        name = user_info.get("name")
        
        # 방어 로직: 이메일이나 이름이 없을 경우 가상 데이터 생성
        if not email:
            email = f"google_{google_id}@studydiary.local"
        if not name:
            name = f"구글유저_{google_id}"

        # DB 저장 및 JWT 토큰 생성
        result = process_social_login(email, name, "Google")
        
        # 앱으로 토큰 전달
        access_token = result.get("access_token")
        
        return RedirectResponse(
            url=f"studydiary://login?token={access_token}"
        )
        
    except Exception as e:
        print(f"구글 로그인 에러 상세: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Google Login Failed: {str(e)}")

# 카카오 콜백
@router.get("/kakao/callback", name="auth_kakao_callback")
async def auth_kakao_callback(request: Request):
    try:
        code = request.query_params.get("code")

        # httpx로 직접 카카오에 토큰 요청
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://kauth.kakao.com/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": oauth.kakao.client_id, # 환경변수에 따라 제대로 불러오는지 확인
                    "redirect_uri": "https://phonogramic-eustolia-anthropologically.ngrok-free.dev/auth/kakao/callback",
                    "code": code,
                }
            )

        token_data = token_response.json()
        kakao_access_token = token_data.get("access_token")

        # 카카오 유저 정보 요청
        async with httpx.AsyncClient() as client:
            user_response = await client.get(
                "https://kapi.kakao.com/v2/user/me",
                headers={"Authorization": f"Bearer {kakao_access_token}"}
            )

        user_info = user_response.json()
        kakao_account = user_info.get("kakao_account", {})
        profile = kakao_account.get("profile", {})

        # 카카오 고유 ID 추출 (이메일 없을 때 사용할 비상용 키)
        kakao_id = user_info.get("id")

        email = kakao_account.get("email")
        name = profile.get("nickname")

        # 방어 로직 1: 카카오가 이메일을 주지 않았을 때 가상 이메일 생성
        if not email:
            email = f"kakao_{kakao_id}@studydiary.local"
            
        # 방어 로직 2: 이름이 없을 경우 기본값 부여
        if not name:
            name = f"카카오유저_{kakao_id}"

        # DB 저장 및 JWT 토큰 생성
        result = process_social_login(email, name, "Kakao")
        access_token = result["access_token"]

        return RedirectResponse(
            url=f"studydiary://login?token={access_token}"
        )
        
    except Exception as e:
        print(f"카카오 로그인 에러 상세: {str(e)}") # 터미널에서 에러 원인 확인용
        raise HTTPException(status_code=500, detail=f"Kakao Login Failed: {str(e)}")

# 네이버 콜백
@router.get("/naver/callback", name="auth_naver_callback")
async def auth_naver_callback(request: Request):
    try:
        token = await oauth.naver.authorize_access_token(request)
        # 네이버는 userinfo가 'response' 키 안에 담겨 옵니다.
        user_info_resp = await oauth.naver.userinfo(token=token)
        user_info = user_info_resp.get("response", {})
        
        # 네이버 고유 ID 추출 (id 키 사용)
        naver_id = user_info.get("id")
        
        email = user_info.get("email")
        name = user_info.get("name")
        
        # 방어 로직: 이메일이나 이름이 없을 경우 가상 데이터 생성
        if not email:
            email = f"naver_{naver_id}@studydiary.local"
        if not name:
            name = f"네이버유저_{naver_id}"
        
        # DB 저장 및 JWT 토큰 생성
        result = process_social_login(email, name, "Naver")
        
        # 앱으로 토큰 전달
        access_token = result.get("access_token")
        
        return RedirectResponse(
            url=f"studydiary://login?token={access_token}"
        )
        
    except Exception as e:
        print(f"네이버 로그인 에러 상세: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Naver Login Failed: {str(e)}")