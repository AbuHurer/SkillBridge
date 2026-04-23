import os
from datetime import datetime, timedelta
from typing import Optional, List
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from passlib.hash import bcrypt
from database import get_db
from sqlalchemy.orm import Session
import models
from dotenv import load_dotenv

if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type('about', (object,), {'__version__': bcrypt.__version__})

load_dotenv() # Load environment variables from .env file
# Config from PDF requirements
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-for-local-dev")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
MONITORING_TOKEN_EXPIRE_HOURS = 1
MONITORING_API_KEY = os.getenv("MONITORING_API_KEY", "SKILLBRIDGE_ADMIN_2024")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    
    # PDF Req: user_id, role, iat, exp
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        role: str = payload.get("role")
        is_monitoring_scoped: bool = payload.get("monitoring_scoped", False)
        
        if user_id is None or role is None:
            raise credentials_exception
        return {"user_id": user_id, "role": role, "scoped": is_monitoring_scoped}
    except JWTError:
        raise credentials_exception

# RBAC Dependency
def check_role(allowed_roles: List[str]):
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for your role"
            )
        return current_user
    return role_checker