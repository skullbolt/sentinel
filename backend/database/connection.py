import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path

# Load .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/sentinel")


class DatabaseManager:
    """Manages database connection and sessions"""

    def __init__(self, url: str = None):
        self.url = url or DATABASE_URL
        self.engine = create_engine(
            self.url,
            echo=False,           # Set True to see SQL queries in console
            pool_size=20,         # Max 20 connections in pool
            max_overflow=30,      # Allow 30 extra connections under load
            pool_timeout=30,      # Wait 30s for connection before error
            pool_recycle=1800,    # Recycle connections every 30 minutes
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
        )

    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()

    def create_all_tables(self):
        """Create all tables in database"""
        from .models import Base
        Base.metadata.create_all(bind=self.engine)
        print("✅ All tables created successfully")

    def drop_all_tables(self):
        """Drop all tables (DANGEROUS - use only in development)"""
        from .models import Base
        Base.metadata.drop_all(bind=self.engine)
        print("⚠️  All tables dropped")

    def test_connection(self) -> bool:
        """Test if database connection works"""
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"✅ Database connected: {self.url}")
            return True
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return False


# Global database manager instance
db_manager = DatabaseManager()


def get_db():
    """Get database session (for use in FastAPI dependency injection)"""
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()