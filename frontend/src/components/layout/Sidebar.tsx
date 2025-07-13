/**
 * Sidebar navigation component with menu items and restaurant branding.
 * Handles active states and responsive behavior.
 */

import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Home,
  ShoppingBag,
  Truck,
  BarChart3,
  Settings,
  Users,
  CreditCard,
  MapPin,
  X,
  Pizza,
} from 'lucide-react';

import { cn } from '@/utils';

interface SidebarProps {
  onClose?: () => void;
}

interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number;
  description?: string;
}

const Sidebar: React.FC<SidebarProps> = ({ onClose }) => {
  const location = useLocation();

  // Navigation menu items
  const navigation: NavItem[] = [
    {
      name: 'Dashboard',
      href: '/',
      icon: Home,
      description: 'Overview and key metrics',
    },
    {
      name: 'Orders',
      href: '/orders',
      icon: ShoppingBag,
      description: 'Manage active orders',
    },
    {
      name: 'Deliveries',
      href: '/deliveries',
      icon: Truck,
      description: 'Track delivery status',
    },
    {
      name: 'Delivery Map',
      href: '/delivery-map',
      icon: MapPin,
      description: 'Live delivery tracking',
    },
    {
      name: 'Analytics',
      href: '/analytics',
      icon: BarChart3,
      description: 'Performance reports',
    },
    {
      name: 'Payments',
      href: '/payments',
      icon: CreditCard,
      description: 'Payment processing',
    },
    {
      name: 'Staff',
      href: '/staff',
      icon: Users,
      description: 'Staff management',
    },
    {
      name: 'Settings',
      href: '/settings',
      icon: Settings,
      description: 'System configuration',
    },
  ];

  const isActive = (href: string): boolean => {
    if (href === '/') {
      return location.pathname === '/';
    }
    return location.pathname.startsWith(href);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between h-16 px-6 border-b border-gray-200">
        <div className="flex items-center">
          <Pizza className="h-8 w-8 text-primary-600" />
          <span className="ml-2 text-xl font-bold text-gray-900">
            PizzaDash
          </span>
        </div>
        
        {/* Close button for mobile */}
        <button
          onClick={onClose}
          className="lg:hidden p-1 rounded-md text-gray-400 hover:text-gray-500 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <X className="h-6 w-6" />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-6 space-y-1 overflow-y-auto">
        {navigation.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href);
          
          return (
            <NavLink
              key={item.name}
              to={item.href}
              onClick={onClose} // Close sidebar on mobile when item is clicked
              className={cn(
                'group flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors duration-150',
                active
                  ? 'bg-primary-100 text-primary-700 border-r-2 border-primary-600'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
              )}
            >
              <Icon
                className={cn(
                  'mr-3 h-5 w-5 flex-shrink-0',
                  active
                    ? 'text-primary-600'
                    : 'text-gray-400 group-hover:text-gray-500'
                )}
              />
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span>{item.name}</span>
                  {item.badge && (
                    <span className="bg-primary-600 text-white text-xs rounded-full px-2 py-1 min-w-[20px] text-center">
                      {item.badge}
                    </span>
                  )}
                </div>
                {item.description && (
                  <p className="text-xs text-gray-500 mt-0.5">
                    {item.description}
                  </p>
                )}
              </div>
            </NavLink>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-200">
        <div className="bg-gray-50 rounded-lg p-3">
          <div className="flex items-center">
            <div className="h-2 w-2 bg-green-400 rounded-full mr-2 animate-pulse"></div>
            <span className="text-xs text-gray-600">System Online</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            All services operational
          </p>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;