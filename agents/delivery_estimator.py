"""
Intelligent delivery time estimation system.
Calculates realistic delivery times based on distance, current load, and randomization factors.
"""

import logging
import asyncio
import random
import math
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

import googlemaps
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

from ..database import get_db_session
from ..database.models import Order, OrderStatus, ActiveSession
from ..database.redis_client import get_redis_async
from ..config.settings import settings
from ..config.logging_config import get_logger

# Configure logging
logger = get_logger(__name__)

# Import performance monitoring (avoid circular imports)
try:
    from ..monitoring.delivery_performance import delivery_performance_monitor
except ImportError:
    delivery_performance_monitor = None
    logger.warning("Performance monitoring not available")


class DeliveryZone(Enum):
    """Delivery zone classifications for time estimation."""
    INNER_ZONE = "inner"  # 0-2 miles
    MIDDLE_ZONE = "middle"  # 2-5 miles
    OUTER_ZONE = "outer"  # 5+ miles


@dataclass
class DeliveryEstimate:
    """Delivery time estimation result."""
    estimated_minutes: int
    distance_miles: float
    base_time_minutes: int
    distance_time_minutes: int
    load_time_minutes: int
    random_variation_minutes: int
    confidence_score: float  # 0.0 to 1.0
    zone: DeliveryZone
    created_at: datetime
    factors: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert estimate to dictionary for storage/API response."""
        return {
            "estimated_minutes": self.estimated_minutes,
            "distance_miles": self.distance_miles,
            "base_time_minutes": self.base_time_minutes,
            "distance_time_minutes": self.distance_time_minutes,
            "load_time_minutes": self.load_time_minutes,
            "random_variation_minutes": self.random_variation_minutes,
            "confidence_score": self.confidence_score,
            "zone": self.zone.value,
            "created_at": self.created_at.isoformat(),
            "factors": self.factors
        }


class GoogleMapsClient:
    """
    Google Maps API client for distance and travel time calculations.
    Handles geocoding, distance matrix, and caching for performance.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Google Maps client with API key."""
        self.api_key = api_key or getattr(settings, 'google_maps_api_key', None)
        
        if self.api_key:
            self.gmaps = googlemaps.Client(key=self.api_key)
            logger.info("Google Maps client initialized successfully")
        else:
            self.gmaps = None
            logger.warning("Google Maps API key not provided - using fallback calculations")
        
        # Fallback geocoder for when Google Maps is unavailable
        self.fallback_geocoder = Nominatim(user_agent="pizza_delivery_estimator")
        
        # Cache settings
        self.distance_cache_ttl = 3600  # 1 hour cache for distances
        self.geocode_cache_ttl = 86400  # 24 hour cache for geocoding
        
        # Restaurant location (configurable)
        self.restaurant_location = getattr(settings, 'restaurant_location', {
            'address': '123 Main St, Anytown, USA',
            'lat': 40.7128,
            'lng': -74.0060
        })
    
    async def calculate_distance_and_time(
        self, 
        delivery_address: str
    ) -> Tuple[float, int, float]:
        """
        Calculate distance and estimated travel time to delivery address.
        
        Args:
            delivery_address (str): Customer delivery address
            
        Returns:
            tuple: (distance_miles, travel_time_minutes, confidence_score)
        """
        try:
            # Check cache first
            cached_result = await self._get_cached_distance(delivery_address)
            if cached_result:
                logger.debug(f"Using cached distance for {delivery_address}")
                return cached_result
            
            # Calculate using Google Maps if available
            if self.gmaps:
                distance, travel_time, confidence = await self._calculate_with_google_maps(delivery_address)
            else:
                distance, travel_time, confidence = await self._calculate_with_fallback(delivery_address)
            
            # Cache the result
            await self._cache_distance_result(delivery_address, distance, travel_time, confidence)
            
            logger.info(f"Calculated distance to {delivery_address}: {distance:.2f} miles, {travel_time} minutes")
            
            return distance, travel_time, confidence
            
        except Exception as e:
            logger.error(f"Error calculating distance to {delivery_address}: {e}")
            
            # Return conservative estimate on error
            return 3.0, 15, 0.3  # 3 miles, 15 minutes, low confidence
    
    async def _calculate_with_google_maps(self, delivery_address: str) -> Tuple[float, int, float]:
        """Calculate distance using Google Maps Distance Matrix API."""
        try:
            # Get distance matrix
            result = self.gmaps.distance_matrix(
                origins=[self.restaurant_location['address']],
                destinations=[delivery_address],
                mode="driving",
                units="imperial",
                departure_time="now",
                traffic_model="best_guess"
            )
            
            if result['status'] == 'OK':
                element = result['rows'][0]['elements'][0]
                
                if element['status'] == 'OK':
                    # Extract distance in miles
                    distance_text = element['distance']['text']
                    distance_miles = element['distance']['value'] * 0.000621371  # meters to miles
                    
                    # Extract duration in minutes
                    duration_seconds = element['duration']['value']
                    travel_time_minutes = int(duration_seconds / 60)
                    
                    # Use traffic duration if available
                    if 'duration_in_traffic' in element:
                        traffic_duration = element['duration_in_traffic']['value']
                        travel_time_minutes = int(traffic_duration / 60)
                    
                    logger.debug(f"Google Maps result: {distance_miles:.2f} miles, {travel_time_minutes} min")
                    
                    return distance_miles, travel_time_minutes, 0.9  # High confidence
                    
            # Fall back to geocoding if distance matrix fails
            return await self._calculate_with_geocoding(delivery_address)
            
        except Exception as e:
            logger.warning(f"Google Maps API error: {e}")
            return await self._calculate_with_geocoding(delivery_address)
    
    async def _calculate_with_geocoding(self, delivery_address: str) -> Tuple[float, int, float]:
        """Calculate distance using geocoding and straight-line distance."""
        try:
            # Geocode the delivery address
            geocode_result = self.gmaps.geocode(delivery_address)
            
            if geocode_result:
                delivery_location = geocode_result[0]['geometry']['location']
                
                # Calculate straight-line distance
                restaurant_coords = (
                    self.restaurant_location['lat'], 
                    self.restaurant_location['lng']
                )
                delivery_coords = (
                    delivery_location['lat'], 
                    delivery_location['lng']
                )
                
                straight_distance = geodesic(restaurant_coords, delivery_coords).miles
                
                # Apply road distance factor (typically 1.3x straight line)
                road_distance = straight_distance * 1.3
                
                # Estimate travel time (assume 25 mph average in city)
                travel_time_minutes = int((road_distance / 25.0) * 60)
                
                logger.debug(f"Geocoding result: {road_distance:.2f} miles, {travel_time_minutes} min")
                
                return road_distance, travel_time_minutes, 0.7  # Medium confidence
                
        except Exception as e:
            logger.warning(f"Geocoding error: {e}")
        
        # Fallback to basic calculation
        return await self._calculate_with_fallback(delivery_address)
    
    async def _calculate_with_fallback(self, delivery_address: str) -> Tuple[float, int, float]:
        """Fallback distance calculation using basic geocoding."""
        try:
            # Use Nominatim for basic geocoding
            location = self.fallback_geocoder.geocode(delivery_address)
            
            if location:
                restaurant_coords = (
                    self.restaurant_location['lat'], 
                    self.restaurant_location['lng']
                )
                delivery_coords = (location.latitude, location.longitude)
                
                straight_distance = geodesic(restaurant_coords, delivery_coords).miles
                road_distance = straight_distance * 1.4  # Higher factor for fallback
                travel_time_minutes = int((road_distance / 20.0) * 60)  # Assume slower city driving
                
                logger.debug(f"Fallback calculation: {road_distance:.2f} miles, {travel_time_minutes} min")
                
                return road_distance, travel_time_minutes, 0.5  # Lower confidence
                
        except Exception as e:
            logger.warning(f"Fallback geocoding error: {e}")
        
        # Last resort: estimate based on address characteristics
        return self._estimate_from_address_text(delivery_address)
    
    def _estimate_from_address_text(self, delivery_address: str) -> Tuple[float, int, float]:
        """Estimate distance from address text analysis."""
        try:
            address_lower = delivery_address.lower()
            
            # Look for distance indicators in address
            if any(word in address_lower for word in ['downtown', 'center', 'main st']):
                return 1.5, 8, 0.3  # Close to downtown
            elif any(word in address_lower for word in ['suburb', 'heights', 'hills']):
                return 4.0, 20, 0.3  # Suburban area
            elif any(word in address_lower for word in ['county', 'rural', 'rd']):
                return 6.0, 30, 0.3  # Rural/county area
            else:
                return 3.0, 15, 0.2  # Default estimate
                
        except Exception as e:
            logger.warning(f"Address text estimation error: {e}")
            return 3.0, 15, 0.1  # Very low confidence default
    
    async def _get_cached_distance(self, delivery_address: str) -> Optional[Tuple[float, int, float]]:
        """Get cached distance calculation if available."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"distance_cache:{hash(delivery_address.lower())}"
            
            with redis_client.get_connection() as conn:
                cached_data = conn.get(cache_key)
                if cached_data:
                    # Parse cached data (simplified - in real implementation use JSON)
                    parts = cached_data.decode().split(',')
                    return float(parts[0]), int(parts[1]), float(parts[2])
                    
        except Exception as e:
            logger.warning(f"Error retrieving cached distance: {e}")
        
        return None
    
    async def _cache_distance_result(
        self, 
        delivery_address: str, 
        distance: float, 
        travel_time: int, 
        confidence: float
    ):
        """Cache distance calculation result."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"distance_cache:{hash(delivery_address.lower())}"
            cache_value = f"{distance},{travel_time},{confidence}"
            
            with redis_client.get_connection() as conn:
                conn.setex(cache_key, self.distance_cache_ttl, cache_value)
                
        except Exception as e:
            logger.warning(f"Error caching distance result: {e}")


class LoadCalculator:
    """
    Calculate current delivery load and queue factors.
    Analyzes active orders to determine delivery time impact.
    """
    
    def __init__(self):
        """Initialize load calculator."""
        self.max_concurrent_deliveries = getattr(settings, 'max_concurrent_deliveries', 4)
        self.preparation_time_minutes = getattr(settings, 'average_preparation_time', 15)
        
    async def calculate_current_load(self) -> Dict[str, Any]:
        """
        Calculate current delivery load factors.
        
        Returns:
            dict: Load analysis including order count, queue time, capacity
        """
        try:
            async with get_db_session() as session:
                # Get orders currently in preparation or out for delivery
                active_orders = session.query(Order).filter(
                    Order.order_status.in_([
                        OrderStatus.PREPARING.value,
                        OrderStatus.OUT_FOR_DELIVERY.value,
                        OrderStatus.PAYMENT_CONFIRMED.value
                    ])
                ).all()
                
                # Get orders awaiting preparation
                pending_orders = session.query(Order).filter(
                    Order.order_status == OrderStatus.PENDING.value
                ).all()
                
                total_active = len(active_orders)
                total_pending = len(pending_orders)
                
                # Calculate queue position impact
                queue_time = self._calculate_queue_time(total_active, total_pending)
                
                # Calculate capacity utilization
                capacity_utilization = min(total_active / self.max_concurrent_deliveries, 1.0)
                
                # Calculate load factor for time estimation
                load_factor_minutes = total_active * 3  # 3 minutes per active order as per PRD
                
                load_analysis = {
                    "active_orders": total_active,
                    "pending_orders": total_pending,
                    "queue_time_minutes": queue_time,
                    "capacity_utilization": capacity_utilization,
                    "load_factor_minutes": load_factor_minutes,
                    "max_capacity": self.max_concurrent_deliveries,
                    "is_at_capacity": total_active >= self.max_concurrent_deliveries,
                    "estimated_queue_position": total_pending + 1
                }
                
                logger.debug(f"Current load: {total_active} active, {total_pending} pending, {queue_time}min queue")
                
                return load_analysis
                
        except Exception as e:
            logger.error(f"Error calculating current load: {e}")
            
            # Return conservative estimate on error
            return {
                "active_orders": 2,
                "pending_orders": 1,
                "queue_time_minutes": 10,
                "capacity_utilization": 0.5,
                "load_factor_minutes": 6,  # 2 active orders * 3 minutes
                "max_capacity": self.max_concurrent_deliveries,
                "is_at_capacity": False,
                "estimated_queue_position": 2
            }
    
    def _calculate_queue_time(self, active_orders: int, pending_orders: int) -> int:
        """Calculate estimated queue time based on order volume."""
        # If at or over capacity, add queue time
        if active_orders >= self.max_concurrent_deliveries:
            # Each order ahead in queue adds average delivery time
            queue_multiplier = pending_orders / self.max_concurrent_deliveries
            return int(queue_multiplier * 30)  # 30 minutes average delivery cycle
        
        # If under capacity, minimal queue time
        return min(pending_orders * 5, 15)  # Max 15 minutes queue time
    
    async def get_peak_hours_factor(self) -> float:
        """Calculate peak hours adjustment factor."""
        try:
            current_hour = datetime.now().hour
            
            # Define peak hours (lunch: 11-2, dinner: 5-9)
            if 11 <= current_hour <= 14 or 17 <= current_hour <= 21:
                return 1.2  # 20% longer during peak hours
            elif 15 <= current_hour <= 16 or 22 <= current_hour <= 23:
                return 1.1  # 10% longer during moderate hours
            else:
                return 1.0  # Normal times
                
        except Exception as e:
            logger.warning(f"Error calculating peak hours factor: {e}")
            return 1.0


class DeliveryEstimator:
    """
    Main delivery time estimation engine.
    Implements intelligent delivery time calculation based on multiple factors.
    """
    
    def __init__(self, google_maps_api_key: Optional[str] = None):
        """Initialize delivery estimator with Google Maps integration."""
        self.maps_client = GoogleMapsClient(google_maps_api_key)
        self.load_calculator = LoadCalculator()
        
        # Configuration from settings or defaults
        self.base_time_minutes = getattr(settings, 'delivery_base_time_minutes', 25)
        self.distance_factor_minutes_per_mile = getattr(settings, 'delivery_distance_factor', 2.0)
        self.min_delivery_time = getattr(settings, 'min_delivery_time_minutes', 15)
        self.max_delivery_time = getattr(settings, 'max_delivery_time_minutes', 90)
        self.delivery_radius_miles = getattr(settings, 'delivery_radius_miles', 8.0)
        
        # Random variation range as specified in PRD: -5 to +10 minutes
        self.random_variation_min = -5
        self.random_variation_max = 10
        
        # Legacy compatibility
        self.base_preparation_time = self.base_time_minutes
        self.minutes_per_mile = self.distance_factor_minutes_per_mile
        self.minutes_per_order = 3
        self.random_min = self.random_variation_min
        self.random_max = self.random_variation_max
        self.minimum_delivery_time = self.min_delivery_time
        self.maximum_delivery_radius = self.delivery_radius_miles
        
        logger.info(f"DeliveryEstimator initialized - base time: {self.base_time_minutes}min, max radius: {self.delivery_radius_miles}mi")
    
    async def estimate_delivery_time(
        self, 
        delivery_address: str,
        order_data: Optional[Dict[str, Any]] = None
    ) -> DeliveryEstimate:
        """
        Calculate comprehensive delivery time estimate.
        
        Args:
            delivery_address (str): Customer delivery address
            order_data (dict): Optional order information for context
            
        Returns:
            DeliveryEstimate: Complete estimation with breakdown
        """
        try:
            start_time = time.time()
            logger.info(f"Calculating delivery estimate for: {delivery_address}")
            
            # Step 1: Calculate distance and travel time
            distance_miles, travel_time_minutes, distance_confidence = await self.maps_client.calculate_distance_and_time(
                delivery_address
            )
            
            # Check if address is within delivery radius
            if distance_miles > self.delivery_radius_miles:
                raise ValueError(f"Address is outside delivery radius ({self.delivery_radius_miles} miles)")
            
            # Step 2: Calculate current load factor
            load_analysis = await self.load_calculator.calculate_current_load()
            load_time_minutes = load_analysis["load_factor_minutes"]
            
            # Step 3: Apply peak hours adjustment
            peak_factor = await self.load_calculator.get_peak_hours_factor()
            
            # Step 4: Calculate distance-based time (2 minutes per mile as per PRD)
            distance_time_minutes = int(distance_miles * self.distance_factor_minutes_per_mile)
            
            # Step 5: Generate random variation (-5 to +10 minutes as per PRD)
            random_variation = random.randint(self.random_variation_min, self.random_variation_max)
            
            # Step 6: Apply main estimation formula from PRD
            # Base time + (distance * 2 min/mile) + (current_orders * 3 min) + random(-5 to +10)
            estimated_minutes = (
                self.base_time_minutes + 
                distance_time_minutes + 
                load_time_minutes + 
                random_variation
            )
            
            # Step 7: Apply peak hours factor
            estimated_minutes = int(estimated_minutes * peak_factor)
            
            # Step 8: Apply bounds checking
            estimated_minutes = max(self.min_delivery_time, min(estimated_minutes, self.max_delivery_time))
            
            # Step 9: Determine delivery zone
            zone = self._determine_delivery_zone(distance_miles)
            
            # Step 10: Calculate confidence score
            confidence_score = self._calculate_confidence_score(
                distance_confidence, 
                load_analysis["capacity_utilization"],
                distance_miles
            )
            
            # Step 11: Prepare additional factors for tracking
            factors = {
                "peak_factor": peak_factor,
                "travel_time_minutes": travel_time_minutes,
                "capacity_utilization": load_analysis["capacity_utilization"],
                "queue_position": load_analysis["estimated_queue_position"],
                "weather_factor": 1.0,  # Future enhancement
                "traffic_factor": 1.0,  # Future enhancement
                "order_complexity": self._assess_order_complexity(order_data)
            }
            
            # Create delivery estimate object
            estimate = DeliveryEstimate(
                estimated_minutes=estimated_minutes,
                distance_miles=distance_miles,
                base_time_minutes=self.base_time_minutes,
                distance_time_minutes=distance_time_minutes,
                load_time_minutes=load_time_minutes,
                random_variation_minutes=random_variation,
                confidence_score=confidence_score,
                zone=zone,
                created_at=datetime.utcnow(),
                factors=factors
            )
            
            logger.info(f"Delivery estimate calculated: {estimated_minutes} minutes (distance: {distance_miles:.1f}mi, load: {load_time_minutes}min)")
            
            # Track performance metrics
            if delivery_performance_monitor:
                try:
                    estimation_time_ms = (time.time() - start_time) * 1000
                    cache_hit = hasattr(self, '_last_cache_hit') and self._last_cache_hit
                    
                    await delivery_performance_monitor.track_estimation_performance(
                        estimation_time_ms=estimation_time_ms,
                        cache_hit=cache_hit,
                        confidence_score=confidence_score,
                        estimation_id=f"est_{int(time.time())}"
                    )
                except Exception as e:
                    logger.warning(f"Error tracking performance: {e}")
            
            return estimate
            
        except ValueError as e:
            # Re-raise validation errors
            logger.warning(f"Delivery estimation validation error: {e}")
            raise
            
        except Exception as e:
            logger.error(f"Error calculating delivery estimate: {e}")
            
            # Track error
            if delivery_performance_monitor:
                try:
                    await delivery_performance_monitor.track_estimation_error(
                        error_type="estimation_error",
                        error_message=str(e),
                        context={"delivery_address": delivery_address, "order_data": order_data}
                    )
                except Exception as track_error:
                    logger.warning(f"Error tracking estimation error: {track_error}")
            
            # Return conservative fallback estimate
            return DeliveryEstimate(
                estimated_minutes=45,  # Conservative fallback
                distance_miles=3.0,
                base_time_minutes=self.base_time_minutes,
                distance_time_minutes=6,  # 3 miles * 2 min/mile
                load_time_minutes=9,  # Assume 3 active orders
                random_variation_minutes=5,
                confidence_score=0.3,  # Low confidence
                zone=DeliveryZone.MIDDLE_ZONE,
                created_at=datetime.utcnow(),
                factors={"error": str(e), "fallback": True}
            )
    
    def estimate_delivery_time_legacy(self, delivery_address: Dict[str, Any], 
                             current_orders: int = 0) -> int:
        """
        Legacy method for backward compatibility.
        Calculate estimated delivery time for an address.
        
        Args:
            delivery_address (dict): Customer delivery address
            current_orders (int): Number of current pending orders
            
        Returns:
            int: Estimated delivery time in minutes
        """
        try:
            logger.debug(f"Estimating delivery time for address: {delivery_address}")
            
            # Convert dict format to string for new method
            if isinstance(delivery_address, dict):
                address_str = f"{delivery_address.get('street', '')}, {delivery_address.get('city', '')}, {delivery_address.get('state', '')} {delivery_address.get('zip', '')}"
            else:
                address_str = str(delivery_address)
            
            # Use async method in sync context (simplified)
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                estimate = loop.run_until_complete(self.estimate_delivery_time(address_str))
                return estimate.estimated_minutes
            except:
                # Fallback to legacy calculation
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
    
    async def update_estimate_on_completion(self, completed_order_id: int) -> List[DeliveryEstimate]:
        """
        Update delivery estimates when an order is completed.
        
        Args:
            completed_order_id (int): ID of completed order
            
        Returns:
            list: Updated estimates for pending orders
        """
        try:
            logger.info(f"Updating delivery estimates after order {completed_order_id} completion")
            
            updated_estimates = []
            
            # Get all pending orders that need estimate updates
            async with get_db_session() as session:
                pending_orders = session.query(Order).filter(
                    Order.order_status.in_([
                        OrderStatus.PENDING.value,
                        OrderStatus.PREPARING.value,
                        OrderStatus.PAYMENT_CONFIRMED.value
                    ])
                ).all()
                
                # Recalculate estimates for each pending order
                for order in pending_orders:
                    try:
                        updated_estimate = await self.estimate_delivery_time(
                            order.address,
                            {"order_id": order.id, "order_details": order.order_details}
                        )
                        
                        # Store updated estimate
                        await self._store_delivery_estimate(order.id, updated_estimate)
                        updated_estimates.append(updated_estimate)
                        
                    except Exception as e:
                        logger.warning(f"Error updating estimate for order {order.id}: {e}")
                        continue
            
            logger.info(f"Updated {len(updated_estimates)} delivery estimates")
            return updated_estimates
            
        except Exception as e:
            logger.error(f"Error updating estimates on completion: {e}")
            return []
    
    async def get_delivery_zones_info(self) -> Dict[str, Any]:
        """Get delivery zones information and boundaries."""
        return {
            "zones": {
                "inner": {
                    "name": "Inner Zone",
                    "radius_miles": 2.0,
                    "typical_time_minutes": "15-25",
                    "delivery_fee": 2.99
                },
                "middle": {
                    "name": "Middle Zone", 
                    "radius_miles": 5.0,
                    "typical_time_minutes": "25-40",
                    "delivery_fee": 3.99
                },
                "outer": {
                    "name": "Outer Zone",
                    "radius_miles": self.delivery_radius_miles,
                    "typical_time_minutes": "40-60",
                    "delivery_fee": 4.99
                }
            },
            "max_delivery_radius": self.delivery_radius_miles,
            "base_delivery_time": self.base_time_minutes
        }
    
    def _determine_delivery_zone(self, distance_miles: float) -> DeliveryZone:
        """Determine delivery zone based on distance."""
        if distance_miles <= 2.0:
            return DeliveryZone.INNER_ZONE
        elif distance_miles <= 5.0:
            return DeliveryZone.MIDDLE_ZONE
        else:
            return DeliveryZone.OUTER_ZONE
    
    def _calculate_confidence_score(
        self, 
        distance_confidence: float, 
        capacity_utilization: float, 
        distance_miles: float
    ) -> float:
        """Calculate overall confidence score for the estimate."""
        # Start with distance calculation confidence
        confidence = distance_confidence
        
        # Reduce confidence based on capacity utilization
        if capacity_utilization > 0.8:
            confidence *= 0.8  # High load reduces confidence
        elif capacity_utilization > 0.6:
            confidence *= 0.9  # Medium load slightly reduces confidence
        
        # Reduce confidence for very long distances
        if distance_miles > 6.0:
            confidence *= 0.85
        elif distance_miles > 4.0:
            confidence *= 0.95
        
        # Ensure confidence is between 0 and 1
        return max(0.0, min(1.0, confidence))
    
    def _assess_order_complexity(self, order_data: Optional[Dict[str, Any]]) -> float:
        """Assess order complexity factor (future enhancement)."""
        if not order_data or "order_details" not in order_data:
            return 1.0  # Standard complexity
        
        try:
            order_details = order_data["order_details"]
            
            # Count items and complexity indicators
            item_count = len(order_details.get("pizzas", []))
            has_customizations = any(
                len(pizza.get("toppings", [])) > 3 
                for pizza in order_details.get("pizzas", [])
            )
            
            # Complex orders take slightly longer
            complexity_factor = 1.0
            if item_count > 3:
                complexity_factor += 0.1
            if has_customizations:
                complexity_factor += 0.05
                
            return min(complexity_factor, 1.2)  # Max 20% increase
            
        except Exception as e:
            logger.warning(f"Error assessing order complexity: {e}")
            return 1.0
    
    async def _store_delivery_estimate(self, order_id: int, estimate: DeliveryEstimate):
        """Store delivery estimate in database."""
        try:
            # This would store the estimate in a delivery_estimates table
            # For now, we'll log it and cache in Redis
            
            redis_client = await get_redis_async()
            estimate_key = f"delivery_estimate:{order_id}"
            estimate_data = estimate.to_dict()
            
            with redis_client.get_connection() as conn:
                conn.setex(estimate_key, 7200, str(estimate_data))  # 2 hour TTL
            
            logger.debug(f"Stored delivery estimate for order {order_id}: {estimate.estimated_minutes} minutes")
            
        except Exception as e:
            logger.warning(f"Error storing delivery estimate: {e}")
    
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


# Create global delivery estimator instance
delivery_estimator = DeliveryEstimator()


# Export main components
__all__ = [
    "DeliveryEstimator",
    "DeliveryEstimate", 
    "GoogleMapsClient",
    "LoadCalculator",
    "DeliveryZone",
    "delivery_estimator",
    "quick_delivery_estimate", 
    "is_address_deliverable"
]