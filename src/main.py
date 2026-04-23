import os
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
import secrets
from typing import List, Optional

# --- 1. STANDARDIZED PATH RESOLUTION ---
# This ensures that the 'src' directory is the first place Python looks for modules.
# This prevents "ModuleNotFoundError" and SQLAlchemy table collision errors.
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure the parent directory is available for .env lookups
if str(BASE_DIR.parent) not in sys.path:
    sys.path.append(str(BASE_DIR.parent))

from fastapi import FastAPI, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# 2. Load environment variables
load_dotenv(dotenv_path=BASE_DIR.parent / '.env')

# 3. Clean Imports
# Using direct imports now that sys.path is correctly configured
import models
import database
import auth_utils
import schemas
from database import engine, get_db

# Create database tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SkillBridge Attendance Management System",
    description="Backend API for state-level skilling programme attendance tracking."
)

@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {"status": "SkillBridge API is Live", "docs": "/docs"}

# --- AUTHENTICATION ENDPOINTS ---

@app.post("/auth/signup", status_code=status.HTTP_201_CREATED)
def signup(user_data: schemas.UserSignup, db: Session = Depends(get_db)):
    """Registers a new user and returns a status message."""
    db_user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Using the hash_password function from your auth_utils.py
    hashed_pwd = auth_utils.get_password_hash(user_data.password)
    new_user = models.User(
        name=user_data.name,
        email=user_data.email,
        hashed_password=hashed_pwd,
        role=user_data.role,
        institution_id=user_data.institution_id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User created", "id": new_user.id}

@app.post("/auth/login")
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    """Validates credentials and returns a 24-hour standard JWT."""
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user or not auth_utils.verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = auth_utils.create_access_token(data={"sub": str(user.id), "role": user.role})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/auth/monitoring-token")
def exchange_monitoring_token(request: schemas.MonitoringTokenRequest, current_user: dict = Depends(auth_utils.get_current_user_data)):
    """Task 2: Exchanges a valid Monitoring JWT + API Key for a 1-hour scoped token."""
    if current_user.get("role") != "monitoring_officer":
        raise HTTPException(status_code=403, detail="Only monitoring officers can request this token")
    
    system_key = os.getenv("MONITORING_API_KEY", "SKILLBRIDGE_ADMIN_2024")
    if request.key != system_key:
        raise HTTPException(status_code=401, detail="Invalid Monitoring API Key")
    
    token = auth_utils.create_access_token(
        data={"sub": current_user["sub"], "role": current_user["role"], "monitoring_scoped": True},
        expires_delta=timedelta(hours=1)
    )
    return {"monitoring_access_token": token, "token_type": "bearer"}

# --- BATCH & INVITE ENDPOINTS ---

@app.post("/batches")
def create_batch(batch_data: schemas.BatchCreate, db: Session = Depends(get_db), current_user: dict = Depends(auth_utils.check_role(["trainer", "institution"]))):
    """Creates a batch linked to an institution."""
    user = db.query(models.User).filter(models.User.id == int(current_user["sub"])).first()
    
    # Institution ownership logic
    inst_id = user.id if current_user["role"] == "institution" else user.institution_id
    
    if not inst_id:
         raise HTTPException(status_code=400, detail="User must be associated with an institution to create batches")

    new_batch = models.Batch(name=batch_data.name, institution_id=inst_id)
    db.add(new_batch)
    
    if current_user["role"] == "trainer":
        new_batch.trainers.append(user)
    
    db.commit()
    db.refresh(new_batch)
    return {"message": "Batch created", "batch_id": new_batch.id}

@app.post("/batches/{batch_id}/invite")
def generate_invite(batch_id: int, db: Session = Depends(get_db), current_user: dict = Depends(auth_utils.check_role(["trainer"]))):
    """Generates a secure invite token for a batch."""
    batch = db.query(models.Batch).filter(models.Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    token = secrets.token_urlsafe(16)
    invite = models.InviteToken(
        batch_id=batch_id,
        token=token,
        is_used=False
    )
    db.add(invite)
    db.commit()
    return {"invite_token": token}

@app.post("/batches/join")
def join_batch(token: str = Body(..., embed=True), db: Session = Depends(get_db), current_user: dict = Depends(auth_utils.check_role(["student"]))):
    """Uses an invite token to enroll a student in a batch."""
    invite = db.query(models.InviteToken).filter(models.InviteToken.token == token, models.InviteToken.is_used == False).first()
    if not invite:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    student = db.query(models.User).filter(models.User.id == int(current_user["sub"])).first()
    batch = db.query(models.Batch).filter(models.Batch.id == invite.batch_id).first()
    
    if student not in batch.students:
        batch.students.append(student)
        invite.is_used = True
        db.commit()
    
    return {"message": f"Successfully joined batch {batch.name}"}

# --- SESSIONS & ATTENDANCE ---

@app.post("/sessions")
def create_session(session_data: schemas.SessionCreate, db: Session = Depends(get_db), current_user: dict = Depends(auth_utils.check_role(["trainer"]))):
    """Creates a new learning session for a batch."""
    batch = db.query(models.Batch).filter(models.Batch.id == session_data.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    new_session = models.Session(
        batch_id=session_data.batch_id,
        trainer_id=int(current_user["sub"]),
        title=session_data.title,
        date=session_data.date,
        start_time=session_data.start_time,
        end_time=session_data.end_time
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return {"message": "Session created", "session_id": new_session.id}

@app.post("/attendance/mark")
def mark_attendance(att_data: schemas.AttendanceMark, db: Session = Depends(get_db), current_user: dict = Depends(auth_utils.check_role(["student"]))):
    """Allows a student to mark their own attendance if they are enrolled in the batch."""
    session = db.query(models.Session).filter(models.Session.id == att_data.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Task 3 Requirement: 403 if not enrolled in batch
    student_id = int(current_user["sub"])
    student_in_batch = db.query(models.batch_students).filter(
        models.batch_students.c.batch_id == session.batch_id,
        models.batch_students.c.student_id == student_id
    ).first()
    
    if not student_in_batch:
        raise HTTPException(status_code=403, detail="You are not enrolled in this batch")
    
    # Prevent double marking
    existing = db.query(models.Attendance).filter(
        models.Attendance.session_id == att_data.session_id,
        models.Attendance.student_id == student_id
    ).first()
    if existing:
        return {"message": "Attendance already marked"}

    attendance = models.Attendance(
        session_id=att_data.session_id,
        student_id=student_id,
        status=att_data.status
    )
    db.add(attendance)
    db.commit()
    return {"message": "Attendance marked successfully"}

# --- MONITORING & SUMMARIES ---

@app.get("/monitoring/attendance")
def get_monitoring_data(db: Session = Depends(get_db), current_user: dict = Depends(auth_utils.get_current_user_data)):
    """Task 2: Read-only access for Monitoring Officers with a scoped token."""
    if not current_user.get("monitoring_scoped"):
        raise HTTPException(status_code=401, detail="Valid monitoring-scoped token required")
    return db.query(models.Attendance).all()

@app.get("/batches/{batch_id}/summary")
def get_batch_summary(batch_id: int, db: Session = Depends(get_db), user: dict = Depends(auth_utils.check_role(["institution", "programme_manager"]))):
    sessions = db.query(models.Session).filter(models.Session.batch_id == batch_id).all()
    session_ids = [s.id for s in sessions]
    total_marked = db.query(models.Attendance).filter(models.Attendance.session_id.in_(session_ids)).count()
    present_count = db.query(models.Attendance).filter(
        models.Attendance.session_id.in_(session_ids), 
        models.Attendance.status == "present"
    ).count()
    return {
        "batch_id": batch_id,
        "total_sessions": len(sessions),
        "attendance_rate": (present_count / total_marked * 100) if total_marked > 0 else 0
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)