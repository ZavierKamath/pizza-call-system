"""
WebSocket manager for real-time dashboard updates.
Handles connections, broadcasting, and message routing for live updates.
"""

import logging
import json
import asyncio
from typing import List, Dict, Any, Set, Optional
from datetime import datetime
from enum import Enum

from fastapi import WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..config.logging_config import get_logger
from ..config.settings import settings

# Configure logging
logger = get_logger(__name__)

# Security dependency
security = HTTPBearer()


class MessageType(Enum):
    """WebSocket message types for dashboard updates."""
    ORDER_UPDATE = "order_update"
    ORDER_STATUS_CHANGE = "order_status_change"
    NEW_ORDER = "new_order"
    ORDER_COMPLETED = "order_completed"
    DELIVERY_UPDATE = "delivery_update"
    SYSTEM_ALERT = "system_alert"
    PERFORMANCE_METRICS = "performance_metrics"
    SESSION_UPDATE = "session_update"
    CONNECTION_STATUS = "connection_status"


class ConnectionManager:
    """
    WebSocket connection manager for dashboard clients.
    Handles connection lifecycle, authentication, and message broadcasting.
    """
    
    def __init__(self):
        # Active connections by client ID
        self.active_connections: Dict[str, WebSocket] = {}
        
        # Connection metadata
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Subscription management (clients can subscribe to specific event types)
        self.subscriptions: Dict[str, Set[MessageType]] = {}
        
        # Connection statistics
        self.connection_count = 0
        self.total_connections = 0
        self.messages_sent = 0
        
        logger.info("WebSocket ConnectionManager initialized")
    
    async def connect(
        self, 
        websocket: WebSocket, 
        client_id: str,
        user_info: Optional[Dict[str, Any]] = None
    ):
        """
        Accept a new WebSocket connection.
        
        Args:
            websocket: WebSocket instance
            client_id: Unique client identifier
            user_info: Optional user authentication information
        """
        try:
            await websocket.accept()
            
            # Store connection
            self.active_connections[client_id] = websocket
            
            # Store metadata
            self.connection_metadata[client_id] = {
                "connected_at": datetime.utcnow().isoformat(),
                "user_info": user_info or {},
                "message_count": 0,
                "last_activity": datetime.utcnow().isoformat()
            }
            
            # Default subscriptions (all message types)
            self.subscriptions[client_id] = set(MessageType)
            
            # Update statistics
            self.connection_count += 1
            self.total_connections += 1
            
            logger.info(f"WebSocket client {client_id} connected. Active connections: {self.connection_count}")
            
            # Send welcome message
            await self.send_personal_message(client_id, {
                "type": MessageType.CONNECTION_STATUS.value,
                "data": {
                    "status": "connected",
                    "client_id": client_id,
                    "server_time": datetime.utcnow().isoformat(),
                    "available_subscriptions": [mt.value for mt in MessageType]
                },
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Notify other clients about connection
            await self.broadcast({
                "type": MessageType.CONNECTION_STATUS.value,
                "data": {
                    "event": "client_connected",
                    "active_connections": self.connection_count
                },
                "timestamp": datetime.utcnow().isoformat()
            }, exclude=[client_id])
            
        except Exception as e:
            logger.error(f"Error connecting WebSocket client {client_id}: {str(e)}")
            raise
    
    def disconnect(self, client_id: str):
        """
        Handle client disconnection.
        
        Args:
            client_id: Client identifier to disconnect
        """
        try:
            if client_id in self.active_connections:
                # Remove connection
                del self.active_connections[client_id]
                
                # Clean up metadata and subscriptions
                if client_id in self.connection_metadata:
                    del self.connection_metadata[client_id]
                if client_id in self.subscriptions:
                    del self.subscriptions[client_id]
                
                # Update statistics
                self.connection_count -= 1
                
                logger.info(f"WebSocket client {client_id} disconnected. Active connections: {self.connection_count}")
                
                # Notify other clients about disconnection (async task)
                asyncio.create_task(self.broadcast({
                    "type": MessageType.CONNECTION_STATUS.value,
                    "data": {
                        "event": "client_disconnected",
                        "active_connections": self.connection_count
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }, exclude=[client_id]))
                
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket client {client_id}: {str(e)}")
    
    async def send_personal_message(self, client_id: str, message: Dict[str, Any]):
        """
        Send a message to a specific client.
        
        Args:
            client_id: Target client identifier
            message: Message data to send
        """
        try:
            if client_id in self.active_connections:
                websocket = self.active_connections[client_id]
                
                # Add message ID and ensure timestamp
                message_with_id = {
                    "id": f"msg_{int(datetime.utcnow().timestamp() * 1000)}",
                    **message,
                    "timestamp": message.get("timestamp", datetime.utcnow().isoformat())
                }
                
                await websocket.send_text(json.dumps(message_with_id))
                
                # Update statistics
                self.messages_sent += 1
                if client_id in self.connection_metadata:
                    self.connection_metadata[client_id]["message_count"] += 1
                    self.connection_metadata[client_id]["last_activity"] = datetime.utcnow().isoformat()
                
                logger.debug(f"Message sent to client {client_id}: {message['type']}")
                
        except WebSocketDisconnect:
            logger.info(f"Client {client_id} disconnected during message send")
            self.disconnect(client_id)
        except Exception as e:
            logger.error(f"Error sending message to client {client_id}: {str(e)}")
            # Don't disconnect on send errors, client might still be connected
    
    async def broadcast(
        self, 
        message: Dict[str, Any], 
        message_type: Optional[MessageType] = None,
        exclude: Optional[List[str]] = None
    ):
        """
        Broadcast a message to all connected clients.
        
        Args:
            message: Message data to broadcast
            message_type: Optional message type for subscription filtering
            exclude: Optional list of client IDs to exclude from broadcast
        """
        try:
            exclude = exclude or []
            
            # Determine message type for subscription filtering
            if message_type is None and "type" in message:
                try:
                    message_type = MessageType(message["type"])
                except ValueError:
                    message_type = None
            
            # Add message ID and ensure timestamp
            message_with_id = {
                "id": f"broadcast_{int(datetime.utcnow().timestamp() * 1000)}",
                **message,
                "timestamp": message.get("timestamp", datetime.utcnow().isoformat())
            }
            
            # Send to all subscribed clients
            disconnected_clients = []
            sent_count = 0
            
            for client_id, websocket in self.active_connections.items():
                if client_id in exclude:
                    continue
                
                # Check subscription
                if message_type and client_id in self.subscriptions:
                    if message_type not in self.subscriptions[client_id]:
                        continue
                
                try:
                    await websocket.send_text(json.dumps(message_with_id))
                    sent_count += 1
                    
                    # Update client statistics
                    if client_id in self.connection_metadata:
                        self.connection_metadata[client_id]["message_count"] += 1
                        self.connection_metadata[client_id]["last_activity"] = datetime.utcnow().isoformat()
                    
                except WebSocketDisconnect:
                    logger.info(f"Client {client_id} disconnected during broadcast")
                    disconnected_clients.append(client_id)
                except Exception as e:
                    logger.error(f"Error broadcasting to client {client_id}: {str(e)}")
                    disconnected_clients.append(client_id)
            
            # Clean up disconnected clients
            for client_id in disconnected_clients:
                self.disconnect(client_id)
            
            # Update statistics
            self.messages_sent += sent_count
            
            logger.debug(f"Broadcast message sent to {sent_count} clients: {message['type']}")
            
        except Exception as e:
            logger.error(f"Error broadcasting message: {str(e)}")
    
    async def update_subscriptions(self, client_id: str, subscriptions: List[str]):
        """
        Update client's event subscriptions.
        
        Args:
            client_id: Client identifier
            subscriptions: List of message types to subscribe to
        """
        try:
            if client_id not in self.active_connections:
                logger.warning(f"Cannot update subscriptions for disconnected client {client_id}")
                return
            
            # Convert string subscriptions to MessageType enum
            new_subscriptions = set()
            for sub in subscriptions:
                try:
                    new_subscriptions.add(MessageType(sub))
                except ValueError:
                    logger.warning(f"Invalid subscription type: {sub}")
            
            # Update subscriptions
            self.subscriptions[client_id] = new_subscriptions
            
            logger.info(f"Updated subscriptions for client {client_id}: {subscriptions}")
            
            # Send confirmation
            await self.send_personal_message(client_id, {
                "type": MessageType.CONNECTION_STATUS.value,
                "data": {
                    "event": "subscriptions_updated",
                    "subscriptions": subscriptions
                },
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error updating subscriptions for client {client_id}: {str(e)}")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get current connection statistics.
        
        Returns:
            dict: Connection statistics
        """
        return {
            "active_connections": self.connection_count,
            "total_connections": self.total_connections,
            "messages_sent": self.messages_sent,
            "clients": {
                client_id: {
                    "connected_at": metadata["connected_at"],
                    "message_count": metadata["message_count"],
                    "last_activity": metadata["last_activity"],
                    "subscriptions": [sub.value for sub in self.subscriptions.get(client_id, set())]
                }
                for client_id, metadata in self.connection_metadata.items()
            }
        }
    
    async def send_system_alert(self, alert_type: str, message: str, severity: str = "info"):
        """
        Send system alert to all connected clients.
        
        Args:
            alert_type: Type of alert (e.g., "performance", "error", "maintenance")
            message: Alert message
            severity: Alert severity ("info", "warning", "error", "critical")
        """
        try:
            alert_message = {
                "type": MessageType.SYSTEM_ALERT.value,
                "data": {
                    "alert_type": alert_type,
                    "message": message,
                    "severity": severity,
                    "timestamp": datetime.utcnow().isoformat()
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.broadcast(alert_message, MessageType.SYSTEM_ALERT)
            
            logger.info(f"System alert sent: {alert_type} - {message}")
            
        except Exception as e:
            logger.error(f"Error sending system alert: {str(e)}")


# Global connection manager instance
websocket_manager = ConnectionManager()


# WebSocket authentication dependency
async def authenticate_websocket(
    websocket: WebSocket,
    token: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Authenticate WebSocket connection using token.
    
    Args:
        websocket: WebSocket instance
        token: Optional authentication token
        
    Returns:
        dict: User information if authenticated, None otherwise
    """
    try:
        if not token:
            # Allow anonymous connections for development
            if settings.environment == "development":
                return {"user_id": "anonymous", "role": "guest"}
            return None
        
        # TODO: Implement proper JWT token validation
        # For now, use simple token validation
        if token == "dashboard-dev-token" or token.startswith("dev-"):
            return {
                "user_id": "dashboard-user",
                "role": "admin",
                "permissions": ["read:orders", "write:orders", "read:analytics"]
            }
        
        if settings.dashboard_api_key and token == settings.dashboard_api_key:
            return {
                "user_id": "api-user",
                "role": "api",
                "permissions": ["read:orders", "write:orders"]
            }
        
        return None
        
    except Exception as e:
        logger.error(f"WebSocket authentication error: {str(e)}")
        return None


# WebSocket helper functions for order events

async def notify_new_order(order_data: Dict[str, Any]):
    """
    Notify all clients about a new order.
    
    Args:
        order_data: Order information
    """
    try:
        message = {
            "type": MessageType.NEW_ORDER.value,
            "data": {
                "order_id": order_data["id"],
                "customer_name": order_data["customer_name"],
                "total_amount": order_data["total_amount"],
                "order_status": order_data["order_status"],
                "interface_type": order_data["interface_type"],
                "created_at": order_data["created_at"]
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await websocket_manager.broadcast(message, MessageType.NEW_ORDER)
        
    except Exception as e:
        logger.error(f"Error notifying new order: {str(e)}")


async def notify_order_status_change(
    order_id: int, 
    old_status: str, 
    new_status: str,
    customer_name: str = None
):
    """
    Notify all clients about order status change.
    
    Args:
        order_id: Order identifier
        old_status: Previous order status
        new_status: New order status
        customer_name: Optional customer name
    """
    try:
        message = {
            "type": MessageType.ORDER_STATUS_CHANGE.value,
            "data": {
                "order_id": order_id,
                "old_status": old_status,
                "new_status": new_status,
                "customer_name": customer_name,
                "updated_at": datetime.utcnow().isoformat()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await websocket_manager.broadcast(message, MessageType.ORDER_STATUS_CHANGE)
        
    except Exception as e:
        logger.error(f"Error notifying order status change: {str(e)}")


async def notify_delivery_update(delivery_data: Dict[str, Any]):
    """
    Notify all clients about delivery updates.
    
    Args:
        delivery_data: Delivery update information
    """
    try:
        message = {
            "type": MessageType.DELIVERY_UPDATE.value,
            "data": delivery_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await websocket_manager.broadcast(message, MessageType.DELIVERY_UPDATE)
        
    except Exception as e:
        logger.error(f"Error notifying delivery update: {str(e)}")


async def send_performance_metrics(metrics_data: Dict[str, Any]):
    """
    Send performance metrics to subscribed clients.
    
    Args:
        metrics_data: Performance metrics data
    """
    try:
        message = {
            "type": MessageType.PERFORMANCE_METRICS.value,
            "data": metrics_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await websocket_manager.broadcast(message, MessageType.PERFORMANCE_METRICS)
        
    except Exception as e:
        logger.error(f"Error sending performance metrics: {str(e)}")


# Export the global manager
__all__ = [
    "websocket_manager",
    "ConnectionManager",
    "MessageType",
    "authenticate_websocket",
    "notify_new_order",
    "notify_order_status_change",
    "notify_delivery_update",
    "send_performance_metrics"
]