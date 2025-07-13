/**
 * WebSocket hook for real-time communication with the backend.
 * Handles connection management, reconnection, and message handling.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';
import toast from 'react-hot-toast';

import { WEBSOCKET_URL, REFRESH_INTERVALS } from '@/utils/constants';
import type { WebSocketMessage, ConnectionStatus } from '@/types';

interface UseWebSocketOptions {
  autoConnect?: boolean;
  reconnectAttempts?: number;
  reconnectInterval?: number;
}

interface UseWebSocketReturn {
  socket: Socket | null;
  isConnected: boolean;
  isReconnecting: boolean;
  connectionCount: number;
  lastMessage: WebSocketMessage | null;
  sendMessage: (type: string, data: any) => void;
  connect: () => void;
  disconnect: () => void;
}

export const useWebSocket = (options: UseWebSocketOptions = {}): UseWebSocketReturn => {
  const {
    autoConnect = true,
    reconnectAttempts = 5,
    reconnectInterval = 3000,
  } = options;

  const socketRef = useRef<Socket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectCountRef = useRef(0);

  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [connectionCount, setConnectionCount] = useState(0);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);

  const connect = useCallback(() => {
    if (socketRef.current?.connected) {
      return;
    }

    console.log('Connecting to WebSocket server...');
    
    const socket = io(WEBSOCKET_URL, {
      transports: ['websocket', 'polling'],
      timeout: 5000,
      forceNew: true,
    });

    socketRef.current = socket;

    // Connection established
    socket.on('connect', () => {
      console.log('WebSocket connected successfully');
      setIsConnected(true);
      setIsReconnecting(false);
      setConnectionCount(prev => prev + 1);
      reconnectCountRef.current = 0;

      // Clear any pending reconnection timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      toast.success('Connected to real-time updates', {
        duration: 2000,
      });
    });

    // Connection error
    socket.on('connect_error', (error) => {
      console.error('WebSocket connection error:', error);
      setIsConnected(false);
      
      if (reconnectCountRef.current === 0) {
        toast.error('Connection lost. Attempting to reconnect...', {
          duration: 3000,
        });
      }
    });

    // Disconnection
    socket.on('disconnect', (reason) => {
      console.log('WebSocket disconnected:', reason);
      setIsConnected(false);

      // Only attempt reconnection if it wasn't a manual disconnect
      if (reason !== 'io client disconnect') {
        attemptReconnection();
      }
    });

    // Handle incoming messages
    socket.on('message', (message: WebSocketMessage) => {
      console.log('WebSocket message received:', message);
      setLastMessage(message);
    });

    // Handle specific event types
    socket.on('order_update', (data) => {
      setLastMessage({
        type: 'order_update',
        data,
        timestamp: new Date().toISOString(),
      });
    });

    socket.on('delivery_update', (data) => {
      setLastMessage({
        type: 'delivery_update',
        data,
        timestamp: new Date().toISOString(),
      });
    });

    socket.on('performance_alert', (data) => {
      setLastMessage({
        type: 'performance_alert',
        data,
        timestamp: new Date().toISOString(),
      });
    });

  }, []);

  const attemptReconnection = useCallback(() => {
    if (reconnectCountRef.current >= reconnectAttempts) {
      console.log('Max reconnection attempts reached');
      setIsReconnecting(false);
      toast.error('Unable to reconnect. Please refresh the page.', {
        duration: 0, // Don't auto-dismiss
      });
      return;
    }

    setIsReconnecting(true);
    reconnectCountRef.current += 1;

    console.log(`Attempting reconnection ${reconnectCountRef.current}/${reconnectAttempts}`);

    reconnectTimeoutRef.current = setTimeout(() => {
      connect();
    }, reconnectInterval * reconnectCountRef.current); // Exponential backoff

  }, [connect, reconnectAttempts, reconnectInterval]);

  const disconnect = useCallback(() => {
    console.log('Manually disconnecting WebSocket');
    
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (socketRef.current) {
      socketRef.current.disconnect();
      socketRef.current = null;
    }

    setIsConnected(false);
    setIsReconnecting(false);
    reconnectCountRef.current = 0;
  }, []);

  const sendMessage = useCallback((type: string, data: any) => {
    if (socketRef.current?.connected) {
      const message: WebSocketMessage = {
        type,
        data,
        timestamp: new Date().toISOString(),
      };
      
      socketRef.current.emit('message', message);
      console.log('WebSocket message sent:', message);
    } else {
      console.warn('Cannot send message: WebSocket not connected');
      toast.error('Cannot send message: Connection lost');
    }
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    // Cleanup on unmount
    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  // Periodic connection health check
  useEffect(() => {
    const healthCheck = setInterval(() => {
      if (socketRef.current && !socketRef.current.connected && !isReconnecting) {
        console.log('Health check failed, attempting reconnection');
        attemptReconnection();
      }
    }, REFRESH_INTERVALS.CONNECTION_CHECK);

    return () => clearInterval(healthCheck);
  }, [isReconnecting, attemptReconnection]);

  return {
    socket: socketRef.current,
    isConnected,
    isReconnecting,
    connectionCount,
    lastMessage,
    sendMessage,
    connect,
    disconnect,
  };
};