import os
from sqlalchemy import create_mock_engine, create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Use SQLite for local development/testing if DATABASE_URL isn't set
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./skillbridge.db")

# If using PostgreSQL, we need to handle the 'postgres://' vs 'postgresql://' issue common in Railway/Render
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()