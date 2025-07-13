/**
 * Validation utilities for form inputs and data.
 */

/**
 * Validate phone number format.
 */
export const isValidPhoneNumber = (phone: string): boolean => {
  const cleaned = phone.replace(/\D/g, '');
  return cleaned.length === 10 || (cleaned.length === 11 && cleaned[0] === '1');
};

/**
 * Validate email address format.
 */
export const isValidEmail = (email: string): boolean => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
};

/**
 * Validate currency amount.
 */
export const isValidAmount = (amount: number): boolean => {
  return amount > 0 && amount <= 10000 && Number.isFinite(amount);
};

/**
 * Validate delivery estimate time.
 */
export const isValidDeliveryTime = (minutes: number): boolean => {
  return minutes >= 15 && minutes <= 120 && Number.isInteger(minutes);
};

/**
 * Validate coordinate values.
 */
export const isValidCoordinate = (lat: number, lng: number): boolean => {
  return (
    lat >= -90 && lat <= 90 &&
    lng >= -180 && lng <= 180 &&
    Number.isFinite(lat) && Number.isFinite(lng)
  );
};

/**
 * Validate order status transition.
 */
export const isValidStatusTransition = (
  currentStatus: string, 
  newStatus: string
): boolean => {
  const validTransitions: Record<string, string[]> = {
    'pending': ['payment_processing', 'payment_confirmed', 'canceled'],
    'payment_processing': ['payment_confirmed', 'payment_failed', 'canceled'],
    'payment_confirmed': ['preparing', 'canceled'],
    'payment_failed': ['pending', 'canceled'],
    'preparing': ['ready', 'canceled'],
    'ready': ['out_for_delivery', 'canceled'],
    'out_for_delivery': ['delivered', 'failed', 'returned'],
    'delivered': ['refunded'],
    'canceled': [],
    'refunded': [],
    'failed': ['pending', 'canceled'],
    'returned': ['pending', 'canceled', 'refunded'],
  };

  return validTransitions[currentStatus]?.includes(newStatus) || false;
};

/**
 * Validate search query.
 */
export const isValidSearchQuery = (query: string): boolean => {
  return query.trim().length >= 2 && query.trim().length <= 100;
};

/**
 * Validate date range.
 */
export const isValidDateRange = (startDate: string, endDate: string): boolean => {
  const start = new Date(startDate);
  const end = new Date(endDate);
  const now = new Date();
  
  return (
    start <= end &&
    start <= now &&
    end <= now &&
    !isNaN(start.getTime()) &&
    !isNaN(end.getTime())
  );
};

/**
 * Validate pagination parameters.
 */
export const isValidPagination = (page: number, limit: number): boolean => {
  return (
    Number.isInteger(page) && page >= 1 &&
    Number.isInteger(limit) && limit >= 1 && limit <= 100
  );
};

/**
 * Sanitize user input for search.
 */
export const sanitizeSearchInput = (input: string): string => {
  return input
    .trim()
    .replace(/[<>]/g, '') // Remove potential HTML tags
    .substring(0, 100); // Limit length
};

/**
 * Validate driver ID format.
 */
export const isValidDriverId = (driverId: string): boolean => {
  return /^[a-zA-Z0-9_-]+$/.test(driverId) && driverId.length <= 50;
};

/**
 * Validate order notes.
 */
export const isValidOrderNotes = (notes: string): boolean => {
  return notes.length <= 500;
};