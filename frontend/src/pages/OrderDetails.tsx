/**
 * Order details page for viewing and managing individual orders.
 * Provides comprehensive order information and management actions.
 */

import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Edit, Print, RefreshCw } from 'lucide-react';

import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useOrder } from '@/hooks/useOrders';
import { formatCurrency, formatDetailedDate, formatPhoneNumber } from '@/utils';

const OrderDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const orderId = Number(id);

  const { data: orderData, isLoading, error, refetch } = useOrder(orderId);
  const order = orderData?.data;

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner size="lg" text="Loading order details..." />
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-md p-4">
        <h3 className="text-sm font-medium text-red-800">
          Order not found
        </h3>
        <p className="mt-2 text-sm text-red-700">
          The order you're looking for doesn't exist or has been removed.
        </p>
        <button
          onClick={() => navigate('/orders')}
          className="mt-3 btn-secondary"
        >
          Back to Orders
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/orders')}
            className="p-2 rounded-md text-gray-400 hover:text-gray-600"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Order #{order.id}
            </h1>
            <p className="text-sm text-gray-600">
              Created {formatDetailedDate(order.created_at)}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={() => refetch()}
            className="btn-secondary"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </button>
          <button className="btn-secondary">
            <Print className="h-4 w-4 mr-2" />
            Print
          </button>
          <button className="btn-primary">
            <Edit className="h-4 w-4 mr-2" />
            Edit Order
          </button>
        </div>
      </div>

      {/* Order Information */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Order Details */}
        <div className="lg:col-span-2 space-y-6">
          {/* Customer Information */}
          <div className="card">
            <div className="card-header">
              <h2 className="text-lg font-medium text-gray-900">Customer Information</h2>
            </div>
            <div className="card-body space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-500">Name</label>
                <p className="text-sm text-gray-900">{order.customer_name}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Phone</label>
                <p className="text-sm text-gray-900">{formatPhoneNumber(order.phone_number)}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Address</label>
                <p className="text-sm text-gray-900">{order.address}</p>
              </div>
            </div>
          </div>

          {/* Order Items */}
          <div className="card">
            <div className="card-header">
              <h2 className="text-lg font-medium text-gray-900">Order Items</h2>
            </div>
            <div className="card-body">
              {order.order_details?.pizzas?.map((pizza, index) => (
                <div key={index} className="border-b border-gray-200 pb-4 mb-4 last:border-b-0 last:mb-0 last:pb-0">
                  <div className="flex justify-between">
                    <div>
                      <h4 className="font-medium text-gray-900">
                        {pizza.size.charAt(0).toUpperCase() + pizza.size.slice(1)} Pizza
                      </h4>
                      <p className="text-sm text-gray-600">
                        {pizza.toppings?.length > 0 ? pizza.toppings.join(', ') : 'Plain'}
                      </p>
                      <p className="text-sm text-gray-500">Quantity: {pizza.quantity}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-medium text-gray-900">
                        {formatCurrency(pizza.price)}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
              
              <div className="pt-4 border-t border-gray-200">
                <div className="flex justify-between text-lg font-semibold">
                  <span>Total</span>
                  <span>{formatCurrency(order.total_amount)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Status & Progress */}
          <div className="card">
            <div className="card-header">
              <h2 className="text-lg font-medium text-gray-900">Status</h2>
            </div>
            <div className="card-body space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-500">Order Status</label>
                <p className="text-sm text-gray-900 capitalize">
                  {order.order_status.replace('_', ' ')}
                </p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Payment Status</label>
                <p className="text-sm text-gray-900 capitalize">
                  {order.payment_status}
                </p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Payment Method</label>
                <p className="text-sm text-gray-900 capitalize">
                  {order.payment_method}
                </p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Estimated Delivery</label>
                <p className="text-sm text-gray-900">
                  {order.estimated_delivery} minutes
                </p>
              </div>
            </div>
          </div>

          {/* Order Source */}
          <div className="card">
            <div className="card-header">
              <h2 className="text-lg font-medium text-gray-900">Order Details</h2>
            </div>
            <div className="card-body space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-500">Source</label>
                <p className="text-sm text-gray-900 capitalize">
                  {order.interface_type} Order
                </p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Created</label>
                <p className="text-sm text-gray-900">
                  {formatDetailedDate(order.created_at)}
                </p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Last Updated</label>
                <p className="text-sm text-gray-900">
                  {formatDetailedDate(order.updated_at)}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OrderDetails;