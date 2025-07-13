"""
User-friendly error message formatting for validation failures.
Provides clear, actionable feedback for customers during the ordering process.
"""

import logging
from typing import Dict, Any, List, Optional

# Configure logging
logger = logging.getLogger(__name__)


class ValidationErrorFormatter:
    """
    Formats validation errors into user-friendly messages for customer communication.
    
    Provides clear explanations of what went wrong and actionable steps to resolve issues.
    """
    
    def __init__(self):
        """Initialize error formatter with user-friendly message templates."""
        # Address validation error messages
        self.address_error_messages = {
            "incomplete": "We need a complete address to deliver your pizza. Please include street address, city, and state.",
            "not_found": "We couldn't find that address. Please double-check the spelling and try again.",
            "outside_delivery": "Sorry, that address is outside our delivery area. We deliver within 5 miles of our restaurant.",
            "geocoding_failed": "We're having trouble verifying that address right now. Please try again or call us directly.",
            "format_error": "Please provide your address in this format: '123 Main St, City, State ZIP'"
        }
        
        # Order validation error messages  
        self.order_error_messages = {
            "no_pizzas": "Looks like you haven't added any pizzas yet! What would you like to order?",
            "invalid_size": "That pizza size isn't available. We have small (10\"), medium (12\"), and large (14\") pizzas.",
            "invalid_toppings": "Some of those toppings aren't available right now. Let me suggest some alternatives.",
            "too_many_toppings": "That's a lot of toppings! This pizza size has a limit. Would you like to try a larger size?",
            "quantity_too_high": "That's quite a few pizzas! Our maximum is 5 of the same pizza per order.",
            "unavailable_item": "Sorry, that item isn't available right now. Can I suggest something similar?",
            "minimum_order": "Your order needs to be at least $15.00 for delivery. Would you like to add something else?"
        }
        
        # Payment validation error messages
        self.payment_error_messages = {
            "no_method": "How would you like to pay? We accept credit cards, debit cards, or cash on delivery.",
            "invalid_method": "That payment method isn't available. Please choose credit card, debit card, or cash on delivery.",
            "card_declined": "Your card was declined. Please try a different card or choose cash on delivery.",
            "invalid_card": "There's an issue with that card information. Please check the number and try again.",
            "expired_card": "That card has expired. Please use a different card or choose cash on delivery.",
            "payment_failed": "We couldn't process that payment. Please try again or choose a different payment method.",
            "amount_error": "There's an issue with the payment amount. Let me recalculate your order total."
        }
        
        # Suggestion templates
        self.suggestion_templates = {
            "address": [
                "Try including your ZIP code",
                "Make sure the street name is spelled correctly", 
                "Double-check the house/apartment number",
                "Use full street names (Street instead of St)"
            ],
            "order": [
                "Try our popular pepperoni pizza",
                "Add a side or drink to reach the minimum order",
                "Consider a larger size to fit more toppings",
                "Check out our daily specials"
            ],
            "payment": [
                "Try a different credit/debit card",
                "Choose cash on delivery instead",
                "Make sure your card info is entered correctly",
                "Contact your bank if the card keeps declining"
            ]
        }
        
        logger.info("ValidationErrorFormatter initialized")
    
    def format_validation_summary(self, validation_results: Dict[str, Any]) -> str:
        """
        Format comprehensive validation results into user-friendly summary.
        
        Args:
            validation_results (dict): Validation results from validation engines
            
        Returns:
            str: User-friendly validation summary
        """
        try:
            summary_parts = []
            errors = []
            warnings = []
            valid_items = []
            
            for field, result in validation_results.items():
                if result["is_valid"]:
                    valid_items.append(f"✓ {field.replace('_', ' ').title()}: Verified")
                    
                    # Add any warnings for valid items
                    if hasattr(result, 'warnings') and result.warnings:
                        for warning in result.warnings:
                            warnings.append(f"ℹ️ {warning}")
                else:
                    # Get user-friendly error message
                    friendly_error = self._get_friendly_error_message(field, result)
                    errors.append(f"❌ {friendly_error}")
                    
                    # Add suggested fix
                    friendly_fix = self._get_friendly_fix_suggestion(field, result)
                    if friendly_fix:
                        errors.append(f"   💡 {friendly_fix}")
            
            # Build the summary with clear sections
            total_checks = len(validation_results)
            passed_checks = sum(1 for r in validation_results.values() if r["is_valid"])
            
            if passed_checks == total_checks:
                summary_parts.append("🎉 Perfect! Everything looks good with your order.")
            else:
                failed_checks = total_checks - passed_checks
                if failed_checks == 1:
                    summary_parts.append("Almost there! Just one thing needs your attention:")
                else:
                    summary_parts.append(f"Just {failed_checks} things need your attention:")
                
                summary_parts.append("")
                summary_parts.extend(errors)
            
            if warnings:
                summary_parts.append("")
                summary_parts.append("📝 Quick notes:")
                summary_parts.extend(warnings)
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Error formatting validation summary: {e}")
            return "Let me help you finish your order. There are a few details we need to review."
    
    def format_field_error(self, field: str, error_details: Dict[str, Any]) -> str:
        """
        Format individual field validation error.
        
        Args:
            field (str): Field name that failed validation
            error_details (dict): Error details from validation
            
        Returns:
            str: User-friendly error message
        """
        try:
            friendly_error = self._get_friendly_error_message(field, error_details)
            friendly_fix = self._get_friendly_fix_suggestion(field, error_details)
            
            if friendly_fix:
                return f"{friendly_error} {friendly_fix}"
            else:
                return friendly_error
                
        except Exception as e:
            logger.error(f"Error formatting field error for {field}: {e}")
            return f"There's an issue with the {field.replace('_', ' ')}. Could you please check that information?"
    
    def get_suggestions_for_field(self, field: str) -> List[str]:
        """
        Get helpful suggestions for a specific field.
        
        Args:
            field (str): Field name
            
        Returns:
            list: List of helpful suggestions
        """
        field_category = self._map_field_to_category(field)
        return self.suggestion_templates.get(field_category, [])
    
    def _get_friendly_error_message(self, field: str, result: Dict[str, Any]) -> str:
        """Get user-friendly error message for field."""
        error_msg = result.get("error_message", "")
        
        # Map field and error to friendly message
        if field == "address":
            if "not found" in error_msg.lower() or "geocoding" in error_msg.lower():
                return self.address_error_messages["not_found"]
            elif "delivery" in error_msg.lower() or "radius" in error_msg.lower():
                return self.address_error_messages["outside_delivery"]
            elif "incomplete" in error_msg.lower() or "missing" in error_msg.lower():
                return self.address_error_messages["incomplete"]
            else:
                return self.address_error_messages["format_error"]
        
        elif field in ["order", "pizzas"]:
            if "no pizzas" in error_msg.lower() or "empty" in error_msg.lower():
                return self.order_error_messages["no_pizzas"]
            elif "minimum" in error_msg.lower():
                return self.order_error_messages["minimum_order"]
            elif "size" in error_msg.lower():
                return self.order_error_messages["invalid_size"]
            elif "topping" in error_msg.lower():
                if "many" in error_msg.lower():
                    return self.order_error_messages["too_many_toppings"]
                else:
                    return self.order_error_messages["invalid_toppings"]
            elif "quantity" in error_msg.lower():
                return self.order_error_messages["quantity_too_high"]
            else:
                return self.order_error_messages["unavailable_item"]
        
        elif field in ["payment", "payment_method"]:
            if "no payment" in error_msg.lower() or "missing" in error_msg.lower():
                return self.payment_error_messages["no_method"]
            elif "invalid" in error_msg.lower() or "unsupported" in error_msg.lower():
                return self.payment_error_messages["invalid_method"]
            elif "declined" in error_msg.lower():
                return self.payment_error_messages["card_declined"]
            elif "expired" in error_msg.lower():
                return self.payment_error_messages["expired_card"]
            else:
                return self.payment_error_messages["payment_failed"]
        
        # Default friendly message
        return f"There's an issue with your {field.replace('_', ' ')}. Let me help you fix that."
    
    def _get_friendly_fix_suggestion(self, field: str, result: Dict[str, Any]) -> Optional[str]:
        """Get user-friendly fix suggestion for field."""
        field_category = self._map_field_to_category(field)
        suggestions = self.suggestion_templates.get(field_category, [])
        
        # Return most relevant suggestion based on field type
        if field == "address":
            return "Please try entering your full address including ZIP code."
        elif field in ["order", "pizzas"]:
            return "What pizza would you like to add to your order?"
        elif field in ["payment", "payment_method"]:
            return "Would you like to try a different payment method?"
        elif suggestions:
            return suggestions[0]  # Return first suggestion as default
        
        return None
    
    def _map_field_to_category(self, field: str) -> str:
        """Map field name to category for suggestions."""
        if field in ["address", "delivery_address"]:
            return "address"
        elif field in ["order", "pizzas", "order_total"]:
            return "order"
        elif field in ["payment", "payment_method", "payment_amount"]:
            return "payment"
        else:
            return "general"


# Create global formatter instance
error_formatter = ValidationErrorFormatter()


# Utility functions for integration
def format_validation_summary(validation_results: Dict[str, Any]) -> str:
    """Utility function for formatting validation summaries."""
    return error_formatter.format_validation_summary(validation_results)


def format_field_error(field: str, error_details: Dict[str, Any]) -> str:
    """Utility function for formatting field errors."""
    return error_formatter.format_field_error(field, error_details)


def get_field_suggestions(field: str) -> List[str]:
    """Utility function for getting field suggestions."""
    return error_formatter.get_suggestions_for_field(field)


# Export main components
__all__ = [
    "ValidationErrorFormatter", "error_formatter", "format_validation_summary", 
    "format_field_error", "get_field_suggestions"
]