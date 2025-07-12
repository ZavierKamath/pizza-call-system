"""
Delivery time estimation logic for the pizza ordering system.
Calculates realistic delivery times based on distance, current load, and other factors.
"""

import random
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import math

# Configure logging
logger = logging.getLogger(__name__)


class DeliveryEstimator:
    """
    Handles delivery time estimation with realistic calculations.
    
    Based on PRD requirements:
    - Base preparation time: 25 minutes
    - Distance calculation: 2 minutes per mile
    - Current load: 3 minutes per pending order
    - Random variation: -5 to +10 minutes
    """
    
    def __init__(self):
        """Initialize delivery estimator with default parameters."""
        self.base_preparation_time = 25  # minutes
        self.minutes_per_mile = 2
        self.minutes_per_order = 3
        self.random_min = -5
        self.random_max = 10
        self.minimum_delivery_time = 15  # Never less than 15 minutes
        self.maximum_delivery_radius = 5  # miles
        
        # Mock restaurant location (would be configurable in real system)
        self.restaurant_location = {
            "lat": 37.7749,  # San Francisco coordinates
            "lng": -122.4194,
            "address": "123 Pizza Street, San Francisco, CA"
        }
        
        logger.info("DeliveryEstimator initialized")
    
    def estimate_delivery_time(self, delivery_address: Dict[str, Any], 
                             current_orders: int = 0) -> int:
        """
        Calculate estimated delivery time for an address.
        
        Args:
            delivery_address (dict): Customer delivery address
            current_orders (int): Number of current pending orders
            
        Returns:
            int: Estimated delivery time in minutes
        """
        try:
            logger.debug(f"Estimating delivery time for address: {delivery_address}")
            
            # Calculate distance to delivery address
            distance_miles = self._calculate_distance_to_address(delivery_address)
            
            # Apply delivery time formula from PRD
            base_time = self.base_preparation_time
            distance_factor = distance_miles * self.minutes_per_mile
            load_factor = current_orders * self.minutes_per_order
            random_variation = random.randint(self.random_min, self.random_max)
            
            # Calculate total time
            total_time = base_time + distance_factor + load_factor + random_variation
            
            # Apply minimum time constraint
            estimated_time = max(self.minimum_delivery_time, int(total_time))
            
            logger.info(f"Delivery estimate: {estimated_time} minutes "
                       f"(base: {base_time}, distance: {distance_factor:.1f}, "
                       f"load: {load_factor}, variation: {random_variation})")
            
            return estimated_time
            
        except Exception as e:
            logger.error(f"Error estimating delivery time: {e}")
            # Return default estimate on error
            return 35
    
    def _calculate_distance_to_address(self, delivery_address: Dict[str, Any]) -> float:
        """
        Calculate distance from restaurant to delivery address.
        
        Args:
            delivery_address (dict): Customer delivery address
            
        Returns:
            float: Distance in miles
        """
        try:
            # In a real system, you would:
            # 1. Geocode the delivery address to get lat/lng
            # 2. Use proper distance calculation (Google Maps API, etc.)
            # 3. Account for actual driving routes, not just straight-line distance
            
            # For demo purposes, we'll estimate based on address components
            distance = self._estimate_distance_from_address_string(delivery_address)
            
            # Ensure distance is within delivery radius
            if distance > self.maximum_delivery_radius:
                logger.warning(f"Address appears to be outside delivery radius: {distance} miles")
                # In real system, this would trigger an "outside delivery area" error
            
            return min(distance, self.maximum_delivery_radius)
            
        except Exception as e:
            logger.error(f"Error calculating distance: {e}")
            # Return default distance on error
            return 2.5
    
    def _estimate_distance_from_address_string(self, delivery_address: Dict[str, Any]) -> float:
        """
        Estimate distance based on address components (demo implementation).
        
        Args:
            delivery_address (dict): Address information
            
        Returns:
            float: Estimated distance in miles
        """
        # This is a simplified estimation for demo purposes
        # In production, use proper geocoding and routing APIs
        
        street = delivery_address.get("street", "").lower()
        city = delivery_address.get("city", "").lower()
        zip_code = delivery_address.get("zip", "")
        
        # Mock distance calculation based on simple heuristics
        base_distance = 2.0  # Default 2 miles
        
        # Adjust based on street number (higher numbers = farther)
        try:
            street_number = int(street.split()[0]) if street.split() and street.split()[0].isdigit() else 1000
            # Normalize street number to distance factor
            distance_factor = min(street_number / 1000, 3.0)  # Max 3x multiplier
            base_distance *= distance_factor
        except (ValueError, IndexError):
            pass
        
        # Adjust based on zip code patterns (very simplified)
        if zip_code:
            try:
                zip_int = int(zip_code[:5])
                # Simple zip-based distance estimation
                if zip_int % 1000 > 500:
                    base_distance *= 1.3
            except ValueError:
                pass
        
        # Add some randomness for realism
        variation = random.uniform(0.8, 1.2)
        estimated_distance = base_distance * variation
        
        # Round to reasonable precision
        return round(estimated_distance, 1)
    
    def get_delivery_time_breakdown(self, delivery_address: Dict[str, Any], 
                                  current_orders: int = 0) -> Dict[str, Any]:
        """
        Get detailed breakdown of delivery time calculation.
        
        Args:
            delivery_address (dict): Customer delivery address
            current_orders (int): Number of current pending orders
            
        Returns:
            dict: Detailed breakdown of time calculation
        """
        try:
            distance_miles = self._calculate_distance_to_address(delivery_address)
            
            base_time = self.base_preparation_time
            distance_factor = distance_miles * self.minutes_per_mile
            load_factor = current_orders * self.minutes_per_order
            random_variation = random.randint(self.random_min, self.random_max)
            
            raw_total = base_time + distance_factor + load_factor + random_variation
            final_time = max(self.minimum_delivery_time, int(raw_total))
            
            return {
                "estimated_time": final_time,
                "breakdown": {
                    "preparation_time": base_time,
                    "distance_miles": distance_miles,
                    "distance_time": distance_factor,
                    "current_orders": current_orders,
                    "load_time": load_factor,
                    "random_variation": random_variation,
                    "raw_total": raw_total,
                    "minimum_applied": final_time > raw_total
                },
                "delivery_feasible": distance_miles <= self.maximum_delivery_radius
            }
            
        except Exception as e:
            logger.error(f"Error getting delivery breakdown: {e}")
            return {
                "estimated_time": 35,
                "breakdown": {"error": str(e)},
                "delivery_feasible": True
            }
    
    def validate_delivery_address(self, delivery_address: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate if address is within delivery area.
        
        Args:
            delivery_address (dict): Customer delivery address
            
        Returns:
            dict: Validation result with delivery feasibility
        """
        try:
            distance = self._calculate_distance_to_address(delivery_address)
            
            is_deliverable = distance <= self.maximum_delivery_radius
            
            result = {
                "is_valid": is_deliverable,
                "distance_miles": distance,
                "max_distance": self.maximum_delivery_radius,
                "estimated_time": self.estimate_delivery_time(delivery_address) if is_deliverable else None
            }
            
            if not is_deliverable:
                result["error"] = f"Address is {distance:.1f} miles away, outside our {self.maximum_delivery_radius}-mile delivery radius"
                result["suggested_fix"] = "Please provide an address within our delivery area"
            
            return result
            
        except Exception as e:
            logger.error(f"Error validating delivery address: {e}")
            return {
                "is_valid": False,
                "error": f"Unable to validate address: {str(e)}",
                "suggested_fix": "Please provide a complete, valid address"
            }
    
    def get_delivery_windows(self) -> Dict[str, Any]:
        """
        Get available delivery time windows and current capacity.
        
        Returns:
            dict: Information about delivery capacity and timing
        """
        current_time = datetime.now()
        current_hour = current_time.hour
        
        # Simulate different delivery speeds based on time of day
        if 11 <= current_hour <= 13:  # Lunch rush
            rush_factor = 1.3
            capacity_usage = 0.8
        elif 17 <= current_hour <= 20:  # Dinner rush
            rush_factor = 1.5
            capacity_usage = 0.9
        else:  # Normal hours
            rush_factor = 1.0
            capacity_usage = 0.4
        
        return {
            "current_time": current_time.strftime("%H:%M"),
            "rush_factor": rush_factor,
            "capacity_usage": capacity_usage,
            "estimated_delay": int((capacity_usage - 0.5) * 20) if capacity_usage > 0.5 else 0,
            "next_available_slot": "Immediate" if capacity_usage < 0.8 else f"{int(capacity_usage * 30)} minutes"
        }
    
    def update_delivery_parameters(self, **kwargs) -> None:
        """
        Update delivery estimation parameters.
        
        Args:
            **kwargs: Parameters to update (base_time, minutes_per_mile, etc.)
        """
        for param, value in kwargs.items():
            if hasattr(self, param):
                old_value = getattr(self, param)
                setattr(self, param, value)
                logger.info(f"Updated {param}: {old_value} -> {value}")
            else:
                logger.warning(f"Unknown parameter: {param}")


# Helper functions for external use

def quick_delivery_estimate(address_dict: Dict[str, Any], orders_count: int = 0) -> int:
    """
    Quick delivery time estimate without creating DeliveryEstimator instance.
    
    Args:
        address_dict (dict): Delivery address
        orders_count (int): Current orders in queue
        
    Returns:
        int: Estimated delivery time in minutes
    """
    estimator = DeliveryEstimator()
    return estimator.estimate_delivery_time(address_dict, orders_count)


def is_address_deliverable(address_dict: Dict[str, Any]) -> bool:
    """
    Quick check if address is within delivery range.
    
    Args:
        address_dict (dict): Delivery address
        
    Returns:
        bool: True if address is deliverable
    """
    estimator = DeliveryEstimator()
    result = estimator.validate_delivery_address(address_dict)
    return result["is_valid"]


# Export main components
__all__ = [
    "DeliveryEstimator",
    "quick_delivery_estimate", 
    "is_address_deliverable"
]