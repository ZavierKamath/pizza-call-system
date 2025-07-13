"""
Address validation for delivery orders with Google Maps integration.
Validates delivery addresses, performs geocoding, and checks delivery area coverage.
"""

import logging
import re
import asyncio
import aiohttp
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import math

from ..config.settings import settings
from ..database.redis_client import get_redis_async

# Configure logging
logger = logging.getLogger(__name__)


class AddressValidator:
    """
    Validates delivery addresses for pizza orders with Google Maps integration.
    
    Performs address validation, geocoding, delivery area checking,
    and address standardization using Google Maps Geocoding API.
    """
    
    def __init__(self):
        """Initialize address validator with Google Maps configuration."""
        self.google_maps_api_key = settings.google_maps_api_key
        self.delivery_radius_miles = settings.delivery_radius_miles  # 5 miles from settings
        self.restaurant_address = settings.restaurant_address
        
        # Google Maps API endpoints
        self.geocoding_url = "https://maps.googleapis.com/maps/api/geocode/json"
        
        # Cache configuration
        self.cache_ttl_hours = 24  # Cache geocoding results for 24 hours
        
        # Restaurant location (will be geocoded on first use)
        self._restaurant_coordinates = None
        
        # Rate limiting
        self.max_requests_per_second = 10
        self._last_request_time = 0
        
        logger.info(f"AddressValidator initialized with {self.delivery_radius_miles}-mile delivery radius")
    
    async def validate_address(self, address_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive address validation with Google Maps geocoding.
        
        Args:
            address_data (dict): Address components to validate
            
        Returns:
            dict: Validation result with geocoding and distance information
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
                "delivery_feasible": False,
                "errors": [],
                "warnings": [],
                "suggestions": []
            }
            
            # Parse and format address string
            address_string = self._format_address_string(address_data)
            if not address_string:
                result["errors"].append("Address information is incomplete")
                return result
            
            # Check cache first
            cached_result = await self._get_cached_validation(address_string)
            if cached_result:
                logger.debug(f"Using cached validation for: {address_string}")
                return cached_result
            
            # Geocode the address using Google Maps
            geocoding_result = await self._geocode_address(address_string)
            if not geocoding_result["success"]:
                result["errors"].extend(geocoding_result["errors"])
                
                # Try to provide suggestions for partial matches
                if geocoding_result.get("partial_matches"):
                    result["suggestions"] = geocoding_result["partial_matches"]
                    result["warnings"].append("Address could not be found exactly. Check suggestions below.")
                
                return result
            
            # Extract geocoding information
            geocoded_data = geocoding_result["data"]
            result["validated_address"] = geocoded_data["address_components"]
            result["standardized_address"] = geocoded_data["formatted_address"]
            result["coordinates"] = geocoded_data["coordinates"]
            
            # Validate delivery area
            delivery_check = await self._validate_delivery_distance(geocoded_data["coordinates"])
            result["delivery_distance_miles"] = delivery_check["distance_miles"]
            result["delivery_feasible"] = delivery_check["within_range"]
            
            if not delivery_check["within_range"]:
                result["errors"].append(
                    f"Address is {delivery_check['distance_miles']:.1f} miles away. "
                    f"We only deliver within {self.delivery_radius_miles} miles of our restaurant."
                )
            else:
                result["is_valid"] = True
                result["warnings"].append(
                    f"Delivery distance: {delivery_check['distance_miles']:.1f} miles"
                )
            
            # Cache the result for future use
            await self._cache_validation_result(address_string, result)
            
            if result["is_valid"]:
                logger.info(f"Address validation successful: {result['standardized_address']}")
            else:
                logger.warning(f"Address validation failed: {result['errors']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error validating address: {e}")
            return {
                "is_valid": False,
                "error": f"Validation error: {str(e)}",
                "errors": [f"Address validation failed: {str(e)}"],
                "warnings": [],
                "validated_address": {},
                "standardized_address": "",
                "coordinates": None,
                "delivery_distance_miles": None,
                "delivery_feasible": False,
                "suggestions": []
            }
    
    async def _geocode_address(self, address: str) -> Dict[str, Any]:
        """
        Geocode address using Google Maps Geocoding API.
        
        Args:
            address (str): Address string to geocode
            
        Returns:
            dict: Geocoding result with coordinates and address components
        """
        try:
            # Rate limiting
            await self._rate_limit()
            
            # Prepare API request
            params = {
                "address": address,
                "key": self.google_maps_api_key,
                "region": "us",  # Bias to US addresses
                "language": "en"
            }
            
            # Make API request
            async with aiohttp.ClientSession() as session:
                async with session.get(self.geocoding_url, params=params) as response:
                    if response.status != 200:
                        return {
                            "success": False,
                            "errors": [f"Google Maps API returned status {response.status}"]
                        }
                    
                    data = await response.json()
            
            # Parse API response
            if data["status"] != "OK":
                if data["status"] == "ZERO_RESULTS":
                    return {
                        "success": False,
                        "errors": ["Address not found. Please check the address and try again."]
                    }
                elif data["status"] == "OVER_QUERY_LIMIT":
                    return {
                        "success": False,
                        "errors": ["Address validation temporarily unavailable. Please try again later."]
                    }
                else:
                    return {
                        "success": False,
                        "errors": [f"Address validation failed: {data.get('error_message', data['status'])}"]
                    }
            
            # Extract the best result
            if not data.get("results"):
                return {
                    "success": False,
                    "errors": ["No address results found"]
                }
            
            best_result = data["results"][0]
            
            # Parse address components
            address_components = self._parse_address_components(best_result["address_components"])
            
            # Extract coordinates
            location = best_result["geometry"]["location"]
            coordinates = {
                "latitude": location["lat"],
                "longitude": location["lng"]
            }
            
            # Check for partial matches and provide alternatives
            partial_matches = []
            if len(data["results"]) > 1:
                for result in data["results"][1:4]:  # Up to 3 alternatives
                    partial_matches.append({
                        "address": result["formatted_address"],
                        "confidence": "partial_match"
                    })
            
            return {
                "success": True,
                "data": {
                    "formatted_address": best_result["formatted_address"],
                    "address_components": address_components,
                    "coordinates": coordinates,
                    "place_id": best_result.get("place_id"),
                    "location_type": best_result["geometry"].get("location_type", "APPROXIMATE")
                },
                "partial_matches": partial_matches
            }
            
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error during geocoding: {e}")
            return {
                "success": False,
                "errors": ["Network error during address validation. Please try again."]
            }
        except Exception as e:
            logger.error(f"Error during geocoding: {e}")
            return {
                "success": False,
                "errors": ["Address validation error. Please try again."]
            }
    
    async def _validate_delivery_distance(self, address_coordinates: Dict[str, float]) -> Dict[str, Any]:
        """
        Check if address is within delivery radius using precise distance calculation.
        
        Args:
            address_coordinates (dict): Target address coordinates
            
        Returns:
            dict: Distance validation result
        """
        try:
            # Get restaurant coordinates
            restaurant_coords = await self._get_restaurant_coordinates()
            if not restaurant_coords:
                # Fallback: assume delivery is possible if we can't get restaurant location
                logger.warning("Could not determine restaurant coordinates for distance calculation")
                return {
                    "within_range": True,
                    "distance_miles": 0.0,
                    "calculation_method": "fallback"
                }
            
            # Calculate distance using Haversine formula
            distance_miles = self._calculate_haversine_distance(
                restaurant_coords["latitude"], restaurant_coords["longitude"],
                address_coordinates["latitude"], address_coordinates["longitude"]
            )
            
            within_range = distance_miles <= self.delivery_radius_miles
            
            logger.debug(
                f"Distance calculation: {distance_miles:.2f} miles "
                f"(limit: {self.delivery_radius_miles} miles, within_range: {within_range})"
            )
            
            return {
                "within_range": within_range,
                "distance_miles": round(distance_miles, 2),
                "calculation_method": "haversine"
            }
            
        except Exception as e:
            logger.error(f"Error calculating delivery distance: {e}")
            # Fallback: allow delivery on error
            return {
                "within_range": True,
                "distance_miles": 0.0,
                "calculation_method": "error_fallback"
            }
    
    async def _get_restaurant_coordinates(self) -> Optional[Dict[str, float]]:
        """
        Get restaurant coordinates, geocoding if necessary.
        
        Returns:
            dict: Restaurant coordinates or None if failed
        """
        if self._restaurant_coordinates:
            return self._restaurant_coordinates
        
        try:
            # Check cache first
            redis_client = await get_redis_async()
            cache_key = f"restaurant_coordinates:{hash(self.restaurant_address)}"
            
            with redis_client.get_connection() as conn:
                cached_coords = conn.get(cache_key)
                if cached_coords:
                    self._restaurant_coordinates = json.loads(cached_coords)
                    return self._restaurant_coordinates
            
            # Geocode restaurant address
            geocoding_result = await self._geocode_address(self.restaurant_address)
            if geocoding_result["success"]:
                coords = geocoding_result["data"]["coordinates"]
                self._restaurant_coordinates = coords
                
                # Cache restaurant coordinates (long TTL since address is unlikely to change)
                with redis_client.get_connection() as conn:
                    conn.setex(cache_key, 7 * 24 * 3600, json.dumps(coords))  # 7 days
                
                logger.info(f"Restaurant coordinates geocoded: {coords}")
                return coords
            else:
                logger.error(f"Failed to geocode restaurant address: {geocoding_result['errors']}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting restaurant coordinates: {e}")
            return None
    
    def _calculate_haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points using Haversine formula.
        
        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates
            
        Returns:
            float: Distance in miles
        """
        # Convert latitude and longitude from degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Radius of earth in miles
        earth_radius_miles = 3959
        
        # Calculate the result
        distance = earth_radius_miles * c
        return distance
    
    def _parse_address_components(self, components: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Parse Google Maps address components into standardized format.
        
        Args:
            components (list): Google Maps address components
            
        Returns:
            dict: Parsed address components
        """
        parsed = {
            "street_number": "",
            "route": "",
            "street_address": "",
            "city": "",
            "state": "",
            "state_code": "",
            "zip_code": "",
            "country": "",
            "country_code": ""
        }
        
        for component in components:
            types = component["types"]
            long_name = component["long_name"]
            short_name = component["short_name"]
            
            if "street_number" in types:
                parsed["street_number"] = long_name
            elif "route" in types:
                parsed["route"] = long_name
            elif "locality" in types:
                parsed["city"] = long_name
            elif "administrative_area_level_1" in types:
                parsed["state"] = long_name
                parsed["state_code"] = short_name
            elif "postal_code" in types:
                parsed["zip_code"] = long_name
            elif "country" in types:
                parsed["country"] = long_name
                parsed["country_code"] = short_name
        
        # Combine street number and route for full street address
        if parsed["street_number"] and parsed["route"]:
            parsed["street_address"] = f"{parsed['street_number']} {parsed['route']}"
        elif parsed["route"]:
            parsed["street_address"] = parsed["route"]
        
        return parsed
    
    def _format_address_string(self, address_data: Dict[str, Any]) -> str:
        """
        Format address components into a single geocodable string.
        
        Args:
            address_data (dict): Address components
            
        Returns:
            str: Formatted address string
        """
        # Handle different input formats
        if isinstance(address_data, str):
            return address_data.strip()
        
        if not isinstance(address_data, dict):
            return ""
        
        # Extract components with various possible keys
        street = address_data.get("street") or address_data.get("street_address") or address_data.get("address") or ""
        city = address_data.get("city") or ""
        state = address_data.get("state") or address_data.get("state_code") or ""
        zip_code = address_data.get("zip") or address_data.get("zip_code") or address_data.get("postal_code") or ""
        
        # Build address string
        parts = []
        if street.strip():
            parts.append(street.strip())
        if city.strip():
            parts.append(city.strip())
        if state.strip():
            parts.append(state.strip())
        if zip_code.strip():
            parts.append(zip_code.strip())
        
        return ", ".join(parts)
    
    async def _rate_limit(self) -> None:
        """Apply rate limiting for Google Maps API requests."""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_request_time
        min_interval = 1.0 / self.max_requests_per_second
        
        if time_since_last < min_interval:
            await asyncio.sleep(min_interval - time_since_last)
        
        self._last_request_time = asyncio.get_event_loop().time()
    
    async def _get_cached_validation(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get cached validation result for address.
        
        Args:
            address (str): Address string
            
        Returns:
            dict: Cached result or None
        """
        try:
            redis_client = await get_redis_async()
            cache_key = f"address_validation:{hash(address)}"
            
            with redis_client.get_connection() as conn:
                cached_data = conn.get(cache_key)
                if cached_data:
                    result = json.loads(cached_data)
                    logger.debug(f"Cache hit for address validation: {address}")
                    return result
            
            return None
            
        except Exception as e:
            logger.warning(f"Error accessing validation cache: {e}")
            return None
    
    async def _cache_validation_result(self, address: str, result: Dict[str, Any]) -> None:
        """
        Cache validation result for future use.
        
        Args:
            address (str): Address string
            result (dict): Validation result
        """
        try:
            redis_client = await get_redis_async()
            cache_key = f"address_validation:{hash(address)}"
            ttl_seconds = self.cache_ttl_hours * 3600
            
            # Only cache successful validations
            if result.get("is_valid") or result.get("suggestions"):
                with redis_client.get_connection() as conn:
                    conn.setex(cache_key, ttl_seconds, json.dumps(result))
                logger.debug(f"Cached validation result for: {address}")
            
        except Exception as e:
            logger.warning(f"Error caching validation result: {e}")
    
    async def suggest_address_corrections(self, partial_address: str) -> List[Dict[str, Any]]:
        """
        Suggest address corrections for partial or incorrect addresses.
        
        Args:
            partial_address (str): Partial or incorrect address
            
        Returns:
            list: List of suggested address corrections
        """
        try:
            geocoding_result = await self._geocode_address(partial_address)
            
            suggestions = []
            if geocoding_result.get("partial_matches"):
                for match in geocoding_result["partial_matches"]:
                    suggestions.append({
                        "address": match["address"],
                        "confidence": match["confidence"],
                        "type": "partial_match"
                    })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error generating address suggestions: {e}")
            return []
    
    async def validate_delivery_feasibility(self, address: str) -> Dict[str, Any]:
        """
        Quick check if delivery is feasible to an address without full validation.
        
        Args:
            address (str): Address string
            
        Returns:
            dict: Feasibility check result
        """
        try:
            # Quick geocoding check
            geocoding_result = await self._geocode_address(address)
            if not geocoding_result["success"]:
                return {
                    "feasible": False,
                    "reason": "Address not found",
                    "distance_miles": None
                }
            
            # Distance check
            coords = geocoding_result["data"]["coordinates"]
            distance_check = await self._validate_delivery_distance(coords)
            
            return {
                "feasible": distance_check["within_range"],
                "reason": "Within delivery range" if distance_check["within_range"] else "Outside delivery range",
                "distance_miles": distance_check["distance_miles"]
            }
            
        except Exception as e:
            logger.error(f"Error checking delivery feasibility: {e}")
            return {
                "feasible": False,
                "reason": "Validation error",
                "distance_miles": None
            }


# Create global validator instance
address_validator = AddressValidator()


# Utility functions for integration
async def validate_address(address_data: Dict[str, Any]) -> Dict[str, Any]:
    """Utility function for address validation."""
    return await address_validator.validate_address(address_data)


async def check_delivery_feasibility(address: str) -> Dict[str, Any]:
    """Utility function for delivery feasibility check."""
    return await address_validator.validate_delivery_feasibility(address)


async def get_address_suggestions(partial_address: str) -> List[Dict[str, Any]]:
    """Utility function for address suggestions."""
    return await address_validator.suggest_address_corrections(partial_address)


# Export main components
__all__ = ["AddressValidator", "address_validator", "validate_address", "check_delivery_feasibility", "get_address_suggestions"]