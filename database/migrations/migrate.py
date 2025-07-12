"""
Database initialization and migration functions.
Handles schema updates, data migrations, and database lifecycle management.
"""

import os
import logging
from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError
from ..connection import db_manager
from ..models import Base, Order, ActiveSession
from ..redis_client import redis_client

# Configure logging for migration operations
logger = logging.getLogger(__name__)


class DatabaseMigrator:
    """
    Handles database migrations and schema updates.
    
    Provides versioned migrations, rollback capabilities, and
    data integrity checks for the pizza ordering system.
    """
    
    def __init__(self):
        """Initialize database migrator with version tracking."""
        self.migration_table = "schema_migrations"
        self.current_version = "1.0.0"
        
    def initialize_database(self) -> bool:
        """
        Initialize database with all required tables and initial data.
        
        Creates schema, applies migrations, and sets up initial configuration.
        
        Returns:
            bool: True if initialization successful
        """
        try:
            logger.info("Starting database initialization...")
            
            # Initialize database connection
            db_manager.initialize()
            
            # Create migration tracking table
            self._create_migration_table()
            
            # Apply all pending migrations
            self._apply_migrations()
            
            # Initialize Redis if available
            try:
                redis_client.initialize()
                logger.info("Redis initialized successfully")
            except Exception as e:
                logger.warning(f"Redis initialization failed (continuing without Redis): {e}")
            
            # Verify database integrity
            if self._verify_database_integrity():
                logger.info("Database initialization completed successfully")
                return True
            else:
                logger.error("Database integrity check failed")
                return False
                
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False
    
    def _create_migration_table(self) -> None:
        """Create migration tracking table if it doesn't exist."""
        migration_sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            checksum TEXT
        )
        """
        
        try:
            with db_manager.get_session() as session:
                session.execute(text(migration_sql))
                logger.debug("Migration tracking table created/verified")
        except Exception as e:
            logger.error(f"Failed to create migration table: {e}")
            raise
    
    def _apply_migrations(self) -> None:
        """Apply all pending database migrations in order."""
        migrations = self._get_pending_migrations()
        
        for migration in migrations:
            try:
                logger.info(f"Applying migration: {migration['version']} - {migration['description']}")
                
                # Execute migration
                migration['function']()
                
                # Record migration as applied
                self._record_migration(migration)
                
                logger.info(f"Migration {migration['version']} applied successfully")
                
            except Exception as e:
                logger.error(f"Migration {migration['version']} failed: {e}")
                raise
    
    def _get_pending_migrations(self) -> List[Dict[str, Any]]:
        """
        Get list of migrations that need to be applied.
        
        Returns:
            list: Pending migrations in order
        """
        # Define migrations in chronological order
        all_migrations = [
            {
                "version": "1.0.0",
                "description": "Initial schema - Orders and ActiveSessions tables",
                "function": self._migration_v1_0_0
            },
            {
                "version": "1.0.1", 
                "description": "Add indexes for performance optimization",
                "function": self._migration_v1_0_1
            }
        ]
        
        # Get applied migrations
        applied_versions = self._get_applied_migrations()
        
        # Filter to pending migrations
        pending = [m for m in all_migrations if m['version'] not in applied_versions]
        
        logger.info(f"Found {len(pending)} pending migrations")
        return pending
    
    def _get_applied_migrations(self) -> List[str]:
        """Get list of already applied migration versions."""
        try:
            with db_manager.get_session() as session:
                result = session.execute(text("SELECT version FROM schema_migrations ORDER BY applied_at"))
                return [row[0] for row in result.fetchall()]
        except Exception:
            # Migration table doesn't exist yet
            return []
    
    def _record_migration(self, migration: Dict[str, Any]) -> None:
        """Record a migration as applied in the tracking table."""
        try:
            with db_manager.get_session() as session:
                session.execute(
                    text("""
                        INSERT INTO schema_migrations (version, description, applied_at)
                        VALUES (:version, :description, :applied_at)
                    """),
                    {
                        "version": migration['version'],
                        "description": migration['description'],
                        "applied_at": datetime.utcnow()
                    }
                )
        except Exception as e:
            logger.error(f"Failed to record migration {migration['version']}: {e}")
            raise
    
    # Migration Functions
    
    def _migration_v1_0_0(self) -> None:
        """Initial schema migration - create Orders and ActiveSessions tables."""
        logger.info("Creating initial database schema...")
        
        # Create all tables defined in models
        with db_manager.get_session() as session:
            Base.metadata.create_all(session.bind)
        
        logger.info("Initial schema created successfully")
    
    def _migration_v1_0_1(self) -> None:
        """Add database indexes for performance optimization."""
        logger.info("Adding performance indexes...")
        
        indexes = [
            # Orders table indexes
            "CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(phone_number)",
            "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status)",
            "CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_orders_interface_type ON orders(interface_type)",
            
            # ActiveSessions table indexes
            "CREATE INDEX IF NOT EXISTS idx_sessions_phone ON active_sessions(customer_phone)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_interface ON active_sessions(interface_type)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON active_sessions(created_at)"
        ]
        
        try:
            with db_manager.get_session() as session:
                for index_sql in indexes:
                    session.execute(text(index_sql))
            
            logger.info("Performance indexes created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
            raise
    
    def _verify_database_integrity(self) -> bool:
        """
        Verify database schema and data integrity.
        
        Returns:
            bool: True if database passes all integrity checks
        """
        try:
            logger.info("Verifying database integrity...")
            
            # Check that all required tables exist
            required_tables = ['orders', 'active_sessions', 'schema_migrations']
            
            with db_manager.get_session() as session:
                inspector = inspect(session.bind)
                existing_tables = inspector.get_table_names()
                
                for table in required_tables:
                    if table not in existing_tables:
                        logger.error(f"Required table missing: {table}")
                        return False
                
                # Verify table schemas
                if not self._verify_table_schema(inspector, 'orders', Order):
                    return False
                
                if not self._verify_table_schema(inspector, 'active_sessions', ActiveSession):
                    return False
                
                # Test basic operations
                session.execute(text("SELECT COUNT(*) FROM orders"))
                session.execute(text("SELECT COUNT(*) FROM active_sessions"))
                
            logger.info("Database integrity check passed")
            return True
            
        except Exception as e:
            logger.error(f"Database integrity check failed: {e}")
            return False
    
    def _verify_table_schema(self, inspector, table_name: str, model_class) -> bool:
        """
        Verify that table schema matches model definition.
        
        Args:
            inspector: SQLAlchemy inspector instance
            table_name (str): Name of table to verify
            model_class: SQLAlchemy model class
            
        Returns:
            bool: True if schema matches
        """
        try:
            columns = inspector.get_columns(table_name)
            column_names = {col['name'] for col in columns}
            
            # Get expected columns from model
            expected_columns = {col.name for col in model_class.__table__.columns}
            
            # Check for missing columns
            missing = expected_columns - column_names
            if missing:
                logger.error(f"Table {table_name} missing columns: {missing}")
                return False
            
            logger.debug(f"Table {table_name} schema verified")
            return True
            
        except Exception as e:
            logger.error(f"Failed to verify schema for table {table_name}: {e}")
            return False
    
    def backup_database(self, backup_path: str) -> bool:
        """
        Create a backup of the SQLite database.
        
        Args:
            backup_path (str): Path for backup file
            
        Returns:
            bool: True if backup successful
        """
        try:
            logger.info(f"Creating database backup at: {backup_path}")
            
            # For SQLite, we can use the backup API
            with db_manager.get_session() as session:
                # Get the database file path from connection URL
                db_url = db_manager.database_url
                if db_url.startswith('sqlite:///'):
                    source_path = db_url[10:]  # Remove 'sqlite:///'
                    
                    # Copy database file
                    import shutil
                    shutil.copy2(source_path, backup_path)
                    
                    logger.info("Database backup completed successfully")
                    return True
                else:
                    logger.error("Backup only supported for SQLite file databases")
                    return False
                    
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            return False
    
    def get_migration_status(self) -> Dict[str, Any]:
        """
        Get current migration status and database information.
        
        Returns:
            dict: Migration and database status information
        """
        try:
            with db_manager.get_session() as session:
                # Get applied migrations
                result = session.execute(
                    text("SELECT version, description, applied_at FROM schema_migrations ORDER BY applied_at")
                )
                applied_migrations = [
                    {
                        "version": row[0],
                        "description": row[1], 
                        "applied_at": row[2].isoformat() if row[2] else None
                    }
                    for row in result.fetchall()
                ]
                
                # Get table counts
                orders_count = session.execute(text("SELECT COUNT(*) FROM orders")).scalar()
                sessions_count = session.execute(text("SELECT COUNT(*) FROM active_sessions")).scalar()
                
                return {
                    "current_version": self.current_version,
                    "applied_migrations": applied_migrations,
                    "table_counts": {
                        "orders": orders_count,
                        "active_sessions": sessions_count
                    },
                    "database_health": db_manager.health_check(),
                    "redis_health": redis_client.health_check() if redis_client._initialized else False
                }
                
        except Exception as e:
            logger.error(f"Failed to get migration status: {e}")
            return {"error": str(e)}


# Global migrator instance
migrator = DatabaseMigrator()


def initialize_database() -> bool:
    """
    Initialize database for application startup.
    
    Returns:
        bool: True if initialization successful
    """
    return migrator.initialize_database()


def get_migration_status() -> Dict[str, Any]:
    """
    Get current database and migration status.
    
    Returns:
        dict: Status information
    """
    return migrator.get_migration_status()


def backup_database(backup_path: str) -> bool:
    """
    Create database backup.
    
    Args:
        backup_path (str): Path for backup file
        
    Returns:
        bool: True if backup successful
    """
    return migrator.backup_database(backup_path)