import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker
from src.main import app
from src.database import Base, get_db
import src.models as models

# Setup an in-memory SQLite database for testing
# Using StaticPool ensures the connection stays open during the test session
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the database dependency so the API uses our test DB
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    """Create all tables before each test and drop them after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

# --- 1. Basic Health & Auth Tests ---

def test_health_check():
    """Verify the API is live"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "SkillBridge API is Live", "docs": "/docs"}

def test_student_auth():
    """Test: Successful student signup and login"""
    signup_res = client.post("/auth/signup", json={
        "name": "Student User", 
        "email": "student@test.com", 
        "password": "password", 
        "role": "student"
    })
    assert signup_res.status_code == 201
    
    login_res = client.post("/auth/login", json={
        "email": "student@test.com", 
        "password": "password"
    })
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

# --- 2. Trainer & Batch Logic ---

def test_trainer_create_session():
    """Test: Trainer flow including Institution setup, Batch creation, and Session creation"""
    # A. Create Institution first (Role requirement)
    client.post("/auth/signup", json={
        "name": "Alpha Inst", "email": "alpha@inst.com", "password": "password", "role": "institution"
    })
    
    # B. Create Trainer linked to Institution
    client.post("/auth/signup", json={
        "name": "Trainer Joe", "email": "joe@test.com", "password": "password", 
        "role": "trainer", "institution_id": 1 # First user created
    })
    
    # C. Login Trainer
    login = client.post("/auth/login", json={"email": "joe@test.com", "password": "password"}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    
    # D. Create Batch
    batch_res = client.post("/batches", json={"name": "Coding 101"}, headers=headers)
    assert batch_res.status_code == 200
    batch_id = batch_res.json()["batch_id"]
    
    # E. Create Session
    session_data = {
        "title": "Python Basics", "date": "2024-12-01T00:00:00",
        "start_time": "09:00:00", "end_time": "11:00:00", "batch_id": batch_id
    }
    sess_res = client.post("/sessions", json=session_data, headers=headers)
    assert sess_res.status_code == 200
    assert "session_id" in sess_res.json()

# --- 3. Security & Requirement Validation ---

def test_student_mark_attendance_forbidden():
    """Test: Student marking attendance for a session they aren't enrolled in (403 logic)"""
    # Setup: Create a session (requires Trainer)
    client.post("/auth/signup", json={
        "name": "Trainer Joe", "email": "joe@test.com", "password": "password", "role": "trainer"
    })
    t_login = client.post("/auth/login", json={"email": "joe@test.com", "password": "password"}).json()
    t_headers = {"Authorization": f"Bearer {t_login['access_token']}"}
    
    batch_res = client.post("/batches", json={"name": "Batch A"}, headers=t_headers).json()
    client.post("/sessions", json={
        "title": "Session 1", "date": "2024-12-01T00:00:00", "start_time": "09:00:00", 
        "end_time": "11:00:00", "batch_id": batch_res["batch_id"]
    }, headers=t_headers)

    # Test: Student Login and attempt to mark attendance
    client.post("/auth/signup", json={
        "name": "Student", "email": "s@test.com", "password": "password", "role": "student"
    })
    s_login = client.post("/auth/login", json={"email": "s@test.com", "password": "password"}).json()
    s_headers = {"Authorization": f"Bearer {s_login['access_token']}"}
    
    # Mark for session_id 1
    response = client.post("/attendance/mark", json={"session_id": 1, "status": "present"}, headers=s_headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "You are not enrolled in this batch"

def test_monitoring_post_method_not_allowed():
    """Test: Verifying 405 Method Not Allowed on GET-only endpoint"""
    response = client.post("/monitoring/attendance", json={})
    assert response.status_code == 405

def test_protected_no_token():
    """Test: Verifying 401 Unauthorized for protected endpoints"""
    response = client.get("/monitoring/attendance")
    assert response.status_code == 401