"""
WebSocket endpoints for real-time dashboard communication.
Handles WebSocket connections, message routing, and client management.
"""

import logging
import json
import uuid
from typing import Optional, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import HTMLResponse

from .websocket import (
    websocket_manager, 
    authenticate_websocket,
    MessageType
)
from ..config.logging_config import get_logger

# Configure logging
logger = get_logger(__name__)

# Create router
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None)
):
    """
    Main WebSocket endpoint for dashboard real-time communication.
    
    Query Parameters:
        token: Authentication token (optional for development)
        client_id: Client identifier (auto-generated if not provided)
    
    Message Format:
        {
            "type": "message_type",
            "data": {...},
            "timestamp": "ISO-8601-timestamp"
        }
    
    Supported Message Types:
        - order_update: Order information updates
        - order_status_change: Order status changes
        - new_order: New order notifications
        - delivery_update: Delivery status updates
        - system_alert: System alerts and notifications
        - performance_metrics: Real-time performance data
        - subscribe: Update subscription preferences
        - ping: Connection keepalive
    """
    # Generate client ID if not provided
    if not client_id:
        client_id = f"client_{uuid.uuid4().hex[:8]}"
    
    # Authenticate connection
    user_info = await authenticate_websocket(websocket, token)
    if user_info is None and getattr(websocket_manager, 'require_auth', False):
        await websocket.close(code=4001, reason="Authentication required")
        return
    
    logger.info(f"WebSocket connection attempt from client {client_id}")
    
    try:
        # Accept and register connection
        await websocket_manager.connect(websocket, client_id, user_info)
        
        # Main message loop
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle client message
                await handle_client_message(client_id, message)
                
            except WebSocketDisconnect:
                logger.info(f"Client {client_id} disconnected")
                break
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received from client {client_id}")
                await websocket_manager.send_personal_message(client_id, {
                    "type": "error",
                    "data": {
                        "message": "Invalid JSON format",
                        "code": "INVALID_JSON"
                    }
                })
            except Exception as e:
                logger.error(f"Error handling message from client {client_id}: {str(e)}")
                await websocket_manager.send_personal_message(client_id, {
                    "type": "error",
                    "data": {
                        "message": "Message processing error",
                        "code": "PROCESSING_ERROR"
                    }
                })
    
    except Exception as e:
        logger.error(f"WebSocket connection error for client {client_id}: {str(e)}")
    
    finally:
        # Clean up connection
        websocket_manager.disconnect(client_id)


async def handle_client_message(client_id: str, message: Dict[str, Any]):
    """
    Handle incoming messages from WebSocket clients.
    
    Args:
        client_id: Client identifier
        message: Parsed message data
    """
    try:
        message_type = message.get("type")
        data = message.get("data", {})
        
        logger.debug(f"Received message from client {client_id}: {message_type}")
        
        if message_type == "ping":
            # Respond to ping with pong
            await websocket_manager.send_personal_message(client_id, {
                "type": "pong",
                "data": {
                    "timestamp": message.get("timestamp"),
                    "server_time": websocket_manager.datetime.utcnow().isoformat()
                }
            })
        
        elif message_type == "subscribe":
            # Update client subscriptions
            subscriptions = data.get("subscriptions", [])
            await websocket_manager.update_subscriptions(client_id, subscriptions)
        
        elif message_type == "get_stats":
            # Send connection statistics
            stats = websocket_manager.get_connection_stats()
            await websocket_manager.send_personal_message(client_id, {
                "type": "stats",
                "data": stats
            })
        
        elif message_type == "broadcast_test":
            # Test broadcast (admin only)
            user_info = websocket_manager.connection_metadata.get(client_id, {}).get("user_info", {})
            if user_info.get("role") == "admin":
                test_message = {
                    "type": "system_alert",
                    "data": {
                        "alert_type": "test",
                        "message": "Test broadcast message",
                        "severity": "info",
                        "from_client": client_id
                    }
                }
                await websocket_manager.broadcast(test_message)
            else:
                await websocket_manager.send_personal_message(client_id, {
                    "type": "error",
                    "data": {
                        "message": "Insufficient permissions for broadcast",
                        "code": "PERMISSION_DENIED"
                    }
                })
        
        else:
            logger.warning(f"Unknown message type from client {client_id}: {message_type}")
            await websocket_manager.send_personal_message(client_id, {
                "type": "error",
                "data": {
                    "message": f"Unknown message type: {message_type}",
                    "code": "UNKNOWN_MESSAGE_TYPE"
                }
            })
    
    except Exception as e:
        logger.error(f"Error handling client message: {str(e)}")
        await websocket_manager.send_personal_message(client_id, {
            "type": "error",
            "data": {
                "message": "Internal error processing message",
                "code": "INTERNAL_ERROR"
            }
        })


@router.get("/ws/stats")
async def get_websocket_stats():
    """
    Get current WebSocket connection statistics.
    
    Returns connection counts, client information, and performance metrics.
    """
    try:
        stats = websocket_manager.get_connection_stats()
        
        return {
            "success": True,
            "data": stats
        }
    
    except Exception as e:
        logger.error(f"Error getting WebSocket stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve WebSocket statistics"
        )


@router.post("/ws/broadcast")
async def broadcast_message(
    message_type: str,
    message_data: Dict[str, Any],
    target_subscriptions: Optional[list] = None
):
    """
    Broadcast a message to all connected WebSocket clients.
    
    This endpoint is for internal use by other services to send updates.
    
    Args:
        message_type: Type of message to broadcast
        message_data: Message data to send
        target_subscriptions: Optional list of subscription types to target
    """
    try:
        # Validate message type
        try:
            msg_type = MessageType(message_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid message type: {message_type}"
            )
        
        # Create broadcast message
        broadcast_msg = {
            "type": message_type,
            "data": message_data
        }
        
        # Send broadcast
        await websocket_manager.broadcast(broadcast_msg, msg_type)
        
        logger.info(f"Broadcast message sent: {message_type}")
        
        return {
            "success": True,
            "data": {
                "message_type": message_type,
                "sent_to": websocket_manager.connection_count,
                "timestamp": websocket_manager.datetime.utcnow().isoformat()
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting message: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to broadcast message"
        )


@router.get("/ws/test")
async def websocket_test_page():
    """
    Simple test page for WebSocket connection testing.
    Returns HTML page with JavaScript WebSocket client.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>WebSocket Test</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            .status { padding: 10px; margin: 10px 0; border-radius: 4px; }
            .connected { background-color: #d4edda; color: #155724; }
            .disconnected { background-color: #f8d7da; color: #721c24; }
            .messages { height: 300px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px; }
            .message { margin: 5px 0; padding: 5px; background-color: #f8f9fa; border-radius: 3px; }
            button { padding: 8px 16px; margin: 5px; cursor: pointer; }
            input[type="text"] { padding: 8px; margin: 5px; width: 200px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>WebSocket Dashboard Test</h1>
            
            <div id="status" class="status disconnected">Disconnected</div>
            
            <div>
                <input type="text" id="tokenInput" placeholder="Auth token (optional)" value="dashboard-dev-token">
                <button onclick="connect()">Connect</button>
                <button onclick="disconnect()">Disconnect</button>
            </div>
            
            <div>
                <button onclick="sendPing()">Send Ping</button>
                <button onclick="getStats()">Get Stats</button>
                <button onclick="testBroadcast()">Test Broadcast</button>
            </div>
            
            <div>
                <h3>Messages:</h3>
                <div id="messages" class="messages"></div>
                <button onclick="clearMessages()">Clear Messages</button>
            </div>
        </div>

        <script>
            let ws = null;
            
            function connect() {
                const token = document.getElementById('tokenInput').value;
                const wsUrl = `ws://localhost:8000/api/ws?token=${encodeURIComponent(token)}`;
                
                ws = new WebSocket(wsUrl);
                
                ws.onopen = function(event) {
                    updateStatus('Connected', true);
                    addMessage('Connected to WebSocket server');
                };
                
                ws.onmessage = function(event) {
                    const message = JSON.parse(event.data);
                    addMessage(`Received: ${JSON.stringify(message, null, 2)}`);
                };
                
                ws.onclose = function(event) {
                    updateStatus('Disconnected', false);
                    addMessage(`Connection closed: ${event.code} - ${event.reason}`);
                };
                
                ws.onerror = function(event) {
                    addMessage('WebSocket error occurred');
                };
            }
            
            function disconnect() {
                if (ws) {
                    ws.close();
                }
            }
            
            function sendPing() {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    const message = {
                        type: 'ping',
                        timestamp: new Date().toISOString()
                    };
                    ws.send(JSON.stringify(message));
                    addMessage('Sent ping');
                }
            }
            
            function getStats() {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    const message = {
                        type: 'get_stats'
                    };
                    ws.send(JSON.stringify(message));
                    addMessage('Requested stats');
                }
            }
            
            function testBroadcast() {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    const message = {
                        type: 'broadcast_test',
                        data: {
                            test_message: 'Hello from test client!'
                        }
                    };
                    ws.send(JSON.stringify(message));
                    addMessage('Sent test broadcast');
                }
            }
            
            function updateStatus(status, connected) {
                const statusEl = document.getElementById('status');
                statusEl.textContent = status;
                statusEl.className = `status ${connected ? 'connected' : 'disconnected'}`;
            }
            
            function addMessage(message) {
                const messagesEl = document.getElementById('messages');
                const messageEl = document.createElement('div');
                messageEl.className = 'message';
                messageEl.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
                messagesEl.appendChild(messageEl);
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }
            
            function clearMessages() {
                document.getElementById('messages').innerHTML = '';
            }
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


# Export router
__all__ = ["router"]