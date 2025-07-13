/**
 * Order-related type definitions for the restaurant dashboard.
 * Matches the backend SQLAlchemy models for consistency.
 */

export interface Pizza {
  size: 'small' | 'medium' | 'large' | 'xlarge';
  toppings: string[];
  quantity: number;
  price: number;
}

export interface OrderDetails {
  pizzas: Pizza[];
  special_instructions?: string;
  customer_notes?: string;
}

export interface Order {
  id: number;
  customer_name: string;
  phone_number: string;
  address: string;
  order_details: OrderDetails;
  total_amount: number;
  estimated_delivery: number;
  payment_method: string;
  payment_status: PaymentStatus;
  order_status: OrderStatus;
  interface_type: 'phone' | 'web';
  created_at: string;
  updated_at: string;
}

export interface DeliveryEstimate {
  id: number;
  order_id: number;
  estimated_minutes: number;
  distance_miles: number;
  base_time_minutes: number;
  distance_time_minutes: number;
  load_time_minutes: number;
  random_variation_minutes: number;
  confidence_score: number;
  delivery_zone: 'inner' | 'middle' | 'outer';
  factors_data?: Record<string, any>;
  is_active: boolean;
  actual_delivery_time?: number;
  created_at: string;
  updated_at: string;
}

export enum PaymentStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  SUCCEEDED = 'succeeded',
  FAILED = 'failed',
  CANCELED = 'canceled',
  REQUIRES_ACTION = 'requires_action',
  REFUNDED = 'refunded',
  PARTIALLY_REFUNDED = 'partially_refunded',
}

export enum OrderStatus {
  PENDING = 'pending',
  PAYMENT_PROCESSING = 'payment_processing',
  PAYMENT_CONFIRMED = 'payment_confirmed',
  PAYMENT_FAILED = 'payment_failed',
  PREPARING = 'preparing',
  READY = 'ready',
  OUT_FOR_DELIVERY = 'out_for_delivery',
  DELIVERED = 'delivered',
  CANCELED = 'canceled',
  REFUNDED = 'refunded',
}

export interface OrderFilter {
  status?: OrderStatus[];
  payment_status?: PaymentStatus[];
  search?: string;
  date_from?: string;
  date_to?: string;
  interface_type?: 'phone' | 'web';
}

export interface OrderUpdateRequest {
  order_id: number;
  status?: OrderStatus;
  payment_status?: PaymentStatus;
  estimated_delivery?: number;
  notes?: string;
}