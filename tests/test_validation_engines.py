"""
Comprehensive test suite for validation engines.
Tests address validation, order validation, payment validation, and error formatting.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal

from validation.address_validator import AddressValidator, validate_address
from validation.order_validator import OrderValidator, validate_order
from validation.payment_validator import PaymentValidator, validate_payment_method
from validation.error_formatter import ValidationErrorFormatter, format_validation_summary


class TestAddressValidator:
    """Test suite for address validation functionality."""
    
    @pytest.fixture
    def address_validator(self):
        """AddressValidator instance for testing."""
        with patch('validation.address_validator.settings') as mock_settings:
            mock_settings.google_maps_api_key = "test_google_maps_key"
            mock_settings.delivery_radius_miles = 5
            mock_settings.restaurant_address = "123 Main St, Anytown, CA 90210"
            
            validator = AddressValidator()
            return validator
    
    @pytest.mark.asyncio
    async def test_valid_address_validation(self, address_validator):
        """Test validation of a valid address within delivery range."""
        # Mock successful geocoding response
        mock_geocoding_response = {
            "success": True,
            "data": {
                "formatted_address": "456 Oak St, Anytown, CA 90210, USA",
                "address_components": {
                    "street_number": "456",
                    "route": "Oak St",
                    "street_address": "456 Oak St",
                    "city": "Anytown",
                    "state": "California",
                    "state_code": "CA",
                    "zip_code": "90210",
                    "country": "United States",
                    "country_code": "US"
                },
                "coordinates": {"latitude": 34.0522, "longitude": -118.2437},
                "place_id": "test_place_id"
            }
        }
        
        # Mock distance calculation (within range)
        with patch.object(address_validator, '_geocode_address', return_value=mock_geocoding_response):
            with patch.object(address_validator, '_validate_delivery_distance') as mock_distance:
                mock_distance.return_value = {
                    "within_range": True,
                    "distance_miles": 3.2,
                    "calculation_method": "haversine"
                }
                
                address_data = {
                    "street": "456 Oak St",
                    "city": "Anytown", 
                    "state": "CA",
                    "zip": "90210"
                }
                
                result = await address_validator.validate_address(address_data)
                
                assert result["is_valid"] is True
                assert result["standardized_address"] == "456 Oak St, Anytown, CA 90210, USA"
                assert result["delivery_feasible"] is True
                assert result["delivery_distance_miles"] == 3.2
                assert len(result["errors"]) == 0
    
    @pytest.mark.asyncio
    async def test_address_outside_delivery_range(self, address_validator):
        """Test validation of address outside delivery range."""
        mock_geocoding_response = {
            "success": True,
            "data": {
                "formatted_address": "789 Far St, Distant City, CA 90001, USA",
                "address_components": {},
                "coordinates": {"latitude": 33.0, "longitude": -117.0},
                "place_id": "test_place_id_far"
            }
        }
        
        # Mock distance calculation (outside range)
        with patch.object(address_validator, '_geocode_address', return_value=mock_geocoding_response):
            with patch.object(address_validator, '_validate_delivery_distance') as mock_distance:
                mock_distance.return_value = {
                    "within_range": False,
                    "distance_miles": 8.7,
                    "calculation_method": "haversine"
                }
                
                address_data = {
                    "street": "789 Far St",
                    "city": "Distant City",
                    "state": "CA",
                    "zip": "90001"
                }
                
                result = await address_validator.validate_address(address_data)
                
                assert result["is_valid"] is False
                assert result["delivery_feasible"] is False
                assert result["delivery_distance_miles"] == 8.7
                assert any("8.7 miles away" in error for error in result["errors"])
    
    @pytest.mark.asyncio
    async def test_invalid_address_not_found(self, address_validator):
        """Test validation of address that cannot be found."""
        mock_geocoding_response = {
            "success": False,
            "errors": ["Address not found. Please check the address and try again."]
        }
        
        with patch.object(address_validator, '_geocode_address', return_value=mock_geocoding_response):
            address_data = {"street": "999 Nonexistent St"}
            
            result = await address_validator.validate_address(address_data)
            
            assert result["is_valid"] is False
            assert result["delivery_feasible"] is False
            assert "Address not found" in result["errors"][0]
    
    @pytest.mark.asyncio
    async def test_incomplete_address_data(self, address_validator):
        """Test validation with incomplete address information."""
        result = await address_validator.validate_address({})
        
        assert result["is_valid"] is False
        assert "incomplete" in result["errors"][0].lower()


class TestOrderValidator:
    """Test suite for order validation functionality."""
    
    @pytest.fixture
    def order_validator(self):
        """OrderValidator instance for testing."""
        with patch('validation.order_validator.settings') as mock_settings:
            mock_settings.max_pizzas_per_order = 10
            
            validator = OrderValidator()
            return validator
    
    @pytest.mark.asyncio
    async def test_valid_pizza_order(self, order_validator):
        """Test validation of a valid pizza order."""
        order_data = {
            "pizzas": [
                {
                    "size": "large",
                    "crust": "thin",
                    "toppings": ["pepperoni", "mushrooms"],
                    "quantity": 2
                },
                {
                    "size": "medium",
                    "crust": "thick",
                    "toppings": ["sausage", "peppers"],
                    "quantity": 1
                }
            ]
        }
        
        result = await order_validator.validate_order(order_data)
        
        assert result["is_valid"] is True
        assert len(result["validated_order"]["pizzas"]) == 2
        assert result["calculated_total"] > 0
        assert len(result["errors"]) == 0
    
    @pytest.mark.asyncio
    async def test_empty_order(self, order_validator):
        """Test validation of empty order."""
        order_data = {"pizzas": []}
        
        result = await order_validator.validate_order(order_data)
        
        assert result["is_valid"] is False
        assert "at least one pizza" in result["errors"][0]
    
    @pytest.mark.asyncio
    async def test_invalid_pizza_size(self, order_validator):
        """Test validation with invalid pizza size."""
        order_data = {
            "pizzas": [
                {
                    "size": "gigantic",  # Invalid size
                    "crust": "thin",
                    "toppings": ["pepperoni"],
                    "quantity": 1
                }
            ]
        }
        
        result = await order_validator.validate_order(order_data)
        
        assert result["is_valid"] is False
        assert any("Invalid size" in error for error in result["errors"])
    
    @pytest.mark.asyncio 
    async def test_too_many_toppings(self, order_validator):
        """Test validation with too many toppings for pizza size."""
        order_data = {
            "pizzas": [
                {
                    "size": "small",
                    "crust": "thin",
                    "toppings": ["pepperoni", "sausage", "mushrooms", "peppers", "onions", "olives", "ham"],  # 7 toppings on small (limit 5)
                    "quantity": 1
                }
            ]
        }
        
        result = await order_validator.validate_order(order_data)
        
        assert result["is_valid"] is False
        assert any("Too many toppings" in error for error in result["errors"])
    
    @pytest.mark.asyncio
    async def test_order_below_minimum(self, order_validator):
        """Test validation of order below minimum total."""
        # Create a very small order that would be below minimum
        order_data = {
            "pizzas": [
                {
                    "size": "small",
                    "crust": "thin", 
                    "toppings": [],  # No toppings to keep price low
                    "quantity": 1
                }
            ]
        }
        
        # Mock a low subtotal
        with patch.object(order_validator, '_calculate_order_totals') as mock_calc:
            mock_calc.return_value = {
                "subtotal": 10.00,  # Below $15 minimum
                "tax": 0.85,
                "delivery_fee": 2.99,
                "total": 13.84
            }
            
            result = await order_validator.validate_order(order_data)
            
            assert result["is_valid"] is False
            assert any("at least $15.00" in error for error in result["errors"])


class TestPaymentValidator:
    """Test suite for payment validation functionality."""
    
    @pytest.fixture
    def payment_validator(self):
        """PaymentValidator instance for testing."""
        with patch('validation.payment_validator.settings') as mock_settings:
            mock_settings.stripe_secret_key = "sk_test_123"
            mock_settings.stripe_publishable_key = "pk_test_123"
            
            validator = PaymentValidator()
            return validator
    
    @pytest.mark.asyncio
    async def test_valid_payment_methods(self, payment_validator):
        """Test validation of supported payment methods."""
        valid_methods = ["credit_card", "debit_card", "cash"]
        
        for method in valid_methods:
            result = await payment_validator.validate_payment_method(method)
            assert result["is_valid"] is True
            assert result["payment_method"] == method
    
    @pytest.mark.asyncio
    async def test_invalid_payment_method(self, payment_validator):
        """Test validation of unsupported payment method."""
        result = await payment_validator.validate_payment_method("cryptocurrency")
        
        assert result["is_valid"] is False
        assert "Unsupported payment method" in result["errors"][0]
        assert "credit_card" in result["supported_methods"]
    
    @pytest.mark.asyncio
    async def test_payment_amount_validation(self, payment_validator):
        """Test payment amount validation."""
        # Valid amount
        result = await payment_validator.validate_payment_amount(25.99)
        assert result["is_valid"] is True
        assert result["validated_amount"] == 25.99
        
        # Too low
        result = await payment_validator.validate_payment_amount(0.50)
        assert result["is_valid"] is False
        assert "at least" in result["errors"][0]
        
        # Too high
        result = await payment_validator.validate_payment_amount(600.00)
        assert result["is_valid"] is False
        assert "cannot exceed" in result["errors"][0]
    
    def test_credit_card_format_validation(self, payment_validator):
        """Test credit card format validation."""
        # Valid Visa card
        valid_card = {
            "card_number": "4532015112830366",
            "exp_month": "12",
            "exp_year": "2025", 
            "cvv": "123",
            "cardholder_name": "John Doe"
        }
        
        result = asyncio.run(payment_validator.validate_card_format(valid_card))
        assert result["is_valid"] is True
        assert result["card_info"]["card_type"] == "visa"
        
        # Invalid card number
        invalid_card = valid_card.copy()
        invalid_card["card_number"] = "1234567890123456"  # Fails Luhn check
        
        result = asyncio.run(payment_validator.validate_card_format(invalid_card))
        assert result["is_valid"] is False
    
    @pytest.mark.asyncio
    async def test_cash_payment_processing(self, payment_validator):
        """Test cash payment processing."""
        payment_data = {
            "payment_method": "cash",
            "amount": 23.45
        }
        
        result = await payment_validator.process_payment_authorization(payment_data)
        
        assert result["success"] is True
        assert result["payment_method"] == "cash"
        assert result["amount"] == 23.45
        assert "cash_" in result["transaction_id"]


class TestValidationErrorFormatter:
    """Test suite for validation error formatting."""
    
    @pytest.fixture
    def error_formatter(self):
        """ValidationErrorFormatter instance for testing."""
        return ValidationErrorFormatter()
    
    def test_validation_summary_all_valid(self, error_formatter):
        """Test formatting when all validations pass."""
        validation_results = {
            "name": {"is_valid": True, "field_name": "customer_name"},
            "address": {"is_valid": True, "field_name": "address"},
            "order": {"is_valid": True, "field_name": "pizzas"},
            "payment": {"is_valid": True, "field_name": "payment_method"}
        }
        
        summary = error_formatter.format_validation_summary(validation_results)
        
        assert "Perfect!" in summary
        assert "everything looks good" in summary.lower()
    
    def test_validation_summary_with_errors(self, error_formatter):
        """Test formatting when validations have errors."""
        validation_results = {
            "address": {
                "is_valid": False,
                "field_name": "address",
                "error_message": "Address not found",
                "suggested_fix": "Please check the address"
            },
            "payment": {
                "is_valid": False, 
                "field_name": "payment_method",
                "error_message": "Invalid payment method",
                "suggested_fix": "Choose credit card, debit card, or cash"
            }
        }
        
        summary = error_formatter.format_validation_summary(validation_results)
        
        assert "2 things need your attention" in summary
        assert "❌" in summary
        assert "💡" in summary
    
    def test_address_error_formatting(self, error_formatter):
        """Test specific address error formatting."""
        error_details = {
            "error_message": "Address not found. Please check the address and try again.",
            "suggested_fix": "Try including ZIP code"
        }
        
        formatted = error_formatter.format_field_error("address", error_details)
        
        assert "couldn't find that address" in formatted.lower()
        assert "double-check" in formatted.lower()
    
    def test_payment_error_formatting(self, error_formatter):
        """Test specific payment error formatting."""
        error_details = {
            "error_message": "Card was declined",
            "suggested_fix": "Try a different card"
        }
        
        formatted = error_formatter.format_field_error("payment", error_details)
        
        assert "card was declined" in formatted.lower()


class TestIntegrationScenarios:
    """Integration tests for complete validation workflows."""
    
    @pytest.mark.asyncio
    async def test_complete_order_validation_success(self):
        """Test complete order validation workflow - success case."""
        # Mock all validators
        with patch('validation.address_validator.get_redis_async'):
            with patch('validation.order_validator.get_redis_async'):
                with patch('validation.payment_validator.settings') as mock_settings:
                    mock_settings.stripe_secret_key = "sk_test_123"
                    mock_settings.stripe_publishable_key = "pk_test_123"
                    mock_settings.google_maps_api_key = "test_key"
                    mock_settings.delivery_radius_miles = 5
                    mock_settings.restaurant_address = "123 Main St"
                    mock_settings.max_pizzas_per_order = 10
                    
                    address_validator = AddressValidator()
                    order_validator = OrderValidator()
                    payment_validator = PaymentValidator()
                    
                    # Mock successful address validation
                    with patch.object(address_validator, 'validate_address') as mock_addr:
                        mock_addr.return_value = {
                            "is_valid": True,
                            "standardized_address": "456 Oak St, Anytown, CA 90210",
                            "delivery_feasible": True,
                            "errors": [],
                            "warnings": []
                        }
                        
                        # Test address validation
                        addr_result = await address_validator.validate_address({
                            "street": "456 Oak St",
                            "city": "Anytown",
                            "state": "CA",
                            "zip": "90210"
                        })
                        
                        assert addr_result["is_valid"] is True
                    
                    # Test order validation
                    order_result = await order_validator.validate_order({
                        "pizzas": [
                            {
                                "size": "large",
                                "crust": "thin",
                                "toppings": ["pepperoni"],
                                "quantity": 1
                            }
                        ]
                    })
                    
                    assert order_result["is_valid"] is True
                    
                    # Test payment validation
                    payment_result = await payment_validator.validate_payment_method("credit_card")
                    
                    assert payment_result["is_valid"] is True
    
    @pytest.mark.asyncio
    async def test_complete_order_validation_failures(self):
        """Test complete order validation workflow - failure cases."""
        with patch('validation.address_validator.get_redis_async'):
            with patch('validation.order_validator.get_redis_async'):
                with patch('validation.payment_validator.settings') as mock_settings:
                    mock_settings.stripe_secret_key = "sk_test_123"
                    mock_settings.max_pizzas_per_order = 10
                    
                    order_validator = OrderValidator()
                    payment_validator = PaymentValidator()
                    
                    # Test order validation failure
                    order_result = await order_validator.validate_order({"pizzas": []})
                    assert order_result["is_valid"] is False
                    
                    # Test payment validation failure  
                    payment_result = await payment_validator.validate_payment_method("invalid_method")
                    assert payment_result["is_valid"] is False
                    
                    # Test error formatting for multiple failures
                    validation_results = {
                        "order": order_result,
                        "payment": {
                            "is_valid": False,
                            "error_message": "Invalid payment method",
                            "field_name": "payment_method"
                        }
                    }
                    
                    summary = format_validation_summary(validation_results)
                    assert "need your attention" in summary


if __name__ == "__main__":
    """
    Run validation engine tests.
    
    Usage:
        python -m pytest tests/test_validation_engines.py -v
    """
    pytest.main([__file__, "-v"])