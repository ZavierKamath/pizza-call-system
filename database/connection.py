"""
Database connection and session management for SQLite.
Provides connection pooling, session handling, and database lifecycle management.
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional
import time
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from .models import Base, create_tables

# Configure logging for database connections
logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages SQLite database connections and sessions.
    
    Provides connection pooling, retry logic, and session lifecycle management
    for the pizza ordering system database operations.
    """
    
    def __init__(self, database_url: Optional[str] = None, max_retries: int = 3):
        """
        Initialize database manager with connection configuration.
        
        Args:
            database_url (str): SQLite database URL, defaults to environment variable
            max_retries (int): Maximum connection retry attempts
        """
        self.database_url = database_url or os.getenv(
            'DATABASE_URL', 
            'sqlite:///./pizza_orders.db'
        )
        self.max_retries = max_retries
        self.engine = None
        self.SessionLocal = None
        self._initialized = False
        
        logger.info(f"DatabaseManager initialized with URL: {self.database_url}")
    
    def initialize(self) -> None:
        """
        Initialize database engine and create tables if needed.
        
        Sets up SQLite engine with connection pooling and creates
        all required tables based on SQLAlchemy models.
        """
        if self._initialized:
            logger.debug("Database already initialized, skipping...")
            return
        
        try:
            # Create SQLite engine with connection pooling
            # StaticPool keeps connections alive for better performance
            self.engine = create_engine(
                self.database_url,
                poolclass=StaticPool,
                pool_pre_ping=True,  # Verify connections before use
                pool_recycle=3600,   # Recycle connections every hour
                echo=False,          # Set to True for SQL query logging
                connect_args={
                    "check_same_thread": False  # Allow SQLite access from multiple threads
                }
            )
            
            # Configure WAL mode for better concurrency
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                """Set SQLite pragmas for optimal performance and reliability."""
                cursor = dbapi_connection.cursor()
                # Enable WAL mode for better concurrency
                cursor.execute("PRAGMA journal_mode=WAL")
                # Set synchronous mode for reliability
                cursor.execute("PRAGMA synchronous=NORMAL")
                # Set timeout for busy database
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()
            
            # Create session factory
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            # Create database tables
            create_tables(self.engine)
            
            self._initialized = True
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions with automatic cleanup.
        
        Provides transactional session management with rollback on errors
        and proper resource cleanup.
        
        Yields:
            Session: SQLAlchemy session for database operations
            
        Example:
            with db_manager.get_session() as session:
                order = session.query(Order).filter_by(id=1).first()
        """
        if not self._initialized:
            self.initialize()
        
        session = self.SessionLocal()
        try:
            logger.debug("Database session created")
            yield session
            session.commit()
            logger.debug("Database session committed")
        except Exception as e:
            session.rollback()
            logger.error(f"Database session rolled back due to error: {e}")
            raise
        finally:
            session.close()
            logger.debug("Database session closed")
    
    def execute_with_retry(self, operation, *args, **kwargs):
        """
        Execute database operation with retry logic for connection issues.
        
        Handles temporary database locks and connection failures
        with exponential backoff retry strategy.
        
        Args:
            operation: Function to execute with database session
            *args: Arguments to pass to operation
            **kwargs: Keyword arguments to pass to operation
            
        Returns:
            Result of the operation
            
        Raises:
            SQLAlchemyError: If all retry attempts fail
        """
        for attempt in range(self.max_retries):
            try:
                with self.get_session() as session:
                    return operation(session, *args, **kwargs)
            except (OperationalError, SQLAlchemyError) as e:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(
                    f"Database operation failed (attempt {attempt + 1}/{self.max_retries}): {e}. "
                    f"Retrying in {wait_time} seconds..."
                )
                
                if attempt == self.max_retries - 1:
                    logger.error(f"Database operation failed after {self.max_retries} attempts")
                    raise
                
                time.sleep(wait_time)
    
    def health_check(self) -> bool:
        """
        Perform database health check to verify connectivity.
        
        Returns:
            bool: True if database is accessible and responsive
        """
        try:
            with self.get_session() as session:
                # Simple query to test connectivity
                session.execute("SELECT 1")
                logger.debug("Database health check passed")
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def get_connection_info(self) -> dict:
        """
        Get database connection information for monitoring.
        
        Returns:
            dict: Connection status and pool information
        """
        if not self.engine:
            return {"status": "not_initialized"}
        
        pool = self.engine.pool
        return {
            "status": "connected" if self._initialized else "disconnected",
            "database_url": self.database_url.split('://')[-1],  # Hide credentials
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "invalid": pool.invalid()
        }
    
    def close(self) -> None:
        """
        Close database connections and cleanup resources.
        
        Should be called during application shutdown.
        """
        if self.engine:
            self.engine.dispose()
            logger.info("Database connections closed")
        self._initialized = False


# Global database manager instance
db_manager = DatabaseManager()


def get_db_session() -> Generator[Session, None, None]:
    """
    Dependency function for FastAPI to inject database sessions.
    
    Yields:
        Session: Database session for request handling
    """
    with db_manager.get_session() as session:
        yield session


def init_database() -> None:
    """
    Initialize database for application startup.
    
    Should be called during application initialization.
    """
    db_manager.initialize()


def close_database() -> None:
    """
    Close database connections for application shutdown.
    
    Should be called during application cleanup.
    """
    db_manager.close()


async def get_database_session() -> Generator[Session, None, None]:
    """
    Async version of get_db_session for async database operations.
    
    Yields:
        Session: Database session for async request handling
    """
    with db_manager.get_session() as session:
        yield session