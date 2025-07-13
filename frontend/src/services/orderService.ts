/**
 * Order service for managing order-related API operations.
 * Handles CRUD operations, status updates, and order queries.
 */

import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from './api';
import type { 
  Order, 
  OrderFilter, 
  OrderUpdateRequest, 
  ApiResponse, 
  PaginatedResponse 
} from '@/types';

/**
 * Fetch orders with optional filtering and pagination.
 */
export const fetchOrders = async (
  filters: OrderFilter = {},
  page = 1,
  limit = 20
): Promise<PaginatedResponse<Order>> => {
  const params = {
    page,
    limit,
    ...filters,
  };

  // Convert array filters to comma-separated strings
  if (filters.status) {
    params.status = filters.status.join(',');
  }
  if (filters.payment_status) {
    params.payment_status = filters.payment_status.join(',');
  }

  return apiGet<Order[]>('/orders', params);
};

/**
 * Fetch a single order by ID.
 */
export const fetchOrder = async (orderId: number): Promise<ApiResponse<Order>> => {
  return apiGet<Order>(`/orders/${orderId}`);
};

/**
 * Create a new order.
 */
export const createOrder = async (orderData: Partial<Order>): Promise<ApiResponse<Order>> => {
  return apiPost<Order>('/orders', orderData);
};

/**
 * Update an existing order.
 */
export const updateOrder = async (
  orderId: number, 
  updates: Partial<Order>
): Promise<ApiResponse<Order>> => {
  return apiPut<Order>(`/orders/${orderId}`, updates);
};

/**
 * Update order status.
 */
export const updateOrderStatus = async (
  orderId: number,
  newStatus: string,
  notes?: string
): Promise<ApiResponse<Order>> => {
  const updateData: OrderUpdateRequest = {
    order_id: orderId,
    status: newStatus as any,
    notes,
  };

  return apiPatch<Order>(`/orders/${orderId}/status`, updateData);
};

/**
 * Update payment status.
 */
export const updatePaymentStatus = async (
  orderId: number,
  paymentStatus: string
): Promise<ApiResponse<Order>> => {
  const updateData: OrderUpdateRequest = {
    order_id: orderId,
    payment_status: paymentStatus as any,
  };

  return apiPatch<Order>(`/orders/${orderId}/payment-status`, updateData);
};

/**
 * Update delivery estimate.
 */
export const updateDeliveryEstimate = async (
  orderId: number,
  estimatedMinutes: number
): Promise<ApiResponse<Order>> => {
  const updateData: OrderUpdateRequest = {
    order_id: orderId,
    estimated_delivery: estimatedMinutes,
  };

  return apiPatch<Order>(`/orders/${orderId}/delivery-estimate`, updateData);
};

/**
 * Cancel an order.
 */
export const cancelOrder = async (
  orderId: number,
  reason?: string
): Promise<ApiResponse<Order>> => {
  return apiPatch<Order>(`/orders/${orderId}/cancel`, { reason });
};

/**
 * Refund an order.
 */
export const refundOrder = async (
  orderId: number,
  amount?: number,
  reason?: string
): Promise<ApiResponse<any>> => {
  return apiPost(`/orders/${orderId}/refund`, { amount, reason });
};

/**
 * Get order history/timeline.
 */
export const fetchOrderHistory = async (
  orderId: number
): Promise<ApiResponse<any[]>> => {
  return apiGet(`/orders/${orderId}/history`);
};

/**
 * Get orders by customer phone number.
 */
export const fetchOrdersByCustomer = async (
  phoneNumber: string
): Promise<ApiResponse<Order[]>> => {
  return apiGet<Order[]>(`/orders/customer/${encodeURIComponent(phoneNumber)}`);
};

/**
 * Get active orders (non-completed).
 */
export const fetchActiveOrders = async (): Promise<ApiResponse<Order[]>> => {
  return fetchOrders({
    status: [
      'pending',
      'payment_processing',
      'payment_confirmed',
      'preparing',
      'ready',
      'out_for_delivery',
    ],
  });
};

/**
 * Get orders ready for delivery.
 */
export const fetchOrdersReadyForDelivery = async (): Promise<ApiResponse<Order[]>> => {
  return fetchOrders({
    status: ['ready', 'out_for_delivery'],
  });
};

/**
 * Get order statistics for dashboard.
 */
export const fetchOrderStats = async (
  period: 'today' | 'week' | 'month' = 'today'
): Promise<ApiResponse<any>> => {
  return apiGet(`/orders/stats?period=${period}`);
};

/**
 * Search orders by various criteria.
 */
export const searchOrders = async (
  query: string,
  limit = 20
): Promise<ApiResponse<Order[]>> => {
  return apiGet<Order[]>('/orders/search', { q: query, limit });
};

/**
 * Export orders to CSV.
 */
export const exportOrders = async (
  filters: OrderFilter = {},
  format: 'csv' | 'xlsx' = 'csv'
): Promise<Blob> => {
  const params = {
    format,
    ...filters,
  };

  // Convert array filters to comma-separated strings
  if (filters.status) {
    params.status = filters.status.join(',');
  }
  if (filters.payment_status) {
    params.payment_status = filters.payment_status.join(',');
  }

  const response = await fetch(`${process.env.VITE_API_BASE_URL}/orders/export?${new URLSearchParams(params)}`, {
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
    },
  });

  if (!response.ok) {
    throw new Error('Export failed');
  }

  return response.blob();
};

/**
 * Print order receipt.
 */
export const printOrderReceipt = async (orderId: number): Promise<Blob> => {
  const response = await fetch(`${process.env.VITE_API_BASE_URL}/orders/${orderId}/receipt`, {
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
    },
  });

  if (!response.ok) {
    throw new Error('Print failed');
  }

  return response.blob();
};