"""
Stripe webhook handling for payment events.
Processes payment status updates, failed payments, and dispute notifications.
"""

import logging
import json
import hashlib
import hmac
import time
from typing import Dict, Any, Optional
from datetime import datetime

import stripe
from fastapi import Request, HTTPException, BackgroundTasks
from stripe.error import StripeError

from ..config.settings import settings
from ..database.redis_client import get_redis_async
from ..database.models import PaymentTransaction, Order, OrderStatus
from ..database import get_db_session
from ..payment.stripe_client import stripe_client
from ..config.logging_config import get_logger

# Configure logging
logger = get_logger(__name__)


class StripeWebhookHandler:
    """
    Handles Stripe webhook events for payment processing.
    
    Provides secure webhook verification, event processing, and database updates
    for all payment-related events including successes, failures, and disputes.
    """
    
    def __init__(self):
        """Initialize webhook handler with security and processing configurations."""
        self.webhook_secret = settings.stripe_webhook_secret
        self.webhook_tolerance = 300  # 5 minutes tolerance for timestamp verification
        
        # Event deduplication configuration
        self.event_cache_ttl = 86400  # 24 hours
        self.max_retry_attempts = 3
        self.retry_delay_seconds = 5
        
        # Supported webhook events
        self.supported_events = {
            "payment_intent.succeeded",
            "payment_intent.payment_failed", 
            "payment_intent.canceled",
            "payment_intent.requires_action",
            "charge.dispute.created",
            "charge.failed",
            "invoice.payment_succeeded",
            "invoice.payment_failed",
            "customer.created",
            "payment_method.attached"
        }
        
        logger.info("StripeWebhookHandler initialized successfully")
    
    async def handle_webhook(
        self, 
        request: Request, 
        background_tasks: BackgroundTasks
    ) -> Dict[str, Any]:
        """
        Handle incoming Stripe webhook with verification and processing.
        
        Args:
            request (Request): FastAPI request object
            background_tasks (BackgroundTasks): Background task processor
            
        Returns:
            dict: Webhook processing result
        """
        try:
            # Get request body and signature
            payload = await request.body()
            signature = request.headers.get("stripe-signature")
            
            if not signature:
                raise HTTPException(status_code=400, detail="Missing Stripe signature")
            
            # Verify webhook signature
            event = self._verify_webhook_signature(payload, signature)
            
            # Check for event deduplication
            if await self._is_event_processed(event["id"]):
                logger.info(f"Event {event['id']} already processed, skipping")
                return {"status": "duplicate", "event_id": event["id"]}
            
            # Mark event as being processed
            await self._mark_event_processing(event["id"])
            
            # Process event in background
            background_tasks.add_task(
                self._process_event_async,
                event
            )
            
            # Mark event as processed
            await self._mark_event_processed(event["id"])
            
            logger.info(f"Webhook event {event['id']} queued for processing: {event['type']}")
            
            return {
                "status": "received",
                "event_id": event["id"],
                "event_type": event["type"]
            }
            
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")
            
        except Exception as e:
            logger.error(f"Webhook processing error: {e}")
            raise HTTPException(status_code=500, detail="Webhook processing failed")
    
    def _verify_webhook_signature(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Verify Stripe webhook signature for security.
        
        Args:
            payload (bytes): Raw webhook payload
            signature (str): Stripe signature header
            
        Returns:
            dict: Verified webhook event
        """
        try:
            # Verify signature and construct event
            event = stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )
            
            # Additional timestamp verification
            event_timestamp = event.get("created", 0)
            current_timestamp = int(time.time())
            
            if abs(current_timestamp - event_timestamp) > self.webhook_tolerance:
                raise stripe.error.SignatureVerificationError(
                    "Webhook timestamp too old", signature
                )
            
            return event
            
        except stripe.error.SignatureVerificationError:
            raise
        except Exception as e:
            logger.error(f"Webhook signature verification error: {e}")
            raise stripe.error.SignatureVerificationError(
                "Signature verification failed", signature
            )
    
    async def _process_event_async(self, event: Dict[str, Any]):
        """
        Process webhook event asynchronously.
        
        Args:
            event (dict): Stripe webhook event
        """
        try:
            event_type = event["type"]
            event_data = event["data"]["object"]
            
            logger.info(f"Processing webhook event: {event_type} (ID: {event['id']})")
            
            # Route to appropriate handler
            if event_type == "payment_intent.succeeded":
                await self._handle_payment_succeeded(event_data, event)
            elif event_type == "payment_intent.payment_failed":
                await self._handle_payment_failed(event_data, event)
            elif event_type == "payment_intent.canceled":
                await self._handle_payment_canceled(event_data, event)
            elif event_type == "payment_intent.requires_action":
                await self._handle_payment_requires_action(event_data, event)
            elif event_type == "charge.dispute.created":
                await self._handle_dispute_created(event_data, event)
            elif event_type == "charge.failed":
                await self._handle_charge_failed(event_data, event)
            elif event_type == "customer.created":
                await self._handle_customer_created(event_data, event)
            elif event_type == "payment_method.attached":
                await self._handle_payment_method_attached(event_data, event)
            else:
                logger.warning(f"Unhandled webhook event type: {event_type}")
            
            logger.info(f"Successfully processed webhook event: {event['id']}")
            
        except Exception as e:
            logger.error(f"Error processing webhook event {event.get('id')}: {e}")
            # Schedule retry if needed
            await self._schedule_event_retry(event, str(e))
    
    async def _handle_payment_succeeded(self, payment_intent: Dict[str, Any], event: Dict[str, Any]):
        """Handle successful payment events."""
        try:
            payment_intent_id = payment_intent["id"]
            amount = payment_intent["amount"] / 100  # Convert from cents
            
            logger.info(f"Payment succeeded: {payment_intent_id} for ${amount:.2f}")
            
            # Update payment status in database
            await self._update_payment_status(
                payment_intent_id, 
                "succeeded", 
                {
                    "amount": amount,
                    "currency": payment_intent["currency"],
                    "charges": payment_intent.get("charges", {}),
                    "receipt_email": payment_intent.get("receipt_email"),
                    "succeeded_at": datetime.utcnow().isoformat()
                }
            )
            
            # Update order status if linked
            order_id = payment_intent.get("metadata", {}).get("order_id")
            if order_id:
                await self._update_order_status(order_id, OrderStatus.PAYMENT_CONFIRMED)
                
                # Trigger order fulfillment process
                await self._trigger_order_fulfillment(order_id, payment_intent_id)
            
            # Send payment confirmation notification
            await self._send_payment_confirmation(payment_intent)
            
        except Exception as e:
            logger.error(f"Error handling payment succeeded event: {e}")
            raise
    
    async def _handle_payment_failed(self, payment_intent: Dict[str, Any], event: Dict[str, Any]):
        """Handle failed payment events."""
        try:
            payment_intent_id = payment_intent["id"]
            
            # Extract failure information
            last_payment_error = payment_intent.get("last_payment_error", {})
            failure_code = last_payment_error.get("code", "unknown")
            failure_message = last_payment_error.get("message", "Payment failed")
            
            logger.warning(f"Payment failed: {payment_intent_id} - {failure_code}: {failure_message}")
            
            # Update payment status in database
            await self._update_payment_status(
                payment_intent_id,
                "failed",
                {
                    "failure_code": failure_code,
                    "failure_message": failure_message,
                    "last_payment_error": last_payment_error,
                    "failed_at": datetime.utcnow().isoformat()
                }
            )
            
            # Update order status if linked
            order_id = payment_intent.get("metadata", {}).get("order_id")
            if order_id:
                await self._update_order_status(order_id, OrderStatus.PAYMENT_FAILED)
                
                # Schedule payment retry if appropriate
                await self._schedule_payment_retry(payment_intent_id, order_id, failure_code)
            
            # Send payment failure notification
            await self._send_payment_failure_notification(payment_intent)
            
        except Exception as e:
            logger.error(f"Error handling payment failed event: {e}")
            raise
    
    async def _handle_payment_canceled(self, payment_intent: Dict[str, Any], event: Dict[str, Any]):
        """Handle canceled payment events."""
        try:
            payment_intent_id = payment_intent["id"]
            cancellation_reason = payment_intent.get("cancellation_reason", "requested_by_customer")
            
            logger.info(f"Payment canceled: {payment_intent_id} - {cancellation_reason}")
            
            # Update payment status in database
            await self._update_payment_status(
                payment_intent_id,
                "canceled",
                {
                    "cancellation_reason": cancellation_reason,
                    "canceled_at": datetime.utcnow().isoformat()
                }
            )
            
            # Update order status if linked
            order_id = payment_intent.get("metadata", {}).get("order_id")
            if order_id:
                await self._update_order_status(order_id, OrderStatus.CANCELED)
            
            # Release inventory if reserved
            await self._release_inventory_reservation(payment_intent_id)
            
        except Exception as e:
            logger.error(f"Error handling payment canceled event: {e}")
            raise
    
    async def _handle_payment_requires_action(self, payment_intent: Dict[str, Any], event: Dict[str, Any]):
        """Handle payments that require additional customer action."""
        try:
            payment_intent_id = payment_intent["id"]
            next_action = payment_intent.get("next_action", {})
            
            logger.info(f"Payment requires action: {payment_intent_id} - {next_action.get('type')}")
            
            # Update payment status in database
            await self._update_payment_status(
                payment_intent_id,
                "requires_action",
                {
                    "next_action": next_action,
                    "requires_action_at": datetime.utcnow().isoformat()
                }
            )
            
            # Send action required notification
            await self._send_action_required_notification(payment_intent)
            
        except Exception as e:
            logger.error(f"Error handling payment requires action event: {e}")
            raise
    
    async def _handle_dispute_created(self, dispute: Dict[str, Any], event: Dict[str, Any]):
        """Handle dispute (chargeback) events."""
        try:
            dispute_id = dispute["id"]
            charge_id = dispute["charge"]
            amount = dispute["amount"] / 100
            reason = dispute["reason"]
            
            logger.warning(f"Dispute created: {dispute_id} for charge {charge_id} - ${amount:.2f} ({reason})")
            
            # Store dispute information
            await self._store_dispute_info(dispute, event)
            
            # Update related order status
            await self._handle_dispute_order_update(charge_id, dispute)
            
            # Send dispute notification to finance team
            await self._send_dispute_notification(dispute)
            
        except Exception as e:
            logger.error(f"Error handling dispute created event: {e}")
            raise
    
    async def _handle_charge_failed(self, charge: Dict[str, Any], event: Dict[str, Any]):
        """Handle charge failure events."""
        try:
            charge_id = charge["id"]
            failure_code = charge.get("failure_code", "unknown")
            failure_message = charge.get("failure_message", "Charge failed")
            
            logger.warning(f"Charge failed: {charge_id} - {failure_code}: {failure_message}")
            
            # Store charge failure information
            await self._store_charge_failure(charge, event)
            
        except Exception as e:
            logger.error(f"Error handling charge failed event: {e}")
            raise
    
    async def _handle_customer_created(self, customer: Dict[str, Any], event: Dict[str, Any]):
        """Handle customer creation events."""
        try:
            customer_id = customer["id"]
            
            logger.info(f"Customer created: {customer_id}")
            
            # Store customer information
            await self._store_customer_info(customer, event)
            
        except Exception as e:
            logger.error(f"Error handling customer created event: {e}")
            raise
    
    async def _handle_payment_method_attached(self, payment_method: Dict[str, Any], event: Dict[str, Any]):
        """Handle payment method attachment events."""
        try:
            payment_method_id = payment_method["id"]
            customer_id = payment_method["customer"]
            
            logger.info(f"Payment method attached: {payment_method_id} to customer {customer_id}")
            
            # Store payment method information
            await self._store_payment_method_info(payment_method, event)
            
        except Exception as e:
            logger.error(f"Error handling payment method attached event: {e}")
            raise
    
    async def _update_payment_status(
        self, 
        payment_intent_id: str, 
        status: str, 
        additional_data: Dict[str, Any]
    ):
        """Update payment status in database."""
        try:
            # Database update logic would go here
            # This is a placeholder for the actual implementation
            logger.info(f"Updating payment {payment_intent_id} status to {status}")
            
            # Example structure for database update:
            # async with get_db_session() as session:
            #     payment = session.query(PaymentTransaction).filter_by(
            #         payment_intent_id=payment_intent_id
            #     ).first()
            #     
            #     if payment:
            #         payment.status = status
            #         payment.updated_at = datetime.utcnow()
            #         payment.additional_data = additional_data
            #         session.commit()
            
        except Exception as e:
            logger.error(f"Error updating payment status: {e}")
            raise
    
    async def _update_order_status(self, order_id: str, status: OrderStatus):
        """Update order status in database."""
        try:
            logger.info(f"Updating order {order_id} status to {status.value}")
            
            # Database update logic would go here
            # This is a placeholder for the actual implementation
            
        except Exception as e:
            logger.error(f"Error updating order status: {e}")
            raise
    
    async def _trigger_order_fulfillment(self, order_id: str, payment_intent_id: str):
        """Trigger order fulfillment process after successful payment."""
        try:
            logger.info(f"Triggering fulfillment for order {order_id}")
            
            # This would typically:
            # 1. Send order to kitchen/preparation system
            # 2. Update delivery estimation
            # 3. Send confirmation to customer
            # 4. Update inventory
            
        except Exception as e:
            logger.error(f"Error triggering order fulfillment: {e}")
    
    async def _schedule_payment_retry(self, payment_intent_id: str, order_id: str, failure_code: str):
        """Schedule payment retry for recoverable failures."""
        try:
            # Determine if failure is retryable
            retryable_codes = {
                "insufficient_funds", "card_declined", "processing_error"
            }
            
            if failure_code in retryable_codes:
                logger.info(f"Scheduling retry for payment {payment_intent_id}")
                
                # Implementation would schedule retry logic
                # Could use background tasks or queue system
            
        except Exception as e:
            logger.error(f"Error scheduling payment retry: {e}")
    
    async def _send_payment_confirmation(self, payment_intent: Dict[str, Any]):
        """Send payment confirmation notification to customer."""
        try:
            # Extract customer contact information
            customer_phone = payment_intent.get("metadata", {}).get("customer_phone")
            customer_email = payment_intent.get("receipt_email")
            
            if customer_phone or customer_email:
                logger.info(f"Sending payment confirmation for {payment_intent['id']}")
                
                # Implementation would send notification
                # Could integrate with SMS/email service
            
        except Exception as e:
            logger.error(f"Error sending payment confirmation: {e}")
    
    async def _send_payment_failure_notification(self, payment_intent: Dict[str, Any]):
        """Send payment failure notification to customer."""
        try:
            customer_phone = payment_intent.get("metadata", {}).get("customer_phone")
            
            if customer_phone:
                logger.info(f"Sending payment failure notification for {payment_intent['id']}")
                
                # Implementation would send notification
            
        except Exception as e:
            logger.error(f"Error sending payment failure notification: {e}")
    
    async def _send_action_required_notification(self, payment_intent: Dict[str, Any]):
        """Send action required notification to customer."""
        try:
            customer_phone = payment_intent.get("metadata", {}).get("customer_phone")
            
            if customer_phone:
                logger.info(f"Sending action required notification for {payment_intent['id']}")
                
                # Implementation would send notification
            
        except Exception as e:
            logger.error(f"Error sending action required notification: {e}")
    
    async def _send_dispute_notification(self, dispute: Dict[str, Any]):
        """Send dispute notification to finance team."""
        try:
            logger.info(f"Sending dispute notification for {dispute['id']}")
            
            # Implementation would send internal notification
            
        except Exception as e:
            logger.error(f"Error sending dispute notification: {e}")
    
    async def _store_dispute_info(self, dispute: Dict[str, Any], event: Dict[str, Any]):
        """Store dispute information in database."""
        try:
            logger.info(f"Storing dispute info for {dispute['id']}")
            
            # Database storage logic would go here
            
        except Exception as e:
            logger.error(f"Error storing dispute info: {e}")
    
    async def _store_charge_failure(self, charge: Dict[str, Any], event: Dict[str, Any]):
        """Store charge failure information in database."""
        try:
            logger.info(f"Storing charge failure for {charge['id']}")
            
            # Database storage logic would go here
            
        except Exception as e:
            logger.error(f"Error storing charge failure: {e}")
    
    async def _store_customer_info(self, customer: Dict[str, Any], event: Dict[str, Any]):
        """Store customer information in database."""
        try:
            logger.info(f"Storing customer info for {customer['id']}")
            
            # Database storage logic would go here
            
        except Exception as e:
            logger.error(f"Error storing customer info: {e}")
    
    async def _store_payment_method_info(self, payment_method: Dict[str, Any], event: Dict[str, Any]):
        """Store payment method information in database."""
        try:
            logger.info(f"Storing payment method info for {payment_method['id']}")
            
            # Database storage logic would go here
            
        except Exception as e:
            logger.error(f"Error storing payment method info: {e}")
    
    async def _handle_dispute_order_update(self, charge_id: str, dispute: Dict[str, Any]):
        """Update order status when dispute is created."""
        try:
            logger.info(f"Handling dispute order update for charge {charge_id}")
            
            # Find related order and update status
            
        except Exception as e:
            logger.error(f"Error handling dispute order update: {e}")
    
    async def _release_inventory_reservation(self, payment_intent_id: str):
        """Release inventory reservation for canceled payment."""
        try:
            logger.info(f"Releasing inventory for payment {payment_intent_id}")
            
            # Implementation would release reserved inventory
            
        except Exception as e:
            logger.error(f"Error releasing inventory reservation: {e}")
    
    async def _is_event_processed(self, event_id: str) -> bool:
        """Check if event has already been processed."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"webhook_event:{event_id}"
            
            with redis_client.get_connection() as conn:
                return conn.exists(cache_key)
            
        except Exception as e:
            logger.warning(f"Error checking event deduplication: {e}")
            return False
    
    async def _mark_event_processing(self, event_id: str):
        """Mark event as being processed."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"webhook_event:{event_id}"
            
            with redis_client.get_connection() as conn:
                conn.setex(cache_key, self.event_cache_ttl, "processing")
            
        except Exception as e:
            logger.warning(f"Error marking event as processing: {e}")
    
    async def _mark_event_processed(self, event_id: str):
        """Mark event as successfully processed."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"webhook_event:{event_id}"
            
            with redis_client.get_connection() as conn:
                conn.setex(cache_key, self.event_cache_ttl, "processed")
            
        except Exception as e:
            logger.warning(f"Error marking event as processed: {e}")
    
    async def _schedule_event_retry(self, event: Dict[str, Any], error: str):
        """Schedule retry for failed event processing."""
        try:
            event_id = event["id"]
            logger.warning(f"Scheduling retry for failed event {event_id}: {error}")
            
            # Implementation would use background task queue for retry
            
        except Exception as e:
            logger.error(f"Error scheduling event retry: {e}")


# Create global webhook handler instance
webhook_handler = StripeWebhookHandler()


# FastAPI endpoint functions
async def handle_stripe_webhook(request: Request, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Handle Stripe webhook endpoint."""
    return await webhook_handler.handle_webhook(request, background_tasks)


# Export main components
__all__ = ["StripeWebhookHandler", "webhook_handler", "handle_stripe_webhook"]