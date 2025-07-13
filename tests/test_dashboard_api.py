"""
Test suite for Dashboard API endpoints.
Tests authentication, endpoints functionality, and WebSocket connections.
"""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from fastapi.testclient import TestClient
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..main import app
from ..database.models import Base, Order, OrderStatus, PaymentStatus
from ..database import get_db_session
from ..api.auth import auth_manager, UserRole
from ..api.websocket import websocket_manager


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_dashboard.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database dependency for testing."""
    try:
        db = TestSessionLocal()
        yield db
    finally:
        db.close()


# Override dependency
app.dependency_overrides[get_db_session] = override_get_db


@pytest.fixture(scope="module")
def test_client():
    """Create test client for API testing."""
    # Create test database tables
    Base.metadata.create_all(bind=test_engine)
    
    with TestClient(app) as client:
        yield client
    
    # Clean up
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def test_db():
    """Create test database session."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def admin_token():
    """Get admin authentication token."""
    admin_user = auth_manager.users["admin"]
    return auth_manager.create_access_token(admin_user)


@pytest.fixture
def staff_token():
    """Get staff authentication token."""
    staff_user = auth_manager.users["staff"]
    return auth_manager.create_access_token(staff_user)


@pytest.fixture
def sample_orders(test_db):
    """Create sample orders for testing."""
    orders = []
    
    # Create test orders
    for i in range(5):
        order = Order(
            customer_name=f"Test Customer {i}",
            phone_number=f"555-000-{i:04d}",
            address=f"{i+1}00 Test St, Test City, CA",
            order_details={
                "pizzas": [
                    {
                        "size": "large",
                        "toppings": ["pepperoni", "cheese"],
                        "quantity": 1,
                        "price": 18.99
                    }
                ]
            },
            total_amount=18.99,
            estimated_delivery=30,
            payment_method="card",
            payment_status=PaymentStatus.SUCCEEDED.value,
            order_status=OrderStatus.PREPARING.value if i < 3 else OrderStatus.DELIVERED.value,
            interface_type="web",
            created_at=datetime.utcnow()
        )
        test_db.add(order)
        orders.append(order)
    
    test_db.commit()
    return orders


class TestAuthentication:
    """Test authentication and authorization."""
    
    def test_health_endpoint_no_auth(self, test_client):
        """Test that health endpoint doesn't require authentication."""
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_dashboard_status_requires_auth(self, test_client):
        """Test that dashboard status requires authentication."""
        response = test_client.get("/api/dashboard/status")
        assert response.status_code == 401
    
    def test_dashboard_status_with_valid_token(self, test_client, admin_token):
        """Test dashboard status with valid authentication."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.get("/api/dashboard/status", headers=headers)
        assert response.status_code == 200
        assert response.json()["success"] is True
    
    def test_invalid_token(self, test_client):
        """Test API access with invalid token."""
        headers = {"Authorization": "Bearer invalid-token"}
        response = test_client.get("/api/dashboard/status", headers=headers)
        assert response.status_code == 401
    
    def test_dev_token_access(self, test_client):
        """Test development token access."""
        headers = {"Authorization": "Bearer dashboard-dev-token"}
        response = test_client.get("/api/dashboard/status", headers=headers)
        assert response.status_code == 200


class TestDashboardEndpoints:
    """Test dashboard API endpoints."""
    
    def test_dashboard_status(self, test_client, admin_token, sample_orders):
        """Test dashboard status endpoint."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.get("/api/dashboard/status", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "system_status" in data["data"]
        assert "agent_status" in data["data"]
        assert "order_metrics" in data["data"]
    
    def test_active_tickets(self, test_client, admin_token, sample_orders):
        """Test active tickets endpoint."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.get("/api/tickets/active", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "summary" in data
        
        # Should return preparing orders (3 in sample data)
        active_tickets = data["data"]
        assert len(active_tickets) == 3
    
    def test_active_tickets_with_filters(self, test_client, admin_token, sample_orders):
        """Test active tickets with status filter."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        params = {"status_filter": ["preparing"]}
        response = test_client.get("/api/tickets/active", headers=headers, params=params)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # All returned tickets should be preparing
        tickets = data["data"]
        for ticket in tickets:
            assert ticket["order_status"] == "preparing"
    
    def test_complete_ticket(self, test_client, admin_token, sample_orders):
        """Test ticket completion endpoint."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get a preparing order
        preparing_order = None
        for order in sample_orders:
            if order.order_status == OrderStatus.PREPARING.value:
                preparing_order = order
                break
        
        assert preparing_order is not None
        
        # Update order status to out for delivery first
        preparing_order.order_status = OrderStatus.OUT_FOR_DELIVERY.value
        
        # Complete the ticket
        response = test_client.post(
            f"/api/tickets/{preparing_order.id}/complete",
            headers=headers,
            json={"actual_delivery_time": 25}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] == OrderStatus.DELIVERED.value
    
    def test_complete_invalid_ticket(self, test_client, admin_token):
        """Test completing non-existent ticket."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.post("/api/tickets/99999/complete", headers=headers)
        
        assert response.status_code == 404
    
    def test_agent_stats(self, test_client, admin_token, sample_orders):
        """Test agent statistics endpoint."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.get("/api/agents/stats", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "performance_metrics" in data["data"]
        assert "usage_statistics" in data["data"]
        assert "capacity_metrics" in data["data"]


class TestMetricsEndpoints:
    """Test metrics API endpoints."""
    
    def test_order_metrics(self, test_client, admin_token, sample_orders):
        """Test order metrics endpoint."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.get("/api/metrics/orders", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "totals" in data["data"]
        assert "status_breakdown" in data["data"]
    
    def test_revenue_metrics(self, test_client, admin_token, sample_orders):
        """Test revenue metrics endpoint."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.get("/api/metrics/revenue", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "summary" in data["data"]
        assert "breakdown" in data["data"]
    
    def test_metrics_with_period(self, test_client, admin_token, sample_orders):
        """Test metrics with different time periods."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        for period in ["hour", "day", "week", "month"]:
            response = test_client.get(f"/api/metrics/orders?period={period}", headers=headers)
            assert response.status_code == 200
            
            data = response.json()
            assert data["success"] is True
            assert data["data"]["period"]["type"] == period
    
    def test_metrics_summary(self, test_client, admin_token, sample_orders):
        """Test comprehensive metrics summary."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.get("/api/metrics/summary", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "orders" in data["data"]
        assert "revenue" in data["data"]
        assert "performance" in data["data"]


class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def test_rate_limiting_headers(self, test_client, admin_token):
        """Test that rate limiting headers are present."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.get("/api/dashboard/status", headers=headers)
        
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
    
    def test_request_id_header(self, test_client, admin_token):
        """Test that request ID header is present."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.get("/api/dashboard/status", headers=headers)
        
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers


class TestErrorHandling:
    """Test error handling and responses."""
    
    def test_404_error(self, test_client):
        """Test 404 error handling."""
        response = test_client.get("/api/nonexistent")
        assert response.status_code == 404
    
    def test_method_not_allowed(self, test_client, admin_token):
        """Test 405 error for unsupported methods."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.patch("/api/dashboard/status", headers=headers)
        assert response.status_code == 405
    
    def test_validation_error(self, test_client, admin_token):
        """Test validation error handling."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.get("/api/metrics/orders?period=invalid", headers=headers)
        assert response.status_code == 422


class TestWebSocketStats:
    """Test WebSocket statistics endpoint."""
    
    def test_websocket_stats(self, test_client, admin_token):
        """Test WebSocket statistics endpoint."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.get("/api/ws/stats", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "active_connections" in data["data"]
    
    def test_websocket_broadcast_endpoint(self, test_client, admin_token):
        """Test WebSocket broadcast endpoint."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        broadcast_data = {
            "message_type": "system_alert",
            "message_data": {
                "alert_type": "test",
                "message": "Test broadcast",
                "severity": "info"
            }
        }
        
        response = test_client.post("/api/ws/broadcast", headers=headers, json=broadcast_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True


# Integration tests
class TestIntegration:
    """Integration tests for complete workflows."""
    
    def test_order_lifecycle(self, test_client, admin_token, test_db):
        """Test complete order lifecycle through API."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create a test order
        order = Order(
            customer_name="Integration Test Customer",
            phone_number="555-TEST",
            address="123 Integration Test St",
            order_details={"pizzas": [{"size": "large", "toppings": ["cheese"], "quantity": 1, "price": 15.99}]},
            total_amount=15.99,
            estimated_delivery=30,
            payment_method="card",
            payment_status=PaymentStatus.SUCCEEDED.value,
            order_status=OrderStatus.PREPARING.value,
            interface_type="web"
        )
        test_db.add(order)
        test_db.commit()
        
        # Check it appears in active tickets
        response = test_client.get("/api/tickets/active", headers=headers)
        assert response.status_code == 200
        tickets = response.json()["data"]
        
        # Find our order
        our_ticket = None
        for ticket in tickets:
            if ticket["customer_name"] == "Integration Test Customer":
                our_ticket = ticket
                break
        
        assert our_ticket is not None
        assert our_ticket["order_status"] == "preparing"
        
        # Update to out for delivery
        order.order_status = OrderStatus.OUT_FOR_DELIVERY.value
        test_db.commit()
        
        # Complete the order
        response = test_client.post(f"/api/tickets/{order.id}/complete", headers=headers)
        assert response.status_code == 200
        
        completion_data = response.json()
        assert completion_data["success"] is True
        assert completion_data["data"]["status"] == OrderStatus.DELIVERED.value


if __name__ == "__main__":
    """Run tests directly."""
    pytest.main([__file__, "-v"])