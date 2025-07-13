/**
 * Order filters component for filtering and searching orders.
 * Provides comprehensive filtering options with real-time updates.
 */

import React from 'react';
import { X, Calendar } from 'lucide-react';

import { cn, formatOrderStatus } from '@/utils';
import type { OrderFilter, OrderStatus, PaymentStatus } from '@/types';

interface OrderFiltersProps {
  filters: OrderFilter;
  onFiltersChange: (filters: Partial<OrderFilter>) => void;
  onClear: () => void;
  className?: string;
}

const OrderFilters: React.FC<OrderFiltersProps> = ({
  filters,
  onFiltersChange,
  onClear,
  className,
}) => {
  const orderStatuses: OrderStatus[] = [
    'pending',
    'payment_processing',
    'payment_confirmed',
    'payment_failed',
    'preparing',
    'ready',
    'out_for_delivery',
    'delivered',
    'canceled',
    'refunded',
  ];

  const paymentStatuses: PaymentStatus[] = [
    'pending',
    'processing',
    'succeeded',
    'failed',
    'canceled',
    'requires_action',
    'refunded',
    'partially_refunded',
  ];

  const interfaceTypes = [
    { value: 'phone', label: 'Phone Orders' },
    { value: 'web', label: 'Web Orders' },
  ];

  const handleStatusToggle = (status: OrderStatus) => {
    const currentStatuses = filters.status || [];
    const newStatuses = currentStatuses.includes(status)
      ? currentStatuses.filter(s => s !== status)
      : [...currentStatuses, status];
    
    onFiltersChange({
      status: newStatuses.length > 0 ? newStatuses : undefined,
    });
  };

  const handlePaymentStatusToggle = (status: PaymentStatus) => {
    const currentStatuses = filters.payment_status || [];
    const newStatuses = currentStatuses.includes(status)
      ? currentStatuses.filter(s => s !== status)
      : [...currentStatuses, status];
    
    onFiltersChange({
      payment_status: newStatuses.length > 0 ? newStatuses : undefined,
    });
  };

  const handleDateChange = (field: 'date_from' | 'date_to', value: string) => {
    onFiltersChange({
      [field]: value || undefined,
    });
  };

  const handleInterfaceTypeChange = (type: 'phone' | 'web' | '') => {
    onFiltersChange({
      interface_type: type || undefined,
    });
  };

  const hasActiveFilters = Object.keys(filters).some(key => 
    filters[key as keyof OrderFilter] !== undefined
  );

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-gray-900">Filters</h3>
        {hasActiveFilters && (
          <button
            onClick={onClear}
            className="flex items-center text-sm text-gray-500 hover:text-gray-700"
          >
            <X className="h-4 w-4 mr-1" />
            Clear all
          </button>
        )}
      </div>

      {/* Order Status Filter */}
      <div>
        <label className="form-label">Order Status</label>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mt-2">
          {orderStatuses.map(status => (
            <button
              key={status}
              onClick={() => handleStatusToggle(status)}
              className={cn(
                'px-3 py-2 text-sm rounded-md border transition-colors',
                filters.status?.includes(status)
                  ? 'bg-primary-50 border-primary-200 text-primary-700'
                  : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
              )}
            >
              {formatOrderStatus(status)}
            </button>
          ))}
        </div>
      </div>

      {/* Payment Status Filter */}
      <div>
        <label className="form-label">Payment Status</label>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 mt-2">
          {paymentStatuses.map(status => (
            <button
              key={status}
              onClick={() => handlePaymentStatusToggle(status)}
              className={cn(
                'px-3 py-2 text-sm rounded-md border transition-colors',
                filters.payment_status?.includes(status)
                  ? 'bg-primary-50 border-primary-200 text-primary-700'
                  : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
              )}
            >
              {status.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* Date Range Filter */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="form-label">From Date</label>
          <div className="relative">
            <Calendar className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="date"
              value={filters.date_from || ''}
              onChange={(e) => handleDateChange('date_from', e.target.value)}
              className="form-input pl-10"
            />
          </div>
        </div>
        
        <div>
          <label className="form-label">To Date</label>
          <div className="relative">
            <Calendar className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="date"
              value={filters.date_to || ''}
              onChange={(e) => handleDateChange('date_to', e.target.value)}
              className="form-input pl-10"
            />
          </div>
        </div>
      </div>

      {/* Interface Type Filter */}
      <div>
        <label className="form-label">Order Source</label>
        <div className="mt-2">
          <select
            value={filters.interface_type || ''}
            onChange={(e) => handleInterfaceTypeChange(e.target.value as any)}
            className="form-select"
          >
            <option value="">All Sources</option>
            {interfaceTypes.map(type => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Active Filters Summary */}
      {hasActiveFilters && (
        <div className="pt-4 border-t border-gray-200">
          <div className="flex flex-wrap gap-2">
            {filters.status?.map(status => (
              <span
                key={`status-${status}`}
                className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
              >
                Status: {formatOrderStatus(status)}
                <button
                  onClick={() => handleStatusToggle(status)}
                  className="ml-1 text-blue-600 hover:text-blue-800"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            
            {filters.payment_status?.map(status => (
              <span
                key={`payment-${status}`}
                className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800"
              >
                Payment: {status.replace('_', ' ')}
                <button
                  onClick={() => handlePaymentStatusToggle(status)}
                  className="ml-1 text-green-600 hover:text-green-800"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            
            {filters.interface_type && (
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                Source: {filters.interface_type}
                <button
                  onClick={() => handleInterfaceTypeChange('')}
                  className="ml-1 text-purple-600 hover:text-purple-800"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
            
            {filters.date_from && (
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                From: {filters.date_from}
                <button
                  onClick={() => handleDateChange('date_from', '')}
                  className="ml-1 text-yellow-600 hover:text-yellow-800"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
            
            {filters.date_to && (
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                To: {filters.date_to}
                <button
                  onClick={() => handleDateChange('date_to', '')}
                  className="ml-1 text-yellow-600 hover:text-yellow-800"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default OrderFilters;