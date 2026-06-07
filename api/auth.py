from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from config.settings import settings
import hashlib

SECRET_KEY = "ip-protection-secret-key-change-in-production-2024"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def simple_hash(password: str) -> str:
    return hashlib.sha256((password + SECRET_KEY).encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return simple_hash(plain_password) == hashed_password


def get_password_hash(password: str) -> str:
    return simple_hash(password)


fake_users_db: Dict[str, Dict] = {
    "admin": {
        "username": "admin",
        "password_hash": simple_hash("admin123"),
        "role": "admin",
        "email": "admin@company.com"
    },
    "legal": {
        "username": "legal",
        "password_hash": simple_hash("legal123"),
        "role": "legal",
        "email": "legal@company.com"
    }
}


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_user(username: str):
    if username in fake_users_db:
        return fake_users_db[username]
    return None


def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return False
    if not verify_password(password, user["password_hash"]):
        return False
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user(username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: dict = Depends(get_current_user)):
    return current_user
