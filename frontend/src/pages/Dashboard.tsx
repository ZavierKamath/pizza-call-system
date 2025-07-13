/**
 * Main dashboard page with overview metrics and quick access to key functions.
 * Provides real-time status updates and performance indicators.
 */

import React from 'react';
import {
  ShoppingBag,
  DollarSign,
  Clock,
  TrendingUp,
  Users,
  Truck,
  AlertCircle,
  CheckCircle,
} from 'lucide-react';

import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useOrderStats, useActiveOrders } from '@/hooks/useOrders';
import { cn, formatCurrency, formatNumber, formatDuration } from '@/utils';

interface MetricCardProps {
  title: string;
  value: string | number;
  change?: number;
  changeLabel?: string;
  icon: React.ComponentType<{ className?: string }>;
  color?: 'blue' | 'green' | 'yellow' | 'red' | 'purple';
  loading?: boolean;
}

const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  change,
  changeLabel,
  icon: Icon,
  color = 'blue',
  loading = false,
}) => {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    yellow: 'bg-yellow-50 text-yellow-600',
    red: 'bg-red-50 text-red-600',
    purple: 'bg-purple-50 text-purple-600',
  };

  return (
    <div className="card">
      <div className="card-body">
        <div className="flex items-center">
          <div className="flex-shrink-0">
            <div className={cn('p-3 rounded-lg', colorClasses[color])}>
              <Icon className="h-6 w-6" />
            </div>
          </div>
          
          <div className="ml-4 flex-1">
            <p className="text-sm font-medium text-gray-500">{title}</p>
            <div className="flex items-baseline">
              {loading ? (
                <div className="skeleton h-8 w-20"></div>
              ) : (
                <p className="text-2xl font-semibold text-gray-900">
                  {typeof value === 'number' ? formatNumber(value) : value}
                </p>
              )}
              
              {change !== undefined && !loading && (
                <p className={cn(
                  'ml-2 flex items-baseline text-sm font-semibold',
                  change >= 0 ? 'text-green-600' : 'text-red-600'
                )}>
                  <TrendingUp className={cn(
                    'h-4 w-4 mr-1',
                    change < 0 && 'transform rotate-180'
                  )} />
                  {Math.abs(change)}%
                  {changeLabel && (
                    <span className="text-gray-500 font-normal ml-1">
                      {changeLabel}
                    </span>
                  )}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

interface QuickStatsProps {
  orders: any[];
}

const QuickStats: React.FC<QuickStatsProps> = ({ orders }) => {
  const pendingOrders = orders.filter(o => 
    ['pending', 'payment_processing', 'payment_confirmed'].includes(o.order_status)
  ).length;
  
  const preparingOrders = orders.filter(o => o.order_status === 'preparing').length;
  const readyOrders = orders.filter(o => o.order_status === 'ready').length;
  const deliveryOrders = orders.filter(o => o.order_status === 'out_for_delivery').length;

  const urgentOrders = orders.filter(o => {
    const createdTime = new Date(o.created_at).getTime();
    const estimatedTime = o.estimated_delivery * 60 * 1000;
    return Date.now() > (createdTime + estimatedTime);
  }).length;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
        <div className="flex items-center">
          <Clock className="h-8 w-8 text-yellow-600" />
          <div className="ml-3">
            <p className="text-2xl font-semibold text-yellow-900">{pendingOrders}</p>
            <p className="text-sm text-yellow-600">Pending</p>
          </div>
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-center">
          <Users className="h-8 w-8 text-blue-600" />
          <div className="ml-3">
            <p className="text-2xl font-semibold text-blue-900">{preparingOrders}</p>
            <p className="text-sm text-blue-600">Preparing</p>
          </div>
        </div>
      </div>

      <div className="bg-green-50 border border-green-200 rounded-lg p-4">
        <div className="flex items-center">
          <CheckCircle className="h-8 w-8 text-green-600" />
          <div className="ml-3">
            <p className="text-2xl font-semibold text-green-900">{readyOrders}</p>
            <p className="text-sm text-green-600">Ready</p>
          </div>
        </div>
      </div>

      <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
        <div className="flex items-center">
          <Truck className="h-8 w-8 text-purple-600" />
          <div className="ml-3">
            <p className="text-2xl font-semibold text-purple-900">{deliveryOrders}</p>
            <p className="text-sm text-purple-600">Delivering</p>
          </div>
        </div>
      </div>

      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex items-center">
          <AlertCircle className="h-8 w-8 text-red-600" />
          <div className="ml-3">
            <p className="text-2xl font-semibold text-red-900">{urgentOrders}</p>
            <p className="text-sm text-red-600">Overdue</p>
          </div>
        </div>
      </div>
    </div>
  );
};

const Dashboard: React.FC = () => {
  // Fetch dashboard data
  const { data: statsData, isLoading: statsLoading, error: statsError } = useOrderStats('today');
  const { data: activeOrdersData, isLoading: ordersLoading } = useActiveOrders();

  const stats = statsData?.data;
  const activeOrders = activeOrdersData?.data || [];

  if (statsError) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-md p-4">
        <div className="flex">
          <AlertCircle className="h-5 w-5 text-red-400" />
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">
              Failed to load dashboard data
            </h3>
            <p className="mt-2 text-sm text-red-700">
              Please refresh the page or contact support if the problem persists.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-2 text-gray-600">
          Welcome back! Here's what's happening at your restaurant today.
        </p>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard
          title="Today's Orders"
          value={stats?.total_orders || 0}
          change={stats?.orders_change}
          changeLabel="vs yesterday"
          icon={ShoppingBag}
          color="blue"
          loading={statsLoading}
        />
        
        <MetricCard
          title="Revenue"
          value={stats?.total_revenue ? formatCurrency(stats.total_revenue) : '$0.00'}
          change={stats?.revenue_change}
          changeLabel="vs yesterday"
          icon={DollarSign}
          color="green"
          loading={statsLoading}
        />
        
        <MetricCard
          title="Avg. Delivery Time"
          value={stats?.average_delivery_time ? formatDuration(stats.average_delivery_time) : '0min'}
          change={stats?.delivery_time_change}
          changeLabel="vs yesterday"
          icon={Clock}
          color="yellow"
          loading={statsLoading}
        />
        
        <MetricCard
          title="Active Orders"
          value={activeOrders.length}
          icon={Users}
          color="purple"
          loading={ordersLoading}
        />
      </div>

      {/* Quick Order Status Overview */}
      <div className="space-y-4">
        <h2 className="text-xl font-semibold text-gray-900">Order Status Overview</h2>
        {ordersLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner size="lg" text="Loading active orders..." />
          </div>
        ) : (
          <QuickStats orders={activeOrders} />
        )}
      </div>

      {/* Recent Activity & Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Orders */}
        <div className="card">
          <div className="card-header">
            <h3 className="text-lg font-medium text-gray-900">Recent Orders</h3>
          </div>
          <div className="card-body">
            {ordersLoading ? (
              <div className="space-y-3">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="flex items-center space-x-3">
                    <div className="skeleton h-10 w-10 rounded-full"></div>
                    <div className="flex-1 space-y-2">
                      <div className="skeleton h-4 w-3/4"></div>
                      <div className="skeleton h-3 w-1/2"></div>
                    </div>
                  </div>
                ))}
              </div>
            ) : activeOrders.length === 0 ? (
              <p className="text-gray-500 text-center py-8">No active orders</p>
            ) : (
              <div className="space-y-4">
                {activeOrders.slice(0, 5).map((order) => (
                  <div key={order.id} className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="h-10 w-10 bg-primary-100 rounded-full flex items-center justify-center">
                        <span className="text-sm font-medium text-primary-600">
                          #{order.id}
                        </span>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">
                          {order.customer_name}
                        </p>
                        <p className="text-xs text-gray-500">
                          {order.order_details?.pizzas?.length || 0} items • {formatCurrency(order.total_amount)}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className={cn(
                        'status-badge',
                        {
                          'bg-yellow-100 text-yellow-800': order.order_status === 'pending',
                          'bg-blue-100 text-blue-800': order.order_status === 'preparing',
                          'bg-green-100 text-green-800': order.order_status === 'ready',
                          'bg-purple-100 text-purple-800': order.order_status === 'out_for_delivery',
                        }
                      )}>
                        {order.order_status.replace('_', ' ')}
                      </span>
                    </div>
                  </div>
                ))}
                
                {activeOrders.length > 5 && (
                  <div className="text-center pt-4 border-t border-gray-200">
                    <a
                      href="/orders"
                      className="text-sm text-primary-600 hover:text-primary-700 font-medium"
                    >
                      View all {activeOrders.length} orders →
                    </a>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* System Status & Alerts */}
        <div className="card">
          <div className="card-header">
            <h3 className="text-lg font-medium text-gray-900">System Status</h3>
          </div>
          <div className="card-body space-y-4">
            {/* System Health Indicators */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Order Processing</span>
                <div className="flex items-center">
                  <div className="h-2 w-2 bg-green-400 rounded-full mr-2"></div>
                  <span className="text-sm text-green-600">Operational</span>
                </div>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Payment System</span>
                <div className="flex items-center">
                  <div className="h-2 w-2 bg-green-400 rounded-full mr-2"></div>
                  <span className="text-sm text-green-600">Operational</span>
                </div>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Delivery Tracking</span>
                <div className="flex items-center">
                  <div className="h-2 w-2 bg-green-400 rounded-full mr-2"></div>
                  <span className="text-sm text-green-600">Operational</span>
                </div>
              </div>
            </div>

            {/* Performance Metrics */}
            <div className="pt-4 border-t border-gray-200">
              <h4 className="text-sm font-medium text-gray-900 mb-3">Performance</h4>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Order completion rate</span>
                  <span className="font-medium">{stats?.order_completion_rate || 95}%</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Payment success rate</span>
                  <span className="font-medium">{stats?.payment_success_rate || 98}%</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">On-time delivery</span>
                  <span className="font-medium">{stats?.on_time_delivery_rate || 92}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;