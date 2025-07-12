"""
SQLAlchemy database models for the pizza ordering system.
Contains Order and ActiveSession models as specified in the PRD.
"""

from sqlalchemy import Column, Integer, String, Text, DECIMAL, TIMESTAMP, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
import logging

# Configure logging for database operations
logger = logging.getLogger(__name__)

# SQLAlchemy base class for all models
Base = declarative_base()


class Order(Base):
    """
    Order model representing a complete pizza order.
    
    Tracks all order information from customer details to payment status.
    Maps to the orders table in SQLite database as defined in PRD.
    """
    __tablename__ = 'orders'
    
    # Primary key - auto-incrementing integer
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Customer information
    customer_name = Column(String(255), nullable=False, comment="Full customer name")
    phone_number = Column(String(20), nullable=False, comment="Customer phone number")
    address = Column(Text, nullable=False, comment="Full delivery address")
    
    # Order details stored as JSON to handle complex pizza configurations
    order_details = Column(JSON, nullable=False, comment="JSON containing pizzas, toppings, quantities")
    
    # Financial information
    total_amount = Column(DECIMAL(10, 2), nullable=False, comment="Total order amount in USD")
    
    # Delivery and timing
    estimated_delivery = Column(Integer, nullable=False, comment="Estimated delivery time in minutes")
    
    # Payment tracking
    payment_method = Column(String(50), nullable=False, comment="Payment method: card, cash, etc.")
    payment_status = Column(String(20), nullable=False, comment="Payment status: pending, completed, failed")
    
    # Order lifecycle management
    order_status = Column(String(20), nullable=False, comment="Order status: pending, preparing, ready, delivered")
    
    # Interface tracking - distinguishes phone vs web orders
    interface_type = Column(String(10), nullable=False, comment="Order source: phone or web")
    
    # Timestamp management with automatic updates
    created_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                       comment="Order creation timestamp")
    updated_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                       onupdate=func.current_timestamp(), comment="Last update timestamp")
    
    def __repr__(self):
        """String representation for debugging and logging."""
        return f"<Order(id={self.id}, customer='{self.customer_name}', status='{self.order_status}', total=${self.total_amount})>"
    
    def to_dict(self):
        """
        Convert order to dictionary for API responses and logging.
        
        Returns:
            dict: Order data with all fields except sensitive payment info
        """
        return {
            'id': self.id,
            'customer_name': self.customer_name,
            'phone_number': self.phone_number,
            'address': self.address,
            'order_details': self.order_details,
            'total_amount': float(self.total_amount),
            'estimated_delivery': self.estimated_delivery,
            'payment_method': self.payment_method,
            'payment_status': self.payment_status,
            'order_status': self.order_status,
            'interface_type': self.interface_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ActiveSession(Base):
    """
    ActiveSession model for tracking live customer interactions.
    
    Manages concurrent session limit (20 max) and stores conversation state.
    Used for both phone and web interface session management.
    """
    __tablename__ = 'active_sessions'
    
    # Primary key - unique session identifier
    session_id = Column(String(255), primary_key=True, comment="Unique session identifier")
    
    # Customer identification for session continuity
    customer_phone = Column(String(20), nullable=True, comment="Customer phone number if available")
    
    # Interface tracking - phone vs web sessions
    interface_type = Column(String(10), nullable=False, comment="Session interface: phone or web")
    
    # LangGraph agent state management
    agent_state = Column(String(50), nullable=False, comment="Current agent conversation state")
    
    # Temporary order data during conversation flow
    order_data = Column(JSON, nullable=True, comment="JSON containing partial order data during conversation")
    
    # Session lifecycle tracking
    created_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                       comment="Session creation timestamp")
    
    def __repr__(self):
        """String representation for debugging and logging."""
        return f"<ActiveSession(id='{self.session_id}', interface='{self.interface_type}', state='{self.agent_state}')>"
    
    def to_dict(self):
        """
        Convert session to dictionary for API responses and monitoring.
        
        Returns:
            dict: Session data for dashboard and monitoring
        """
        return {
            'session_id': self.session_id,
            'customer_phone': self.customer_phone,
            'interface_type': self.interface_type,
            'agent_state': self.agent_state,
            'order_data': self.order_data,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def is_expired(self, timeout_minutes=30):
        """
        Check if session has exceeded timeout limit.
        
        Args:
            timeout_minutes (int): Session timeout in minutes (default: 30)
            
        Returns:
            bool: True if session is expired
        """
        if not self.created_at:
            return True
        
        from datetime import datetime, timedelta
        timeout = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        return self.created_at < timeout


# Database metadata for table creation and migration
def create_tables(engine):
    """
    Create all database tables based on models.
    
    Args:
        engine: SQLAlchemy engine instance
    """
    logger.info("Creating database tables...")
    Base.metadata.create_all(engine)
    logger.info("Database tables created successfully")


def drop_tables(engine):
    """
    Drop all database tables (for testing and cleanup).
    
    Args:
        engine: SQLAlchemy engine instance
    """
    logger.warning("Dropping all database tables...")
    Base.metadata.drop_all(engine)
    logger.warning("All database tables dropped")