/**
 * Application constants and configuration values.
 */

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';
export const WEBSOCKET_URL = import.meta.env.VITE_WEBSOCKET_URL || 'http://localhost:8000';

export const ORDER_STATUS_COLORS = {
  pending: 'bg-yellow-100 text-yellow-800',
  payment_processing: 'bg-blue-100 text-blue-800',
  payment_confirmed: 'bg-green-100 text-green-800',
  payment_failed: 'bg-red-100 text-red-800',
  preparing: 'bg-orange-100 text-orange-800',
  ready: 'bg-green-100 text-green-800',
  out_for_delivery: 'bg-purple-100 text-purple-800',
  delivered: 'bg-green-100 text-green-800',
  canceled: 'bg-gray-100 text-gray-800',
  refunded: 'bg-red-100 text-red-800',
} as const;

export const PAYMENT_STATUS_COLORS = {
  pending: 'bg-yellow-100 text-yellow-800',
  processing: 'bg-blue-100 text-blue-800',
  succeeded: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  canceled: 'bg-gray-100 text-gray-800',
  requires_action: 'bg-orange-100 text-orange-800',
  refunded: 'bg-red-100 text-red-800',
  partially_refunded: 'bg-orange-100 text-orange-800',
} as const;

export const DELIVERY_STATUS_COLORS = {
  pending: 'bg-yellow-100 text-yellow-800',
  assigned: 'bg-blue-100 text-blue-800',
  picked_up: 'bg-orange-100 text-orange-800',
  en_route: 'bg-purple-100 text-purple-800',
  arrived: 'bg-green-100 text-green-800',
  delivered: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  returned: 'bg-gray-100 text-gray-800',
} as const;

export const PIZZA_SIZES = {
  small: { label: 'Small (10")', price_modifier: 0.8 },
  medium: { label: 'Medium (12")', price_modifier: 1.0 },
  large: { label: 'Large (14")', price_modifier: 1.3 },
  xlarge: { label: 'X-Large (16")', price_modifier: 1.6 },
} as const;

export const DELIVERY_ZONES = {
  inner: { label: 'Inner Zone (0-2 miles)', color: '#10b981' },
  middle: { label: 'Middle Zone (2-5 miles)', color: '#f59e0b' },
  outer: { label: 'Outer Zone (5+ miles)', color: '#ef4444' },
} as const;

export const REFRESH_INTERVALS = {
  ORDERS: 5000, // 5 seconds
  DELIVERIES: 10000, // 10 seconds
  ANALYTICS: 30000, // 30 seconds
  CONNECTION_CHECK: 15000, // 15 seconds
} as const;

export const PAGINATION = {
  DEFAULT_LIMIT: 20,
  MAX_LIMIT: 100,
} as const;

export const GOOGLE_MAPS_CONFIG = {
  DEFAULT_CENTER: { lat: 40.7128, lng: -74.0060 }, // New York City
  DEFAULT_ZOOM: 12,
  MARKERS: {
    RESTAURANT: '/icons/restaurant-marker.png',
    DELIVERY: '/icons/delivery-marker.png',
    CUSTOMER: '/icons/customer-marker.png',
  },
} as const;

export const NOTIFICATION_SETTINGS = {
  AUTO_DISMISS_TIME: 5000, // 5 seconds
  MAX_NOTIFICATIONS: 5,
  SOUND_ENABLED: true,
} as const;