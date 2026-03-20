from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os

# Default to a 'data' directory in the project root if DATA_DIR is not set
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))

# Ensure the data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'subscribers.db')}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String, index=True, nullable=True)
    
    verified_email = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    verification_token = Column(String, index=True, nullable=True)
    verification_token_created_at = Column(DateTime, nullable=True)
    unsubscribe_token = Column(String, index=True, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class PageView(Base):
    __tablename__ = "page_views"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class ReadSession(Base):
    __tablename__ = "read_sessions"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, index=True)
    duration_seconds = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)

# Dependency to get db session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
