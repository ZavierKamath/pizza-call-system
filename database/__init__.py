"""
Database package for the pizza ordering system.

Provides SQLAlchemy models, Redis client, connection management,
and utility functions for orders and sessions.
"""

# Import main components for easy access
from .models import Base, Order, ActiveSession, create_tables, drop_tables
from .connection import (
    db_manager, 
    get_db_session, 
    init_database, 
    close_database,
    DatabaseManager
)
from .redis_client import (
    redis_client,
    init_redis,
    close_redis,
    get_redis_client,
    RedisClient
)
from .migrations import (
    initialize_database,
    get_migration_status,
    backup_database,
    migrator
)
from .utils import (
    # Order operations
    create_order,
    get_order,
    get_active_orders,
    OrderManager,
    
    # Session operations
    create_session,
    get_session,
    update_session,
    get_active_sessions,
    cleanup_expired_sessions,
    SessionManager
)

# Package metadata
__version__ = "1.0.0"
__author__ = "Pizza Agent Development Team"

# Logging configuration
import logging
logger = logging.getLogger(__name__)

def initialize_all_databases():
    """
    Initialize both SQLite and Redis databases.
    
    Convenience function for application startup.
    """
    try:
        logger.info("Initializing database systems...")
        
        # Initialize SQLite database with migrations
        if initialize_database():
            logger.info("SQLite database initialized successfully")
        else:
            logger.error("SQLite database initialization failed")
            return False
        
        # Initialize Redis client
        try:
            init_redis()
            logger.info("Redis client initialized successfully")
        except Exception as e:
            logger.warning(f"Redis initialization failed (continuing without Redis): {e}")
        
        logger.info("Database systems initialization completed")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


def close_all_databases():
    """
    Close all database connections.
    
    Convenience function for application shutdown.
    """
    try:
        logger.info("Closing database connections...")
        close_database()
        close_redis()
        logger.info("All database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")


def get_database_status():
    """
    Get comprehensive database status for monitoring.
    
    Returns:
        dict: Database status information
    """
    return {
        "sqlite": {
            "status": "connected" if db_manager._initialized else "disconnected",
            "health": db_manager.health_check(),
            "connection_info": db_manager.get_connection_info()
        },
        "redis": {
            "status": "connected" if redis_client._initialized else "disconnected", 
            "health": redis_client.health_check() if redis_client._initialized else False,
            "connection_info": redis_client.get_connection_info() if redis_client._initialized else {}
        },
        "migrations": get_migration_status()
    }


# Export all important components
__all__ = [
    # Models
    'Base', 'Order', 'ActiveSession', 'create_tables', 'drop_tables',
    
    # Connection management
    'db_manager', 'get_db_session', 'init_database', 'close_database', 'DatabaseManager',
    
    # Redis client
    'redis_client', 'init_redis', 'close_redis', 'get_redis_client', 'RedisClient',
    
    # Migrations
    'initialize_database', 'get_migration_status', 'backup_database', 'migrator',
    
    # Utilities
    'create_order', 'get_order', 'get_active_orders', 'OrderManager',
    'create_session', 'get_session', 'update_session', 'get_active_sessions', 
    'cleanup_expired_sessions', 'SessionManager',
    
    # Package functions
    'initialize_all_databases', 'close_all_databases', 'get_database_status'
]