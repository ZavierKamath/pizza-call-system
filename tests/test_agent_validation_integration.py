"""
Integration tests for validation engines with LangGraph pizza ordering agent.
Tests the complete flow from user input through validation to response generation.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from agents.pizza_agent import PizzaOrderingAgent
from agents.states import StateManager, OrderState
from validation.address_validator import AddressValidator
from validation.order_validator import OrderValidator
from validation.payment_validator import PaymentValidator


class TestAgentValidationIntegration:
    """Test suite for agent-validation integration."""
    
    @pytest.fixture
    def pizza_agent(self):
        """PizzaOrderingAgent instance for testing."""
        with patch('agents.pizza_agent.ChatOpenAI'):
            with patch('agents.pizza_agent.settings') as mock_settings:
                mock_settings.openai_api_key = "test_openai_key"
                mock_settings.google_maps_api_key = "test_google_key"
                mock_settings.stripe_secret_key = "sk_test_123"
                mock_settings.stripe_publishable_key = "pk_test_123"
                mock_settings.delivery_radius_miles = 5
                mock_settings.restaurant_address = "123 Main St, Anytown, CA"
                mock_settings.max_pizzas_per_order = 10
                
                agent = PizzaOrderingAgent()
                return agent
    
    @pytest.fixture
    def sample_order_state(self):
        """Sample order state for testing."""
        return OrderState(
            session_id="test_session_123",
            interface_type="phone",
            current_state="validate_inputs",
            customer_name="John Doe",
            address={
                "street": "456 Oak Street",
                "city": "Anytown", 
                "state": "CA",
                "zip": "90210"
            },
            pizzas=[
                {
                    "size": "large",
                    "crust": "thin",
                    "toppings": ["pepperoni", "mushrooms"],
                    "quantity": 1
                }
            ],
            payment_method="credit_card",
            order_total=23.99,
            phone_number="+1234567890"
        )
    
    @pytest.mark.asyncio
    async def test_successful_validation_flow(self, pizza_agent, sample_order_state):
        """Test complete validation flow with successful validation."""
        # Mock successful address validation
        mock_address_validation = {
            "is_valid": True,
            "standardized_address": "456 Oak Street, Anytown, CA 90210, USA",
            "coordinates": {"latitude": 34.0522, "longitude": -118.2437},
            "delivery_distance_miles": 3.2,
            "delivery_feasible": True,
            "errors": [],
            "warnings": ["Delivery distance: 3.2 miles"]
        }
        
        # Mock successful order validation
        mock_order_validation = {
            "is_valid": True,
            "validated_order": {
                "pizzas": [
                    {
                        "size": "large",
                        "crust": "thin", 
                        "toppings": ["pepperoni", "mushrooms"],
                        "quantity": 1,
                        "unit_price": 21.99,
                        "total_price": 21.99
                    }
                ],
                "totals": {
                    "subtotal": 21.99,
                    "tax": 1.87,
                    "delivery_fee": 2.99,
                    "total": 26.85
                }
            },
            "calculated_total": 26.85,
            "errors": [],
            "warnings": []
        }
        
        # Mock successful payment validation
        mock_payment_validation = {
            "is_valid": True,
            "payment_method": "credit_card",
            "requires_card_details": True,
            "stripe_integration": True,
            "errors": []
        }
        
        with patch.object(pizza_agent.address_validator, 'validate_address', return_value=mock_address_validation):
            with patch.object(pizza_agent.order_validator, 'validate_order', return_value=mock_order_validation):
                with patch.object(pizza_agent.payment_validator, 'validate_payment_method', return_value=mock_payment_validation):
                    # Run validation
                    validation_results = await pizza_agent._perform_comprehensive_validation(sample_order_state)
                    
                    # Verify all validations passed
                    assert validation_results["address"]["is_valid"] is True
                    assert validation_results["order"]["is_valid"] is True
                    assert validation_results["payment"]["is_valid"] is True
                    
                    # Verify state was updated with validated data
                    assert "validated_address" in sample_order_state
                    assert "validated_order" in sample_order_state
                    assert "validated_payment_method" in sample_order_state
                    assert sample_order_state["order_total"] == 26.85
    
    @pytest.mark.asyncio
    async def test_address_validation_failure(self, pizza_agent, sample_order_state):
        """Test validation flow with address validation failure."""
        # Mock failed address validation (outside delivery range)
        mock_address_validation = {
            "is_valid": False,
            "standardized_address": "",
            "coordinates": None,
            "delivery_distance_miles": 8.5,
            "delivery_feasible": False,
            "errors": ["Address is 8.5 miles away. We only deliver within 5 miles of our restaurant."],
            "warnings": []
        }
        
        # Mock successful other validations
        mock_order_validation = {"is_valid": True, "errors": []}
        mock_payment_validation = {"is_valid": True, "errors": []}
        
        with patch.object(pizza_agent.address_validator, 'validate_address', return_value=mock_address_validation):
            with patch.object(pizza_agent.order_validator, 'validate_order', return_value=mock_order_validation):
                with patch.object(pizza_agent.payment_validator, 'validate_payment_method', return_value=mock_payment_validation):
                    
                    validation_results = await pizza_agent._perform_comprehensive_validation(sample_order_state)
                    
                    # Verify address validation failed
                    assert validation_results["address"]["is_valid"] is False
                    assert "8.5 miles away" in validation_results["address"]["error_message"]
                    
                    # Verify routing would send back to address collection
                    next_state = pizza_agent._determine_validation_fix_state(validation_results)
                    assert next_state == "collect_address"
    
    @pytest.mark.asyncio
    async def test_order_validation_failure(self, pizza_agent, sample_order_state):
        """Test validation flow with order validation failure."""
        # Mock order with invalid pizza configuration
        sample_order_state["pizzas"] = [
            {
                "size": "gigantic",  # Invalid size
                "crust": "thin",
                "toppings": ["pepperoni"],
                "quantity": 1
            }
        ]
        
        # Mock failed order validation
        mock_order_validation = {
            "is_valid": False,
            "validated_order": {},
            "calculated_total": 0.0,
            "errors": ["Pizza 1: Invalid size 'gigantic'. Available: small, medium, large"],
            "warnings": []
        }
        
        # Mock successful other validations
        mock_address_validation = {"is_valid": True, "errors": []}
        mock_payment_validation = {"is_valid": True, "errors": []}
        
        with patch.object(pizza_agent.address_validator, 'validate_address', return_value=mock_address_validation):
            with patch.object(pizza_agent.order_validator, 'validate_order', return_value=mock_order_validation):
                with patch.object(pizza_agent.payment_validator, 'validate_payment_method', return_value=mock_payment_validation):
                    
                    validation_results = await pizza_agent._perform_comprehensive_validation(sample_order_state)
                    
                    # Verify order validation failed
                    assert validation_results["order"]["is_valid"] is False
                    assert "Invalid size 'gigantic'" in validation_results["order"]["error_message"]
                    
                    # Verify routing would send back to order collection
                    next_state = pizza_agent._determine_validation_fix_state(validation_results)
                    assert next_state == "collect_order"
    
    @pytest.mark.asyncio
    async def test_payment_validation_failure(self, pizza_agent, sample_order_state):
        """Test validation flow with payment validation failure."""
        # Set invalid payment method
        sample_order_state["payment_method"] = "cryptocurrency"
        
        # Mock failed payment validation
        mock_payment_validation = {
            "is_valid": False,
            "errors": ["Unsupported payment method: cryptocurrency"],
            "supported_methods": ["credit_card", "debit_card", "cash"]
        }
        
        # Mock successful other validations
        mock_address_validation = {"is_valid": True, "errors": []}
        mock_order_validation = {"is_valid": True, "errors": []}
        
        with patch.object(pizza_agent.address_validator, 'validate_address', return_value=mock_address_validation):
            with patch.object(pizza_agent.order_validator, 'validate_order', return_value=mock_order_validation):
                with patch.object(pizza_agent.payment_validator, 'validate_payment_method', return_value=mock_payment_validation):
                    
                    validation_results = await pizza_agent._perform_comprehensive_validation(sample_order_state)
                    
                    # Verify payment validation failed
                    assert validation_results["payment"]["is_valid"] is False
                    assert "Unsupported payment method" in validation_results["payment"]["error_message"]
                    
                    # Verify routing would send back to payment collection
                    next_state = pizza_agent._determine_validation_fix_state(validation_results)
                    assert next_state == "collect_payment_preference"
    
    @pytest.mark.asyncio
    async def test_multiple_validation_failures(self, pizza_agent, sample_order_state):
        """Test validation flow with multiple failures."""
        # Set up multiple invalid states
        sample_order_state["address"] = {"street": "999 Nonexistent St"}
        sample_order_state["pizzas"] = []  # Empty order
        sample_order_state["payment_method"] = "invalid_method"
        
        # Mock all validations failing
        mock_address_validation = {
            "is_valid": False,
            "errors": ["Address not found"],
            "warnings": []
        }
        
        mock_order_validation = {
            "is_valid": False,
            "errors": ["Order must contain at least one pizza"],
            "warnings": []
        }
        
        mock_payment_validation = {
            "is_valid": False,
            "errors": ["Unsupported payment method"],
            "warnings": []
        }
        
        with patch.object(pizza_agent.address_validator, 'validate_address', return_value=mock_address_validation):
            with patch.object(pizza_agent.order_validator, 'validate_order', return_value=mock_order_validation):
                with patch.object(pizza_agent.payment_validator, 'validate_payment_method', return_value=mock_payment_validation):
                    
                    validation_results = await pizza_agent._perform_comprehensive_validation(sample_order_state)
                    
                    # Verify all validations failed
                    assert validation_results["address"]["is_valid"] is False
                    assert validation_results["order"]["is_valid"] is False
                    assert validation_results["payment"]["is_valid"] is False
                    
                    # Verify priority routing (name has highest priority, but name is valid)
                    next_state = pizza_agent._determine_validation_fix_state(validation_results)
                    assert next_state == "collect_address"  # Address comes first in priority
    
    @pytest.mark.asyncio
    async def test_validation_with_warnings(self, pizza_agent, sample_order_state):
        """Test validation flow with warnings but valid results."""
        # Mock validations with warnings
        mock_address_validation = {
            "is_valid": True,
            "standardized_address": "456 Oak Street, Anytown, CA 90210, USA",
            "coordinates": {"latitude": 34.0522, "longitude": -118.2437},
            "delivery_distance_miles": 4.8,
            "delivery_feasible": True,
            "errors": [],
            "warnings": ["Address is near the edge of our delivery area"]
        }
        
        mock_order_validation = {
            "is_valid": True,
            "validated_order": {"pizzas": [], "totals": {"total": 25.99}},
            "calculated_total": 25.99,
            "errors": [],
            "warnings": ["Order contains duplicate pizza configurations - consider combining quantities"]
        }
        
        mock_payment_validation = {"is_valid": True, "errors": [], "warnings": []}
        
        with patch.object(pizza_agent.address_validator, 'validate_address', return_value=mock_address_validation):
            with patch.object(pizza_agent.order_validator, 'validate_order', return_value=mock_order_validation):
                with patch.object(pizza_agent.payment_validator, 'validate_payment_method', return_value=mock_payment_validation):
                    
                    validation_results = await pizza_agent._perform_comprehensive_validation(sample_order_state)
                    
                    # Verify all validations passed despite warnings
                    assert all(result["is_valid"] for result in validation_results.values())
                    
                    # Check that warnings are preserved
                    assert hasattr(validation_results["order"], 'warnings')
    
    @pytest.mark.asyncio
    async def test_payment_processing_integration(self, pizza_agent, sample_order_state):
        """Test payment processing with validation integration."""
        # Set up validated payment method
        sample_order_state["validated_payment_method"] = {
            "method": "credit_card",
            "requires_card_details": True,
            "stripe_integration": True
        }
        sample_order_state["order_total"] = 25.99
        
        # Mock successful payment processing
        mock_payment_result = {
            "success": True,
            "payment_method": "credit_card",
            "amount": 25.99,
            "transaction_id": "txn_12345678",
            "message": "Payment of $25.99 processed successfully"
        }
        
        with patch.object(pizza_agent.payment_validator, 'validate_payment_amount', return_value={"is_valid": True}):
            with patch.object(pizza_agent.payment_validator, 'process_payment_authorization', return_value=mock_payment_result):
                
                payment_result = await pizza_agent._process_payment_transaction(sample_order_state)
                
                assert payment_result["success"] is True
                assert payment_result["amount"] == 25.99
                assert "payment_confirmation" in sample_order_state
                assert sample_order_state["payment_confirmation"]["transaction_id"] == "txn_12345678"
    
    @pytest.mark.asyncio
    async def test_end_to_end_validation_workflow(self, pizza_agent):
        """Test complete end-to-end validation workflow in agent."""
        # Create initial state
        initial_state = StateManager.create_initial_state("test_session", "phone")
        initial_state.update({
            "customer_name": "Jane Smith",
            "address": {
                "street": "789 Pine Ave",
                "city": "Testtown",
                "state": "CA", 
                "zip": "90210"
            },
            "pizzas": [
                {
                    "size": "medium",
                    "crust": "thick",
                    "toppings": ["sausage", "peppers"],
                    "quantity": 2
                }
            ],
            "payment_method": "cash",
            "user_input": "Please validate my order"
        })
        
        # Mock all validation components
        with patch.object(pizza_agent.address_validator, 'validate_address') as mock_addr:
            with patch.object(pizza_agent.order_validator, 'validate_order') as mock_order:
                with patch.object(pizza_agent.payment_validator, 'validate_payment_method') as mock_payment:
                    with patch.object(pizza_agent.llm, 'invoke') as mock_llm:
                        
                        # Configure mocks for successful validation
                        mock_addr.return_value = {
                            "is_valid": True,
                            "standardized_address": "789 Pine Ave, Testtown, CA 90210",
                            "delivery_feasible": True,
                            "errors": [], "warnings": []
                        }
                        
                        mock_order.return_value = {
                            "is_valid": True,
                            "validated_order": {"totals": {"total": 31.98}},
                            "calculated_total": 31.98,
                            "errors": [], "warnings": []
                        }
                        
                        mock_payment.return_value = {
                            "is_valid": True,
                            "errors": [], "warnings": []
                        }
                        
                        # Mock LLM response
                        mock_response = Mock()
                        mock_response.content = "Perfect! Your order is validated and ready. The total is $31.98 for cash payment."
                        mock_llm.return_value = mock_response
                        
                        # Run validation handler
                        result_state = await pizza_agent._handle_validate_inputs(initial_state)
                        
                        # Verify validation completed successfully
                        assert result_state["current_state"] == "validate_inputs"
                        assert "validation_status" in result_state
                        assert result_state["next_state"] == "process_payment"
                        assert "Perfect!" in result_state["agent_response"]


if __name__ == "__main__":
    """
    Run agent validation integration tests.
    
    Usage:
        python -m pytest tests/test_agent_validation_integration.py -v
    """
    pytest.main([__file__, "-v"])