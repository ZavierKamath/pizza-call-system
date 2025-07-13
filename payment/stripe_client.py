"""
Comprehensive Stripe payment processing client.
Handles payment intents, tokenization, refunds, and secure transaction processing.
"""

import logging
import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import uuid

import stripe
from stripe.error import (
    StripeError, CardError, InvalidRequestError, AuthenticationError,
    APIConnectionError, APIError, RateLimitError
)

from ..config.settings import settings
from ..database.redis_client import get_redis_async
from ..database.models import PaymentTransaction, PaymentStatus
from ..database import get_db_session

# Configure logging
logger = logging.getLogger(__name__)


class StripePaymentClient:
    """
    Comprehensive Stripe payment processing client.
    
    Provides secure payment processing, tokenization, refunds, and webhook handling
    with comprehensive error recovery and retry mechanisms.
    """
    
    def __init__(self):
        """Initialize Stripe client with configuration and security settings."""
        # Initialize Stripe with API keys
        stripe.api_key = settings.stripe_secret_key
        self.publishable_key = settings.stripe_publishable_key
        
        # Payment configuration
        self.default_currency = "usd"
        self.payment_timeout_seconds = 30
        self.max_retry_attempts = 3
        self.retry_delay_seconds = 1
        
        # Business rules
        self.minimum_charge_amount = 1.00  # $1.00 minimum
        self.maximum_charge_amount = 500.00  # $500.00 maximum for pizza orders
        self.default_capture_method = "automatic"
        
        # Cache configuration for payment methods
        self.payment_method_cache_ttl = 3600  # 1 hour
        
        # Webhook configuration
        self.webhook_tolerance = 300  # 5 minutes tolerance for webhook timestamps
        
        # Error retry configuration
        self.retryable_errors = {
            "rate_limit_error",
            "api_connection_error", 
            "api_error"
        }
        
        logger.info("StripePaymentClient initialized successfully")
    
    async def create_payment_intent(
        self, 
        amount: float, 
        customer_info: Optional[Dict[str, Any]] = None,
        order_info: Optional[Dict[str, Any]] = None,
        payment_method_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a Stripe PaymentIntent for order processing.
        
        Args:
            amount (float): Payment amount in dollars
            customer_info (dict, optional): Customer information
            order_info (dict, optional): Order details for metadata
            payment_method_id (str, optional): Existing payment method ID
            
        Returns:
            dict: Payment intent creation result
        """
        try:
            # Validate payment amount
            amount_validation = self._validate_payment_amount(amount)
            if not amount_validation["is_valid"]:
                return {
                    "success": False,
                    "errors": amount_validation["errors"]
                }
            
            amount_cents = int(amount * 100)  # Convert to cents
            
            # Build metadata for tracking
            metadata = {
                "source": "pizza_agent",
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Add order information to metadata
            if order_info:
                metadata.update({
                    "order_id": order_info.get("order_id", ""),
                    "session_id": order_info.get("session_id", ""),
                    "customer_phone": order_info.get("customer_phone", ""),
                    "pizza_count": str(order_info.get("pizza_count", 0)),
                    "delivery_address": order_info.get("delivery_address", "")[:500]  # Limit length
                })
            
            # Add customer information
            if customer_info:
                metadata.update({
                    "customer_name": customer_info.get("name", "")[:100],
                    "customer_email": customer_info.get("email", "")
                })
            
            # Build PaymentIntent parameters
            intent_params = {
                "amount": amount_cents,
                "currency": self.default_currency,
                "automatic_payment_methods": {"enabled": True},
                "capture_method": self.default_capture_method,
                "description": f"Pizza order - ${amount:.2f}",
                "metadata": metadata,
                "receipt_email": customer_info.get("email") if customer_info else None
            }
            
            # Add payment method if provided
            if payment_method_id:
                intent_params["payment_method"] = payment_method_id
                intent_params["confirm"] = False  # Don't auto-confirm
            
            # Create PaymentIntent with retry logic
            payment_intent = await self._execute_with_retry(
                stripe.PaymentIntent.create,
                **intent_params
            )
            
            # Store payment intent in database
            await self._store_payment_intent(payment_intent, order_info)
            
            result = {
                "success": True,
                "payment_intent_id": payment_intent.id,
                "client_secret": payment_intent.client_secret,
                "amount": amount,
                "amount_cents": amount_cents,
                "status": payment_intent.status,
                "requires_action": payment_intent.status == "requires_action",
                "next_action": payment_intent.next_action
            }
            
            logger.info(f"PaymentIntent created successfully: {payment_intent.id} for ${amount:.2f}")
            return result
            
        except StripeError as e:
            error_details = self._handle_stripe_error(e)
            logger.error(f"Stripe error creating PaymentIntent: {error_details}")
            return {
                "success": False,
                "errors": [error_details["user_message"]],
                "error_code": error_details["error_code"]
            }
        except Exception as e:
            logger.error(f"Unexpected error creating PaymentIntent: {e}")
            return {
                "success": False,
                "errors": ["Payment processing is temporarily unavailable. Please try again."]
            }
    
    async def confirm_payment_intent(
        self, 
        payment_intent_id: str,
        payment_method_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Confirm a PaymentIntent to process the payment.
        
        Args:
            payment_intent_id (str): PaymentIntent ID to confirm
            payment_method_id (str, optional): Payment method to use
            
        Returns:
            dict: Payment confirmation result
        """
        try:
            # Build confirmation parameters
            confirm_params = {}
            if payment_method_id:
                confirm_params["payment_method"] = payment_method_id
            
            # Confirm PaymentIntent with retry logic
            payment_intent = await self._execute_with_retry(
                stripe.PaymentIntent.confirm,
                payment_intent_id,
                **confirm_params
            )
            
            # Update payment status in database
            await self._update_payment_status(payment_intent)
            
            # Process result based on status
            if payment_intent.status == "succeeded":
                result = {
                    "success": True,
                    "payment_intent_id": payment_intent.id,
                    "transaction_id": payment_intent.id,
                    "amount": payment_intent.amount / 100,  # Convert from cents
                    "status": payment_intent.status,
                    "charges": self._extract_charge_info(payment_intent),
                    "receipt_url": payment_intent.charges.data[0].receipt_url if payment_intent.charges.data else None
                }
                
                logger.info(f"Payment confirmed successfully: {payment_intent.id}")
                return result
                
            elif payment_intent.status == "requires_action":
                return {
                    "success": False,
                    "requires_action": True,
                    "next_action": payment_intent.next_action,
                    "client_secret": payment_intent.client_secret,
                    "status": payment_intent.status
                }
                
            else:
                return {
                    "success": False,
                    "errors": [f"Payment could not be processed. Status: {payment_intent.status}"],
                    "status": payment_intent.status
                }
                
        except CardError as e:
            error_details = self._handle_card_error(e)
            logger.warning(f"Card error confirming payment: {error_details}")
            
            # Update payment status for failed payment
            await self._record_payment_failure(payment_intent_id, error_details)
            
            return {
                "success": False,
                "errors": [error_details["user_message"]],
                "decline_code": error_details.get("decline_code"),
                "card_declined": True
            }
            
        except StripeError as e:
            error_details = self._handle_stripe_error(e)
            logger.error(f"Stripe error confirming payment: {error_details}")
            
            await self._record_payment_failure(payment_intent_id, error_details)
            
            return {
                "success": False,
                "errors": [error_details["user_message"]],
                "error_code": error_details["error_code"]
            }
        except Exception as e:
            logger.error(f"Unexpected error confirming payment: {e}")
            return {
                "success": False,
                "errors": ["Payment confirmation failed. Please try again."]
            }
    
    async def process_immediate_charge(
        self, 
        amount: float,
        payment_method_id: str,
        customer_info: Optional[Dict[str, Any]] = None,
        order_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process an immediate charge (create and confirm PaymentIntent in one step).
        
        Args:
            amount (float): Payment amount in dollars
            payment_method_id (str): Payment method to charge
            customer_info (dict, optional): Customer information
            order_info (dict, optional): Order details
            
        Returns:
            dict: Charge processing result
        """
        try:
            # Create PaymentIntent
            creation_result = await self.create_payment_intent(
                amount=amount,
                customer_info=customer_info,
                order_info=order_info,
                payment_method_id=payment_method_id
            )
            
            if not creation_result["success"]:
                return creation_result
            
            # Immediately confirm the PaymentIntent
            confirmation_result = await self.confirm_payment_intent(
                creation_result["payment_intent_id"]
            )
            
            return confirmation_result
            
        except Exception as e:
            logger.error(f"Error processing immediate charge: {e}")
            return {
                "success": False,
                "errors": ["Payment processing failed. Please try again."]
            }
    
    async def create_refund(
        self, 
        payment_intent_id: str,
        amount: Optional[float] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a refund for a successful payment.
        
        Args:
            payment_intent_id (str): PaymentIntent ID to refund
            amount (float, optional): Refund amount (full refund if not specified)
            reason (str, optional): Reason for refund
            metadata (dict, optional): Additional refund metadata
            
        Returns:
            dict: Refund creation result
        """
        try:
            # Get the PaymentIntent to find the charge
            payment_intent = await self._execute_with_retry(
                stripe.PaymentIntent.retrieve,
                payment_intent_id
            )
            
            if payment_intent.status != "succeeded":
                return {
                    "success": False,
                    "errors": ["Can only refund successful payments"]
                }
            
            # Get the charge ID from the PaymentIntent
            if not payment_intent.charges.data:
                return {
                    "success": False,
                    "errors": ["No charges found for this payment"]
                }
            
            charge_id = payment_intent.charges.data[0].id
            
            # Build refund parameters
            refund_params = {
                "charge": charge_id,
                "reason": reason or "requested_by_customer"
            }
            
            # Add amount if partial refund
            if amount is not None:
                amount_cents = int(amount * 100)
                refund_params["amount"] = amount_cents
            
            # Add metadata
            if metadata:
                refund_metadata = {
                    "refund_requested_at": datetime.utcnow().isoformat(),
                    "original_payment_intent": payment_intent_id
                }
                refund_metadata.update(metadata)
                refund_params["metadata"] = refund_metadata
            
            # Create refund with retry logic
            refund = await self._execute_with_retry(
                stripe.Refund.create,
                **refund_params
            )
            
            # Store refund information in database
            await self._store_refund_info(refund, payment_intent_id)
            
            result = {
                "success": True,
                "refund_id": refund.id,
                "amount": refund.amount / 100,  # Convert from cents
                "status": refund.status,
                "reason": refund.reason,
                "receipt_number": refund.receipt_number
            }
            
            logger.info(f"Refund created successfully: {refund.id} for ${refund.amount / 100:.2f}")
            return result
            
        except StripeError as e:
            error_details = self._handle_stripe_error(e)
            logger.error(f"Stripe error creating refund: {error_details}")
            return {
                "success": False,
                "errors": [error_details["user_message"]],
                "error_code": error_details["error_code"]
            }
        except Exception as e:
            logger.error(f"Unexpected error creating refund: {e}")
            return {
                "success": False,
                "errors": ["Refund processing failed. Please contact support."]
            }
    
    async def cancel_payment_intent(
        self, 
        payment_intent_id: str,
        cancellation_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel a PaymentIntent before it's confirmed.
        
        Args:
            payment_intent_id (str): PaymentIntent ID to cancel
            cancellation_reason (str, optional): Reason for cancellation
            
        Returns:
            dict: Cancellation result
        """
        try:
            # Cancel PaymentIntent with retry logic
            payment_intent = await self._execute_with_retry(
                stripe.PaymentIntent.cancel,
                payment_intent_id,
                cancellation_reason=cancellation_reason or "requested_by_customer"
            )
            
            # Update payment status in database
            await self._update_payment_status(payment_intent, cancellation_reason)
            
            result = {
                "success": True,
                "payment_intent_id": payment_intent.id,
                "status": payment_intent.status,
                "cancellation_reason": cancellation_reason
            }
            
            logger.info(f"PaymentIntent cancelled: {payment_intent.id}")
            return result
            
        except StripeError as e:
            error_details = self._handle_stripe_error(e)
            logger.error(f"Stripe error cancelling PaymentIntent: {error_details}")
            return {
                "success": False,
                "errors": [error_details["user_message"]],
                "error_code": error_details["error_code"]
            }
        except Exception as e:
            logger.error(f"Unexpected error cancelling PaymentIntent: {e}")
            return {
                "success": False,
                "errors": ["Payment cancellation failed. Please contact support."]
            }
    
    async def retrieve_payment_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        """
        Retrieve a PaymentIntent and its current status.
        
        Args:
            payment_intent_id (str): PaymentIntent ID to retrieve
            
        Returns:
            dict: PaymentIntent information
        """
        try:
            payment_intent = await self._execute_with_retry(
                stripe.PaymentIntent.retrieve,
                payment_intent_id
            )
            
            return {
                "success": True,
                "payment_intent_id": payment_intent.id,
                "status": payment_intent.status,
                "amount": payment_intent.amount / 100,
                "currency": payment_intent.currency,
                "client_secret": payment_intent.client_secret,
                "metadata": payment_intent.metadata,
                "charges": self._extract_charge_info(payment_intent)
            }
            
        except StripeError as e:
            error_details = self._handle_stripe_error(e)
            logger.error(f"Stripe error retrieving PaymentIntent: {error_details}")
            return {
                "success": False,
                "errors": [error_details["user_message"]]
            }
        except Exception as e:
            logger.error(f"Unexpected error retrieving PaymentIntent: {e}")
            return {
                "success": False,
                "errors": ["Could not retrieve payment information."]
            }
    
    async def create_ephemeral_key(self, customer_id: str, api_version: str) -> Dict[str, Any]:
        """
        Create an ephemeral key for mobile client integration.
        
        Args:
            customer_id (str): Stripe customer ID
            api_version (str): Stripe API version
            
        Returns:
            dict: Ephemeral key information
        """
        try:
            ephemeral_key = await self._execute_with_retry(
                stripe.EphemeralKey.create,
                customer=customer_id,
                stripe_version=api_version
            )
            
            return {
                "success": True,
                "ephemeral_key": ephemeral_key.secret,
                "customer_id": customer_id
            }
            
        except StripeError as e:
            error_details = self._handle_stripe_error(e)
            logger.error(f"Stripe error creating ephemeral key: {error_details}")
            return {
                "success": False,
                "errors": [error_details["user_message"]]
            }
    
    def _validate_payment_amount(self, amount: float) -> Dict[str, Any]:
        """Validate payment amount against business rules."""
        if not isinstance(amount, (int, float)) or amount <= 0:
            return {
                "is_valid": False,
                "errors": ["Invalid payment amount"]
            }
        
        if amount < self.minimum_charge_amount:
            return {
                "is_valid": False,
                "errors": [f"Payment amount must be at least ${self.minimum_charge_amount:.2f}"]
            }
        
        if amount > self.maximum_charge_amount:
            return {
                "is_valid": False,
                "errors": [f"Payment amount cannot exceed ${self.maximum_charge_amount:.2f}"]
            }
        
        return {"is_valid": True}
    
    async def _execute_with_retry(self, func, *args, **kwargs):
        """Execute Stripe API call with retry logic for transient errors."""
        last_error = None
        
        for attempt in range(self.max_retry_attempts):
            try:
                return func(*args, **kwargs)
                
            except RateLimitError as e:
                # Rate limiting - wait and retry
                wait_time = self.retry_delay_seconds * (2 ** attempt)
                logger.warning(f"Rate limited on attempt {attempt + 1}, waiting {wait_time}s")
                await asyncio.sleep(wait_time)
                last_error = e
                
            except APIConnectionError as e:
                # Network issues - retry
                wait_time = self.retry_delay_seconds * (2 ** attempt)
                logger.warning(f"Connection error on attempt {attempt + 1}, waiting {wait_time}s")
                await asyncio.sleep(wait_time)
                last_error = e
                
            except APIError as e:
                # Generic API error - retry
                wait_time = self.retry_delay_seconds * (2 ** attempt)
                logger.warning(f"API error on attempt {attempt + 1}, waiting {wait_time}s")
                await asyncio.sleep(wait_time)
                last_error = e
                
            except (CardError, InvalidRequestError, AuthenticationError) as e:
                # Don't retry these errors
                raise e
        
        # All retries exhausted
        raise last_error
    
    def _handle_stripe_error(self, error: StripeError) -> Dict[str, Any]:
        """Handle and format Stripe API errors."""
        error_details = {
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", "unknown"),
            "user_message": "Payment processing failed. Please try again."
        }
        
        if hasattr(error, "user_message") and error.user_message:
            error_details["user_message"] = error.user_message
        elif hasattr(error, "message") and error.message:
            error_details["user_message"] = error.message
        
        return error_details
    
    def _handle_card_error(self, error: CardError) -> Dict[str, Any]:
        """Handle and format card-specific errors."""
        decline_code = error.decline_code
        
        # Map decline codes to user-friendly messages
        decline_messages = {
            "insufficient_funds": "Your card has insufficient funds for this transaction.",
            "card_declined": "Your card was declined. Please try a different card.",
            "expired_card": "Your card has expired. Please use a different card.",
            "incorrect_cvc": "The security code you entered is incorrect.",
            "incorrect_number": "The card number you entered is incorrect.",
            "processing_error": "There was an error processing your card. Please try again.",
            "generic_decline": "Your card was declined. Please contact your bank or try a different card."
        }
        
        user_message = decline_messages.get(decline_code, decline_messages["generic_decline"])
        
        return {
            "error_type": "CardError",
            "error_code": error.code,
            "decline_code": decline_code,
            "user_message": user_message
        }
    
    def _extract_charge_info(self, payment_intent) -> List[Dict[str, Any]]:
        """Extract charge information from PaymentIntent."""
        charges = []
        
        for charge in payment_intent.charges.data:
            charge_info = {
                "charge_id": charge.id,
                "amount": charge.amount / 100,
                "currency": charge.currency,
                "status": charge.status,
                "receipt_url": charge.receipt_url,
                "payment_method_details": self._extract_payment_method_details(charge)
            }
            charges.append(charge_info)
        
        return charges
    
    def _extract_payment_method_details(self, charge) -> Dict[str, Any]:
        """Extract payment method details from charge."""
        pm_details = charge.payment_method_details
        
        if pm_details.type == "card":
            return {
                "type": "card",
                "brand": pm_details.card.brand,
                "last4": pm_details.card.last4,
                "exp_month": pm_details.card.exp_month,
                "exp_year": pm_details.card.exp_year,
                "funding": pm_details.card.funding
            }
        
        return {"type": pm_details.type}
    
    async def _store_payment_intent(
        self, 
        payment_intent, 
        order_info: Optional[Dict[str, Any]] = None
    ):
        """Store PaymentIntent information in database."""
        try:
            # Implementation will depend on your database schema
            # This is a placeholder for database storage
            logger.info(f"Storing PaymentIntent {payment_intent.id} in database")
            
        except Exception as e:
            logger.error(f"Error storing PaymentIntent: {e}")
    
    async def _update_payment_status(
        self, 
        payment_intent, 
        additional_info: Optional[str] = None
    ):
        """Update payment status in database."""
        try:
            # Implementation will depend on your database schema
            logger.info(f"Updating payment status for {payment_intent.id}: {payment_intent.status}")
            
        except Exception as e:
            logger.error(f"Error updating payment status: {e}")
    
    async def _record_payment_failure(
        self, 
        payment_intent_id: str, 
        error_details: Dict[str, Any]
    ):
        """Record payment failure in database."""
        try:
            # Implementation will depend on your database schema
            logger.info(f"Recording payment failure for {payment_intent_id}: {error_details}")
            
        except Exception as e:
            logger.error(f"Error recording payment failure: {e}")
    
    async def _store_refund_info(self, refund, payment_intent_id: str):
        """Store refund information in database."""
        try:
            # Implementation will depend on your database schema
            logger.info(f"Storing refund {refund.id} for PaymentIntent {payment_intent_id}")
            
        except Exception as e:
            logger.error(f"Error storing refund info: {e}")


# Create global client instance
stripe_client = StripePaymentClient()


# Utility functions for integration
async def create_payment_intent(
    amount: float,
    customer_info: Optional[Dict[str, Any]] = None,
    order_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Utility function for creating payment intents."""
    return await stripe_client.create_payment_intent(amount, customer_info, order_info)


async def confirm_payment(payment_intent_id: str) -> Dict[str, Any]:
    """Utility function for confirming payments."""
    return await stripe_client.confirm_payment_intent(payment_intent_id)


async def process_immediate_charge(
    amount: float,
    payment_method_id: str,
    customer_info: Optional[Dict[str, Any]] = None,
    order_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Utility function for immediate charge processing."""
    return await stripe_client.process_immediate_charge(
        amount, payment_method_id, customer_info, order_info
    )


async def create_refund(
    payment_intent_id: str,
    amount: Optional[float] = None,
    reason: Optional[str] = None
) -> Dict[str, Any]:
    """Utility function for creating refunds."""
    return await stripe_client.create_refund(payment_intent_id, amount, reason)


# Export main components
__all__ = [
    "StripePaymentClient", "stripe_client", "create_payment_intent", 
    "confirm_payment", "process_immediate_charge", "create_refund"
]