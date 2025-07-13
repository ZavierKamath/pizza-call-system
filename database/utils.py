"""
Database utility functions for CRUD operations on orders and sessions.
Provides high-level database operations with error handling and logging.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_
from sqlalchemy.exc import SQLAlchemyError
from .connection import db_manager
from .models import Order, ActiveSession
from .redis_client import redis_client

# Configure logging for database utilities
logger = logging.getLogger(__name__)


class OrderManager:
    """
    High-level order management with CRUD operations and business logic.
    
    Handles order lifecycle from creation to completion with proper
    error handling and logging.
    """
    
    @staticmethod
    def create_order(order_data: Dict[str, Any]) -> Optional[Order]:
        """
        Create a new order with validation and logging.
        
        Args:
            order_data (dict): Order information including customer details,
                             order items, payment info, etc.
                             
        Returns:
            Order: Created order instance or None if failed
        """
        try:
            def _create_order_operation(session: Session, data: Dict[str, Any]) -> Order:
                # Create new order instance
                order = Order(
                    customer_name=data['customer_name'],
                    phone_number=data['phone_number'], 
                    address=data['address'],
                    order_details=data['order_details'],
                    total_amount=data['total_amount'],
                    estimated_delivery=data['estimated_delivery'],
                    payment_method=data['payment_method'],
                    payment_status=data.get('payment_status', 'pending'),
                    order_status=data.get('order_status', 'pending'),
                    interface_type=data['interface_type']
                )
                
                # Add to session and flush to get ID
                session.add(order)
                session.flush()
                
                logger.info(f"Order created: ID={order.id}, Customer={order.customer_name}, Total=${order.total_amount}")
                return order
            
            # Execute with retry logic
            return db_manager.execute_with_retry(_create_order_operation, order_data)
            
        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            return None
    
    @staticmethod
    def get_order(order_id: int) -> Optional[Order]:
        """
        Retrieve order by ID.
        
        Args:
            order_id (int): Order identifier
            
        Returns:
            Order: Order instance or None if not found
        """
        try:
            def _get_order_operation(session: Session, order_id: int) -> Optional[Order]:
                order = session.query(Order).filter(Order.id == order_id).first()
                if order:
                    logger.debug(f"Order retrieved: ID={order_id}")
                else:
                    logger.debug(f"Order not found: ID={order_id}")
                return order
            
            return db_manager.execute_with_retry(_get_order_operation, order_id)
            
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None
    
    @staticmethod
    def update_order_status(order_id: int, status: str) -> bool:
        """
        Update order status with logging.
        
        Args:
            order_id (int): Order identifier
            status (str): New order status (pending, preparing, ready, delivered)
            
        Returns:
            bool: True if update successful
        """
        try:
            def _update_status_operation(session: Session, order_id: int, status: str) -> bool:
                order = session.query(Order).filter(Order.id == order_id).first()
                if not order:
                    logger.warning(f"Cannot update status for non-existent order: {order_id}")
                    return False
                
                old_status = order.order_status
                order.order_status = status
                order.updated_at = datetime.utcnow()
                
                logger.info(f"Order {order_id} status updated: {old_status} -> {status}")
                return True
            
            return db_manager.execute_with_retry(_update_status_operation, order_id, status)
            
        except Exception as e:
            logger.error(f"Failed to update order {order_id} status: {e}")
            return False
    
    @staticmethod
    def update_payment_status(order_id: int, payment_status: str, payment_details: Optional[Dict] = None) -> bool:
        """
        Update order payment status.
        
        Args:
            order_id (int): Order identifier
            payment_status (str): New payment status (pending, completed, failed)
            payment_details (dict): Additional payment information
            
        Returns:
            bool: True if update successful
        """
        try:
            def _update_payment_operation(session: Session, order_id: int, status: str, details: Optional[Dict]) -> bool:
                order = session.query(Order).filter(Order.id == order_id).first()
                if not order:
                    logger.warning(f"Cannot update payment for non-existent order: {order_id}")
                    return False
                
                old_status = order.payment_status
                order.payment_status = status
                order.updated_at = datetime.utcnow()
                
                # Update order details with payment information if provided
                if details:
                    if not order.order_details:
                        order.order_details = {}
                    order.order_details.update({"payment_details": details})
                
                logger.info(f"Order {order_id} payment status updated: {old_status} -> {status}")
                return True
            
            return db_manager.execute_with_retry(_update_payment_operation, order_id, payment_status, payment_details)
            
        except Exception as e:
            logger.error(f"Failed to update order {order_id} payment status: {e}")
            return False
    
    @staticmethod
    def get_orders_by_phone(phone_number: str, limit: int = 10) -> List[Order]:
        """
        Get recent orders for a customer by phone number.
        
        Args:
            phone_number (str): Customer phone number
            limit (int): Maximum number of orders to return
            
        Returns:
            list: List of Order instances
        """
        try:
            def _get_orders_by_phone_operation(session: Session, phone: str, limit: int) -> List[Order]:
                orders = session.query(Order).filter(
                    Order.phone_number == phone
                ).order_by(desc(Order.created_at)).limit(limit).all()
                
                logger.debug(f"Retrieved {len(orders)} orders for phone: {phone}")
                return orders
            
            return db_manager.execute_with_retry(_get_orders_by_phone_operation, phone_number, limit)
            
        except Exception as e:
            logger.error(f"Failed to get orders for phone {phone_number}: {e}")
            return []
    
    @staticmethod
    def get_active_orders() -> List[Order]:
        """
        Get all active orders (not delivered or cancelled).
        
        Returns:
            list: List of active Order instances
        """
        try:
            def _get_active_orders_operation(session: Session) -> List[Order]:
                orders = session.query(Order).filter(
                    and_(
                        Order.order_status.in_(['pending', 'preparing', 'ready']),
                        Order.payment_status == 'completed'
                    )
                ).order_by(Order.created_at).all()
                
                logger.debug(f"Retrieved {len(orders)} active orders")
                return orders
            
            return db_manager.execute_with_retry(_get_active_orders_operation)
            
        except Exception as e:
            logger.error(f"Failed to get active orders: {e}")
            return []
    
    @staticmethod
    def get_orders_by_status(status: str) -> List[Order]:
        """
        Get orders by status for dashboard monitoring.
        
        Args:
            status (str): Order status to filter by
            
        Returns:
            list: List of Order instances with specified status
        """
        try:
            def _get_orders_by_status_operation(session: Session, status: str) -> List[Order]:
                orders = session.query(Order).filter(
                    Order.order_status == status
                ).order_by(desc(Order.created_at)).all()
                
                logger.debug(f"Retrieved {len(orders)} orders with status: {status}")
                return orders
            
            return db_manager.execute_with_retry(_get_orders_by_status_operation, status)
            
        except Exception as e:
            logger.error(f"Failed to get orders by status {status}: {e}")
            return []


class SessionManager:
    """
    High-level session management with CRUD operations and Redis integration.
    
    Manages active conversation sessions with automatic cleanup and
    connection pool monitoring.
    """
    
    @staticmethod
    def create_session(session_id: str, session_data: Dict[str, Any]) -> bool:
        """
        Create a new active session in both database and Redis.
        
        Args:
            session_id (str): Unique session identifier
            session_data (dict): Session information and state
            
        Returns:
            bool: True if session created successfully
        """
        try:
            # Create session in Redis for real-time operations
            redis_success = redis_client.create_session(session_id, session_data)
            if not redis_success:
                logger.warning(f"Failed to create Redis session: {session_id}")
                return False
            
            # Create session in database for persistence
            def _create_session_operation(session: Session, session_id: str, data: Dict[str, Any]) -> bool:
                db_session = ActiveSession(
                    session_id=session_id,
                    customer_phone=data.get('customer_phone'),
                    interface_type=data['interface_type'],
                    agent_state=data.get('agent_state', 'greeting'),
                    order_data=data.get('order_data')
                )
                
                session.add(db_session)
                session.flush()
                
                logger.info(f"Session created: {session_id} ({data['interface_type']})")
                return True
            
            db_success = db_manager.execute_with_retry(_create_session_operation, session_id, session_data)
            
            if not db_success:
                # Cleanup Redis session if database creation failed
                redis_client.delete_session(session_id)
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create session {session_id}: {e}")
            # Cleanup Redis session on error
            redis_client.delete_session(session_id)
            return False
    
    @staticmethod
    def get_session(session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data, preferring Redis for speed.
        
        Args:
            session_id (str): Session identifier
            
        Returns:
            dict: Session data or None if not found
        """
        try:
            # Try Redis first for speed
            session_data = redis_client.get_session(session_id)
            if session_data:
                logger.debug(f"Session retrieved from Redis: {session_id}")
                return session_data
            
            # Fallback to database
            def _get_session_operation(session: Session, session_id: str) -> Optional[Dict[str, Any]]:
                db_session = session.query(ActiveSession).filter(
                    ActiveSession.session_id == session_id
                ).first()
                
                if db_session:
                    logger.debug(f"Session retrieved from database: {session_id}")
                    return db_session.to_dict()
                else:
                    logger.debug(f"Session not found: {session_id}")
                    return None
            
            return db_manager.execute_with_retry(_get_session_operation, session_id)
            
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None
    
    @staticmethod
    def update_session(session_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update session data in both Redis and database.
        
        Args:
            session_id (str): Session identifier
            updates (dict): Fields to update
            
        Returns:
            bool: True if update successful
        """
        try:
            # Update Redis session
            redis_success = redis_client.update_session(session_id, updates)
            
            # Update database session
            def _update_session_operation(session: Session, session_id: str, updates: Dict[str, Any]) -> bool:
                db_session = session.query(ActiveSession).filter(
                    ActiveSession.session_id == session_id
                ).first()
                
                if not db_session:
                    logger.warning(f"Cannot update non-existent session: {session_id}")
                    return False
                
                # Update fields
                if 'customer_phone' in updates:
                    db_session.customer_phone = updates['customer_phone']
                if 'agent_state' in updates:
                    db_session.agent_state = updates['agent_state']
                if 'order_data' in updates:
                    db_session.order_data = updates['order_data']
                
                logger.debug(f"Session updated in database: {session_id}")
                return True
            
            db_success = db_manager.execute_with_retry(_update_session_operation, session_id, updates)
            
            logger.debug(f"Session updated: {session_id} (Redis: {redis_success}, DB: {db_success})")
            return redis_success or db_success  # Success if either succeeds
            
        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return False
    
    @staticmethod
    def delete_session(session_id: str) -> bool:
        """
        Delete session from both Redis and database.
        
        Args:
            session_id (str): Session identifier
            
        Returns:
            bool: True if deletion successful
        """
        try:
            # Delete from Redis
            redis_success = redis_client.delete_session(session_id)
            
            # Delete from database
            def _delete_session_operation(session: Session, session_id: str) -> bool:
                deleted = session.query(ActiveSession).filter(
                    ActiveSession.session_id == session_id
                ).delete()
                
                if deleted:
                    logger.info(f"Session deleted from database: {session_id}")
                    return True
                else:
                    logger.warning(f"Session not found in database for deletion: {session_id}")
                    return False
            
            db_success = db_manager.execute_with_retry(_delete_session_operation, session_id)
            
            logger.info(f"Session deleted: {session_id} (Redis: {redis_success}, DB: {db_success})")
            return redis_success or db_success
            
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
    
    @staticmethod
    def get_active_sessions() -> List[Dict[str, Any]]:
        """
        Get all active sessions for monitoring.
        
        Returns:
            list: List of active session data
        """
        try:
            # Use Redis for real-time session data
            session_ids = redis_client.get_active_sessions()
            sessions = []
            
            for session_id in session_ids:
                session_data = redis_client.get_session(session_id)
                if session_data:
                    sessions.append(session_data)
            
            logger.debug(f"Retrieved {len(sessions)} active sessions from Redis")
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to get active sessions from Redis, falling back to database: {e}")
            
            # Fallback to database
            try:
                def _get_active_sessions_operation(session: Session) -> List[Dict[str, Any]]:
                    db_sessions = session.query(ActiveSession).all()
                    return [s.to_dict() for s in db_sessions]
                
                sessions = db_manager.execute_with_retry(_get_active_sessions_operation)
                logger.debug(f"Retrieved {len(sessions)} active sessions from database")
                return sessions
                
            except Exception as db_error:
                logger.error(f"Failed to get active sessions from database: {db_error}")
                return []
    
    @staticmethod
    def cleanup_expired_sessions() -> int:
        """
        Clean up expired sessions from both Redis and database.
        
        Returns:
            int: Number of sessions cleaned up
        """
        try:
            # Clean up Redis sessions
            redis_cleaned = redis_client.cleanup_expired_sessions()
            
            # Clean up database sessions (older than 30 minutes)
            def _cleanup_db_sessions_operation(session: Session) -> int:
                cutoff_time = datetime.utcnow() - timedelta(minutes=30)
                deleted = session.query(ActiveSession).filter(
                    ActiveSession.created_at < cutoff_time
                ).delete()
                
                return deleted
            
            db_cleaned = db_manager.execute_with_retry(_cleanup_db_sessions_operation)
            
            total_cleaned = redis_cleaned + (db_cleaned or 0)
            if total_cleaned > 0:
                logger.info(f"Cleaned up {total_cleaned} expired sessions (Redis: {redis_cleaned}, DB: {db_cleaned})")
            
            return total_cleaned
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0
    
    @staticmethod
    def get_session_count() -> int:
        """
        Get current count of active sessions.
        
        Returns:
            int: Number of active sessions
        """
        try:
            # Use Redis for real-time count
            return redis_client.get_active_session_count()
        except Exception:
            # Fallback to database count
            try:
                def _get_session_count_operation(session: Session) -> int:
                    return session.query(ActiveSession).count()
                
                return db_manager.execute_with_retry(_get_session_count_operation)
            except Exception as e:
                logger.error(f"Failed to get session count: {e}")
                return 0


# Convenience functions for common operations

def create_order(order_data: Dict[str, Any]) -> Optional[Order]:
    """Create a new order."""
    return OrderManager.create_order(order_data)


def get_order(order_id: int) -> Optional[Order]:
    """Get order by ID."""
    return OrderManager.get_order(order_id)


def get_active_orders() -> List[Order]:
    """Get all active orders for dashboard."""
    return OrderManager.get_active_orders()


def create_session(session_id: str, session_data: Dict[str, Any]) -> bool:
    """Create a new active session."""
    return SessionManager.create_session(session_id, session_data)


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get session data."""
    return SessionManager.get_session(session_id)


def update_session(session_id: str, updates: Dict[str, Any]) -> bool:
    """Update session data."""
    return SessionManager.update_session(session_id, updates)


def get_active_sessions() -> List[Dict[str, Any]]:
    """Get all active sessions."""
    return SessionManager.get_active_sessions()


def cleanup_expired_sessions() -> int:
    """Clean up expired sessions."""
    return SessionManager.cleanup_expired_sessions()