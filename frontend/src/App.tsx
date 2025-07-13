/**
 * Main App component with routing and error boundary setup.
 * Provides the overall application structure and navigation.
 */

import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

import ErrorBoundary from '@/components/common/ErrorBoundary';
import DashboardLayout from '@/components/layout/DashboardLayout';

// Lazy load pages for better performance
const Dashboard = React.lazy(() => import('@/pages/Dashboard'));
const Orders = React.lazy(() => import('@/pages/Orders'));
const OrderDetails = React.lazy(() => import('@/pages/OrderDetails'));
const Deliveries = React.lazy(() => import('@/pages/Deliveries'));
const DeliveryMap = React.lazy(() => import('@/pages/DeliveryMap'));
const Analytics = React.lazy(() => import('@/pages/Analytics'));
const Payments = React.lazy(() => import('@/pages/Payments'));
const Staff = React.lazy(() => import('@/pages/Staff'));
const Settings = React.lazy(() => import('@/pages/Settings'));

// Loading fallback component
const PageLoader: React.FC = () => (
  <div className="flex items-center justify-center h-64">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
  </div>
);

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <React.Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Main dashboard routes */}
          <Route path="/" element={<DashboardLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="orders" element={<Orders />} />
            <Route path="orders/:id" element={<OrderDetails />} />
            <Route path="deliveries" element={<Deliveries />} />
            <Route path="delivery-map" element={<DeliveryMap />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="payments" element={<Payments />} />
            <Route path="staff" element={<Staff />} />
            <Route path="settings" element={<Settings />} />
          </Route>

          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </React.Suspense>
    </ErrorBoundary>
  );
};

export default App;