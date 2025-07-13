"""
SQLAlchemy database models for the pizza ordering system.
Contains Order and ActiveSession models as specified in the PRD.
"""

from sqlalchemy import Column, Integer, String, Text, DECIMAL, TIMESTAMP, JSON, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
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
    
    # Relationships
    payment_transactions = relationship("PaymentTransaction", back_populates="order")
    delivery_estimates = relationship("DeliveryEstimateRecord", back_populates="order")
    
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


# Enums for payment and order status
class PaymentStatus(Enum):
    """Payment status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REQUIRES_ACTION = "requires_action"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "pending"
    PAYMENT_PROCESSING = "payment_processing"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_FAILED = "payment_failed"
    PREPARING = "preparing"
    READY = "ready"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELED = "canceled"
    REFUNDED = "refunded"


class PaymentTransaction(Base):
    """
    Payment transaction model for tracking Stripe payments.
    
    Stores payment intents, transaction details, and status updates
    with full audit trail for financial reconciliation.
    """
    __tablename__ = 'payment_transactions'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Stripe identifiers
    payment_intent_id = Column(String(255), unique=True, nullable=False, 
                              comment="Stripe PaymentIntent ID")
    stripe_customer_id = Column(String(255), nullable=True,
                               comment="Stripe Customer ID if available")
    
    # Order relationship
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=True,
                     comment="Related order ID")
    order = relationship("Order", back_populates="payment_transactions")
    
    # Payment details
    amount_cents = Column(Integer, nullable=False, comment="Payment amount in cents")
    currency = Column(String(3), nullable=False, default="usd", comment="Payment currency")
    payment_method_type = Column(String(50), nullable=True, comment="Payment method type (card, etc.)")
    
    # Status tracking
    status = Column(String(50), nullable=False, default=PaymentStatus.PENDING.value,
                   comment="Current payment status")
    
    # Stripe metadata and details
    stripe_metadata = Column(JSON, nullable=True, comment="Stripe metadata and additional data")
    
    # Failure tracking
    failure_code = Column(String(100), nullable=True, comment="Failure code if payment failed")
    failure_message = Column(Text, nullable=True, comment="Failure message if payment failed")
    
    # Timeline tracking
    created_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                       comment="Transaction creation timestamp")
    updated_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                       onupdate=func.current_timestamp(), comment="Last update timestamp")
    confirmed_at = Column(TIMESTAMP, nullable=True, comment="Payment confirmation timestamp")
    failed_at = Column(TIMESTAMP, nullable=True, comment="Payment failure timestamp")
    
    def __repr__(self):
        """String representation for debugging."""
        return f"<PaymentTransaction(id={self.id}, payment_intent='{self.payment_intent_id}', status='{self.status}', amount=${self.amount_cents/100:.2f})>"
    
    def to_dict(self):
        """Convert transaction to dictionary."""
        return {
            'id': self.id,
            'payment_intent_id': self.payment_intent_id,
            'stripe_customer_id': self.stripe_customer_id,
            'order_id': self.order_id,
            'amount': self.amount_cents / 100,  # Convert to dollars
            'currency': self.currency,
            'payment_method_type': self.payment_method_type,
            'status': self.status,
            'failure_code': self.failure_code,
            'failure_message': self.failure_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'confirmed_at': self.confirmed_at.isoformat() if self.confirmed_at else None,
            'failed_at': self.failed_at.isoformat() if self.failed_at else None
        }


class PaymentMethodRecord(Base):
    """
    Payment method record for storing non-sensitive payment method information.
    
    Stores safe card details and customer associations for payment history
    and customer management without storing sensitive card data.
    """
    __tablename__ = 'payment_methods'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Stripe identifiers
    payment_method_id = Column(String(255), unique=True, nullable=False,
                              comment="Stripe PaymentMethod ID")
    stripe_customer_id = Column(String(255), nullable=True,
                               comment="Associated Stripe Customer ID")
    
    # Payment method details (non-sensitive)
    method_type = Column(String(50), nullable=False, comment="Payment method type")
    
    # Card details (safe information only)
    card_brand = Column(String(20), nullable=True, comment="Card brand (visa, mastercard, etc.)")
    card_last4 = Column(String(4), nullable=True, comment="Last 4 digits of card")
    card_exp_month = Column(Integer, nullable=True, comment="Card expiration month")
    card_exp_year = Column(Integer, nullable=True, comment="Card expiration year")
    card_funding = Column(String(20), nullable=True, comment="Card funding type (credit, debit, etc.)")
    card_country = Column(String(2), nullable=True, comment="Card country code")
    
    # Customer information
    billing_name = Column(String(255), nullable=True, comment="Billing name")
    billing_email = Column(String(255), nullable=True, comment="Billing email")
    
    # Status tracking
    is_active = Column(Boolean, default=True, nullable=False, comment="Whether payment method is active")
    
    # Timestamp management
    created_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                       comment="Payment method creation timestamp")
    updated_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                       onupdate=func.current_timestamp(), comment="Last update timestamp")
    
    def __repr__(self):
        """String representation for debugging."""
        return f"<PaymentMethodRecord(id={self.id}, method_id='{self.payment_method_id}', type='{self.method_type}', last4='{self.card_last4}')>"
    
    def to_dict(self):
        """Convert payment method to dictionary."""
        return {
            'id': self.id,
            'payment_method_id': self.payment_method_id,
            'stripe_customer_id': self.stripe_customer_id,
            'method_type': self.method_type,
            'card_brand': self.card_brand,
            'card_last4': self.card_last4,
            'card_exp_month': self.card_exp_month,
            'card_exp_year': self.card_exp_year,
            'card_funding': self.card_funding,
            'billing_name': self.billing_name,
            'billing_email': self.billing_email,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class WebhookEvent(Base):
    """
    Webhook event tracking for Stripe webhook processing.
    
    Ensures event deduplication and provides audit trail for all
    webhook events received from Stripe.
    """
    __tablename__ = 'webhook_events'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Stripe event details
    stripe_event_id = Column(String(255), unique=True, nullable=False,
                            comment="Stripe event ID")
    event_type = Column(String(100), nullable=False, comment="Stripe event type")
    
    # Processing status
    processing_status = Column(String(20), nullable=False, default="received",
                              comment="Event processing status: received, processing, completed, failed")
    
    # Event data and metadata
    event_data = Column(JSON, nullable=True, comment="Full Stripe event data")
    processing_attempts = Column(Integer, nullable=False, default=0,
                                comment="Number of processing attempts")
    
    # Error tracking
    last_error = Column(Text, nullable=True, comment="Last processing error if any")
    
    # Timestamp management
    stripe_created_at = Column(TIMESTAMP, nullable=True, comment="Stripe event creation timestamp")
    received_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                        comment="Webhook received timestamp")
    processed_at = Column(TIMESTAMP, nullable=True, comment="Event processing completion timestamp")
    
    def __repr__(self):
        """String representation for debugging."""
        return f"<WebhookEvent(id={self.id}, stripe_event='{self.stripe_event_id}', type='{self.event_type}', status='{self.processing_status}')>"
    
    def to_dict(self):
        """Convert webhook event to dictionary."""
        return {
            'id': self.id,
            'stripe_event_id': self.stripe_event_id,
            'event_type': self.event_type,
            'processing_status': self.processing_status,
            'processing_attempts': self.processing_attempts,
            'last_error': self.last_error,
            'stripe_created_at': self.stripe_created_at.isoformat() if self.stripe_created_at else None,
            'received_at': self.received_at.isoformat() if self.received_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None
        }


class RefundRecord(Base):
    """
    Refund record for tracking payment refunds.
    
    Stores refund information linked to original payment transactions
    for financial reconciliation and customer service.
    """
    __tablename__ = 'refunds'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Stripe identifiers
    stripe_refund_id = Column(String(255), unique=True, nullable=False,
                             comment="Stripe Refund ID")
    
    # Payment relationship
    payment_transaction_id = Column(Integer, ForeignKey('payment_transactions.id'), nullable=False,
                                   comment="Related payment transaction ID")
    payment_transaction = relationship("PaymentTransaction")
    
    # Refund details
    amount_cents = Column(Integer, nullable=False, comment="Refund amount in cents")
    currency = Column(String(3), nullable=False, default="usd", comment="Refund currency")
    reason = Column(String(100), nullable=True, comment="Refund reason")
    
    # Status tracking
    status = Column(String(20), nullable=False, comment="Refund status")
    
    # Additional information
    receipt_number = Column(String(100), nullable=True, comment="Refund receipt number")
    stripe_metadata = Column(JSON, nullable=True, comment="Stripe refund metadata")
    
    # Timestamp management
    created_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                       comment="Refund creation timestamp")
    updated_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                       onupdate=func.current_timestamp(), comment="Last update timestamp")
    
    def __repr__(self):
        """String representation for debugging."""
        return f"<RefundRecord(id={self.id}, stripe_refund='{self.stripe_refund_id}', amount=${self.amount_cents/100:.2f}, status='{self.status}')>"
    
    def to_dict(self):
        """Convert refund to dictionary."""
        return {
            'id': self.id,
            'stripe_refund_id': self.stripe_refund_id,
            'payment_transaction_id': self.payment_transaction_id,
            'amount': self.amount_cents / 100,  # Convert to dollars
            'currency': self.currency,
            'reason': self.reason,
            'status': self.status,
            'receipt_number': self.receipt_number,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class DeliveryEstimateRecord(Base):
    """
    Delivery estimate record for tracking delivery time predictions.
    
    Stores delivery estimates with detailed breakdown for analysis
    and customer communication about delivery times.
    """
    __tablename__ = 'delivery_estimates'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Order relationship
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False,
                     comment="Related order ID")
    order = relationship("Order", back_populates="delivery_estimates")
    
    # Estimation details
    estimated_minutes = Column(Integer, nullable=False, comment="Total estimated delivery time in minutes")
    distance_miles = Column(DECIMAL(5, 2), nullable=False, comment="Distance to delivery address in miles")
    base_time_minutes = Column(Integer, nullable=False, comment="Base preparation time in minutes")
    distance_time_minutes = Column(Integer, nullable=False, comment="Distance-based delivery time in minutes")
    load_time_minutes = Column(Integer, nullable=False, comment="Load-based additional time in minutes")
    random_variation_minutes = Column(Integer, nullable=False, comment="Random variation applied in minutes")
    
    # Confidence and zone information
    confidence_score = Column(DECIMAL(3, 2), nullable=False, comment="Estimation confidence score (0.0-1.0)")
    delivery_zone = Column(String(20), nullable=False, comment="Delivery zone (inner, middle, outer)")
    
    # Additional factors for analysis
    factors_data = Column(JSON, nullable=True, comment="Additional estimation factors and metadata")
    
    # Status tracking
    is_active = Column(Boolean, default=True, nullable=False, comment="Whether this is the current active estimate")
    actual_delivery_time = Column(Integer, nullable=True, comment="Actual delivery time for accuracy tracking")
    
    # Timestamp management
    created_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                       comment="Estimate creation timestamp")
    updated_at = Column(TIMESTAMP, nullable=False, default=func.current_timestamp(),
                       onupdate=func.current_timestamp(), comment="Last update timestamp")
    
    def __repr__(self):
        """String representation for debugging."""
        return f"<DeliveryEstimateRecord(id={self.id}, order_id={self.order_id}, estimated_minutes={self.estimated_minutes}, zone='{self.delivery_zone}')>"
    
    def to_dict(self):
        """Convert delivery estimate to dictionary."""
        return {
            'id': self.id,
            'order_id': self.order_id,
            'estimated_minutes': self.estimated_minutes,
            'distance_miles': float(self.distance_miles),
            'base_time_minutes': self.base_time_minutes,
            'distance_time_minutes': self.distance_time_minutes,
            'load_time_minutes': self.load_time_minutes,
            'random_variation_minutes': self.random_variation_minutes,
            'confidence_score': float(self.confidence_score),
            'delivery_zone': self.delivery_zone,
            'factors_data': self.factors_data,
            'is_active': self.is_active,
            'actual_delivery_time': self.actual_delivery_time,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


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