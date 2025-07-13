"""
Secure payment method and tokenization manager.
Handles payment method creation, validation, and secure token management.
"""

import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

import stripe
from stripe.error import StripeError, CardError, InvalidRequestError

from config.settings import settings
from database.redis_client import get_redis_async

# Configure logging
logger = logging.getLogger(__name__)


class PaymentMethodManager:
    """
    Manages payment methods and secure tokenization for Stripe integration.
    
    Provides PCI-compliant handling of payment methods, customer management,
    and secure token operations without storing sensitive card data.
    """
    
    def __init__(self):
        """Initialize payment method manager with security configurations."""
        # Initialize Stripe
        stripe.api_key = settings.stripe_secret_key
        
        # Cache configuration for payment methods
        self.payment_method_cache_ttl = 1800  # 30 minutes
        self.customer_cache_ttl = 3600  # 1 hour
        
        # Security configurations
        self.max_payment_methods_per_customer = 5
        self.token_expiry_minutes = 60  # Ephemeral tokens expire in 1 hour
        
        logger.info("PaymentMethodManager initialized successfully")
    
    async def create_customer(
        self, 
        customer_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a Stripe customer for payment method management.
        
        Args:
            customer_info (dict): Customer information
            
        Returns:
            dict: Customer creation result
        """
        try:
            # Build customer parameters
            customer_params = {
                "description": f"Pizza customer - {customer_info.get('name', 'Unknown')}",
                "metadata": {
                    "source": "pizza_agent",
                    "created_at": datetime.utcnow().isoformat(),
                    "phone": customer_info.get("phone", ""),
                    "session_id": customer_info.get("session_id", "")
                }
            }
            
            # Add optional fields
            if customer_info.get("email"):
                customer_params["email"] = customer_info["email"]
            
            if customer_info.get("name"):
                customer_params["name"] = customer_info["name"]
            
            if customer_info.get("phone"):
                customer_params["phone"] = customer_info["phone"]
            
            # Add address if provided
            if customer_info.get("address"):
                address = customer_info["address"]
                customer_params["address"] = {
                    "line1": address.get("street", ""),
                    "city": address.get("city", ""),
                    "state": address.get("state", ""),
                    "postal_code": address.get("zip", ""),
                    "country": "US"
                }
            
            # Create customer
            customer = stripe.Customer.create(**customer_params)
            
            # Cache customer information
            await self._cache_customer_info(customer)
            
            result = {
                "success": True,
                "customer_id": customer.id,
                "customer_info": {
                    "id": customer.id,
                    "email": customer.email,
                    "name": customer.name,
                    "phone": customer.phone,
                    "created": customer.created
                }
            }
            
            logger.info(f"Customer created successfully: {customer.id}")
            return result
            
        except StripeError as e:
            logger.error(f"Stripe error creating customer: {e}")
            return {
                "success": False,
                "errors": [f"Customer creation failed: {str(e)}"]
            }
        except Exception as e:
            logger.error(f"Unexpected error creating customer: {e}")
            return {
                "success": False,
                "errors": ["Customer creation failed. Please try again."]
            }
    
    async def create_payment_method(
        self, 
        payment_method_data: Dict[str, Any],
        customer_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a payment method securely without storing card data.
        
        Args:
            payment_method_data (dict): Payment method information
            customer_id (str, optional): Customer to attach payment method to
            
        Returns:
            dict: Payment method creation result
        """
        try:
            # Build payment method parameters
            pm_params = {
                "type": payment_method_data.get("type", "card")
            }
            
            # Handle card payment method
            if pm_params["type"] == "card":
                card_data = payment_method_data.get("card", {})
                pm_params["card"] = {
                    "number": card_data.get("number"),
                    "exp_month": int(card_data.get("exp_month")),
                    "exp_year": int(card_data.get("exp_year")),
                    "cvc": card_data.get("cvc")
                }
            
            # Add billing details if provided
            if payment_method_data.get("billing_details"):
                pm_params["billing_details"] = payment_method_data["billing_details"]
            
            # Create payment method
            payment_method = stripe.PaymentMethod.create(**pm_params)
            
            # Attach to customer if provided
            if customer_id:
                try:
                    payment_method.attach(customer=customer_id)
                    logger.info(f"Payment method {payment_method.id} attached to customer {customer_id}")
                except StripeError as attach_error:
                    logger.warning(f"Failed to attach payment method to customer: {attach_error}")
                    # Continue without attachment - payment method is still usable
            
            # Cache payment method information (non-sensitive data only)
            await self._cache_payment_method_info(payment_method)
            
            result = {
                "success": True,
                "payment_method_id": payment_method.id,
                "payment_method": {
                    "id": payment_method.id,
                    "type": payment_method.type,
                    "card": self._extract_safe_card_info(payment_method) if payment_method.type == "card" else None,
                    "billing_details": payment_method.billing_details,
                    "customer": payment_method.customer
                }
            }
            
            logger.info(f"Payment method created successfully: {payment_method.id}")
            return result
            
        except CardError as e:
            logger.warning(f"Card error creating payment method: {e}")
            return {
                "success": False,
                "errors": [self._format_card_error(e)],
                "card_error": True
            }
        except StripeError as e:
            logger.error(f"Stripe error creating payment method: {e}")
            return {
                "success": False,
                "errors": [f"Payment method creation failed: {str(e)}"]
            }
        except Exception as e:
            logger.error(f"Unexpected error creating payment method: {e}")
            return {
                "success": False,
                "errors": ["Payment method creation failed. Please try again."]
            }
    
    async def create_setup_intent(
        self, 
        customer_id: str,
        payment_method_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a SetupIntent for future payment method collection.
        
        Args:
            customer_id (str): Customer ID for the setup intent
            payment_method_types (list, optional): Allowed payment method types
            
        Returns:
            dict: Setup intent creation result
        """
        try:
            # Build setup intent parameters
            setup_params = {
                "customer": customer_id,
                "payment_method_types": payment_method_types or ["card"],
                "usage": "off_session",  # For future payments
                "metadata": {
                    "source": "pizza_agent",
                    "created_at": datetime.utcnow().isoformat()
                }
            }
            
            # Create setup intent
            setup_intent = stripe.SetupIntent.create(**setup_params)
            
            result = {
                "success": True,
                "setup_intent_id": setup_intent.id,
                "client_secret": setup_intent.client_secret,
                "status": setup_intent.status
            }
            
            logger.info(f"SetupIntent created successfully: {setup_intent.id}")
            return result
            
        except StripeError as e:
            logger.error(f"Stripe error creating SetupIntent: {e}")
            return {
                "success": False,
                "errors": [f"Setup intent creation failed: {str(e)}"]
            }
        except Exception as e:
            logger.error(f"Unexpected error creating SetupIntent: {e}")
            return {
                "success": False,
                "errors": ["Setup intent creation failed. Please try again."]
            }
    
    async def list_customer_payment_methods(
        self, 
        customer_id: str,
        payment_method_type: str = "card"
    ) -> Dict[str, Any]:
        """
        List payment methods for a customer.
        
        Args:
            customer_id (str): Customer ID
            payment_method_type (str): Type of payment methods to list
            
        Returns:
            dict: Payment methods list
        """
        try:
            # Check cache first
            cached_methods = await self._get_cached_payment_methods(customer_id, payment_method_type)
            if cached_methods:
                return {
                    "success": True,
                    "payment_methods": cached_methods,
                    "from_cache": True
                }
            
            # Retrieve from Stripe
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type=payment_method_type
            )
            
            # Extract safe information
            safe_methods = []
            for pm in payment_methods.data:
                safe_info = {
                    "id": pm.id,
                    "type": pm.type,
                    "billing_details": pm.billing_details,
                    "created": pm.created
                }
                
                if pm.type == "card":
                    safe_info["card"] = self._extract_safe_card_info(pm)
                
                safe_methods.append(safe_info)
            
            # Cache the results
            await self._cache_payment_methods(customer_id, payment_method_type, safe_methods)
            
            result = {
                "success": True,
                "payment_methods": safe_methods,
                "total_count": len(safe_methods)
            }
            
            logger.info(f"Retrieved {len(safe_methods)} payment methods for customer {customer_id}")
            return result
            
        except StripeError as e:
            logger.error(f"Stripe error listing payment methods: {e}")
            return {
                "success": False,
                "errors": [f"Failed to retrieve payment methods: {str(e)}"]
            }
        except Exception as e:
            logger.error(f"Unexpected error listing payment methods: {e}")
            return {
                "success": False,
                "errors": ["Failed to retrieve payment methods. Please try again."]
            }
    
    async def detach_payment_method(
        self, 
        payment_method_id: str
    ) -> Dict[str, Any]:
        """
        Detach a payment method from its customer.
        
        Args:
            payment_method_id (str): Payment method ID to detach
            
        Returns:
            dict: Detachment result
        """
        try:
            # Detach payment method
            payment_method = stripe.PaymentMethod.detach(payment_method_id)
            
            # Clear from cache
            await self._clear_payment_method_cache(payment_method_id)
            
            result = {
                "success": True,
                "payment_method_id": payment_method.id,
                "status": "detached"
            }
            
            logger.info(f"Payment method detached successfully: {payment_method_id}")
            return result
            
        except StripeError as e:
            logger.error(f"Stripe error detaching payment method: {e}")
            return {
                "success": False,
                "errors": [f"Failed to detach payment method: {str(e)}"]
            }
        except Exception as e:
            logger.error(f"Unexpected error detaching payment method: {e}")
            return {
                "success": False,
                "errors": ["Failed to detach payment method. Please try again."]
            }
    
    async def validate_payment_method(
        self, 
        payment_method_id: str
    ) -> Dict[str, Any]:
        """
        Validate a payment method without charging it.
        
        Args:
            payment_method_id (str): Payment method ID to validate
            
        Returns:
            dict: Validation result
        """
        try:
            # Retrieve payment method
            payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
            
            # Check if payment method is valid and usable
            validation_result = {
                "success": True,
                "payment_method_id": payment_method.id,
                "is_valid": True,
                "type": payment_method.type,
                "customer": payment_method.customer
            }
            
            # Add card-specific validation
            if payment_method.type == "card":
                card = payment_method.card
                validation_result["card_info"] = {
                    "brand": card.brand,
                    "last4": card.last4,
                    "exp_month": card.exp_month,
                    "exp_year": card.exp_year,
                    "funding": card.funding,
                    "country": card.country
                }
                
                # Check if card is expired
                current_date = datetime.now()
                card_exp_date = datetime(card.exp_year, card.exp_month, 1)
                
                if card_exp_date < current_date:
                    validation_result["is_valid"] = False
                    validation_result["errors"] = ["Card has expired"]
            
            logger.info(f"Payment method validated: {payment_method_id}")
            return validation_result
            
        except StripeError as e:
            logger.error(f"Stripe error validating payment method: {e}")
            return {
                "success": False,
                "errors": [f"Payment method validation failed: {str(e)}"]
            }
        except Exception as e:
            logger.error(f"Unexpected error validating payment method: {e}")
            return {
                "success": False,
                "errors": ["Payment method validation failed. Please try again."]
            }
    
    def _extract_safe_card_info(self, payment_method) -> Dict[str, Any]:
        """Extract safe card information (no sensitive data)."""
        if payment_method.type != "card" or not payment_method.card:
            return {}
        
        card = payment_method.card
        return {
            "brand": card.brand,
            "last4": card.last4,
            "exp_month": card.exp_month,
            "exp_year": card.exp_year,
            "funding": card.funding,
            "country": card.country,
            "fingerprint": card.fingerprint  # Unique card identifier
        }
    
    def _format_card_error(self, error: CardError) -> str:
        """Format card error for user-friendly display."""
        decline_code = error.decline_code
        
        error_messages = {
            "incorrect_number": "The card number is incorrect.",
            "invalid_number": "The card number is not a valid credit card number.",
            "invalid_expiry_month": "The card's expiration month is invalid.",
            "invalid_expiry_year": "The card's expiration year is invalid.",
            "invalid_cvc": "The card's security code is invalid.",
            "expired_card": "The card has expired.",
            "incorrect_cvc": "The card's security code is incorrect.",
            "card_declined": "The card was declined.",
            "processing_error": "An error occurred while processing the card."
        }
        
        return error_messages.get(error.code, "There was an error with your card information.")
    
    async def _cache_customer_info(self, customer):
        """Cache customer information for performance."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"customer:{customer.id}"
            
            customer_data = {
                "id": customer.id,
                "email": customer.email,
                "name": customer.name,
                "phone": customer.phone,
                "created": customer.created,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            with redis_client.get_connection() as conn:
                conn.setex(cache_key, self.customer_cache_ttl, json.dumps(customer_data))
            
        except Exception as e:
            logger.warning(f"Failed to cache customer info: {e}")
    
    async def _cache_payment_method_info(self, payment_method):
        """Cache payment method information (non-sensitive only)."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"payment_method:{payment_method.id}"
            
            pm_data = {
                "id": payment_method.id,
                "type": payment_method.type,
                "customer": payment_method.customer,
                "billing_details": payment_method.billing_details,
                "created": payment_method.created,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            if payment_method.type == "card":
                pm_data["card"] = self._extract_safe_card_info(payment_method)
            
            with redis_client.get_connection() as conn:
                conn.setex(cache_key, self.payment_method_cache_ttl, json.dumps(pm_data))
            
        except Exception as e:
            logger.warning(f"Failed to cache payment method info: {e}")
    
    async def _cache_payment_methods(self, customer_id: str, method_type: str, methods: List[Dict]):
        """Cache customer's payment methods list."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"customer_payment_methods:{customer_id}:{method_type}"
            
            cache_data = {
                "methods": methods,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            with redis_client.get_connection() as conn:
                conn.setex(cache_key, self.payment_method_cache_ttl, json.dumps(cache_data))
            
        except Exception as e:
            logger.warning(f"Failed to cache payment methods: {e}")
    
    async def _get_cached_payment_methods(self, customer_id: str, method_type: str) -> Optional[List[Dict]]:
        """Get cached payment methods for customer."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"customer_payment_methods:{customer_id}:{method_type}"
            
            with redis_client.get_connection() as conn:
                cached_data = conn.get(cache_key)
                if cached_data:
                    data = json.loads(cached_data)
                    return data["methods"]
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get cached payment methods: {e}")
            return None
    
    async def _clear_payment_method_cache(self, payment_method_id: str):
        """Clear payment method from cache."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"payment_method:{payment_method_id}"
            
            with redis_client.get_connection() as conn:
                conn.delete(cache_key)
            
        except Exception as e:
            logger.warning(f"Failed to clear payment method cache: {e}")


# Create global payment method manager instance
payment_method_manager = PaymentMethodManager()


# Utility functions for integration
async def create_customer(customer_info: Dict[str, Any]) -> Dict[str, Any]:
    """Utility function for creating customers."""
    return await payment_method_manager.create_customer(customer_info)


async def create_payment_method(
    payment_method_data: Dict[str, Any],
    customer_id: Optional[str] = None
) -> Dict[str, Any]:
    """Utility function for creating payment methods."""
    return await payment_method_manager.create_payment_method(payment_method_data, customer_id)


async def list_customer_payment_methods(customer_id: str) -> Dict[str, Any]:
    """Utility function for listing customer payment methods."""
    return await payment_method_manager.list_customer_payment_methods(customer_id)


async def validate_payment_method(payment_method_id: str) -> Dict[str, Any]:
    """Utility function for validating payment methods."""
    return await payment_method_manager.validate_payment_method(payment_method_id)


# Export main components
__all__ = [
    "PaymentMethodManager", "payment_method_manager", "create_customer",
    "create_payment_method", "list_customer_payment_methods", "validate_payment_method"
]