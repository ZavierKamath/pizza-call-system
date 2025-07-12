"""
Redis client with connection pooling for session management and caching.
Handles active session tracking, connection pooling, and real-time data storage.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
import time
from contextlib import contextmanager
import redis
from redis.connection import ConnectionPool
from redis.exceptions import ConnectionError, TimeoutError, RedisError

# Configure logging for Redis operations
logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis client manager with connection pooling and session management.
    
    Provides high-level operations for session tracking, caching, and
    real-time data storage for the pizza ordering system.
    """
    
    def __init__(self, redis_url: Optional[str] = None, max_connections: int = 20):
        """
        Initialize Redis client with connection pooling.
        
        Args:
            redis_url (str): Redis connection URL, defaults to environment variable
            max_connections (int): Maximum connections in pool
        """
        self.redis_url = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.max_connections = max_connections
        self.pool = None
        self.client = None
        self._initialized = False
        
        # Session management configuration
        self.session_ttl = 30 * 60  # 30 minutes default TTL
        self.max_concurrent_sessions = 20  # Match PRD requirement
        
        logger.info(f"RedisClient initialized with URL: {self.redis_url}")
    
    def initialize(self) -> None:
        """
        Initialize Redis connection pool and client.
        
        Creates connection pool with retry logic and health checking.
        """
        if self._initialized:
            logger.debug("Redis client already initialized, skipping...")
            return
        
        try:
            # Create connection pool with configuration
            self.pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                retry_on_timeout=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                health_check_interval=30
            )
            
            # Create Redis client with connection pool
            self.client = redis.Redis(
                connection_pool=self.pool,
                decode_responses=True,  # Automatically decode byte responses
                socket_keepalive=True,
                socket_keepalive_options={}
            )
            
            # Test connection
            self.client.ping()
            
            self._initialized = True
            logger.info("Redis client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for Redis connections with error handling.
        
        Yields:
            redis.Redis: Redis client for operations
        """
        if not self._initialized:
            self.initialize()
        
        try:
            yield self.client
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Redis connection error: {e}")
            raise
        except RedisError as e:
            logger.error(f"Redis operation error: {e}")
            raise
    
    # Session Management Operations
    
    def create_session(self, session_id: str, session_data: Dict[str, Any]) -> bool:
        """
        Create a new active session with automatic expiration.
        
        Args:
            session_id (str): Unique session identifier
            session_data (dict): Session information and state
            
        Returns:
            bool: True if session created successfully
        """
        try:
            with self.get_connection() as redis_client:
                # Check if we've reached the maximum concurrent sessions
                current_sessions = self.get_active_session_count()
                if current_sessions >= self.max_concurrent_sessions:
                    logger.warning(
                        f"Maximum concurrent sessions ({self.max_concurrent_sessions}) reached. "
                        f"Cannot create new session: {session_id}"
                    )
                    return False
                
                # Add session creation timestamp
                session_data['created_at'] = time.time()
                session_data['last_activity'] = time.time()
                
                # Store session with TTL
                session_key = f"session:{session_id}"
                redis_client.setex(
                    session_key,
                    self.session_ttl,
                    json.dumps(session_data)
                )
                
                # Add to active sessions set for monitoring
                redis_client.sadd("active_sessions", session_id)
                redis_client.expire("active_sessions", self.session_ttl)
                
                logger.info(f"Session created: {session_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to create session {session_id}: {e}")
            return False
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data by session ID.
        
        Args:
            session_id (str): Session identifier
            
        Returns:
            dict: Session data if found, None otherwise
        """
        try:
            with self.get_connection() as redis_client:
                session_key = f"session:{session_id}"
                session_data = redis_client.get(session_key)
                
                if session_data:
                    # Update last activity timestamp
                    data = json.loads(session_data)
                    data['last_activity'] = time.time()
                    redis_client.setex(session_key, self.session_ttl, json.dumps(data))
                    
                    logger.debug(f"Session retrieved: {session_id}")
                    return data
                
                logger.debug(f"Session not found: {session_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None
    
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update existing session data.
        
        Args:
            session_id (str): Session identifier
            updates (dict): Fields to update
            
        Returns:
            bool: True if session updated successfully
        """
        try:
            with self.get_connection() as redis_client:
                session_key = f"session:{session_id}"
                session_data = redis_client.get(session_key)
                
                if not session_data:
                    logger.warning(f"Cannot update non-existent session: {session_id}")
                    return False
                
                # Merge updates with existing data
                data = json.loads(session_data)
                data.update(updates)
                data['last_activity'] = time.time()
                
                # Store updated session
                redis_client.setex(session_key, self.session_ttl, json.dumps(data))
                
                logger.debug(f"Session updated: {session_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return False
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete session and remove from active sessions.
        
        Args:
            session_id (str): Session identifier
            
        Returns:
            bool: True if session deleted successfully
        """
        try:
            with self.get_connection() as redis_client:
                session_key = f"session:{session_id}"
                
                # Remove session data
                deleted = redis_client.delete(session_key)
                
                # Remove from active sessions set
                redis_client.srem("active_sessions", session_id)
                
                if deleted:
                    logger.info(f"Session deleted: {session_id}")
                    return True
                else:
                    logger.warning(f"Session not found for deletion: {session_id}")
                    return False
                
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
    
    def get_active_sessions(self) -> List[str]:
        """
        Get list of all active session IDs.
        
        Returns:
            list: Active session identifiers
        """
        try:
            with self.get_connection() as redis_client:
                sessions = redis_client.smembers("active_sessions")
                logger.debug(f"Retrieved {len(sessions)} active sessions")
                return list(sessions)
                
        except Exception as e:
            logger.error(f"Failed to get active sessions: {e}")
            return []
    
    def get_active_session_count(self) -> int:
        """
        Get count of active sessions for monitoring.
        
        Returns:
            int: Number of active sessions
        """
        try:
            with self.get_connection() as redis_client:
                count = redis_client.scard("active_sessions")
                logger.debug(f"Active session count: {count}")
                return count
                
        except Exception as e:
            logger.error(f"Failed to get active session count: {e}")
            return 0
    
    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions from active sessions set.
        
        Returns:
            int: Number of sessions cleaned up
        """
        try:
            with self.get_connection() as redis_client:
                active_sessions = self.get_active_sessions()
                expired_count = 0
                
                for session_id in active_sessions:
                    session_key = f"session:{session_id}"
                    if not redis_client.exists(session_key):
                        # Session expired, remove from active set
                        redis_client.srem("active_sessions", session_id)
                        expired_count += 1
                
                if expired_count > 0:
                    logger.info(f"Cleaned up {expired_count} expired sessions")
                
                return expired_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0
    
    # Caching Operations
    
    def cache_set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """
        Set cache value with TTL.
        
        Args:
            key (str): Cache key
            value: Value to cache (will be JSON serialized)
            ttl (int): Time to live in seconds
            
        Returns:
            bool: True if value cached successfully
        """
        try:
            with self.get_connection() as redis_client:
                redis_client.setex(f"cache:{key}", ttl, json.dumps(value))
                logger.debug(f"Cache set: {key}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to set cache {key}: {e}")
            return False
    
    def cache_get(self, key: str) -> Optional[Any]:
        """
        Get cached value.
        
        Args:
            key (str): Cache key
            
        Returns:
            Cached value if found, None otherwise
        """
        try:
            with self.get_connection() as redis_client:
                value = redis_client.get(f"cache:{key}")
                if value:
                    logger.debug(f"Cache hit: {key}")
                    return json.loads(value)
                else:
                    logger.debug(f"Cache miss: {key}")
                    return None
                
        except Exception as e:
            logger.error(f"Failed to get cache {key}: {e}")
            return None
    
    def cache_delete(self, key: str) -> bool:
        """
        Delete cached value.
        
        Args:
            key (str): Cache key
            
        Returns:
            bool: True if value deleted successfully
        """
        try:
            with self.get_connection() as redis_client:
                deleted = redis_client.delete(f"cache:{key}")
                logger.debug(f"Cache deleted: {key}")
                return bool(deleted)
                
        except Exception as e:
            logger.error(f"Failed to delete cache {key}: {e}")
            return False
    
    # Health and Monitoring
    
    def health_check(self) -> bool:
        """
        Perform Redis health check.
        
        Returns:
            bool: True if Redis is accessible and responsive
        """
        try:
            with self.get_connection() as redis_client:
                redis_client.ping()
                logger.debug("Redis health check passed")
                return True
                
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get Redis connection pool information for monitoring.
        
        Returns:
            dict: Connection pool status and statistics
        """
        if not self.pool:
            return {"status": "not_initialized"}
        
        try:
            with self.get_connection() as redis_client:
                info = redis_client.info()
                return {
                    "status": "connected" if self._initialized else "disconnected",
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "active_sessions": self.get_active_session_count(),
                    "max_concurrent_sessions": self.max_concurrent_sessions,
                    "pool_created_connections": self.pool.created_connections,
                    "pool_available_connections": len(self.pool._available_connections)
                }
        except Exception as e:
            logger.error(f"Failed to get Redis connection info: {e}")
            return {"status": "error", "error": str(e)}
    
    def close(self) -> None:
        """
        Close Redis connection pool and cleanup resources.
        
        Should be called during application shutdown.
        """
        if self.pool:
            self.pool.disconnect()
            logger.info("Redis connection pool closed")
        self._initialized = False


# Global Redis client instance
redis_client = RedisClient()


def init_redis() -> None:
    """
    Initialize Redis client for application startup.
    
    Should be called during application initialization.
    """
    redis_client.initialize()


def close_redis() -> None:
    """
    Close Redis connections for application shutdown.
    
    Should be called during application cleanup.
    """
    redis_client.close()


def get_redis_client() -> RedisClient:
    """
    Get global Redis client instance.
    
    Returns:
        RedisClient: Initialized Redis client
    """
    if not redis_client._initialized:
        redis_client.initialize()
    return redis_client