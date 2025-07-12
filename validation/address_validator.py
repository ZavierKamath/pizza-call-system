"""
Address validation for delivery orders.
Validates delivery addresses and checks delivery area coverage.
"""

import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class AddressValidator:
    """
    Validates delivery addresses for pizza orders.
    
    Performs address validation, delivery area checking,
    and address standardization.
    """
    
    def __init__(self):
        """Initialize address validator with configuration."""
        # Delivery area configuration (would be configurable in real system)
        self.delivery_radius_miles = 5
        self.restaurant_location = {
            "lat": 37.7749,  # San Francisco coordinates  
            "lng": -122.4194,
            "address": "123 Pizza Street, San Francisco, CA"
        }
        
        # Supported delivery areas (simplified for demo)
        self.supported_zip_codes = {
            "94102", "94103", "94104", "94105", "94107", "94108", "94109", 
            "94110", "94111", "94112", "94114", "94115", "94116", "94117",
            "94118", "94121", "94122", "94123", "94124", "94127", "94131"
        }
        
        self.supported_cities = {
            "san francisco", "sf", "san fran"
        }
        
        logger.info("AddressValidator initialized")
    
    def validate_address(self, address_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive address validation.
        
        Args:
            address_data (dict): Address components to validate
            
        Returns:
            dict: Validation result with details
        """
        try:
            logger.debug(f"Validating address: {address_data}")
            
            # Initialize validation result
            result = {
                "is_valid": False,
                "validated_address": {},
                "errors": [],
                "warnings": [],
                "delivery_feasible": False
            }
            
            # Validate required components
            validation_checks = [
                self._validate_street_address(address_data),
                self._validate_city(address_data),
                self._validate_state(address_data),
                self._validate_zip_code(address_data)
            ]
            
            # Collect all errors and warnings
            all_errors = []
            all_warnings = []
            validated_components = {}
            
            for check in validation_checks:
                if not check["is_valid"]:
                    all_errors.extend(check.get("errors", []))
                all_warnings.extend(check.get("warnings", []))
                validated_components.update(check.get("validated_data", {}))
            
            # If basic validation passes, check delivery area
            if not all_errors:
                delivery_check = self._validate_delivery_area(validated_components)
                if not delivery_check["is_valid"]:
                    all_errors.extend(delivery_check.get("errors", []))
                else:
                    result["delivery_feasible"] = True
            
            # Compile final result
            result["is_valid"] = len(all_errors) == 0
            result["errors"] = all_errors
            result["warnings"] = all_warnings
            result["validated_address"] = validated_components
            
            if result["is_valid"]:
                logger.info(f"Address validation successful: {validated_components}")
            else:
                logger.warning(f"Address validation failed: {all_errors}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error validating address: {e}")
            return {
                "is_valid": False,
                "error": f"Validation error: {str(e)}",
                "errors": [str(e)],
                "warnings": [],
                "validated_address": {},
                "delivery_feasible": False
            }
    
    def _validate_street_address(self, address_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate street address component."""
        street = address_data.get("street", "").strip()
        
        if not street:
            return {
                "is_valid": False,
                "errors": ["Street address is required"],
                "validated_data": {}
            }
        
        # Basic street address pattern validation
        street_pattern = r"^\d+\s+[a-zA-Z\s\-\.']+(?:\s+(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|way|court|ct|place|pl|circle|cir)\.?)?$"
        
        if not re.match(street_pattern, street, re.IGNORECASE):
            return {
                "is_valid": False,
                "errors": ["Street address format is invalid. Please include house number and street name."],
                "validated_data": {}
            }
        
        # Standardize street address
        standardized_street = self._standardize_street_address(street)
        
        return {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "validated_data": {"street": standardized_street}
        }
    
    def _validate_city(self, address_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate city component."""
        city = address_data.get("city", "").strip().lower()
        
        if not city:
            # Default to San Francisco for demo
            return {
                "is_valid": True,
                "errors": [],
                "warnings": ["City not provided, defaulting to San Francisco"],
                "validated_data": {"city": "San Francisco"}
            }
        
        # Check if city is in supported delivery area
        if city not in self.supported_cities:
            return {
                "is_valid": False,
                "errors": [f"We don't deliver to {city.title()}. We currently only deliver in San Francisco."],
                "validated_data": {}
            }
        
        return {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "validated_data": {"city": "San Francisco"}
        }
    
    def _validate_state(self, address_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate state component."""
        state = address_data.get("state", "").strip().upper()
        
        if not state:
            # Default to CA for demo
            return {
                "is_valid": True,
                "errors": [],
                "warnings": ["State not provided, defaulting to CA"],
                "validated_data": {"state": "CA"}
            }
        
        # Normalize state format
        state_mappings = {
            "CALIFORNIA": "CA",
            "CALIF": "CA",
            "CAL": "CA"
        }
        
        normalized_state = state_mappings.get(state, state)
        
        if normalized_state != "CA":
            return {
                "is_valid": False,
                "errors": ["We only deliver within California"],
                "validated_data": {}
            }
        
        return {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "validated_data": {"state": "CA"}
        }
    
    def _validate_zip_code(self, address_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate ZIP code component."""
        zip_code = address_data.get("zip", "").strip()
        
        if not zip_code:
            return {
                "is_valid": False,
                "errors": ["ZIP code is required for delivery"],
                "validated_data": {}
            }
        
        # Validate ZIP code format
        zip_pattern = r"^\d{5}(?:-\d{4})?$"
        if not re.match(zip_pattern, zip_code):
            return {
                "is_valid": False,
                "errors": ["ZIP code must be in format 12345 or 12345-6789"],
                "validated_data": {}
            }
        
        # Extract 5-digit ZIP for area checking
        primary_zip = zip_code.split("-")[0]
        
        # Check if ZIP is in delivery area
        if primary_zip not in self.supported_zip_codes:
            return {
                "is_valid": False,
                "errors": [f"ZIP code {primary_zip} is outside our delivery area"],
                "validated_data": {}
            }
        
        return {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "validated_data": {"zip": zip_code}
        }
    
    def _validate_delivery_area(self, address_components: Dict[str, Any]) -> Dict[str, Any]:
        """Validate address is within delivery area."""
        # In a real system, this would use geocoding and distance calculation
        # For demo, we use ZIP code validation as proxy
        
        zip_code = address_components.get("zip", "").split("-")[0]
        
        if zip_code in self.supported_zip_codes:
            return {
                "is_valid": True,
                "errors": [],
                "delivery_distance": 2.5  # Mock distance
            }
        else:
            return {
                "is_valid": False,
                "errors": ["Address is outside our delivery area"],
                "delivery_distance": None
            }
    
    def _standardize_street_address(self, street: str) -> str:
        """Standardize street address format."""
        # Basic standardization rules
        standardized = street.strip().title()
        
        # Standardize common abbreviations
        abbreviations = {
            " St.": " Street",
            " St ": " Street ",
            " Ave.": " Avenue", 
            " Ave ": " Avenue ",
            " Rd.": " Road",
            " Rd ": " Road ",
            " Dr.": " Drive",
            " Dr ": " Drive ",
            " Ln.": " Lane",
            " Ln ": " Lane ",
            " Blvd.": " Boulevard",
            " Blvd ": " Boulevard "
        }
        
        for abbrev, full in abbreviations.items():
            standardized = standardized.replace(abbrev, full)
        
        return standardized


# Export main class
__all__ = ["AddressValidator"]