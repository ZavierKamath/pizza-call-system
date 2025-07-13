/**
 * Orders grid component displaying active orders in a responsive grid layout.
 * Provides real-time updates, filtering, and quick actions for order management.
 */

import React, { useState, useMemo } from 'react';
import { Search, Filter, RefreshCw, Plus } from 'lucide-react';

import OrderCard from './OrderCard';
import OrderFilters from './OrderFilters';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useOrders } from '@/hooks/useOrders';
import { cn, formatNumber } from '@/utils';
import type { OrderFilter, OrderStatus, PaymentStatus } from '@/types';

interface OrdersGridProps {
  className?: string;
  onOrderSelect?: (orderId: number) => void;
  filterOverride?: Partial<OrderFilter>;
}

const OrdersGrid: React.FC<OrdersGridProps> = ({
  className,
  onOrderSelect,
  filterOverride,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<OrderFilter>({
    ...filterOverride,
  });

  // Fetch orders with real-time updates
  const {
    data: ordersData,
    isLoading,
    isError,
    error,
    refetch,
    isRefetching,
  } = useOrders({
    ...filters,
    search: searchQuery.trim() || undefined,
  });

  const orders = ordersData?.data || [];
  const pagination = ordersData?.pagination;

  // Group orders by status for better organization
  const groupedOrders = useMemo(() => {
    const groups: Record<string, typeof orders> = {};
    
    orders.forEach(order => {
      const status = order.order_status;
      if (!groups[status]) {
        groups[status] = [];
      }
      groups[status].push(order);
    });

    return groups;
  }, [orders]);

  // Status order for display priority
  const statusOrder: OrderStatus[] = [
    'pending',
    'payment_processing',
    'payment_confirmed',
    'preparing',
    'ready',
    'out_for_delivery',
    'delivered',
    'payment_failed',
    'canceled',
  ];

  const handleFilterChange = (newFilters: Partial<OrderFilter>) => {
    setFilters(prev => ({ ...prev, ...newFilters }));
  };

  const clearFilters = () => {
    setFilters({});
    setSearchQuery('');
  };

  const getStatusDisplayName = (status: string): string => {
    return status
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const getStatusCount = (status: string): number => {
    return groupedOrders[status]?.length || 0;
  };

  if (isError) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-md p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">
              Error loading orders
            </h3>
            <div className="mt-2 text-sm text-red-700">
              <p>{error?.message || 'Failed to load orders. Please try again.'}</p>
            </div>
            <div className="mt-4">
              <button
                onClick={() => refetch()}
                className="btn-secondary text-sm"
              >
                Try Again
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Orders</h2>
          <p className="text-sm text-gray-600">
            {pagination ? formatNumber(pagination.total) : 0} total orders
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={() => refetch()}
            disabled={isRefetching}
            className="btn-secondary"
          >
            <RefreshCw className={cn('h-4 w-4 mr-2', isRefetching && 'animate-spin')} />
            Refresh
          </button>
          
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="btn-secondary"
          >
            <Filter className="h-4 w-4 mr-2" />
            Filters
          </button>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="space-y-4">
        {/* Search Bar */}
        <div className="relative max-w-md">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-5 w-5 text-gray-400" />
          </div>
          <input
            type="text"
            placeholder="Search orders, customers, phone..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="form-input pl-10"
          />
        </div>

        {/* Filters Panel */}
        {showFilters && (
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <OrderFilters
              filters={filters}
              onFiltersChange={handleFilterChange}
              onClear={clearFilters}
            />
          </div>
        )}
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="flex justify-center py-12">
          <LoadingSpinner size="lg" text="Loading orders..." />
        </div>
      )}

      {/* Orders Display */}
      {!isLoading && (
        <>
          {orders.length === 0 ? (
            <div className="text-center py-12">
              <div className="mx-auto h-12 w-12 text-gray-400">
                <Plus className="h-12 w-12" />
              </div>
              <h3 className="mt-2 text-sm font-medium text-gray-900">No orders found</h3>
              <p className="mt-1 text-sm text-gray-500">
                {searchQuery || Object.keys(filters).length > 0
                  ? 'Try adjusting your search or filters'
                  : 'Orders will appear here as they come in'}
              </p>
              {(searchQuery || Object.keys(filters).length > 0) && (
                <button
                  onClick={clearFilters}
                  className="mt-3 btn-secondary"
                >
                  Clear filters
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-6">
              {statusOrder.map(status => {
                const statusOrders = groupedOrders[status];
                if (!statusOrders || statusOrders.length === 0) {
                  return null;
                }

                return (
                  <div key={status} className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-lg font-medium text-gray-900">
                        {getStatusDisplayName(status)}
                      </h3>
                      <span className="bg-gray-100 text-gray-800 px-2 py-1 rounded-full text-sm">
                        {getStatusCount(status)}
                      </span>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                      {statusOrders.map(order => (
                        <OrderCard
                          key={order.id}
                          order={order}
                          onClick={() => onOrderSelect?.(order.id)}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination */}
          {pagination && pagination.pages > 1 && (
            <div className="flex items-center justify-between border-t border-gray-200 bg-white px-4 py-3 sm:px-6">
              <div className="flex flex-1 justify-between sm:hidden">
                <button
                  disabled={pagination.page <= 1}
                  className="btn-secondary disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  disabled={pagination.page >= pagination.pages}
                  className="btn-secondary disabled:opacity-50"
                >
                  Next
                </button>
              </div>
              <div className="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm text-gray-700">
                    Showing{' '}
                    <span className="font-medium">
                      {((pagination.page - 1) * pagination.limit) + 1}
                    </span>{' '}
                    to{' '}
                    <span className="font-medium">
                      {Math.min(pagination.page * pagination.limit, pagination.total)}
                    </span>{' '}
                    of{' '}
                    <span className="font-medium">{pagination.total}</span>{' '}
                    results
                  </p>
                </div>
                <div>
                  <nav className="isolate inline-flex -space-x-px rounded-md shadow-sm">
                    {/* Pagination buttons would go here */}
                  </nav>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default OrdersGrid;