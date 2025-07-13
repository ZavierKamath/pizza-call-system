/**
 * Central export for all utility functions.
 */

export * from './constants';
export * from './formatters';
export * from './validation';

// Re-export commonly used utilities from external libraries
export { clsx } from 'clsx';
export { twMerge } from 'tailwind-merge';

/**
 * Utility for combining Tailwind classes with conflict resolution.
 */
export const cn = (...inputs: any[]) => {
  return twMerge(clsx(inputs));
};