"""
Comprehensive test suite for delivery time estimation system.
Tests all components of the delivery estimation pipeline including Google Maps integration,
load calculation, and estimation accuracy.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal

from agents.delivery_estimator import (
    DeliveryEstimator, DeliveryEstimate, GoogleMapsClient, 
    LoadCalculator, DeliveryZone, delivery_estimator
)
from database.models import Order, OrderStatus, DeliveryEstimateRecord
from database import get_db_session


class TestGoogleMapsClient:
    """Test suite for Google Maps API integration."""
    
    @pytest.fixture
    def maps_client(self):
        """GoogleMapsClient instance for testing."""
        with patch('agents.delivery_estimator.settings') as mock_settings:
            mock_settings.google_maps_api_key = "test_api_key"
            mock_settings.restaurant_location = {
                'address': '123 Test St, Test City, CA',
                'lat': 37.7749,
                'lng': -122.4194
            }
            
            return GoogleMapsClient("test_api_key")
    
    @pytest.mark.asyncio
    async def test_google_maps_distance_calculation_success(self, maps_client):
        """Test successful Google Maps distance calculation."""
        # Mock Google Maps API response
        mock_response = {
            'status': 'OK',
            'rows': [{
                'elements': [{
                    'status': 'OK',
                    'distance': {
                        'text': '3.2 mi',
                        'value': 5150  # meters
                    },
                    'duration': {
                        'text': '12 mins',
                        'value': 720  # seconds
                    },
                    'duration_in_traffic': {
                        'text': '15 mins',
                        'value': 900  # seconds
                    }
                }]
            }]
        }
        
        with patch.object(maps_client.gmaps, 'distance_matrix', return_value=mock_response):
            with patch.object(maps_client, '_cache_distance_result', new_callable=AsyncMock):
                distance, travel_time, confidence = await maps_client.calculate_distance_and_time(
                    "456 Customer St, Customer City, CA"
                )
                
                assert distance == pytest.approx(3.2, rel=0.1)  # 5150 meters ≈ 3.2 miles
                assert travel_time == 15  # Uses traffic duration
                assert confidence == 0.9  # High confidence for Google Maps result
    
    @pytest.mark.asyncio
    async def test_google_maps_fallback_to_geocoding(self, maps_client):
        """Test fallback to geocoding when distance matrix fails."""
        # Mock failed distance matrix response
        mock_distance_response = {
            'status': 'ZERO_RESULTS',
            'rows': [{'elements': [{'status': 'ZERO_RESULTS'}]}]
        }
        
        # Mock successful geocoding response
        mock_geocode_response = [{
            'geometry': {
                'location': {'lat': 37.7849, 'lng': -122.4094}
            }
        }]
        
        with patch.object(maps_client.gmaps, 'distance_matrix', return_value=mock_distance_response):
            with patch.object(maps_client.gmaps, 'geocode', return_value=mock_geocode_response):
                with patch.object(maps_client, '_cache_distance_result', new_callable=AsyncMock):
                    distance, travel_time, confidence = await maps_client.calculate_distance_and_time(
                        "789 Test Address"
                    )
                    
                    assert distance > 0  # Should calculate some distance
                    assert travel_time > 0  # Should calculate some travel time
                    assert confidence == 0.7  # Medium confidence for geocoding
    
    @pytest.mark.asyncio
    async def test_nominatim_fallback(self, maps_client):
        """Test fallback to Nominatim geocoding."""
        # Mock Google Maps failure
        with patch.object(maps_client.gmaps, 'distance_matrix', side_effect=Exception("API Error")):
            with patch.object(maps_client.gmaps, 'geocode', side_effect=Exception("API Error")):
                # Mock Nominatim response
                mock_location = Mock()
                mock_location.latitude = 37.7949
                mock_location.longitude = -122.3994
                
                with patch.object(maps_client.fallback_geocoder, 'geocode', return_value=mock_location):
                    with patch.object(maps_client, '_cache_distance_result', new_callable=AsyncMock):
                        distance, travel_time, confidence = await maps_client.calculate_distance_and_time(
                            "Fallback Address"
                        )
                        
                        assert distance > 0
                        assert travel_time > 0
                        assert confidence == 0.5  # Lower confidence for fallback
    
    @pytest.mark.asyncio
    async def test_address_text_estimation(self, maps_client):
        """Test address text-based estimation as last resort."""
        # Mock all geocoding failures
        with patch.object(maps_client.gmaps, 'distance_matrix', side_effect=Exception("API Error")):
            with patch.object(maps_client.gmaps, 'geocode', side_effect=Exception("API Error")):
                with patch.object(maps_client.fallback_geocoder, 'geocode', side_effect=Exception("API Error")):
                    with patch.object(maps_client, '_cache_distance_result', new_callable=AsyncMock):
                        # Test downtown address
                        distance, travel_time, confidence = await maps_client.calculate_distance_and_time(
                            "123 Main St Downtown"
                        )
                        
                        assert distance == 1.5  # Downtown estimate
                        assert travel_time == 8
                        assert confidence == 0.3
    
    @pytest.mark.asyncio
    async def test_distance_caching(self, maps_client):
        """Test distance calculation caching."""
        cached_result = (2.5, 10, 0.9)
        
        with patch.object(maps_client, '_get_cached_distance', return_value=cached_result):
            distance, travel_time, confidence = await maps_client.calculate_distance_and_time(
                "Cached Address"
            )
            
            assert distance == 2.5
            assert travel_time == 10
            assert confidence == 0.9
    
    @pytest.mark.asyncio
    async def test_error_handling_conservative_estimate(self, maps_client):
        """Test error handling returns conservative estimate."""
        # Mock all methods to fail
        with patch.object(maps_client, '_get_cached_distance', side_effect=Exception("Cache Error")):
            with patch.object(maps_client, '_calculate_with_google_maps', side_effect=Exception("Maps Error")):
                distance, travel_time, confidence = await maps_client.calculate_distance_and_time(
                    "Error Address"
                )
                
                assert distance == 3.0  # Conservative fallback
                assert travel_time == 15
                assert confidence == 0.3


class TestLoadCalculator:
    """Test suite for delivery load calculation."""
    
    @pytest.fixture
    def load_calculator(self):
        """LoadCalculator instance for testing."""
        with patch('agents.delivery_estimator.settings') as mock_settings:
            mock_settings.max_concurrent_deliveries = 4
            mock_settings.average_preparation_time = 15
            
            return LoadCalculator()
    
    @pytest.mark.asyncio
    async def test_load_calculation_with_active_orders(self, load_calculator):
        """Test load calculation with active orders."""
        # Mock database session with active orders
        mock_active_orders = [Mock() for _ in range(3)]  # 3 active orders
        mock_pending_orders = [Mock() for _ in range(2)]  # 2 pending orders
        
        mock_session = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = mock_active_orders
        mock_query.filter.return_value = mock_query
        mock_session.query.return_value = mock_query
        
        # Separate query for pending orders
        pending_query = Mock()
        pending_query.filter.return_value.all.return_value = mock_pending_orders
        mock_session.query.side_effect = [mock_query, pending_query]
        
        with patch('agents.delivery_estimator.get_db_session') as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            load_analysis = await load_calculator.calculate_current_load()
            
            assert load_analysis["active_orders"] == 3
            assert load_analysis["pending_orders"] == 2
            assert load_analysis["load_factor_minutes"] == 9  # 3 active * 3 minutes
            assert load_analysis["capacity_utilization"] == 0.75  # 3/4 capacity
            assert not load_analysis["is_at_capacity"]
            assert load_analysis["estimated_queue_position"] == 3  # 2 pending + 1
    
    @pytest.mark.asyncio
    async def test_load_calculation_at_capacity(self, load_calculator):
        """Test load calculation when at capacity."""
        # Mock 4 active orders (at capacity) and 3 pending
        mock_active_orders = [Mock() for _ in range(4)]
        mock_pending_orders = [Mock() for _ in range(3)]
        
        mock_session = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = mock_active_orders
        mock_query.filter.return_value = mock_query
        mock_session.query.return_value = mock_query
        
        pending_query = Mock()
        pending_query.filter.return_value.all.return_value = mock_pending_orders
        mock_session.query.side_effect = [mock_query, pending_query]
        
        with patch('agents.delivery_estimator.get_db_session') as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            load_analysis = await load_calculator.calculate_current_load()
            
            assert load_analysis["active_orders"] == 4
            assert load_analysis["pending_orders"] == 3
            assert load_analysis["load_factor_minutes"] == 12  # 4 active * 3 minutes
            assert load_analysis["capacity_utilization"] == 1.0  # 4/4 capacity
            assert load_analysis["is_at_capacity"]
            assert load_analysis["queue_time_minutes"] > 0  # Should have queue time
    
    @pytest.mark.asyncio
    async def test_peak_hours_factor(self, load_calculator):
        """Test peak hours adjustment factor."""
        # Test lunch rush (12 PM)
        with patch('agents.delivery_estimator.datetime') as mock_datetime:
            mock_datetime.now.return_value.hour = 12
            
            factor = await load_calculator.get_peak_hours_factor()
            assert factor == 1.2  # 20% longer during lunch
        
        # Test dinner rush (7 PM)
        with patch('agents.delivery_estimator.datetime') as mock_datetime:
            mock_datetime.now.return_value.hour = 19
            
            factor = await load_calculator.get_peak_hours_factor()
            assert factor == 1.2  # 20% longer during dinner
        
        # Test normal hours (10 AM)
        with patch('agents.delivery_estimator.datetime') as mock_datetime:
            mock_datetime.now.return_value.hour = 10
            
            factor = await load_calculator.get_peak_hours_factor()
            assert factor == 1.0  # Normal time
    
    @pytest.mark.asyncio
    async def test_load_calculation_error_fallback(self, load_calculator):
        """Test load calculation error fallback."""
        with patch('agents.delivery_estimator.get_db_session', side_effect=Exception("DB Error")):
            load_analysis = await load_calculator.calculate_current_load()
            
            # Should return conservative fallback values
            assert load_analysis["active_orders"] == 2
            assert load_analysis["pending_orders"] == 1
            assert load_analysis["load_factor_minutes"] == 6


class TestDeliveryEstimator:
    """Test suite for main delivery estimator."""
    
    @pytest.fixture
    def estimator(self):
        """DeliveryEstimator instance for testing."""
        with patch('agents.delivery_estimator.settings') as mock_settings:
            mock_settings.delivery_base_time_minutes = 25
            mock_settings.delivery_distance_factor = 2.0
            mock_settings.min_delivery_time_minutes = 15
            mock_settings.max_delivery_time_minutes = 90
            mock_settings.delivery_radius_miles = 8.0
            
            return DeliveryEstimator()
    
    @pytest.mark.asyncio
    async def test_complete_estimation_flow(self, estimator):
        """Test complete delivery estimation flow."""
        # Mock Google Maps response
        with patch.object(estimator.maps_client, 'calculate_distance_and_time', 
                         return_value=(3.5, 14, 0.9)):
            
            # Mock load calculation
            load_data = {
                "active_orders": 2,
                "pending_orders": 1,
                "load_factor_minutes": 6,
                "capacity_utilization": 0.5,
                "estimated_queue_position": 2
            }
            
            with patch.object(estimator.load_calculator, 'calculate_current_load', 
                             return_value=load_data):
                
                with patch.object(estimator.load_calculator, 'get_peak_hours_factor', 
                                 return_value=1.1):
                    
                    with patch.object(estimator, '_store_delivery_estimate', new_callable=AsyncMock):
                        # Mock random variation to be predictable
                        with patch('agents.delivery_estimator.random.randint', return_value=3):
                            
                            estimate = await estimator.estimate_delivery_time(
                                "123 Test St, Test City, CA",
                                {"order_details": {"pizzas": [{"size": "large"}]}}
                            )
                            
                            # Verify estimate calculation
                            # Base (25) + Distance (3.5*2=7) + Load (6) + Random (3) = 41 * Peak (1.1) = 45.1 → 45
                            assert estimate.estimated_minutes == 45
                            assert estimate.distance_miles == 3.5
                            assert estimate.base_time_minutes == 25
                            assert estimate.distance_time_minutes == 7
                            assert estimate.load_time_minutes == 6
                            assert estimate.random_variation_minutes == 3
                            assert estimate.confidence_score > 0.7  # High confidence
                            assert estimate.zone == DeliveryZone.MIDDLE_ZONE
    
    @pytest.mark.asyncio
    async def test_estimation_with_address_outside_radius(self, estimator):
        """Test estimation fails for address outside delivery radius."""
        # Mock distance beyond radius
        with patch.object(estimator.maps_client, 'calculate_distance_and_time', 
                         return_value=(10.0, 25, 0.8)):  # 10 miles > 8 mile radius
            
            with pytest.raises(ValueError, match="outside delivery radius"):
                await estimator.estimate_delivery_time("Far Away Address")
    
    @pytest.mark.asyncio
    async def test_estimation_error_fallback(self, estimator):
        """Test estimation error returns fallback estimate."""
        # Mock all methods to fail
        with patch.object(estimator.maps_client, 'calculate_distance_and_time', 
                         side_effect=Exception("Maps Error")):
            
            estimate = await estimator.estimate_delivery_time("Error Address")
            
            # Should return conservative fallback
            assert estimate.estimated_minutes == 45
            assert estimate.distance_miles == 3.0
            assert estimate.confidence_score == 0.3
            assert "fallback" in estimate.factors
    
    @pytest.mark.asyncio
    async def test_delivery_zone_determination(self, estimator):
        """Test delivery zone classification."""
        assert estimator._determine_delivery_zone(1.5) == DeliveryZone.INNER_ZONE
        assert estimator._determine_delivery_zone(3.5) == DeliveryZone.MIDDLE_ZONE
        assert estimator._determine_delivery_zone(7.0) == DeliveryZone.OUTER_ZONE
    
    @pytest.mark.asyncio
    async def test_confidence_score_calculation(self, estimator):
        """Test confidence score calculation factors."""
        # High confidence scenario
        confidence = estimator._calculate_confidence_score(0.9, 0.3, 2.0)
        assert confidence >= 0.85  # Should be high
        
        # Low confidence scenario (high load, long distance)
        confidence = estimator._calculate_confidence_score(0.5, 0.9, 7.0)
        assert confidence <= 0.4  # Should be low
    
    @pytest.mark.asyncio
    async def test_order_complexity_assessment(self, estimator):
        """Test order complexity factor calculation."""
        # Simple order
        simple_order = {"order_details": {"pizzas": [{"size": "medium", "toppings": ["cheese"]}]}}
        complexity = estimator._assess_order_complexity(simple_order)
        assert complexity == 1.0
        
        # Complex order
        complex_order = {
            "order_details": {
                "pizzas": [
                    {"size": "large", "toppings": ["pepperoni", "mushrooms", "olives", "peppers", "sausage"]},
                    {"size": "medium", "toppings": ["cheese"]},
                    {"size": "small", "toppings": ["pepperoni"]},
                    {"size": "large", "toppings": ["supreme"]}
                ]
            }
        }
        complexity = estimator._assess_order_complexity(complex_order)
        assert complexity > 1.0  # Should add complexity
        assert complexity <= 1.2  # But capped at 20% increase
    
    @pytest.mark.asyncio
    async def test_update_estimates_on_completion(self, estimator):
        """Test updating estimates when order is completed."""
        # Mock pending orders
        mock_orders = [
            Mock(id=1, address="123 Address A", order_details={"pizzas": []}),
            Mock(id=2, address="456 Address B", order_details={"pizzas": []})
        ]
        
        mock_session = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = mock_orders
        mock_session.query.return_value = mock_query
        
        with patch('agents.delivery_estimator.get_db_session') as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            # Mock estimate calculation
            mock_estimate = Mock()
            mock_estimate.estimated_minutes = 30
            
            with patch.object(estimator, 'estimate_delivery_time', return_value=mock_estimate):
                with patch.object(estimator, '_store_delivery_estimate', new_callable=AsyncMock):
                    
                    updated_estimates = await estimator.update_estimate_on_completion(99)
                    
                    assert len(updated_estimates) == 2  # Updated 2 pending orders
                    assert all(est.estimated_minutes == 30 for est in updated_estimates)
    
    @pytest.mark.asyncio
    async def test_delivery_zones_info(self, estimator):
        """Test delivery zones information retrieval."""
        zones_info = await estimator.get_delivery_zones_info()
        
        assert "zones" in zones_info
        assert "inner" in zones_info["zones"]
        assert "middle" in zones_info["zones"]
        assert "outer" in zones_info["zones"]
        assert zones_info["max_delivery_radius"] == estimator.delivery_radius_miles
        assert zones_info["base_delivery_time"] == estimator.base_time_minutes


class TestDeliveryEstimateModel:
    """Test suite for DeliveryEstimate data model."""
    
    def test_delivery_estimate_creation(self):
        """Test DeliveryEstimate object creation and methods."""
        estimate = DeliveryEstimate(
            estimated_minutes=35,
            distance_miles=2.5,
            base_time_minutes=25,
            distance_time_minutes=5,
            load_time_minutes=3,
            random_variation_minutes=2,
            confidence_score=0.85,
            zone=DeliveryZone.INNER_ZONE,
            created_at=datetime.utcnow(),
            factors={"peak_factor": 1.0, "traffic_factor": 1.0}
        )
        
        assert estimate.estimated_minutes == 35
        assert estimate.zone == DeliveryZone.INNER_ZONE
        assert estimate.confidence_score == 0.85
        
        # Test to_dict method
        estimate_dict = estimate.to_dict()
        assert estimate_dict["estimated_minutes"] == 35
        assert estimate_dict["zone"] == "inner"
        assert estimate_dict["confidence_score"] == 0.85
        assert "created_at" in estimate_dict
        assert "factors" in estimate_dict


class TestDeliveryEstimationIntegration:
    """Integration tests for delivery estimation system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_estimation_flow(self):
        """Test complete end-to-end delivery estimation flow."""
        # This would test the full integration from address input to database storage
        # Mock all external dependencies
        
        with patch('agents.delivery_estimator.googlemaps.Client'):
            with patch('agents.delivery_estimator.get_redis_async'):
                with patch('agents.delivery_estimator.get_db_session'):
                    
                    estimator = DeliveryEstimator("test_key")
                    
                    # Mock successful Google Maps response
                    with patch.object(estimator.maps_client, 'calculate_distance_and_time', 
                                     return_value=(2.8, 11, 0.9)):
                        
                        # Mock load calculation
                        load_data = {
                            "active_orders": 1,
                            "pending_orders": 0,
                            "load_factor_minutes": 3,
                            "capacity_utilization": 0.25,
                            "estimated_queue_position": 1
                        }
                        
                        with patch.object(estimator.load_calculator, 'calculate_current_load', 
                                         return_value=load_data):
                            
                            with patch.object(estimator.load_calculator, 'get_peak_hours_factor', 
                                             return_value=1.0):
                                
                                with patch.object(estimator, '_store_delivery_estimate', new_callable=AsyncMock):
                                    
                                    # Test estimation
                                    estimate = await estimator.estimate_delivery_time(
                                        "123 Integration Test St, Test City, CA",
                                        {"order_details": {"pizzas": [{"size": "medium"}]}}
                                    )
                                    
                                    # Verify realistic estimate
                                    assert 15 <= estimate.estimated_minutes <= 90
                                    assert estimate.distance_miles == 2.8
                                    assert estimate.zone == DeliveryZone.INNER_ZONE
                                    assert estimate.confidence_score > 0.8
    
    @pytest.mark.asyncio
    async def test_legacy_compatibility(self):
        """Test backward compatibility with legacy delivery estimation."""
        estimator = DeliveryEstimator()
        
        # Test legacy method call
        legacy_address = {
            "street": "123 Legacy St",
            "city": "Legacy City",
            "state": "CA",
            "zip": "90210"
        }
        
        # Mock the async method for legacy compatibility
        with patch.object(estimator, 'estimate_delivery_time') as mock_estimate:
            mock_estimate.return_value = Mock(estimated_minutes=30)
            
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_until_complete.return_value = Mock(estimated_minutes=30)
                
                result = estimator.estimate_delivery_time_legacy(legacy_address, current_orders=2)
                
                assert result == 30


class TestPerformanceAndResilience:
    """Test suite for performance and resilience of delivery estimation."""
    
    @pytest.mark.asyncio
    async def test_concurrent_estimation_requests(self):
        """Test handling multiple concurrent estimation requests."""
        estimator = DeliveryEstimator()
        
        # Mock fast responses
        with patch.object(estimator.maps_client, 'calculate_distance_and_time', 
                         return_value=(3.0, 12, 0.8)):
            with patch.object(estimator.load_calculator, 'calculate_current_load', 
                             return_value={"active_orders": 1, "load_factor_minutes": 3, "capacity_utilization": 0.25}):
                with patch.object(estimator.load_calculator, 'get_peak_hours_factor', return_value=1.0):
                    with patch.object(estimator, '_store_delivery_estimate', new_callable=AsyncMock):
                        
                        # Run multiple concurrent requests
                        addresses = [f"Address {i}" for i in range(10)]
                        
                        tasks = [
                            estimator.estimate_delivery_time(address) 
                            for address in addresses
                        ]
                        
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        # All should succeed
                        assert len(results) == 10
                        assert all(isinstance(r, DeliveryEstimate) for r in results)
    
    @pytest.mark.asyncio
    async def test_api_timeout_resilience(self):
        """Test resilience to API timeouts."""
        estimator = DeliveryEstimator()
        
        # Mock timeout on first call, success on retry
        with patch.object(estimator.maps_client, 'calculate_distance_and_time', 
                         side_effect=[asyncio.TimeoutError("Timeout"), (2.5, 10, 0.7)]):
            
            # Should handle timeout gracefully and provide fallback
            estimate = await estimator.estimate_delivery_time("Timeout Test Address")
            
            # Should get fallback estimate
            assert estimate.estimated_minutes > 0
            assert estimate.confidence_score < 1.0


if __name__ == "__main__":
    """
    Run delivery estimation tests.
    
    Usage:
        python -m pytest tests/test_delivery_estimation.py -v
    """
    pytest.main([__file__, "-v"])