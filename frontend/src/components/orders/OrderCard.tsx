/**
 * Individual order card component for displaying order summary.
 * Shows key order information with status indicators and quick actions.
 */

import React, { useState } from 'react';
import {
  Clock,
  Phone,
  MapPin,
  DollarSign,
  MoreVertical,
  Edit,
  Eye,
  Truck,
  CheckCircle,
  AlertCircle,
  User,
} from 'lucide-react';

import {
  cn,
  formatCurrency,
  formatOrderDate,
  formatPhoneNumber,
  formatCompactAddress,
  formatDuration,
  ORDER_STATUS_COLORS,
  PAYMENT_STATUS_COLORS,
} from '@/utils';
import type { Order } from '@/types';

interface OrderCardProps {
  order: Order;
  onClick?: () => void;
  onStatusUpdate?: (orderId: number, newStatus: string) => void;
  className?: string;
}

const OrderCard: React.FC<OrderCardProps> = ({
  order,
  onClick,
  onStatusUpdate,
  className,
}) => {
  const [showActions, setShowActions] = useState(false);

  const pizzaCount = order.order_details?.pizzas?.length || 0;
  const isUrgent = order.estimated_delivery <= 15; // Less than 15 minutes
  const isOverdue = new Date(order.created_at).getTime() + (order.estimated_delivery * 60 * 1000) < Date.now();

  const handleStatusUpdate = (newStatus: string) => {
    onStatusUpdate?.(order.id, newStatus);
    setShowActions(false);
  };

  const getStatusActions = () => {
    const actions = [];
    
    switch (order.order_status) {
      case 'pending':
        actions.push({ label: 'Confirm Payment', status: 'payment_confirmed' });
        actions.push({ label: 'Cancel', status: 'canceled' });
        break;
      case 'payment_confirmed':
        actions.push({ label: 'Start Preparing', status: 'preparing' });
        break;
      case 'preparing':
        actions.push({ label: 'Mark Ready', status: 'ready' });
        break;
      case 'ready':
        actions.push({ label: 'Out for Delivery', status: 'out_for_delivery' });
        break;
      case 'out_for_delivery':
        actions.push({ label: 'Mark Delivered', status: 'delivered' });
        break;
    }
    
    return actions;
  };

  const statusActions = getStatusActions();

  return (
    <div
      className={cn(
        'bg-white rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-shadow duration-200 cursor-pointer',
        isUrgent && 'ring-2 ring-orange-200',
        isOverdue && 'ring-2 ring-red-200',
        className
      )}
      onClick={onClick}
    >
      <div className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center space-x-2">
            <span className="text-lg font-semibold text-gray-900">
              #{order.id}
            </span>
            {isUrgent && (
              <AlertCircle className="h-4 w-4 text-orange-500" />
            )}
            {isOverdue && (
              <AlertCircle className="h-4 w-4 text-red-500" />
            )}
          </div>
          
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowActions(!showActions);
              }}
              className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100"
            >
              <MoreVertical className="h-4 w-4" />
            </button>

            {/* Actions dropdown */}
            {showActions && (
              <div className="absolute right-0 mt-1 w-48 bg-white rounded-md shadow-lg ring-1 ring-black ring-opacity-5 z-10">
                <div className="py-1">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onClick?.();
                      setShowActions(false);
                    }}
                    className="flex items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                  >
                    <Eye className="h-4 w-4 mr-3" />
                    View Details
                  </button>
                  
                  {statusActions.map((action, index) => (
                    <button
                      key={index}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleStatusUpdate(action.status);
                      }}
                      className="flex items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    >
                      <CheckCircle className="h-4 w-4 mr-3" />
                      {action.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Status Badges */}
        <div className="flex flex-wrap gap-2">
          <span
            className={cn(
              'status-badge',
              ORDER_STATUS_COLORS[order.order_status] || 'bg-gray-100 text-gray-800'
            )}
          >
            {order.order_status.replace('_', ' ')}
          </span>
          <span
            className={cn(
              'status-badge',
              PAYMENT_STATUS_COLORS[order.payment_status] || 'bg-gray-100 text-gray-800'
            )}
          >
            {order.payment_status}
          </span>
        </div>

        {/* Customer Info */}
        <div className="space-y-2">
          <div className="flex items-center text-sm text-gray-600">
            <User className="h-4 w-4 mr-2" />
            <span className="font-medium">{order.customer_name}</span>
          </div>
          
          <div className="flex items-center text-sm text-gray-600">
            <Phone className="h-4 w-4 mr-2" />
            <span>{formatPhoneNumber(order.phone_number)}</span>
          </div>
          
          <div className="flex items-start text-sm text-gray-600">
            <MapPin className="h-4 w-4 mr-2 mt-0.5 flex-shrink-0" />
            <span className="line-clamp-2">
              {formatCompactAddress(order.address, 40)}
            </span>
          </div>
        </div>

        {/* Order Details */}
        <div className="space-y-2">
          <div className="text-sm text-gray-700">
            <span className="font-medium">{pizzaCount}</span> pizza{pizzaCount !== 1 ? 's' : ''}
            {order.order_details?.pizzas?.[0] && (
              <span className="text-gray-500">
                {' '}• {order.order_details.pizzas[0].size} {order.order_details.pizzas[0].toppings?.[0] || 'plain'}
                {order.order_details.pizzas.length > 1 && ` +${order.order_details.pizzas.length - 1} more`}
              </span>
            )}
          </div>
          
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center text-gray-600">
              <DollarSign className="h-4 w-4 mr-1" />
              <span className="font-medium text-gray-900">
                {formatCurrency(order.total_amount)}
              </span>
            </div>
            
            <div className="flex items-center text-gray-600">
              <Clock className="h-4 w-4 mr-1" />
              <span>{formatDuration(order.estimated_delivery)}</span>
            </div>
          </div>
        </div>

        {/* Interface Type */}
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span className="flex items-center">
            {order.interface_type === 'phone' ? (
              <Phone className="h-3 w-3 mr-1" />
            ) : (
              <Truck className="h-3 w-3 mr-1" />
            )}
            {order.interface_type} order
          </span>
          
          <span>{formatOrderDate(order.created_at)}</span>
        </div>
      </div>

      {/* Click outside handler for actions dropdown */}
      {showActions && (
        <div
          className="fixed inset-0 z-5"
          onClick={(e) => {
            e.stopPropagation();
            setShowActions(false);
          }}
        />
      )}
    </div>
  );
};

export default OrderCard;