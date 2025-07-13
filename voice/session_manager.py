"""
Session manager for tracking active phone sessions in Redis.
Implements 20 concurrent call limit and handles session lifecycle management.
"""

import logging
import asyncio
import json
import time
from typing import Dict, List, Optional, Set, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

from database.redis_client import get_redis_async
from database.models import ActiveSession
from database.connection import db_manager
from config.settings import settings
from agents.states import OrderState, StateManager

# Configure logging for session management
logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Information about an active session."""
    session_id: str
    interface_type: str  # "phone" or "web"
    customer_phone: Optional[str]
    agent_state: str
    created_at: datetime
    last_activity: datetime
    is_expired: bool = False


class SessionManager:
    """
    Manages active voice sessions with Redis-based tracking and concurrent limits.
    
    Provides session lifecycle management, concurrent call limiting, and cleanup
    for both phone and web interface sessions.
    """
    
    def __init__(self):
        """Initialize session manager with Redis connection and settings."""
        self.max_concurrent_sessions = settings.max_concurrent_calls
        self.session_timeout_minutes = settings.session_timeout_minutes
        self.cleanup_interval_seconds = 300  # Clean up expired sessions every 5 minutes
        
        # Redis key patterns
        self.active_sessions_key = "active_sessions"
        self.session_data_prefix = "session_data"
        self.session_count_key = "session_count"
        
        logger.info(f"SessionManager initialized with max {self.max_concurrent_sessions} concurrent sessions")
    
    async def can_accept_new_session(self, interface_type: str = None) -> bool:
        """
        Check if system can accept a new session within concurrent limits.
        
        Args:
            interface_type: Optional interface type filter ("phone" or "web")
            
        Returns:
            bool: True if new session can be accepted
        """
        try:
            current_count = await self.get_active_session_count(interface_type)
            
            # If checking for specific interface, use total limit
            if interface_type:
                can_accept = current_count < self.max_concurrent_sessions
            else:
                can_accept = current_count < self.max_concurrent_sessions
            
            logger.debug(f"Session capacity check: {current_count}/{self.max_concurrent_sessions} active, can_accept={can_accept}")
            return can_accept
            
        except Exception as e:
            logger.error(f"Error checking session capacity: {str(e)}")
            # Fail safe - allow session if we can't check
            return True
    
    async def create_session(self, session_id: str, interface_type: str, 
                           customer_phone: Optional[str] = None) -> str:
        """
        Create a new active session with concurrent limit enforcement.
        
        Args:
            session_id: Unique session identifier
            interface_type: "phone" or "web"
            customer_phone: Customer phone number if available
            
        Returns:
            str: Created session ID
            
        Raises:
            ValueError: If concurrent limit exceeded or invalid parameters
        """
        try:
            # Validate parameters
            if not session_id or not interface_type:
                raise ValueError("session_id and interface_type are required")
            
            if interface_type not in ["phone", "web"]:
                raise ValueError("interface_type must be 'phone' or 'web'")
            
            # Check concurrent limits
            if not await self.can_accept_new_session():
                raise ValueError(f"Concurrent session limit ({self.max_concurrent_sessions}) exceeded")
            
            # Create session info
            now = datetime.utcnow()
            session_info = SessionInfo(
                session_id=session_id,
                interface_type=interface_type,
                customer_phone=customer_phone,
                agent_state="greeting",
                created_at=now,
                last_activity=now
            )
            
            # Store in Redis
            redis_client = await get_redis_async()
            
            with redis_client.get_connection() as conn:
                # Add to active sessions set
                conn.sadd(self.active_sessions_key, session_id)
                
                # Store session data with expiration
                session_data_key = f"{self.session_data_prefix}:{session_id}"
                session_data = json.dumps(asdict(session_info), default=str)
                conn.setex(
                    session_data_key,
                    self.session_timeout_minutes * 60,
                    session_data
                )
                
                # Update session count
                conn.incr(self.session_count_key)
            
            # Store in database for persistence
            await self._store_session_in_database(session_info)
            
            logger.info(f"Created session {session_id} ({interface_type}) for customer {customer_phone}")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to create session {session_id}: {str(e)}")
            raise
    
    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """
        Retrieve session information by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            SessionInfo: Session data or None if not found
        """
        try:
            redis_client = await get_redis_async()
            session_data_key = f"{self.session_data_prefix}:{session_id}"
            
            with redis_client.get_connection() as conn:
                session_data = conn.get(session_data_key)
            if not session_data:
                logger.debug(f"Session {session_id} not found in Redis")
                return None
            
            # Parse session data
            session_dict = json.loads(session_data)
            
            # Convert datetime strings back to datetime objects
            session_dict['created_at'] = datetime.fromisoformat(session_dict['created_at'].replace('Z', '+00:00'))
            session_dict['last_activity'] = datetime.fromisoformat(session_dict['last_activity'].replace('Z', '+00:00'))
            
            session_info = SessionInfo(**session_dict)
            
            # Check if session is expired
            session_info.is_expired = self._is_session_expired(session_info)
            
            return session_info
            
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {str(e)}")
            return None
    
    async def update_session_activity(self, session_id: str, new_state: Optional[str] = None) -> bool:
        """
        Update session last activity time and optionally the agent state.
        
        Args:
            session_id: Session identifier
            new_state: Optional new agent state
            
        Returns:
            bool: True if updated successfully
        """
        try:
            session_info = await self.get_session(session_id)
            if not session_info:
                logger.warning(f"Cannot update activity for non-existent session {session_id}")
                return False
            
            # Update activity time
            session_info.last_activity = datetime.utcnow()
            
            # Update state if provided
            if new_state:
                session_info.agent_state = new_state
            
            # Store updated session data
            redis_client = await get_redis_async()
            session_data_key = f"{self.session_data_prefix}:{session_id}"
            session_data = json.dumps(asdict(session_info), default=str)
            
            with redis_client.get_connection() as conn:
                conn.setex(
                    session_data_key,
                    self.session_timeout_minutes * 60,
                    session_data
                )
            
            logger.debug(f"Updated activity for session {session_id}, state: {session_info.agent_state}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update session activity {session_id}: {str(e)}")
            return False
    
    async def end_session(self, session_id: str, reason: str = "completed") -> bool:
        """
        End an active session and clean up resources.
        
        Args:
            session_id: Session identifier
            reason: Reason for ending session
            
        Returns:
            bool: True if ended successfully
        """
        try:
            redis_client = await get_redis_async()
            
            # Check if session exists
            session_info = await self.get_session(session_id)
            if session_info:
                logger.info(f"Ending session {session_id} (reason: {reason}, duration: {datetime.utcnow() - session_info.created_at})")
            else:
                logger.info(f"Ending session {session_id} (reason: {reason}, no session data found)")
            
            with redis_client.get_connection() as conn:
                # Remove from active sessions set
                conn.srem(self.active_sessions_key, session_id)
                
                # Remove session data
                session_data_key = f"{self.session_data_prefix}:{session_id}"
                conn.delete(session_data_key)
                
                # Decrement session count
                count = conn.decr(self.session_count_key)
                if count < 0:
                    conn.set(self.session_count_key, 0)
            
            # Update database record
            await self._end_session_in_database(session_id)
            
            logger.info(f"Successfully ended session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to end session {session_id}: {str(e)}")
            return False
    
    async def get_active_sessions(self, interface_type: Optional[str] = None) -> List[SessionInfo]:
        """
        Get list of all active sessions, optionally filtered by interface type.
        
        Args:
            interface_type: Optional filter ("phone" or "web")
            
        Returns:
            List[SessionInfo]: Active sessions
        """
        try:
            redis_client = await get_redis_async()
            
            # Get all active session IDs
            with redis_client.get_connection() as conn:
                session_ids = conn.smembers(self.active_sessions_key)
            
            active_sessions = []
            for session_id in session_ids:
                session_info = await self.get_session(session_id.decode() if isinstance(session_id, bytes) else session_id)
                
                if session_info:
                    # Filter by interface type if specified
                    if interface_type and session_info.interface_type != interface_type:
                        continue
                    
                    # Skip expired sessions (will be cleaned up later)
                    if session_info.is_expired:
                        continue
                    
                    active_sessions.append(session_info)
            
            logger.debug(f"Retrieved {len(active_sessions)} active sessions (filter: {interface_type})")
            return active_sessions
            
        except Exception as e:
            logger.error(f"Failed to get active sessions: {str(e)}")
            return []
    
    async def get_active_session_count(self, interface_type: Optional[str] = None) -> int:
        """
        Get count of active sessions, optionally filtered by interface type.
        
        Args:
            interface_type: Optional filter ("phone" or "web")
            
        Returns:
            int: Number of active sessions
        """
        try:
            if interface_type:
                # Need to count sessions of specific type
                sessions = await self.get_active_sessions(interface_type)
                return len(sessions)
            else:
                # Use Redis counter for total count
                redis_client = await get_redis_async()
                with redis_client.get_connection() as conn:
                    count = conn.get(self.session_count_key)
                return int(count) if count else 0
                
        except Exception as e:
            logger.error(f"Failed to get session count: {str(e)}")
            return 0
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions from Redis and database.
        
        Returns:
            int: Number of sessions cleaned up
        """
        try:
            sessions = await self.get_active_sessions()
            expired_count = 0
            
            for session in sessions:
                if self._is_session_expired(session):
                    await self.end_session(session.session_id, "expired")
                    expired_count += 1
            
            if expired_count > 0:
                logger.info(f"Cleaned up {expired_count} expired sessions")
            
            return expired_count
            
        except Exception as e:
            logger.error(f"Error during session cleanup: {str(e)}")
            return 0
    
    async def get_session_statistics(self) -> Dict[str, Any]:
        """
        Get session management statistics for monitoring.
        
        Returns:
            dict: Session statistics
        """
        try:
            active_sessions = await self.get_active_sessions()
            phone_sessions = [s for s in active_sessions if s.interface_type == "phone"]
            web_sessions = [s for s in active_sessions if s.interface_type == "web"]
            
            # Calculate average session duration
            now = datetime.utcnow()
            durations = [(now - s.created_at).total_seconds() / 60 for s in active_sessions]
            avg_duration = sum(durations) / len(durations) if durations else 0
            
            stats = {
                'total_active_sessions': len(active_sessions),
                'phone_sessions': len(phone_sessions),
                'web_sessions': len(web_sessions),
                'max_concurrent_sessions': self.max_concurrent_sessions,
                'capacity_utilization': len(active_sessions) / self.max_concurrent_sessions,
                'average_session_duration_minutes': round(avg_duration, 2),
                'session_timeout_minutes': self.session_timeout_minutes
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get session statistics: {str(e)}")
            return {'error': str(e)}
    
    def _is_session_expired(self, session_info: SessionInfo) -> bool:
        """
        Check if a session has expired based on last activity.
        
        Args:
            session_info: Session information
            
        Returns:
            bool: True if session is expired
        """
        timeout_delta = timedelta(minutes=self.session_timeout_minutes)
        return (datetime.utcnow() - session_info.last_activity) > timeout_delta
    
    async def _store_session_in_database(self, session_info: SessionInfo) -> None:
        """
        Store session information in SQLite database for persistence.
        
        Args:
            session_info: Session information to store
        """
        try:
            with db_manager.get_session() as db_session:
                # Create ActiveSession database record
                active_session = ActiveSession(
                session_id=session_info.session_id,
                customer_phone=session_info.customer_phone,
                interface_type=session_info.interface_type,
                agent_state=session_info.agent_state,
                order_data=None,  # Will be updated as conversation progresses
                created_at=session_info.created_at
                )
                
                db_session.add(active_session)
                db_session.commit()
                
                logger.debug(f"Stored session {session_info.session_id} in database")
            
        except Exception as e:
            logger.error(f"Failed to store session in database: {str(e)}")
            # Don't raise - Redis storage is primary, database is backup
    
    async def _end_session_in_database(self, session_id: str) -> None:
        """
        Mark session as ended in database.
        
        Args:
            session_id: Session identifier
        """
        try:
            with db_manager.get_session() as db_session:
                # Remove from active sessions table
                active_session = db_session.query(ActiveSession).filter(
                    ActiveSession.session_id == session_id
                ).first()
                
                if active_session:
                    db_session.delete(active_session)
                    db_session.commit()
                    logger.debug(f"Removed session {session_id} from database")
            
        except Exception as e:
            logger.error(f"Failed to end session in database: {str(e)}")
            # Don't raise - Redis cleanup is primary
    
    async def start_cleanup_task(self) -> None:
        """
        Start background task for periodic session cleanup.
        
        This should be called during application startup.
        """
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(self.cleanup_interval_seconds)
                    await self.cleanup_expired_sessions()
                except Exception as e:
                    logger.error(f"Error in session cleanup task: {str(e)}")
        
        # Start cleanup task in background
        asyncio.create_task(cleanup_loop())
        logger.info(f"Started session cleanup task (interval: {self.cleanup_interval_seconds}s)")


# Create global session manager instance
session_manager = SessionManager()


# Utility functions for FastAPI integration
async def get_current_session_count() -> int:
    """Get current active session count."""
    return await session_manager.get_active_session_count()


async def can_accept_new_call() -> bool:
    """Check if system can accept new phone call."""
    return await session_manager.can_accept_new_session("phone")


async def get_session_stats() -> Dict[str, Any]:
    """Get session management statistics."""
    return await session_manager.get_session_statistics()


async def cleanup_sessions() -> int:
    """Manually trigger session cleanup."""
    return await session_manager.cleanup_expired_sessions()