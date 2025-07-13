/**
 * React Query hook for managing order data and operations.
 * Provides optimistic updates, caching, and real-time synchronization.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';

import {
  fetchOrders,
  fetchOrder,
  updateOrderStatus,
  updatePaymentStatus,
  updateDeliveryEstimate,
  cancelOrder,
  refundOrder,
  fetchActiveOrders,
  fetchOrderStats,
} from '@/services/orderService';
import { REFRESH_INTERVALS } from '@/utils/constants';
import type { OrderFilter, Order, PaginatedResponse } from '@/types';

// Query keys for consistent caching
export const orderKeys = {
  all: ['orders'] as const,
  lists: () => [...orderKeys.all, 'list'] as const,
  list: (filters: OrderFilter) => [...orderKeys.lists(), filters] as const,
  details: () => [...orderKeys.all, 'detail'] as const,
  detail: (id: number) => [...orderKeys.details(), id] as const,
  stats: () => [...orderKeys.all, 'stats'] as const,
  active: () => [...orderKeys.all, 'active'] as const,
};

interface UseOrdersOptions {
  page?: number;
  limit?: number;
  enabled?: boolean;
  refetchInterval?: number;
}

/**
 * Hook for fetching and managing orders list.
 */
export const useOrders = (
  filters: OrderFilter = {},
  options: UseOrdersOptions = {}
) => {
  const {
    page = 1,
    limit = 20,
    enabled = true,
    refetchInterval = REFRESH_INTERVALS.ORDERS,
  } = options;

  return useQuery({
    queryKey: orderKeys.list({ ...filters, page, limit }),
    queryFn: () => fetchOrders(filters, page, limit),
    enabled,
    refetchInterval,
    keepPreviousData: true,
    staleTime: 1000 * 30, // 30 seconds
  });
};

/**
 * Hook for fetching a single order.
 */
export const useOrder = (orderId: number, enabled = true) => {
  return useQuery({
    queryKey: orderKeys.detail(orderId),
    queryFn: () => fetchOrder(orderId),
    enabled: enabled && !!orderId,
    staleTime: 1000 * 60, // 1 minute
  });
};

/**
 * Hook for fetching active orders.
 */
export const useActiveOrders = (enabled = true) => {
  return useQuery({
    queryKey: orderKeys.active(),
    queryFn: fetchActiveOrders,
    enabled,
    refetchInterval: REFRESH_INTERVALS.ORDERS,
    staleTime: 1000 * 30, // 30 seconds
  });
};

/**
 * Hook for fetching order statistics.
 */
export const useOrderStats = (period: 'today' | 'week' | 'month' = 'today') => {
  return useQuery({
    queryKey: [...orderKeys.stats(), period],
    queryFn: () => fetchOrderStats(period),
    staleTime: 1000 * 60 * 5, // 5 minutes
    cacheTime: 1000 * 60 * 10, // 10 minutes
  });
};

/**
 * Hook for updating order status.
 */
export const useUpdateOrderStatus = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ 
      orderId, 
      newStatus, 
      notes 
    }: { 
      orderId: number; 
      newStatus: string; 
      notes?: string; 
    }) => updateOrderStatus(orderId, newStatus, notes),
    
    onMutate: async ({ orderId, newStatus }) => {
      // Cancel outgoing queries to avoid overwriting optimistic update
      await queryClient.cancelQueries({ queryKey: orderKeys.detail(orderId) });

      // Get snapshot of previous data
      const previousOrder = queryClient.getQueryData<Order>(orderKeys.detail(orderId));

      // Optimistically update order status
      if (previousOrder) {
        queryClient.setQueryData(orderKeys.detail(orderId), {
          ...previousOrder,
          order_status: newStatus,
          updated_at: new Date().toISOString(),
        });
      }

      // Update orders list cache
      queryClient.setQueriesData(
        { queryKey: orderKeys.lists() },
        (oldData: PaginatedResponse<Order> | undefined) => {
          if (!oldData) return oldData;
          
          return {
            ...oldData,
            data: oldData.data.map(order =>
              order.id === orderId
                ? { ...order, order_status: newStatus as any, updated_at: new Date().toISOString() }
                : order
            ),
          };
        }
      );

      return { previousOrder };
    },

    onError: (error, variables, context) => {
      // Revert optimistic update on error
      if (context?.previousOrder) {
        queryClient.setQueryData(orderKeys.detail(variables.orderId), context.previousOrder);
      }
      
      toast.error('Failed to update order status');
      console.error('Order status update error:', error);
    },

    onSuccess: (data, { orderId, newStatus }) => {
      toast.success(`Order #${orderId} status updated to ${newStatus}`);
      
      // Invalidate related queries to ensure consistency
      queryClient.invalidateQueries({ queryKey: orderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: orderKeys.active() });
      queryClient.invalidateQueries({ queryKey: orderKeys.stats() });
    },
  });
};

/**
 * Hook for updating payment status.
 */
export const useUpdatePaymentStatus = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ 
      orderId, 
      paymentStatus 
    }: { 
      orderId: number; 
      paymentStatus: string; 
    }) => updatePaymentStatus(orderId, paymentStatus),
    
    onSuccess: (data, { orderId, paymentStatus }) => {
      toast.success(`Payment status updated to ${paymentStatus}`);
      
      // Invalidate queries
      queryClient.invalidateQueries({ queryKey: orderKeys.detail(orderId) });
      queryClient.invalidateQueries({ queryKey: orderKeys.lists() });
    },

    onError: (error) => {
      toast.error('Failed to update payment status');
      console.error('Payment status update error:', error);
    },
  });
};

/**
 * Hook for updating delivery estimate.
 */
export const useUpdateDeliveryEstimate = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ 
      orderId, 
      estimatedMinutes 
    }: { 
      orderId: number; 
      estimatedMinutes: number; 
    }) => updateDeliveryEstimate(orderId, estimatedMinutes),
    
    onSuccess: (data, { orderId, estimatedMinutes }) => {
      toast.success(`Delivery estimate updated to ${estimatedMinutes} minutes`);
      
      // Invalidate queries
      queryClient.invalidateQueries({ queryKey: orderKeys.detail(orderId) });
      queryClient.invalidateQueries({ queryKey: orderKeys.lists() });
    },

    onError: (error) => {
      toast.error('Failed to update delivery estimate');
      console.error('Delivery estimate update error:', error);
    },
  });
};

/**
 * Hook for canceling an order.
 */
export const useCancelOrder = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ 
      orderId, 
      reason 
    }: { 
      orderId: number; 
      reason?: string; 
    }) => cancelOrder(orderId, reason),
    
    onSuccess: (data, { orderId }) => {
      toast.success(`Order #${orderId} has been canceled`);
      
      // Invalidate queries
      queryClient.invalidateQueries({ queryKey: orderKeys.detail(orderId) });
      queryClient.invalidateQueries({ queryKey: orderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: orderKeys.active() });
    },

    onError: (error) => {
      toast.error('Failed to cancel order');
      console.error('Order cancellation error:', error);
    },
  });
};

/**
 * Hook for refunding an order.
 */
export const useRefundOrder = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ 
      orderId, 
      amount, 
      reason 
    }: { 
      orderId: number; 
      amount?: number; 
      reason?: string; 
    }) => refundOrder(orderId, amount, reason),
    
    onSuccess: (data, { orderId }) => {
      toast.success(`Refund processed for order #${orderId}`);
      
      // Invalidate queries
      queryClient.invalidateQueries({ queryKey: orderKeys.detail(orderId) });
      queryClient.invalidateQueries({ queryKey: orderKeys.lists() });
    },

    onError: (error) => {
      toast.error('Failed to process refund');
      console.error('Order refund error:', error);
    },
  });
};

/**
 * Hook for bulk operations on orders.
 */
export const useBulkOrderOperations = () => {
  const queryClient = useQueryClient();

  const bulkUpdateStatus = useMutation({
    mutationFn: async ({ 
      orderIds, 
      newStatus 
    }: { 
      orderIds: number[]; 
      newStatus: string; 
    }) => {
      const results = await Promise.allSettled(
        orderIds.map(id => updateOrderStatus(id, newStatus))
      );
      return results;
    },
    
    onSuccess: (results, { orderIds, newStatus }) => {
      const successful = results.filter(r => r.status === 'fulfilled').length;
      const failed = results.filter(r => r.status === 'rejected').length;
      
      if (successful > 0) {
        toast.success(`Updated ${successful} order${successful !== 1 ? 's' : ''} to ${newStatus}`);
      }
      
      if (failed > 0) {
        toast.error(`Failed to update ${failed} order${failed !== 1 ? 's' : ''}`);
      }
      
      // Invalidate all order queries
      queryClient.invalidateQueries({ queryKey: orderKeys.all });
    },

    onError: (error) => {
      toast.error('Bulk operation failed');
      console.error('Bulk order operation error:', error);
    },
  });

  return { bulkUpdateStatus };
};