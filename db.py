"""
Database interface for arXiv bot using PostgreSQL
"""
import os
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, Integer, BigInteger, Boolean, DateTime, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import JSONB
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")
USE_DATABASE = os.getenv("USE_DATABASE", "false").lower() == "true"

# Create base class for declarative models
Base = declarative_base()


class Paper(Base):
    """Paper model for storing arXiv papers"""
    __tablename__ = 'papers'
    
    id = Column(String(50), primary_key=True)  # arXiv ID
    arxiv_id = Column(String(50), nullable=False, index=True)
    title = Column(Text, nullable=False)
    authors = Column(JSONB)  # Store as JSON array
    url = Column(Text)
    abstract = Column(Text)
    main_content = Column(JSONB)  # Store structured content
    tuples = Column(JSONB)  # Store tuples for processing
    section_summaries = Column(JSONB)  # Store summaries
    general_summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Create text search index
    __table_args__ = (
        Index('idx_title_search', 'title', postgresql_using='gin', postgresql_ops={'title': 'gin_trgm_ops'}),
    )


class BotUser(Base):
    """User model for Telegram bot users"""
    __tablename__ = 'bot_users'
    
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    is_admin = Column(Boolean, default=False, index=True)
    is_authorized = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)


class Search(Base):
    """Search history model"""
    __tablename__ = 'searches'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    topic = Column(Text, nullable=False)
    time_range = Column(String(100))
    papers_found = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


class DatabaseManager:
    """Database manager for paper storage and retrieval"""
    
    def __init__(self, database_url: str = None):
        """Initialize database connection"""
        self.database_url = database_url or DATABASE_URL
        
        if not self.database_url:
            logger.warning("DATABASE_URL not set. Database operations will fail.")
            self.engine = None
            self.SessionLocal = None
            return
        
        try:
            self.engine = create_engine(
                self.database_url,
                pool_size=10,  # Increased pool size
                max_overflow=20,  # More overflow connections
                pool_pre_ping=True,  # Verify connections before using
                pool_recycle=3600,  # Recycle connections after 1 hour
                pool_timeout=120,  # Wait up to 2 minutes for a connection
                connect_args={
                    'connect_timeout': 60,  # 60 seconds to establish connection
                    'options': '-c statement_timeout=14400000'  # 4 hour query timeout (in ms)
                },
                echo=False  # Set to True for SQL debugging
            )
            self.SessionLocal = sessionmaker(bind=self.engine)
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            self.engine = None
            self.SessionLocal = None
    
    def create_tables(self):
        """Create all tables if they don't exist"""
        if self.engine:
            Base.metadata.create_all(self.engine)
            logger.info("Database tables created/verified")
    
    def get_session(self) -> Session:
        """Get a new database session"""
        if not self.SessionLocal:
            raise RuntimeError("Database not initialized")
        return self.SessionLocal()
    
    # Paper operations
    
    def add_paper(self, paper_data: Dict) -> bool:
        """Add a new paper to database"""
        try:
            session = self.get_session()
            
            paper = Paper(
                id=paper_data.get("id"),
                arxiv_id=paper_data.get("id"),
                title=paper_data.get("title"),
                authors=json.dumps(paper_data.get("authors", [])),
                url=paper_data.get("url"),
                abstract=paper_data.get("Abstract", ""),
                main_content=json.dumps(paper_data.get("Main", {})),
                tuples=json.dumps(paper_data.get("Tuples", [])),
                section_summaries=json.dumps(paper_data.get("section_summaries", [])),
                general_summary=paper_data.get("general_summary", "")
            )
            
            session.add(paper)
            session.commit()
            session.close()
            logger.info(f"Added paper: {paper_data.get('id')}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding paper: {e}")
            session.rollback()
            session.close()
            return False
    
    def get_paper(self, paper_id: str) -> Optional[Dict]:
        """Get a paper by ID"""
        try:
            session = self.get_session()
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            session.close()
            
            if paper:
                return self._paper_to_dict(paper)
            return None
            
        except Exception as e:
            logger.error(f"Error getting paper: {e}")
            return None
    
    def paper_exists(self, paper_id: str) -> bool:
        """Check if a paper exists in database"""
        try:
            session = self.get_session()
            exists = session.query(Paper.id).filter(Paper.id == paper_id).first() is not None
            session.close()
            return exists
        except Exception as e:
            logger.error(f"Error checking paper existence: {e}")
            return False
    
    def get_all_papers(self) -> List[Dict]:
        """Get all papers from database"""
        try:
            session = self.get_session()
            papers = session.query(Paper).all()
            session.close()
            
            return [self._paper_to_dict(p) for p in papers]
            
        except Exception as e:
            logger.error(f"Error getting all papers: {e}")
            return []
    
    def get_papers_by_ids(self, paper_ids: List[str]) -> List[Dict]:
        """Get multiple papers by their IDs"""
        try:
            session = self.get_session()
            papers = session.query(Paper).filter(Paper.id.in_(paper_ids)).all()
            session.close()
            
            return [self._paper_to_dict(p) for p in papers]
            
        except Exception as e:
            logger.error(f"Error getting papers by IDs: {e}")
            return []
    
    def update_paper(self, paper_id: str, updates: Dict) -> bool:
        """Update a paper's information"""
        try:
            session = self.get_session()
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            
            if not paper:
                session.close()
                return False
            
            # Update fields
            for key, value in updates.items():
                if hasattr(paper, key):
                    setattr(paper, key, value)
            
            session.commit()
            session.close()
            return True
            
        except Exception as e:
            logger.error(f"Error updating paper: {e}")
            session.rollback()
            session.close()
            return False
    
    def delete_old_papers(self, days: int = 180) -> int:
        """Delete papers older than specified days"""
        try:
            from datetime import timedelta
            
            session = self.get_session()
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            deleted = session.query(Paper).filter(Paper.created_at < cutoff_date).delete()
            session.commit()
            session.close()
            
            logger.info(f"Deleted {deleted} old papers")
            return deleted
            
        except Exception as e:
            logger.error(f"Error deleting old papers: {e}")
            session.rollback()
            session.close()
            return 0
    
    # User operations
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, 
                 last_name: str = None, is_admin: bool = False) -> bool:
        """Add a new user"""
        try:
            session = self.get_session()
            
            # Check if user exists
            existing = session.query(BotUser).filter(BotUser.user_id == user_id).first()
            if existing:
                # Update last active
                existing.last_active = datetime.utcnow()
                session.commit()
                session.close()
                return True
            
            user = BotUser(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_admin=is_admin
            )
            
            session.add(user)
            session.commit()
            session.close()
            return True
            
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            session.rollback()
            session.close()
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        try:
            session = self.get_session()
            user = session.query(BotUser).filter(BotUser.user_id == user_id).first()
            session.close()
            
            if user:
                return {
                    'user_id': user.user_id,
                    'username': user.username,
                    'is_admin': user.is_admin,
                    'is_authorized': user.is_authorized
                }
            return None
            
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    def get_authorized_users(self) -> List[int]:
        """Get list of authorized user IDs"""
        try:
            session = self.get_session()
            users = session.query(BotUser.user_id).filter(BotUser.is_authorized == True).all()
            session.close()
            
            return [u[0] for u in users]
            
        except Exception as e:
            logger.error(f"Error getting authorized users: {e}")
            return []
    
    def update_user_authorization(self, user_id: int, is_authorized: bool) -> bool:
        """Update user authorization status"""
        try:
            session = self.get_session()
            user = session.query(BotUser).filter(BotUser.user_id == user_id).first()
            
            if user:
                user.is_authorized = is_authorized
                session.commit()
                session.close()
                return True
            
            session.close()
            return False
            
        except Exception as e:
            logger.error(f"Error updating user authorization: {e}")
            session.rollback()
            session.close()
            return False
    
    # Search history operations
    
    def log_search(self, user_id: int, topic: str, time_range: str, papers_found: int) -> bool:
        """Log a search query"""
        try:
            session = self.get_session()
            
            search = Search(
                user_id=user_id,
                topic=topic,
                time_range=time_range,
                papers_found=papers_found
            )
            
            session.add(search)
            session.commit()
            session.close()
            return True
            
        except Exception as e:
            logger.error(f"Error logging search: {e}")
            session.rollback()
            session.close()
            return False
    
    # Helper methods
    
    @staticmethod
    def _paper_to_dict(paper: Paper) -> Dict:
        """Convert Paper object to dictionary"""
        return {
            'id': paper.id,
            'title': paper.title,
            'authors': json.loads(paper.authors) if paper.authors else [],
            'url': paper.url,
            'Abstract': paper.abstract,
            'Main': json.loads(paper.main_content) if paper.main_content else {},
            'Tuples': json.loads(paper.tuples) if paper.tuples else [],
            'section_summaries': json.loads(paper.section_summaries) if paper.section_summaries else [],
            'general_summary': paper.general_summary or ''
        }


# Singleton instance
_db_manager = None

def get_db_manager() -> DatabaseManager:
    """Get or create database manager singleton"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        if _db_manager.engine:
            _db_manager.create_tables()
    return _db_manager

