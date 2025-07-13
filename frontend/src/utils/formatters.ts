/**
 * Utility functions for formatting data display.
 */

import { format, formatDistance, formatRelative } from 'date-fns';

/**
 * Format currency amount with proper localization.
 */
export const formatCurrency = (amount: number, currency = 'USD'): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
};

/**
 * Format phone number for display.
 */
export const formatPhoneNumber = (phone: string): string => {
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  if (cleaned.length === 11 && cleaned[0] === '1') {
    return `+1 (${cleaned.slice(1, 4)}) ${cleaned.slice(4, 7)}-${cleaned.slice(7)}`;
  }
  return phone; // Return original if format doesn't match
};

/**
 * Format time duration in minutes to human-readable format.
 */
export const formatDuration = (minutes: number): string => {
  if (minutes < 60) {
    return `${minutes}min`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (remainingMinutes === 0) {
    return `${hours}h`;
  }
  return `${hours}h ${remainingMinutes}min`;
};

/**
 * Format delivery time estimation with confidence indicator.
 */
export const formatDeliveryEstimate = (
  minutes: number, 
  confidence: number
): string => {
  const timeStr = formatDuration(minutes);
  if (confidence >= 0.8) {
    return timeStr;
  } else if (confidence >= 0.6) {
    return `~${timeStr}`;
  } else {
    return `${timeStr} (est.)`;
  }
};

/**
 * Format distance with appropriate units.
 */
export const formatDistance = (miles: number): string => {
  if (miles < 0.1) {
    return `${Math.round(miles * 5280)}ft`;
  } else if (miles < 1) {
    return `${(miles * 5280).toFixed(0)}ft`;
  } else {
    return `${miles.toFixed(1)}mi`;
  }
};

/**
 * Format percentage with proper decimal places.
 */
export const formatPercentage = (value: number, decimals = 1): string => {
  return `${(value * 100).toFixed(decimals)}%`;
};

/**
 * Format date for display in orders list.
 */
export const formatOrderDate = (dateString: string): string => {
  const date = new Date(dateString);
  const now = new Date();
  
  // If today, show relative time
  if (date.toDateString() === now.toDateString()) {
    return formatRelative(date, now);
  }
  
  // If this week, show day and time
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  if (date > weekAgo) {
    return format(date, 'EEE h:mm a');
  }
  
  // Otherwise show full date
  return format(date, 'MMM d, h:mm a');
};

/**
 * Format date for detailed view.
 */
export const formatDetailedDate = (dateString: string): string => {
  const date = new Date(dateString);
  return format(date, 'PPpp'); // "Apr 29, 2021 at 1:53 PM"
};

/**
 * Format order status for display.
 */
export const formatOrderStatus = (status: string): string => {
  return status
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

/**
 * Format pizza details for display.
 */
export const formatPizzaDescription = (pizza: any): string => {
  const size = pizza.size.charAt(0).toUpperCase() + pizza.size.slice(1);
  const toppings = pizza.toppings?.length > 0 
    ? pizza.toppings.join(', ')
    : 'Plain';
  
  return `${size} Pizza - ${toppings}`;
};

/**
 * Format order summary for notifications.
 */
export const formatOrderSummary = (order: any): string => {
  const pizzaCount = order.order_details?.pizzas?.length || 0;
  const total = formatCurrency(order.total_amount);
  return `${pizzaCount} pizza${pizzaCount !== 1 ? 's' : ''} - ${total}`;
};

/**
 * Format address for compact display.
 */
export const formatCompactAddress = (address: string, maxLength = 50): string => {
  if (address.length <= maxLength) {
    return address;
  }
  
  // Try to break at comma
  const parts = address.split(',');
  if (parts.length > 1 && parts[0].length <= maxLength) {
    return `${parts[0].trim()}...`;
  }
  
  // Otherwise truncate
  return `${address.substring(0, maxLength - 3)}...`;
};

/**
 * Format number with thousand separators.
 */
export const formatNumber = (num: number): string => {
  return new Intl.NumberFormat('en-US').format(num);
};

/**
 * Get relative time from now.
 */
export const getRelativeTime = (dateString: string): string => {
  const date = new Date(dateString);
  const now = new Date();
  return formatDistance(date, now, { addSuffix: true });
};

/**
 * Format relative time from date string.
 */
export const formatRelativeTime = (dateString: string): string => {
  return getRelativeTime(dateString);
};