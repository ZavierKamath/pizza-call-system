"""
Payment validation for pizza orders.
Validates payment methods and processes payment authorization.
"""

import logging
import re
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import uuid

# Configure logging
logger = logging.getLogger(__name__)


class PaymentValidator:
    """
    Validates payment information and processes payment authorization.
    
    Handles credit card validation, cash payments, and payment security.
    """
    
    def __init__(self):
        """Initialize payment validator with configuration."""
        # Supported payment methods
        self.supported_methods = {
            "credit_card": {
                "name": "Credit Card",
                "requires_card_info": True,
                "processing_fee": 0.00
            },
            "debit_card": {
                "name": "Debit Card", 
                "requires_card_info": True,
                "processing_fee": 0.00
            },
            "cash": {
                "name": "Cash",
                "requires_card_info": False,
                "processing_fee": 0.00
            }
        }
        
        # Card validation patterns
        self.card_patterns = {
            "visa": r"^4[0-9]{12}(?:[0-9]{3})?$",
            "mastercard": r"^5[1-5][0-9]{14}$",
            "amex": r"^3[47][0-9]{13}$",
            "discover": r"^6(?:011|5[0-9]{2})[0-9]{12}$"
        }
        
        # Business rules
        self.minimum_charge_amount = 1.00
        self.maximum_charge_amount = 500.00
        
        logger.info("PaymentValidator initialized")
    
    def validate_payment_method(self, payment_method: str) -> Dict[str, Any]:
        """
        Validate payment method selection.
        
        Args:
            payment_method (str): Payment method to validate
            
        Returns:
            dict: Validation result
        """
        try:
            method = payment_method.lower().strip()
            
            if method not in self.supported_methods:
                return {
                    "is_valid": False,
                    "error": f"Unsupported payment method: {payment_method}",
                    "supported_methods": list(self.supported_methods.keys())
                }
            
            method_info = self.supported_methods[method]
            
            return {
                "is_valid": True,
                "payment_method": method,
                "method_info": method_info,
                "requires_card_details": method_info["requires_card_info"]
            }
            
        except Exception as e:
            logger.error(f"Error validating payment method: {e}")
            return {
                "is_valid": False,
                "error": f"Payment method validation error: {str(e)}"
            }
    
    def validate_card_information(self, card_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate credit/debit card information.
        
        Args:
            card_data (dict): Card information to validate
            
        Returns:
            dict: Validation result with tokenized card info
        """
        try:
            logger.debug("Validating card information")
            
            errors = []
            warnings = []
            validated_card = {}
            
            # Validate card number
            card_number = card_data.get("card_number", "").replace(" ", "").replace("-", "")
            if not card_number:
                errors.append("Card number is required")
            else:
                card_validation = self._validate_card_number(card_number)
                if card_validation["is_valid"]:
                    validated_card.update(card_validation["card_info"])
                else:
                    errors.extend(card_validation["errors"])
            
            # Validate expiration date
            exp_month = card_data.get("exp_month")
            exp_year = card_data.get("exp_year")
            if not exp_month or not exp_year:
                errors.append("Card expiration date is required")
            else:
                exp_validation = self._validate_expiration_date(exp_month, exp_year)
                if exp_validation["is_valid"]:
                    validated_card.update(exp_validation["exp_info"])
                else:
                    errors.extend(exp_validation["errors"])
            
            # Validate CVV
            cvv = card_data.get("cvv", "").strip()
            if not cvv:
                errors.append("CVV security code is required")
            else:
                cvv_validation = self._validate_cvv(cvv, validated_card.get("card_type"))
                if cvv_validation["is_valid"]:
                    validated_card["cvv_valid"] = True
                else:
                    errors.extend(cvv_validation["errors"])
            
            # Validate cardholder name
            cardholder_name = card_data.get("cardholder_name", "").strip()
            if not cardholder_name:
                errors.append("Cardholder name is required")
            elif len(cardholder_name) < 2:
                errors.append("Cardholder name is too short")
            else:
                validated_card["cardholder_name"] = cardholder_name.title()
            
            # Validate billing ZIP (if provided)
            billing_zip = card_data.get("billing_zip", "").strip()
            if billing_zip:
                if not re.match(r"^\d{5}(?:-\d{4})?$", billing_zip):
                    warnings.append("Billing ZIP code format may be invalid")
                else:
                    validated_card["billing_zip"] = billing_zip
            
            # If all validations pass, create secure token
            if not errors:
                validated_card["token"] = self._generate_card_token()
                validated_card["last_four"] = card_number[-4:] if len(card_number) >= 4 else "****"
                # Never store actual card number
                validated_card.pop("card_number", None)
            
            return {
                "is_valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "validated_card": validated_card if not errors else {}
            }
            
        except Exception as e:
            logger.error(f"Error validating card information: {e}")
            return {
                "is_valid": False,
                "errors": [f"Card validation error: {str(e)}"],
                "warnings": [],
                "validated_card": {}
            }
    
    def validate_payment_amount(self, amount: float) -> Dict[str, Any]:
        """
        Validate payment amount against business rules.
        
        Args:
            amount (float): Payment amount to validate
            
        Returns:
            dict: Validation result
        """
        try:
            if amount < self.minimum_charge_amount:
                return {
                    "is_valid": False,
                    "error": f"Payment amount must be at least ${self.minimum_charge_amount:.2f}"
                }
            
            if amount > self.maximum_charge_amount:
                return {
                    "is_valid": False,
                    "error": f"Payment amount cannot exceed ${self.maximum_charge_amount:.2f}"
                }
            
            return {
                "is_valid": True,
                "validated_amount": round(amount, 2)
            }
            
        except (ValueError, TypeError):
            return {
                "is_valid": False,
                "error": "Invalid payment amount format"
            }
    
    def process_payment_authorization(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process payment authorization (simulation for demo).
        
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
                return self._process_cash_payment(amount)
            elif payment_method in ["credit_card", "debit_card"]:
                return self._process_card_payment(payment_data)
            else:
                return {
                    "success": False,
                    "error": "Unsupported payment method"
                }
                
        except Exception as e:
            logger.error(f"Error processing payment authorization: {e}")
            return {
                "success": False,
                "error": f"Payment processing error: {str(e)}"
            }
    
    def _validate_card_number(self, card_number: str) -> Dict[str, Any]:
        """Validate credit card number using Luhn algorithm and patterns."""
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
                "card_number": card_number  # Will be removed after tokenization
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
            max_future_date = current_date + timedelta(days=365 * 10)  # 10 years
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
    
    def _validate_cvv(self, cvv: str, card_type: Optional[str] = None) -> Dict[str, Any]:
        """Validate CVV security code."""
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
        elif card_type != "amex" and len(cvv) != 3:
            return {
                "is_valid": False,
                "errors": ["CVV must be 3 digits"]
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
    
    def _generate_card_token(self) -> str:
        """Generate secure token for card storage."""
        return f"tok_{uuid.uuid4().hex[:16]}"
    
    def _process_cash_payment(self, amount: float) -> Dict[str, Any]:
        """Process cash payment authorization."""
        return {
            "success": True,
            "method": "cash",
            "amount": amount,
            "transaction_id": f"cash_{uuid.uuid4().hex[:8]}",
            "message": f"Cash payment of ${amount:.2f} confirmed for delivery",
            "instructions": "Please have exact change ready for the delivery driver"
        }
    
    def _process_card_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process credit/debit card payment (simulation)."""
        # In a real system, this would integrate with Stripe, Square, etc.
        
        amount = payment_data.get("amount", 0.0)
        card_info = payment_data.get("card_info", {})
        
        # Simulate payment processing
        # In demo, always succeed unless specific test cases
        transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
        
        return {
            "success": True,
            "method": payment_data.get("payment_method"),
            "amount": amount,
            "transaction_id": transaction_id,
            "last_four": card_info.get("last_four", "****"),
            "card_type": card_info.get("card_type", "unknown"),
            "message": f"Payment of ${amount:.2f} processed successfully",
            "authorization_code": f"auth_{uuid.uuid4().hex[:6]}"
        }
    
    def get_supported_payment_methods(self) -> Dict[str, Any]:
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
            }
        }


# Export main class
__all__ = ["PaymentValidator"]