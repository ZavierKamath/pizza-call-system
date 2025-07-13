/**
 * Delivery-related type definitions for tracking and management.
 */

export interface DeliveryLocation {
  lat: number;
  lng: number;
  address: string;
}

export interface DeliveryDriver {
  id: string;
  name: string;
  phone: string;
  current_location?: DeliveryLocation;
  is_available: boolean;
  active_deliveries: number;
  max_deliveries: number;
}

export interface DeliveryTracking {
  order_id: number;
  driver_id?: string;
  driver?: DeliveryDriver;
  pickup_time?: string;
  estimated_arrival: string;
  actual_arrival?: string;
  delivery_status: DeliveryStatus;
  tracking_updates: DeliveryUpdate[];
  route_distance?: number;
  route_duration?: number;
}

export interface DeliveryUpdate {
  timestamp: string;
  status: DeliveryStatus;
  location?: DeliveryLocation;
  notes?: string;
  estimated_arrival?: string;
}

export enum DeliveryStatus {
  PENDING = 'pending',
  ASSIGNED = 'assigned',
  PICKED_UP = 'picked_up',
  EN_ROUTE = 'en_route',
  ARRIVED = 'arrived',
  DELIVERED = 'delivered',
  FAILED = 'failed',
  RETURNED = 'returned',
}

export interface DeliveryZone {
  name: string;
  zone_type: 'inner' | 'middle' | 'outer';
  boundary_points: DeliveryLocation[];
  base_delivery_time: number;
  active_orders: number;
  average_delivery_time: number;
}

export interface DeliveryMetrics {
  total_deliveries_today: number;
  average_delivery_time: number;
  on_time_percentage: number;
  active_deliveries: number;
  pending_deliveries: number;
  available_drivers: number;
  busy_drivers: number;
  zones: DeliveryZone[];
}