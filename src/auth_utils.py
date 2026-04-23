import os
import sys
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, List
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# --- 1. REFINED PASSLIB BCRYPT COMPATIBILITY FIX ---
# Prevents AttributeError: module 'bcrypt' has no attribute '__about__'
if not hasattr(bcrypt, "__about__"):
    bcrypt_version = getattr(bcrypt, "__version__", "4.0.1")
    try:
        bcrypt.__about__ = type('about', (object,), {'__version__': bcrypt_version})
    except (AttributeError, TypeError):
        if 'bcrypt' in sys.modules:
            sys.modules['bcrypt'].__about__ = type('about', (object,), {'__version__': bcrypt_version})

# --- 2. CONFIGURATION ---
SECRET_KEY = os.getenv("SECRET_KEY", "your-very-secret-key-here")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
MONITORING_API_KEY = os.getenv("MONITORING_API_KEY", "SKILLBRIDGE_ADMIN_2024")
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # 24 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# --- 3. HASHING FUNCTIONS ---

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password):
    return pwd_context.hash(password)

# For backward compatibility with some versions of main.py
def get_password_hash(password):
    return pwd_context.hash(password)

# --- 4. JWT FUNCTIONS ---

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Renamed from get_current_user_data to match main.py calls.
    Decodes the JWT and returns the payload (user_id and role).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # Ensure user_id or sub is present
        if "user_id" not in payload and "sub" not in payload:
            raise credentials_exception
        return payload
    except JWTError:
        raise credentials_exception

def check_role(allowed_roles: List[str]):
    """
    Role-based access control dependency.
    """
    def role_checker(user_data: dict = Depends(get_current_user)):
        if user_data.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for your role"
            )
        return user_data
    return role_checker