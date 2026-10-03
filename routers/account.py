from fastapi import APIRouter, Depends
from security import get_current_user

router = APIRouter(prefix="/api", tags=["Account"])


@router.get("/me")
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "name": current_user["name"],
        "email": current_user["email"],
        "provider": current_user["provider"]
    }