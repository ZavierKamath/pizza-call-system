/**
 * API response and request type definitions.
 */

export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
  timestamp: string;
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  pagination: {
    page: number;
    limit: number;
    total: number;
    pages: number;
  };
}

export interface WebSocketMessage {
  type: string;
  data: any;
  timestamp: string;
}

export interface OrderWebSocketMessage extends WebSocketMessage {
  type: 'new_order' | 'order_update' | 'order_status_change';
  data: {
    order_id: number;
    order?: any;
    previous_status?: string;
    new_status?: string;
    customer_name?: string;
  };
}

export interface DeliveryWebSocketMessage extends WebSocketMessage {
  type: 'delivery_update' | 'driver_location' | 'delivery_status_change';
  data: {
    order_id: number;
    driver_id?: string;
    location?: {
      lat: number;
      lng: number;
    };
    status?: string;
    estimated_arrival?: string;
  };
}

export interface PerformanceWebSocketMessage extends WebSocketMessage {
  type: 'metrics_update' | 'performance_alert';
  data: {
    metrics?: any;
    alert_type?: string;
    alert_data?: any;
  };
}

export type WebSocketEventType = 
  | 'new_order'
  | 'order_update' 
  | 'order_status_change'
  | 'delivery_update'
  | 'driver_location'
  | 'delivery_status_change'
  | 'metrics_update'
  | 'performance_alert';

export interface ConnectionStatus {
  connected: boolean;
  reconnecting: boolean;
  last_connected?: string;
  connection_count: number;
}