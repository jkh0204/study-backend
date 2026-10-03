from pydantic import BaseModel

# 회원가입 요청
class SignUpRequest(BaseModel):
    email: str
    name: str
    password: str
    password_confirm: str

# 로그인 요청
class LoginRequest(BaseModel):
    email: str
    password: str

# 토큰 응답
class Token(BaseModel):
    access_token: str
    token_type: str
    user_name: str

# 채팅 요청 및 응답
class ChatRequest(BaseModel):
    user_message: str
    model_type: str = "llama3" #openai 또는 gemini 중 선택, gemini는 api연동확인을 위해 추가한 것임

class ChatResponse(BaseModel):
    ai_response: str