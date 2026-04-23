from fastapi import FastAPI, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import secrets
import models, schemas, auth_utils
from database import engine, get_db
import os
from dotenv import load_dotenv
from pathlib import Path
import sys
# --- 1. AGGRESSIVE PATH & IMPORT RESOLUTION ---
# This ensures that the current directory and its parent are both in the search path.
# This fixes "ModuleNotFoundError: No module named 'models'" for nested structures.
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BASE_DIR.parent))

# 2. Load environment variables
env_path = BASE_DIR.parent / '.env'
load_dotenv(dotenv_path=env_path)

# 3. Flexible Module Imports
try:
    # Try importing as a package first (recommended for Uvicorn)
    try:
        from . import models, database, auth_utils, schemas
        from .database import engine, get_db
    except (ImportError, ValueError):
        # Fallback to direct top-level imports
        import models
        import database
        import auth_utils
        import schemas
        from database import engine, get_db
except Exception as e:
    # Final debugging info for the logs if it still fails
    print(f"CRITICAL IMPORT ERROR: {e}")
    print(f"Python Path: {sys.path}")
    print(f"Current Directory Contents: {os.listdir(BASE_DIR)}")
    raise e

# Create database tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SkillBridge Attendance Management System",
    description="Backend API for state-level skilling programme attendance tracking."
)
@app.get("/")
def read_root():
    return {"status": "SkillBridge API is Live", "docs": "/docs"}
# --- TASK 1 & 2: AUTHENTICATION ENDPOINTS ---

@app.post("/auth/signup", status_code=status.HTTP_201_CREATED)
def signup(user_data: schemas.UserSignup, db: Session = Depends(get_db)):
    """Registers a new user and returns a standard JWT."""
    db_user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pwd = auth_utils.hash_password(user_data.password)
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
    
    token = auth_utils.create_access_token(data={"user_id": new_user.id, "role": new_user.role})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/auth/login")
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    """Validates credentials and returns a 24-hour standard JWT."""
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user or not auth_utils.verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = auth_utils.create_access_token(data={"user_id": user.id, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/auth/monitoring-token", dependencies=[Depends(auth_utils.check_role(["monitoring_officer"]))])
def exchange_monitoring_token(request: schemas.MonitoringTokenRequest, current_user: dict = Depends(auth_utils.get_current_user)):
    """Task 2: Exchanges a valid Monitoring JWT + API Key for a 1-hour scoped token."""
    if request.key != auth_utils.MONITORING_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid Monitoring API Key")
    
    token = auth_utils.create_access_token(
        data={"user_id": current_user["user_id"], "role": current_user["role"], "monitoring_scoped": True},
        expires_delta=timedelta(hours=1)
    )
    return {"monitoring_access_token": token, "token_type": "bearer"}

# --- TASK 1: BATCH & INVITE ENDPOINTS ---

@app.post("/batches", dependencies=[Depends(auth_utils.check_role(["trainer", "institution"]))])
def create_batch(batch_data: schemas.BatchCreate, db: Session = Depends(get_db), current_user: dict = Depends(auth_utils.get_current_user)):
    """Creates a batch. Trainers must have an institution_id assigned."""
    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()
    
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

@app.post("/batches/{batch_id}/invite", dependencies=[Depends(auth_utils.check_role(["trainer"]))])
def generate_invite(batch_id: int, db: Session = Depends(get_db), current_user: dict = Depends(auth_utils.get_current_user)):
    """Generates a secure invite token for a batch."""
    batch = db.query(models.Batch).filter(models.Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    token = secrets.token_urlsafe(16)
    invite = models.BatchInvite(
        batch_id=batch_id,
        token=token,
        created_by=current_user["user_id"],
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db.add(invite)
    db.commit()
    return {"invite_token": token}

@app.post("/batches/join", dependencies=[Depends(auth_utils.check_role(["student"]))])
def join_batch(token: str = Body(..., embed=True), db: Session = Depends(get_db), current_user: dict = Depends(auth_utils.get_current_user)):
    """Uses an invite token to enroll a student in a batch."""
    invite = db.query(models.BatchInvite).filter(models.BatchInvite.token == token, models.BatchInvite.used == False).first()
    if not invite or invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    student = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()
    batch = db.query(models.Batch).filter(models.Batch.id == invite.batch_id).first()
    
    if student not in batch.students:
        batch.students.append(student)
        invite.used = True
        db.commit()
    
    return {"message": f"Successfully joined batch {batch.name}"}

# --- TASK 1 & 3: SESSIONS & ATTENDANCE ---

@app.post("/sessions", dependencies=[Depends(auth_utils.check_role(["trainer"]))])
def create_session(session_data: schemas.SessionCreate, db: Session = Depends(get_db), current_user: dict = Depends(auth_utils.get_current_user)):
    """Creates a new learning session for a batch."""
    batch = db.query(models.Batch).filter(models.Batch.id == session_data.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    new_session = models.Session(
        batch_id=session_data.batch_id,
        trainer_id=current_user["user_id"],
        title=session_data.title,
        date=session_data.date,
        start_time=session_data.start_time,
        end_time=session_data.end_time
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return {"message": "Session created", "session_id": new_session.id}

@app.post("/attendance/mark", dependencies=[Depends(auth_utils.check_role(["student"]))])
def mark_attendance(att_data: schemas.AttendanceMark, db: Session = Depends(get_db), current_user: dict = Depends(auth_utils.get_current_user)):
    """Allows a student to mark their own attendance if they are enrolled in the batch."""
    session = db.query(models.Session).filter(models.Session.id == att_data.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Task 3 Requirement: 403 if not enrolled in batch
    student_in_batch = db.query(models.batch_students).filter(
        models.batch_students.c.batch_id == session.batch_id,
        models.batch_students.c.student_id == current_user["user_id"]
    ).first()
    
    if not student_in_batch:
        raise HTTPException(status_code=403, detail="You are not enrolled in this batch")
    
    # Optional: Prevent double marking
    existing = db.query(models.Attendance).filter(
        models.Attendance.session_id == att_data.session_id,
        models.Attendance.student_id == current_user["user_id"]
    ).first()
    if existing:
        return {"message": "Attendance already marked"}

    attendance = models.Attendance(
        session_id=att_data.session_id,
        student_id=current_user["user_id"],
        status=att_data.status
    )
    db.add(attendance)
    db.commit()
    return {"message": "Attendance marked successfully"}

# --- TASK 1: SUMMARY & MONITORING (GET ONLY) ---

@app.get("/sessions/{session_id}/attendance", dependencies=[Depends(auth_utils.check_role(["trainer"]))])
def get_session_attendance(session_id: int, db: Session = Depends(get_db)):
    return db.query(models.Attendance).filter(models.Attendance.session_id == session_id).all()

@app.get("/batches/{batch_id}/summary", dependencies=[Depends(auth_utils.check_role(["institution"]))])
def get_batch_summary(batch_id: int, db: Session = Depends(get_db)):
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

@app.get("/institutions/{inst_id}/summary", dependencies=[Depends(auth_utils.check_role(["programme_manager", "institution"]))])
def get_institution_summary(inst_id: int, db: Session = Depends(get_db)):
    batches = db.query(models.Batch).filter(models.Batch.institution_id == inst_id).all()
    return {"institution_id": inst_id, "batch_count": len(batches)}

@app.get("/programme/summary", dependencies=[Depends(auth_utils.check_role(["programme_manager", "institution"]))])
def get_programme_summary(db: Session = Depends(get_db)):
    """Allows both Programme Managers and Institutions to see global stats."""
    return {
        "total_students": db.query(models.User).filter(models.User.role == "student").count(),
        "total_batches": db.query(models.Batch).count()
    }

@app.get("/monitoring/attendance")
def get_monitoring_data(current_user: dict = Depends(auth_utils.get_current_user), db: Session = Depends(get_db)):
    """Task 2: Read-only access for Monitoring Officers with a scoped token."""
    if not current_user.get("scoped"):
        raise HTTPException(status_code=401, detail="Valid monitoring-scoped token required")
    return db.query(models.Attendance).all()

if __name__ == "__main__":
    import uvicorn
    # Use PORT environment variable for deployment (default to 8000 for local)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)