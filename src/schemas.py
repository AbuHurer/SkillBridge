from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, time

# User Schemas
class UserSignup(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str # student, trainer, institution, programme_manager, monitoring_officer
    institution_id: Optional[int] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Monitoring Officer Req
class MonitoringTokenRequest(BaseModel):
    key: str

# Batch Schemas
class BatchCreate(BaseModel):
    name: str

class SessionCreate(BaseModel):
    title: str
    date: datetime
    start_time: time
    end_time: time
    batch_id: int

class AttendanceMark(BaseModel):
    session_id: int
    status: str # present, absent, late