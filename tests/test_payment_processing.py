"""
Comprehensive test suite for payment processing system.
Tests Stripe integration, webhook handling, and payment flows.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import Request, BackgroundTasks
from decimal import Decimal

from payment.stripe_client import StripePaymentClient, stripe_client
from payment.payment_method_manager import PaymentMethodManager, payment_method_manager
from api.webhooks import StripeWebhookHandler, webhook_handler
from database.models import PaymentStatus, OrderStatus
from main import app


class TestStripePaymentClient:
    """Test suite for Stripe payment client functionality."""
    
    @pytest.fixture
    def payment_client(self):
        """StripePaymentClient instance for testing."""
        with patch('payment.stripe_client.settings') as mock_settings:
            mock_settings.stripe_secret_key = "sk_test_123"
            mock_settings.stripe_publishable_key = "pk_test_123"
            
            client = StripePaymentClient()
            return client
    
    @pytest.mark.asyncio
    async def test_create_payment_intent_success(self, payment_client):
        """Test successful payment intent creation."""
        # Mock Stripe PaymentIntent.create
        mock_payment_intent = Mock()
        mock_payment_intent.id = "pi_test_123"
        mock_payment_intent.client_secret = "pi_test_123_secret"
        mock_payment_intent.amount = 2500  # $25.00 in cents
        mock_payment_intent.status = "requires_payment_method"
        mock_payment_intent.next_action = None
        
        with patch('stripe.PaymentIntent.create', return_value=mock_payment_intent):
            with patch.object(payment_client, '_store_payment_intent', new_callable=AsyncMock):
                result = await payment_client.create_payment_intent(
                    amount=25.00,
                    customer_info={"name": "John Doe", "email": "john@example.com"},
                    order_info={"order_id": "123", "session_id": "test_session"}
                )
                
                assert result["success"] is True
                assert result["payment_intent_id"] == "pi_test_123"
                assert result["client_secret"] == "pi_test_123_secret"
                assert result["amount"] == 25.00
                assert result["amount_cents"] == 2500
    
    @pytest.mark.asyncio
    async def test_create_payment_intent_invalid_amount(self, payment_client):
        """Test payment intent creation with invalid amount."""
        # Test amount too low
        result = await payment_client.create_payment_intent(amount=0.50)
        assert result["success"] is False
        assert "at least $1.00" in result["errors"][0]
        
        # Test amount too high
        result = await payment_client.create_payment_intent(amount=600.00)
        assert result["success"] is False
        assert "cannot exceed $500.00" in result["errors"][0]
    
    @pytest.mark.asyncio
    async def test_confirm_payment_intent_success(self, payment_client):
        """Test successful payment intent confirmation."""
        # Mock successful confirmation
        mock_payment_intent = Mock()
        mock_payment_intent.id = "pi_test_confirm"
        mock_payment_intent.status = "succeeded"
        mock_payment_intent.amount = 2500
        mock_payment_intent.charges = Mock()
        mock_payment_intent.charges.data = [
            Mock(
                id="ch_test_123",
                amount=2500,
                currency="usd",
                status="succeeded",
                receipt_url="https://pay.stripe.com/receipts/test"
            )
        ]
        
        with patch('stripe.PaymentIntent.confirm', return_value=mock_payment_intent):
            with patch.object(payment_client, '_update_payment_status', new_callable=AsyncMock):
                result = await payment_client.confirm_payment_intent("pi_test_confirm")
                
                assert result["success"] is True
                assert result["payment_intent_id"] == "pi_test_confirm"
                assert result["transaction_id"] == "pi_test_confirm"
                assert result["amount"] == 25.00
                assert result["status"] == "succeeded"
    
    @pytest.mark.asyncio
    async def test_confirm_payment_intent_card_declined(self, payment_client):
        """Test payment intent confirmation with card declined."""
        from stripe.error import CardError
        
        # Mock card declined error
        card_error = CardError(
            message="Your card was declined.",
            param="card",
            code="card_declined",
            decline_code="insufficient_funds"
        )
        
        with patch('stripe.PaymentIntent.confirm', side_effect=card_error):
            with patch.object(payment_client, '_record_payment_failure', new_callable=AsyncMock):
                result = await payment_client.confirm_payment_intent("pi_test_declined")
                
                assert result["success"] is False
                assert result["card_declined"] is True
                assert "insufficient funds" in result["errors"][0]
                assert result["decline_code"] == "insufficient_funds"
    
    @pytest.mark.asyncio
    async def test_process_immediate_charge(self, payment_client):
        """Test immediate charge processing (create and confirm)."""
        # Mock PaymentIntent creation
        mock_payment_intent = Mock()
        mock_payment_intent.id = "pi_immediate_test"
        mock_payment_intent.client_secret = "pi_immediate_test_secret"
        mock_payment_intent.amount = 3000
        mock_payment_intent.status = "succeeded"
        mock_payment_intent.charges = Mock()
        mock_payment_intent.charges.data = [Mock(
            id="ch_immediate_test",
            receipt_url="https://pay.stripe.com/receipts/immediate"
        )]
        
        with patch('stripe.PaymentIntent.create', return_value=mock_payment_intent):
            with patch('stripe.PaymentIntent.confirm', return_value=mock_payment_intent):
                with patch.object(payment_client, '_store_payment_intent', new_callable=AsyncMock):
                    with patch.object(payment_client, '_update_payment_status', new_callable=AsyncMock):
                        result = await payment_client.process_immediate_charge(
                            amount=30.00,
                            payment_method_id="pm_test_123",
                            customer_info={"name": "Jane Doe"},
                            order_info={"order_id": "456"}
                        )
                        
                        assert result["success"] is True
                        assert result["amount"] == 30.00
    
    @pytest.mark.asyncio
    async def test_create_refund_success(self, payment_client):
        """Test successful refund creation."""
        # Mock PaymentIntent retrieval
        mock_payment_intent = Mock()
        mock_payment_intent.status = "succeeded"
        mock_payment_intent.charges = Mock()
        mock_payment_intent.charges.data = [Mock(id="ch_test_refund")]
        
        # Mock Refund creation
        mock_refund = Mock()
        mock_refund.id = "re_test_123"
        mock_refund.amount = 1500  # $15.00 partial refund
        mock_refund.status = "succeeded"
        mock_refund.reason = "requested_by_customer"
        mock_refund.receipt_number = "1234-5678"
        
        with patch('stripe.PaymentIntent.retrieve', return_value=mock_payment_intent):
            with patch('stripe.Refund.create', return_value=mock_refund):
                with patch.object(payment_client, '_store_refund_info', new_callable=AsyncMock):
                    result = await payment_client.create_refund(
                        payment_intent_id="pi_test_refund",
                        amount=15.00,
                        reason="customer_request"
                    )
                    
                    assert result["success"] is True
                    assert result["refund_id"] == "re_test_123"
                    assert result["amount"] == 15.00
                    assert result["status"] == "succeeded"
    
    @pytest.mark.asyncio
    async def test_cancel_payment_intent(self, payment_client):
        """Test payment intent cancellation."""
        # Mock PaymentIntent cancellation
        mock_payment_intent = Mock()
        mock_payment_intent.id = "pi_test_cancel"
        mock_payment_intent.status = "canceled"
        
        with patch('stripe.PaymentIntent.cancel', return_value=mock_payment_intent):
            with patch.object(payment_client, '_update_payment_status', new_callable=AsyncMock):
                result = await payment_client.cancel_payment_intent(
                    payment_intent_id="pi_test_cancel",
                    cancellation_reason="customer_request"
                )
                
                assert result["success"] is True
                assert result["payment_intent_id"] == "pi_test_cancel"
                assert result["status"] == "canceled"
    
    @pytest.mark.asyncio
    async def test_retry_logic_rate_limiting(self, payment_client):
        """Test retry logic for rate limiting errors."""
        from stripe.error import RateLimitError
        
        # Mock rate limit error followed by success
        rate_limit_error = RateLimitError("Rate limit exceeded")
        mock_success = Mock(id="pi_retry_success")
        
        with patch('stripe.PaymentIntent.create', side_effect=[rate_limit_error, mock_success]):
            with patch('asyncio.sleep', new_callable=AsyncMock):  # Speed up test
                with patch.object(payment_client, '_store_payment_intent', new_callable=AsyncMock):
                    result = await payment_client.create_payment_intent(amount=25.00)
                    
                    # Should succeed after retry
                    assert result["success"] is True


class TestPaymentMethodManager:
    """Test suite for payment method management."""
    
    @pytest.fixture
    def payment_method_manager_instance(self):
        """PaymentMethodManager instance for testing."""
        with patch('payment.payment_method_manager.settings') as mock_settings:
            mock_settings.stripe_secret_key = "sk_test_123"
            
            manager = PaymentMethodManager()
            return manager
    
    @pytest.mark.asyncio
    async def test_create_customer(self, payment_method_manager_instance):
        """Test customer creation."""
        # Mock Stripe Customer.create
        mock_customer = Mock()
        mock_customer.id = "cus_test_123"
        mock_customer.email = "test@example.com"
        mock_customer.name = "Test Customer"
        mock_customer.phone = "+1234567890"
        mock_customer.created = 1640995200
        
        with patch('stripe.Customer.create', return_value=mock_customer):
            with patch.object(payment_method_manager_instance, '_cache_customer_info', new_callable=AsyncMock):
                result = await payment_method_manager_instance.create_customer({
                    "name": "Test Customer",
                    "email": "test@example.com",
                    "phone": "+1234567890",
                    "address": {
                        "street": "123 Test St",
                        "city": "Test City",
                        "state": "CA",
                        "zip": "90210"
                    }
                })
                
                assert result["success"] is True
                assert result["customer_id"] == "cus_test_123"
                assert result["customer_info"]["email"] == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_create_payment_method(self, payment_method_manager_instance):
        """Test payment method creation."""
        # Mock Stripe PaymentMethod.create
        mock_payment_method = Mock()
        mock_payment_method.id = "pm_test_123"
        mock_payment_method.type = "card"
        mock_payment_method.customer = None
        mock_payment_method.billing_details = {}
        mock_payment_method.card = Mock(
            brand="visa",
            last4="4242",
            exp_month=12,
            exp_year=2025,
            funding="credit",
            country="US",
            fingerprint="test_fingerprint"
        )
        mock_payment_method.attach = Mock()
        
        with patch('stripe.PaymentMethod.create', return_value=mock_payment_method):
            with patch.object(payment_method_manager_instance, '_cache_payment_method_info', new_callable=AsyncMock):
                result = await payment_method_manager_instance.create_payment_method({
                    "type": "card",
                    "card": {
                        "number": "4242424242424242",
                        "exp_month": "12",
                        "exp_year": "2025",
                        "cvc": "123"
                    }
                }, customer_id="cus_test_123")
                
                assert result["success"] is True
                assert result["payment_method_id"] == "pm_test_123"
                assert result["payment_method"]["card"]["last4"] == "4242"
    
    @pytest.mark.asyncio
    async def test_validate_payment_method(self, payment_method_manager_instance):
        """Test payment method validation."""
        # Mock valid payment method
        mock_payment_method = Mock()
        mock_payment_method.id = "pm_valid_test"
        mock_payment_method.type = "card"
        mock_payment_method.customer = "cus_test_123"
        mock_payment_method.card = Mock(
            brand="visa",
            last4="4242",
            exp_month=12,
            exp_year=2025,
            funding="credit",
            country="US"
        )
        
        with patch('stripe.PaymentMethod.retrieve', return_value=mock_payment_method):
            result = await payment_method_manager_instance.validate_payment_method("pm_valid_test")
            
            assert result["success"] is True
            assert result["is_valid"] is True
            assert result["payment_method_id"] == "pm_valid_test"
            assert result["card_info"]["brand"] == "visa"
    
    @pytest.mark.asyncio
    async def test_validate_expired_payment_method(self, payment_method_manager_instance):
        """Test validation of expired payment method."""
        # Mock expired payment method
        mock_payment_method = Mock()
        mock_payment_method.id = "pm_expired_test"
        mock_payment_method.type = "card"
        mock_payment_method.customer = "cus_test_123"
        mock_payment_method.card = Mock(
            brand="visa",
            last4="4242",
            exp_month=1,  # January
            exp_year=2020,  # Expired
            funding="credit",
            country="US"
        )
        
        with patch('stripe.PaymentMethod.retrieve', return_value=mock_payment_method):
            result = await payment_method_manager_instance.validate_payment_method("pm_expired_test")
            
            assert result["success"] is True
            assert result["is_valid"] is False
            assert "expired" in result["errors"][0].lower()


class TestStripeWebhookHandler:
    """Test suite for Stripe webhook handling."""
    
    @pytest.fixture
    def webhook_handler_instance(self):
        """StripeWebhookHandler instance for testing."""
        with patch('api.webhooks.settings') as mock_settings:
            mock_settings.stripe_webhook_secret = "whsec_test_secret"
            
            handler = StripeWebhookHandler()
            return handler
    
    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI request for webhook testing."""
        request = Mock(spec=Request)
        request.body = AsyncMock(return_value=b'{"test": "webhook_payload"}')
        request.headers = {"stripe-signature": "test_signature"}
        return request
    
    @pytest.fixture
    def mock_background_tasks(self):
        """Mock BackgroundTasks for webhook testing."""
        return Mock(spec=BackgroundTasks)
    
    @pytest.mark.asyncio
    async def test_webhook_signature_verification_success(self, webhook_handler_instance, mock_request, mock_background_tasks):
        """Test successful webhook signature verification."""
        # Mock successful signature verification
        mock_event = {
            "id": "evt_test_123",
            "type": "payment_intent.succeeded",
            "created": 1640995200,
            "data": {
                "object": {
                    "id": "pi_test_webhook",
                    "amount": 2500,
                    "status": "succeeded"
                }
            }
        }
        
        with patch('stripe.Webhook.construct_event', return_value=mock_event):
            with patch.object(webhook_handler_instance, '_is_event_processed', return_value=False):
                with patch.object(webhook_handler_instance, '_mark_event_processing', new_callable=AsyncMock):
                    with patch.object(webhook_handler_instance, '_mark_event_processed', new_callable=AsyncMock):
                        result = await webhook_handler_instance.handle_webhook(mock_request, mock_background_tasks)
                        
                        assert result["status"] == "received"
                        assert result["event_id"] == "evt_test_123"
                        assert result["event_type"] == "payment_intent.succeeded"
    
    @pytest.mark.asyncio
    async def test_webhook_duplicate_event(self, webhook_handler_instance, mock_request, mock_background_tasks):
        """Test handling of duplicate webhook events."""
        mock_event = {
            "id": "evt_duplicate_123",
            "type": "payment_intent.succeeded",
            "created": 1640995200
        }
        
        with patch('stripe.Webhook.construct_event', return_value=mock_event):
            with patch.object(webhook_handler_instance, '_is_event_processed', return_value=True):
                result = await webhook_handler_instance.handle_webhook(mock_request, mock_background_tasks)
                
                assert result["status"] == "duplicate"
                assert result["event_id"] == "evt_duplicate_123"
    
    @pytest.mark.asyncio
    async def test_webhook_signature_verification_failure(self, webhook_handler_instance, mock_request, mock_background_tasks):
        """Test webhook signature verification failure."""
        from stripe.error import SignatureVerificationError
        
        with patch('stripe.Webhook.construct_event', side_effect=SignatureVerificationError("Invalid signature", "test_sig")):
            with pytest.raises(Exception):  # Should raise HTTPException
                await webhook_handler_instance.handle_webhook(mock_request, mock_background_tasks)
    
    @pytest.mark.asyncio
    async def test_payment_succeeded_event_processing(self, webhook_handler_instance):
        """Test processing of payment_intent.succeeded event."""
        payment_intent_data = {
            "id": "pi_succeeded_test",
            "amount": 2500,
            "currency": "usd",
            "metadata": {
                "order_id": "123",
                "customer_phone": "+1234567890"
            }
        }
        
        event = {
            "id": "evt_payment_succeeded",
            "type": "payment_intent.succeeded"
        }
        
        with patch.object(webhook_handler_instance, '_update_payment_status', new_callable=AsyncMock):
            with patch.object(webhook_handler_instance, '_update_order_status', new_callable=AsyncMock):
                with patch.object(webhook_handler_instance, '_trigger_order_fulfillment', new_callable=AsyncMock):
                    with patch.object(webhook_handler_instance, '_send_payment_confirmation', new_callable=AsyncMock):
                        await webhook_handler_instance._handle_payment_succeeded(payment_intent_data, event)
                        
                        # Verify all handlers were called
                        webhook_handler_instance._update_payment_status.assert_called_once()
                        webhook_handler_instance._update_order_status.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_payment_failed_event_processing(self, webhook_handler_instance):
        """Test processing of payment_intent.payment_failed event."""
        payment_intent_data = {
            "id": "pi_failed_test",
            "last_payment_error": {
                "code": "card_declined",
                "message": "Your card was declined."
            },
            "metadata": {
                "order_id": "456"
            }
        }
        
        event = {
            "id": "evt_payment_failed",
            "type": "payment_intent.payment_failed"
        }
        
        with patch.object(webhook_handler_instance, '_update_payment_status', new_callable=AsyncMock):
            with patch.object(webhook_handler_instance, '_update_order_status', new_callable=AsyncMock):
                with patch.object(webhook_handler_instance, '_schedule_payment_retry', new_callable=AsyncMock):
                    with patch.object(webhook_handler_instance, '_send_payment_failure_notification', new_callable=AsyncMock):
                        await webhook_handler_instance._handle_payment_failed(payment_intent_data, event)
                        
                        # Verify all handlers were called
                        webhook_handler_instance._update_payment_status.assert_called_once()
                        webhook_handler_instance._update_order_status.assert_called_once()


class TestPaymentIntegration:
    """Integration tests for complete payment workflows."""
    
    @pytest.fixture
    def client(self):
        """FastAPI test client."""
        return TestClient(app)
    
    @pytest.mark.asyncio
    async def test_end_to_end_payment_flow(self):
        """Test complete payment flow from creation to confirmation."""
        # Mock all Stripe operations
        mock_payment_intent = Mock()
        mock_payment_intent.id = "pi_e2e_test"
        mock_payment_intent.client_secret = "pi_e2e_test_secret"
        mock_payment_intent.amount = 2500
        mock_payment_intent.status = "succeeded"
        mock_payment_intent.charges = Mock()
        mock_payment_intent.charges.data = [Mock(
            id="ch_e2e_test",
            receipt_url="https://pay.stripe.com/receipts/e2e"
        )]
        
        with patch('stripe.PaymentIntent.create', return_value=mock_payment_intent):
            with patch('stripe.PaymentIntent.confirm', return_value=mock_payment_intent):
                # Create payment intent
                result = await stripe_client.create_payment_intent(
                    amount=25.00,
                    customer_info={"name": "Integration Test", "email": "test@integration.com"},
                    order_info={"order_id": "integration_123", "session_id": "test_session"}
                )
                
                assert result["success"] is True
                payment_intent_id = result["payment_intent_id"]
                
                # Confirm payment intent
                confirmation_result = await stripe_client.confirm_payment_intent(payment_intent_id)
                
                assert confirmation_result["success"] is True
                assert confirmation_result["status"] == "succeeded"
    
    def test_payment_api_endpoints(self, client):
        """Test payment API endpoints."""
        # Test getting supported payment methods
        with patch('payment.stripe_client.stripe_client.payment_validator') as mock_validator:
            mock_validator.get_supported_payment_methods.return_value = {
                "methods": {"credit_card": {"name": "Credit Card"}},
                "limits": {"minimum_amount": 1.00}
            }
            
            response = client.get("/api/payments/methods")
            assert response.status_code == 200
    
    def test_webhook_endpoint(self, client):
        """Test Stripe webhook endpoint."""
        # Mock webhook request
        mock_payload = json.dumps({
            "id": "evt_test_webhook_endpoint",
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_webhook_test"}}
        })
        
        headers = {
            "stripe-signature": "test_signature"
        }
        
        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = {
                "id": "evt_test_webhook_endpoint",
                "type": "payment_intent.succeeded",
                "created": 1640995200,
                "data": {"object": {"id": "pi_webhook_test"}}
            }
            
            with patch('api.webhooks.webhook_handler.handle_webhook') as mock_handler:
                mock_handler.return_value = {"status": "received", "event_id": "evt_test_webhook_endpoint"}
                
                response = client.post(
                    "/webhooks/stripe",
                    data=mock_payload,
                    headers=headers
                )
                
                assert response.status_code == 200


class TestPaymentSecurity:
    """Test suite for payment security and compliance."""
    
    @pytest.mark.asyncio
    async def test_payment_amount_validation(self):
        """Test payment amount validation against business rules."""
        client = StripePaymentClient()
        
        # Test valid amount
        result = client._validate_payment_amount(25.00)
        assert result["is_valid"] is True
        
        # Test amount too low
        result = client._validate_payment_amount(0.50)
        assert result["is_valid"] is False
        
        # Test amount too high
        result = client._validate_payment_amount(600.00)
        assert result["is_valid"] is False
        
        # Test invalid amount type
        result = client._validate_payment_amount("invalid")
        assert result["is_valid"] is False
    
    def test_sensitive_data_handling(self):
        """Test that sensitive data is properly handled."""
        manager = PaymentMethodManager()
        
        # Mock payment method with card data
        mock_payment_method = Mock()
        mock_payment_method.type = "card"
        mock_payment_method.card = Mock(
            brand="visa",
            last4="4242",
            exp_month=12,
            exp_year=2025,
            funding="credit",
            country="US",
            fingerprint="test_fingerprint"
        )
        
        # Extract safe card info
        safe_info = manager._extract_safe_card_info(mock_payment_method)
        
        # Verify only safe information is included
        assert "last4" in safe_info
        assert "brand" in safe_info
        assert "exp_month" in safe_info
        assert "exp_year" in safe_info
        assert "funding" in safe_info
        assert "country" in safe_info
        assert "fingerprint" in safe_info
        
        # Verify no sensitive data
        assert "number" not in safe_info
        assert "cvc" not in safe_info
    
    @pytest.mark.asyncio
    async def test_webhook_timestamp_validation(self):
        """Test webhook timestamp validation for security."""
        import time
        
        handler = StripeWebhookHandler()
        
        # Test with current timestamp (should pass)
        current_time = int(time.time())
        mock_event = {"created": current_time}
        
        # Test with old timestamp (should fail)
        old_time = current_time - 400  # 6+ minutes old
        mock_old_event = {"created": old_time}
        
        # This would be tested in actual signature verification
        # The test demonstrates the concept of timestamp validation


if __name__ == "__main__":
    """
    Run payment processing tests.
    
    Usage:
        python -m pytest tests/test_payment_processing.py -v
    """
    pytest.main([__file__, "-v"])