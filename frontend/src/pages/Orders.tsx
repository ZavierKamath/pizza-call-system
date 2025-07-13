/**
 * Orders page displaying the complete order management interface.
 * Integrates OrdersGrid with real-time updates and navigation.
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import OrdersGrid from '@/components/orders/OrdersGrid';
import { useUpdateOrderStatus } from '@/hooks/useOrders';

const Orders: React.FC = () => {
  const navigate = useNavigate();
  const updateOrderStatus = useUpdateOrderStatus();

  const handleOrderSelect = (orderId: number) => {
    navigate(`/orders/${orderId}`);
  };

  const handleStatusUpdate = async (orderId: number, newStatus: string) => {
    try {
      await updateOrderStatus.mutateAsync({
        orderId,
        newStatus,
      });
    } catch (error) {
      console.error('Failed to update order status:', error);
    }
  };

  return (
    <div>
      <OrdersGrid
        onOrderSelect={handleOrderSelect}
        onStatusUpdate={handleStatusUpdate}
      />
    </div>
  );
};

export default Orders;