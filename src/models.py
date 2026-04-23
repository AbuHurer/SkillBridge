from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table, Time, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from database import Base
import datetime
# --- ASSOCIATION TABLES (Many-to-Many) ---

# PDF Req: batch_trainers (batch_id, trainer_id)
batch_trainers = Table(
    'batch_trainers',
    Base.metadata,
    Column('batch_id', Integer, ForeignKey('batches.id', ondelete="CASCADE"), primary_key=True),
    Column('trainer_id', Integer, ForeignKey('users.id', ondelete="CASCADE"), primary_key=True)
)

# PDF Req: batch_students (batch_id, student_id)
batch_students = Table(
    'batch_students',
    Base.metadata,
    Column('batch_id', Integer, ForeignKey('batches.id', ondelete="CASCADE"), primary_key=True),
    Column('student_id', Integer, ForeignKey('users.id', ondelete="CASCADE"), primary_key=True)
)

# --- MODELS ---

class User(Base):
    """
    PDF Req: users (id, name, email, hashed_password, role, institution_id, created_at)
    Roles: student, trainer, institution, programme_manager, monitoring_officer
    """
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False) 
    institution_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    managed_batches = relationship("Batch", back_populates="institution", foreign_keys="Batch.institution_id")
    assigned_batches = relationship("Batch", secondary=batch_trainers, back_populates="trainers")
    enrolled_batches = relationship("Batch", secondary=batch_students, back_populates="students")

class Batch(Base):
    """
    PDF Req: batches (id, name, institution_id, created_at)
    """
    __tablename__ = "batches"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    institution_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    institution = relationship("User", back_populates="managed_batches", foreign_keys=[institution_id])
    trainers = relationship("User", secondary=batch_trainers, back_populates="assigned_batches")
    students = relationship("User", secondary=batch_students, back_populates="enrolled_batches")
    sessions = relationship("Session", back_populates="batch")

class BatchInvite(Base):
    """
    PDF Req: batch_invites (id, batch_id, token, created_by, expires_at, used)
    """
    __tablename__ = "batch_invites"
    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)

class Session(Base):
    """
    PDF Req: sessions (id, batch_id, trainer_id, title, date, start_time, end_time, created_at)
    """
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    trainer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    date = Column(DateTime, nullable=False) # Store the day
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    batch = relationship("Batch", back_populates="sessions")
    attendance_records = relationship("Attendance", back_populates="session")

class Attendance(Base):
    """
    PDF Req: attendance (id, session_id, student_id, status, marked_at)
    Status: present / absent / late
    """
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, nullable=False) 
    marked_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("Session", back_populates="attendance_records")

class InviteToken(Base):
    __tablename__ = "invite_tokens"
    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"))
    token = Column(String, unique=True, index=True)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)