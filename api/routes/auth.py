from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from api.auth import (
    authenticate_user, create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES, get_current_active_user
)
from api.schemas import Token, UserResponse, APIResponse

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=APIResponse)
async def read_users_me(current_user: dict = Depends(get_current_active_user)):
    return APIResponse(
        success=True,
        message="获取用户信息成功",
        data=UserResponse(
            username=current_user["username"],
            role=current_user["role"],
            email=current_user.get("email")
        )
    )


@router.post("/logout", response_model=APIResponse)
async def logout(current_user: dict = Depends(get_current_active_user)):
    return APIResponse(success=True, message="退出登录成功")
