"""
Payment validation for pizza orders with Stripe integration.
Validates payment methods, processes payment authorization with PCI-compliant handling.
"""

import logging
import re
import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import uuid

import stripe
from stripe.error import StripeError, CardError, InvalidRequestError

from ..config.settings import settings
from ..database.redis_client import get_redis_async

# Configure logging
logger = logging.getLogger(__name__)


class PaymentValidator:
    """
    Validates payment information and processes payment authorization with Stripe.
    
    Handles credit card validation, tokenization, and PCI-compliant payment processing.
    Integrates with Stripe for secure payment handling.
    """
    
    def __init__(self):
        """Initialize payment validator with Stripe configuration."""
        # Initialize Stripe with secret key
        stripe.api_key = settings.stripe_secret_key
        self.stripe_publishable_key = settings.stripe_publishable_key
        
        # Payment configuration
        self.minimum_charge_amount = 1.00  # $1.00 minimum
        self.maximum_charge_amount = 500.00  # $500.00 maximum for pizza orders
        
        # Supported payment methods
        self.supported_methods = {
            "credit_card": {
                "name": "Credit Card",
                "requires_card_info": True,
                "processing_fee": 0.00,
                "stripe_payment_method": "card"
            },
            "debit_card": {
                "name": "Debit Card", 
                "requires_card_info": True,
                "processing_fee": 0.00,
                "stripe_payment_method": "card"
            },
            "cash": {
                "name": "Cash on Delivery",
                "requires_card_info": False,
                "processing_fee": 0.00,
                "stripe_payment_method": None
            }
        }
        
        # Card validation patterns (for additional client-side validation)
        self.card_patterns = {
            "visa": r"^4[0-9]{12}(?:[0-9]{3})?$",
            "mastercard": r"^5[1-5][0-9]{14}$|^2(?:2(?:2[1-9]|[3-9][0-9])|[3-6][0-9][0-9]|7(?:[01][0-9]|20))[0-9]{12}$",
            "amex": r"^3[47][0-9]{13}$",
            "discover": r"^6(?:011|5[0-9]{2})[0-9]{12}$",
            "diners": r"^3[0689][0-9]{13}$",
            "jcb": r"^(?:2131|1800|35[0-9]{3})[0-9]{11}$"
        }
        
        # Cache configuration for validation results
        self.validation_cache_ttl_minutes = 10
        
        logger.info("PaymentValidator initialized with Stripe integration")
    
    async def validate_payment_method(self, payment_method: str) -> Dict[str, Any]:
        """
        Validate payment method selection.
        
        Args:
            payment_method (str): Payment method to validate
            
        Returns:
            dict: Validation result with method information
        """
        try:
            method = payment_method.lower().strip()
            
            if method not in self.supported_methods:
                return {
                    "is_valid": False,
                    "errors": [f"Unsupported payment method: {payment_method}"],
                    "supported_methods": list(self.supported_methods.keys())
                }
            
            method_info = self.supported_methods[method]
            
            return {
                "is_valid": True,
                "payment_method": method,
                "method_info": method_info,
                "requires_card_details": method_info["requires_card_info"],
                "stripe_integration": method_info["stripe_payment_method"] is not None
            }
            
        except Exception as e:
            logger.error(f"Error validating payment method: {e}")
            return {
                "is_valid": False,
                "errors": [f"Payment method validation error: {str(e)}"]
            }
    
    async def validate_stripe_token(self, stripe_token: str, amount: float) -> Dict[str, Any]:
        """
        Validate Stripe payment token and perform test charge authorization.
        
        Args:
            stripe_token (str): Stripe token from frontend
            amount (float): Amount to validate for charging
            
        Returns:
            dict: Validation result with payment method details
        """
        try:
            logger.debug(f"Validating Stripe token for amount: ${amount:.2f}")
            
            # Validate amount first
            amount_validation = await self.validate_payment_amount(amount)
            if not amount_validation["is_valid"]:
                return amount_validation
            
            # Convert amount to cents for Stripe
            amount_cents = int(amount * 100)
            
            # Create PaymentIntent for validation (without confirming)
            try:
                payment_intent = stripe.PaymentIntent.create(
                    amount=amount_cents,
                    currency='usd',
                    payment_method=stripe_token,
                    confirm=False,  # Don't actually charge yet
                    capture_method='manual',  # Allow capture later
                    description=f"Pizza order validation - ${amount:.2f}",
                    metadata={
                        'validation': 'true',
                        'order_type': 'pizza',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                # Get payment method details from Stripe
                payment_method = stripe.PaymentMethod.retrieve(stripe_token)
                
                # Extract card information safely
                card_info = self._extract_card_info(payment_method)
                
                return {
                    "is_valid": True,
                    "stripe_payment_intent_id": payment_intent.id,
                    "payment_method_id": stripe_token,
                    "card_info": card_info,
                    "amount_cents": amount_cents,
                    "amount_dollars": amount,
                    "status": payment_intent.status,
                    "client_secret": payment_intent.client_secret,
                    "errors": [],
                    "warnings": []
                }
                
            except CardError as e:
                # Card was declined
                error_msg = self._format_card_error(e)
                logger.warning(f"Card declined during validation: {error_msg}")
                return {
                    "is_valid": False,
                    "errors": [error_msg],
                    "decline_code": e.decline_code,
                    "card_declined": True
                }
                
            except InvalidRequestError as e:
                # Invalid token or request
                logger.error(f"Invalid Stripe request: {e}")
                return {
                    "is_valid": False,
                    "errors": ["Invalid payment information. Please try again."]
                }
                
        except StripeError as e:
            logger.error(f"Stripe API error during validation: {e}")
            return {
                "is_valid": False,
                "errors": ["Payment validation temporarily unavailable. Please try again."]
            }
        except Exception as e:
            logger.error(f"Error validating Stripe token: {e}")
            return {
                "is_valid": False,
                "errors": ["Payment validation error. Please try again."]
            }
    
    async def validate_card_format(self, card_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Client-side card format validation (for immediate feedback).
        
        Args:
            card_data (dict): Card information for format validation
            
        Returns:
            dict: Format validation result
        """
        try:
            errors = []
            warnings = []
            card_info = {}
            
            # Validate card number format
            card_number = card_data.get("card_number", "").replace(" ", "").replace("-", "")
            if card_number:
                card_validation = self._validate_card_number_format(card_number)
                if card_validation["is_valid"]:
                    card_info.update(card_validation["card_info"])
                else:
                    errors.extend(card_validation["errors"])
            else:
                errors.append("Card number is required")
            
            # Validate expiration date
            exp_month = card_data.get("exp_month")
            exp_year = card_data.get("exp_year")
            if exp_month and exp_year:
                exp_validation = self._validate_expiration_date(exp_month, exp_year)
                if exp_validation["is_valid"]:
                    card_info.update(exp_validation["exp_info"])
                else:
                    errors.extend(exp_validation["errors"])
            else:
                errors.append("Card expiration date is required")
            
            # Validate CVV format
            cvv = card_data.get("cvv", "").strip()
            if cvv:
                cvv_validation = self._validate_cvv_format(cvv, card_info.get("card_type"))
                if not cvv_validation["is_valid"]:
                    errors.extend(cvv_validation["errors"])
            else:
                errors.append("CVV security code is required")
            
            # Validate cardholder name
            cardholder_name = card_data.get("cardholder_name", "").strip()
            if cardholder_name:
                if len(cardholder_name) < 2:
                    errors.append("Cardholder name is too short")
                else:
                    card_info["cardholder_name"] = cardholder_name.title()
            else:
                errors.append("Cardholder name is required")
            
            return {
                "is_valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "card_info": card_info if not errors else {}
            }
            
        except Exception as e:
            logger.error(f"Error validating card format: {e}")
            return {
                "is_valid": False,
                "errors": ["Card format validation error"],
                "warnings": [],
                "card_info": {}
            }
    
    async def validate_payment_amount(self, amount: float) -> Dict[str, Any]:
        """
        Validate payment amount against business rules.
        
        Args:
            amount (float): Payment amount to validate
            
        Returns:
            dict: Validation result
        """
        try:
            if not isinstance(amount, (int, float)):
                return {
                    "is_valid": False,
                    "errors": ["Invalid payment amount format"]
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
            
            return {
                "is_valid": True,
                "validated_amount": round(amount, 2),
                "amount_cents": int(amount * 100)
            }
            
        except (ValueError, TypeError):
            return {
                "is_valid": False,
                "errors": ["Invalid payment amount format"]
            }
    
    async def process_payment_authorization(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process payment authorization with Stripe or cash handling.
        
        Args:
            payment_data (dict): Complete payment information
            
        Returns:
            dict: Authorization result
        """
        try:
            payment_method = payment_data.get("payment_method")
            amount = payment_data.get("amount", 0.0)
            
            logger.info(f"Processing {payment_method} payment authorization for ${amount:.2f}")
            
            if payment_method == "cash":
                return await self._process_cash_payment(amount)
            elif payment_method in ["credit_card", "debit_card"]:
                return await self._process_stripe_payment(payment_data)
            else:
                return {
                    "success": False,
                    "errors": ["Unsupported payment method"]
                }
                
        except Exception as e:
            logger.error(f"Error processing payment authorization: {e}")
            return {
                "success": False,
                "errors": [f"Payment processing error: {str(e)}"]
            }
    
    async def confirm_stripe_payment(self, payment_intent_id: str) -> Dict[str, Any]:
        """
        Confirm a Stripe payment intent (actually charge the card).
        
        Args:
            payment_intent_id (str): Stripe PaymentIntent ID
            
        Returns:
            dict: Payment confirmation result
        """
        try:
            # Confirm the payment intent
            payment_intent = stripe.PaymentIntent.confirm(payment_intent_id)
            
            if payment_intent.status == 'succeeded':
                return {
                    "success": True,
                    "payment_intent_id": payment_intent.id,
                    "transaction_id": payment_intent.id,
                    "amount": payment_intent.amount / 100,  # Convert from cents
                    "status": payment_intent.status,
                    "message": f"Payment of ${payment_intent.amount / 100:.2f} processed successfully"
                }
            else:
                return {
                    "success": False,
                    "errors": [f"Payment failed with status: {payment_intent.status}"],
                    "status": payment_intent.status
                }
                
        except CardError as e:
            error_msg = self._format_card_error(e)
            logger.warning(f"Card declined during confirmation: {error_msg}")
            return {
                "success": False,
                "errors": [error_msg],
                "decline_code": e.decline_code
            }
        except StripeError as e:
            logger.error(f"Stripe error during payment confirmation: {e}")
            return {
                "success": False,
                "errors": ["Payment processing failed. Please try again."]
            }
        except Exception as e:
            logger.error(f"Error confirming Stripe payment: {e}")
            return {
                "success": False,
                "errors": ["Payment confirmation error. Please try again."]
            }
    
    def _extract_card_info(self, payment_method) -> Dict[str, Any]:
        """Extract safe card information from Stripe PaymentMethod."""
        if not payment_method or payment_method.type != 'card':
            return {}
        
        card = payment_method.card
        return {
            "card_type": card.brand,
            "last_four": card.last4,
            "exp_month": card.exp_month,
            "exp_year": card.exp_year,
            "funding": card.funding,  # credit, debit, prepaid, unknown
            "country": card.country,
            "fingerprint": card.fingerprint  # Unique identifier for this card
        }
    
    def _format_card_error(self, error: CardError) -> str:
        """Format Stripe card error for user-friendly message."""
        decline_code = error.decline_code
        
        # Map common decline codes to user-friendly messages
        decline_messages = {
            'insufficient_funds': "Your card has insufficient funds for this transaction.",
            'card_declined': "Your card was declined. Please try a different card.",
            'expired_card': "Your card has expired. Please use a different card.",
            'incorrect_cvc': "The CVV code you entered is incorrect.",
            'incorrect_number': "The card number you entered is incorrect.",
            'invalid_cvc': "The CVV code format is invalid.",
            'invalid_expiry_month': "The expiration month is invalid.",
            'invalid_expiry_year': "The expiration year is invalid.",
            'invalid_number': "The card number is invalid.",
            'processing_error': "An error occurred processing your card. Please try again.",
            'lost_card': "Your card cannot be used for this transaction.",
            'stolen_card': "Your card cannot be used for this transaction.",
            'generic_decline': "Your card was declined. Please contact your bank or try a different card."
        }
        
        return decline_messages.get(decline_code, "Your card was declined. Please try a different payment method.")
    
    def _validate_card_number_format(self, card_number: str) -> Dict[str, Any]:
        """Validate card number format using Luhn algorithm and patterns."""
        if not card_number.isdigit():
            return {
                "is_valid": False,
                "errors": ["Card number must contain only digits"]
            }
        
        if len(card_number) < 13 or len(card_number) > 19:
            return {
                "is_valid": False,
                "errors": ["Card number length is invalid"]
            }
        
        # Check Luhn algorithm
        if not self._luhn_check(card_number):
            return {
                "is_valid": False,
                "errors": ["Card number is invalid"]
            }
        
        # Determine card type
        card_type = self._determine_card_type(card_number)
        if not card_type:
            return {
                "is_valid": False,
                "errors": ["Unsupported card type"]
            }
        
        return {
            "is_valid": True,
            "card_info": {
                "card_type": card_type,
                "last_four": card_number[-4:]
            }
        }
    
    def _validate_expiration_date(self, month: Any, year: Any) -> Dict[str, Any]:
        """Validate card expiration date."""
        try:
            exp_month = int(month)
            exp_year = int(year)
            
            # Handle 2-digit years
            if exp_year < 100:
                exp_year += 2000
            
            if exp_month < 1 or exp_month > 12:
                return {
                    "is_valid": False,
                    "errors": ["Invalid expiration month"]
                }
            
            # Check if card is expired
            current_date = datetime.now()
            exp_date = datetime(exp_year, exp_month, 1)
            
            if exp_date < current_date:
                return {
                    "is_valid": False,
                    "errors": ["Card has expired"]
                }
            
            # Check if expiration is too far in future (likely input error)
            max_future_date = current_date + timedelta(days=365 * 15)  # 15 years
            if exp_date > max_future_date:
                return {
                    "is_valid": False,
                    "errors": ["Card expiration date is too far in the future"]
                }
            
            return {
                "is_valid": True,
                "exp_info": {
                    "exp_month": exp_month,
                    "exp_year": exp_year
                }
            }
            
        except (ValueError, TypeError):
            return {
                "is_valid": False,
                "errors": ["Invalid expiration date format"]
            }
    
    def _validate_cvv_format(self, cvv: str, card_type: Optional[str] = None) -> Dict[str, Any]:
        """Validate CVV security code format."""
        if not cvv.isdigit():
            return {
                "is_valid": False,
                "errors": ["CVV must contain only digits"]
            }
        
        # CVV length validation based on card type
        if card_type == "amex" and len(cvv) != 4:
            return {
                "is_valid": False,
                "errors": ["American Express CVV must be 4 digits"]
            }
        elif card_type != "amex" and len(cvv) not in [3, 4]:
            return {
                "is_valid": False,
                "errors": ["CVV must be 3 or 4 digits"]
            }
        
        return {"is_valid": True}
    
    def _luhn_check(self, card_number: str) -> bool:
        """Implement Luhn algorithm for card number validation."""
        def luhn_checksum(card_num):
            def digits_of(n):
                return [int(d) for d in str(n)]
            
            digits = digits_of(card_num)
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            checksum = sum(odd_digits)
            for d in even_digits:
                checksum += sum(digits_of(d*2))
            return checksum % 10
        
        return luhn_checksum(card_number) == 0
    
    def _determine_card_type(self, card_number: str) -> Optional[str]:
        """Determine card type from card number."""
        for card_type, pattern in self.card_patterns.items():
            if re.match(pattern, card_number):
                return card_type
        return None
    
    async def _process_cash_payment(self, amount: float) -> Dict[str, Any]:
        """Process cash payment authorization."""
        return {
            "success": True,
            "payment_method": "cash",
            "amount": amount,
            "transaction_id": f"cash_{uuid.uuid4().hex[:8]}",
            "message": f"Cash payment of ${amount:.2f} confirmed for delivery",
            "instructions": "Please have exact change ready for the delivery driver",
            "requires_confirmation": False
        }
    
    async def _process_stripe_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process Stripe payment authorization."""
        try:
            amount = payment_data.get("amount", 0.0)
            payment_intent_id = payment_data.get("stripe_payment_intent_id")
            
            if payment_intent_id:
                # Payment intent already created during validation
                return {
                    "success": True,
                    "payment_method": payment_data.get("payment_method"),
                    "amount": amount,
                    "payment_intent_id": payment_intent_id,
                    "message": f"Payment of ${amount:.2f} authorized successfully",
                    "requires_confirmation": True,
                    "next_step": "confirm_payment"
                }
            else:
                return {
                    "success": False,
                    "errors": ["Payment authorization required before processing"]
                }
                
        except Exception as e:
            logger.error(f"Error processing Stripe payment: {e}")
            return {
                "success": False,
                "errors": ["Payment processing error"]
            }
    
    async def get_supported_payment_methods(self) -> Dict[str, Any]:
        """
        Get information about supported payment methods.
        
        Returns:
            dict: Payment method information
        """
        return {
            "methods": self.supported_methods,
            "card_types": list(self.card_patterns.keys()),
            "limits": {
                "minimum_amount": self.minimum_charge_amount,
                "maximum_amount": self.maximum_charge_amount
            },
            "stripe_publishable_key": self.stripe_publishable_key
        }
    
    async def create_payment_intent(self, amount: float, customer_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create a Stripe PaymentIntent for the order.
        
        Args:
            amount (float): Payment amount
            customer_info (dict): Optional customer information
            
        Returns:
            dict: PaymentIntent creation result
        """
        try:
            # Validate amount
            amount_validation = await self.validate_payment_amount(amount)
            if not amount_validation["is_valid"]:
                return {
                    "success": False,
                    "errors": amount_validation["errors"]
                }
            
            amount_cents = int(amount * 100)
            
            # Create PaymentIntent
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency='usd',
                automatic_payment_methods={'enabled': True},
                description=f"Pizza order - ${amount:.2f}",
                metadata={
                    'order_type': 'pizza',
                    'customer_name': customer_info.get('name', '') if customer_info else '',
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
            
            return {
                "success": True,
                "payment_intent_id": payment_intent.id,
                "client_secret": payment_intent.client_secret,
                "amount": amount,
                "amount_cents": amount_cents,
                "status": payment_intent.status
            }
            
        except StripeError as e:
            logger.error(f"Stripe error creating PaymentIntent: {e}")
            return {
                "success": False,
                "errors": ["Failed to create payment intent"]
            }
        except Exception as e:
            logger.error(f"Error creating PaymentIntent: {e}")
            return {
                "success": False,
                "errors": ["Payment setup error"]
            }


# Create global validator instance
payment_validator = PaymentValidator()


# Utility functions for integration
async def validate_payment_method(payment_method: str) -> Dict[str, Any]:
    """Utility function for payment method validation."""
    return await payment_validator.validate_payment_method(payment_method)


async def validate_stripe_token(stripe_token: str, amount: float) -> Dict[str, Any]:
    """Utility function for Stripe token validation."""
    return await payment_validator.validate_stripe_token(stripe_token, amount)


async def validate_card_format(card_data: Dict[str, Any]) -> Dict[str, Any]:
    """Utility function for card format validation."""
    return await payment_validator.validate_card_format(card_data)


async def process_payment_authorization(payment_data: Dict[str, Any]) -> Dict[str, Any]:
    """Utility function for payment authorization."""
    return await payment_validator.process_payment_authorization(payment_data)


async def confirm_payment(payment_intent_id: str) -> Dict[str, Any]:
    """Utility function for payment confirmation."""
    return await payment_validator.confirm_stripe_payment(payment_intent_id)


async def get_payment_methods() -> Dict[str, Any]:
    """Utility function to get supported payment methods."""
    return await payment_validator.get_supported_payment_methods()


# Export main components
__all__ = [
    "PaymentValidator", "payment_validator", "validate_payment_method", 
    "validate_stripe_token", "validate_card_format", "process_payment_authorization", 
    "confirm_payment", "get_payment_methods"
]