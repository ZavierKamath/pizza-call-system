"""
Address validation for delivery orders - simplified demo version.
Validates delivery addresses using basic regex patterns without external API calls.
"""

import logging
import re
from typing import Dict, Any, Optional, List

# Configure logging
logger = logging.getLogger(__name__)


class AddressValidator:
    """
    Validates delivery addresses for pizza orders using simple pattern matching.
    
    For demo purposes - validates that address looks like a real street address
    without requiring external APIs or complex validation.
    """
    
    def __init__(self):
        """Initialize address validator with simple validation rules."""
        self.delivery_radius_miles = 5  # Demo - accept all addresses within conceptual radius
        
        # Street address validation patterns
        self.street_patterns = [
            r'\d+\s+\w+\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Circle|Cir|Court|Ct|Place|Pl)\b',
            r'\d+\s+\w+\s+\w+\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Circle|Cir|Court|Ct|Place|Pl)\b',
            r'\d+\s+[A-Za-z\s]+',  # Fallback: number + letters
        ]
        
        # Compiled regex patterns for efficiency
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.street_patterns]
        
        logger.info(f"AddressValidator initialized with {self.delivery_radius_miles}-mile delivery radius")
    
    async def validate_address(self, address_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simple address validation using regex patterns.
        
        Args:
            address_data (dict): Address components to validate
            
        Returns:
            dict: Validation result with basic validation information
        """
        try:
            logger.debug(f"Validating address: {address_data}")
            
            # Initialize validation result
            result = {
                "is_valid": False,
                "validated_address": {},
                "standardized_address": "",
                "coordinates": None,
                "delivery_distance_miles": None,
                "delivery_feasible": True,  # Demo: assume all addresses are deliverable
                "errors": [],
                "warnings": [],
                "suggestions": []
            }
            
            # Get street address from data
            street_address = address_data.get("street", "").strip()
            if not street_address:
                result["errors"].append("Street address is required")
                return result
            
            # Validate street address format using regex patterns
            is_valid_format = self._validate_street_format(street_address)
            
            if is_valid_format:
                result["is_valid"] = True
                result["validated_address"] = address_data.copy()
                result["standardized_address"] = street_address
                result["delivery_feasible"] = True
                result["delivery_distance_miles"] = 2.5  # Demo: fake reasonable distance
                
                logger.info(f"Address validated successfully: {street_address}")
            else:
                result["errors"].append("Address format appears invalid (should include street number and name)")
                logger.warning(f"Address validation failed: {street_address}")
            
            return result
        
        except Exception as e:
            logger.error(f"Error validating address: {e}")
            return {
                "is_valid": False,
                "validated_address": {},
                "standardized_address": "",
                "coordinates": None,
                "delivery_distance_miles": None,
                "delivery_feasible": False,
                "errors": [f"Validation error: {str(e)}"],
                "warnings": [],
                "suggestions": []
            }
    
    def _validate_street_format(self, street_address: str) -> bool:
        """
        Validate street address format using regex patterns.
        
        Args:
            street_address (str): Street address to validate
            
        Returns:
            bool: True if address format is valid
        """
        if not street_address or len(street_address.strip()) < 3:
            return False
        
        # Check against compiled regex patterns
        for pattern in self.compiled_patterns:
            if pattern.search(street_address):
                return True
        
        # Additional basic checks
        # Must have at least one number and one letter
        has_number = bool(re.search(r'\d', street_address))
        has_letter = bool(re.search(r'[A-Za-z]', street_address))
        
        return has_number and has_letter


# Create module-level instance for easy import
address_validator = AddressValidator()


# Utility functions
async def validate_address(address_data: Dict[str, Any]) -> Dict[str, Any]:
    """Utility function to validate addresses."""
    return await address_validator.validate_address(address_data)


def is_valid_address_format(address_string: str) -> bool:
    """Quick utility to check if address format is valid."""
    return address_validator._validate_street_format(address_string)


# Export main components
__all__ = [
    "AddressValidator", "address_validator", "validate_address", "is_valid_address_format"
]