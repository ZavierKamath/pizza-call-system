/**
 * Dashboard header component with menu toggle, notifications, and user controls.
 * Displays real-time connection status and system alerts.
 */

import React, { useState } from 'react';
import {
  Menu,
  Bell,
  Search,
  Wifi,
  WifiOff,
  RefreshCw,
  User,
  Settings,
  LogOut,
  ChevronDown,
} from 'lucide-react';

import { cn, formatDetailedDate } from '@/utils';
import { useWebSocket } from '@/hooks/useWebSocket';

interface HeaderProps {
  onMenuClick: () => void;
  sidebarOpen: boolean;
}

const Header: React.FC<HeaderProps> = ({ onMenuClick, sidebarOpen }) => {
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  
  // WebSocket connection status
  const { isConnected, isReconnecting, connectionCount } = useWebSocket();

  // Mock notifications - in real app, these would come from context/state
  const notifications = [
    {
      id: 1,
      type: 'order',
      title: 'New Order #1234',
      message: 'Large Pepperoni Pizza - $18.99',
      time: new Date().toISOString(),
      read: false,
    },
    {
      id: 2,
      type: 'delivery',
      title: 'Delivery Completed',
      message: 'Order #1230 delivered successfully',
      time: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      read: false,
    },
    {
      id: 3,
      type: 'alert',
      title: 'High Order Volume',
      message: 'Current wait time increased to 45 minutes',
      time: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
      read: true,
    },
  ];

  const unreadCount = notifications.filter(n => !n.read).length;

  const getConnectionStatus = () => {
    if (isReconnecting) {
      return {
        icon: RefreshCw,
        text: 'Reconnecting...',
        className: 'text-yellow-600 animate-spin',
      };
    } else if (isConnected) {
      return {
        icon: Wifi,
        text: `Connected (${connectionCount})`,
        className: 'text-green-600',
      };
    } else {
      return {
        icon: WifiOff,
        text: 'Disconnected',
        className: 'text-red-600',
      };
    }
  };

  const connectionStatus = getConnectionStatus();
  const ConnectionIcon = connectionStatus.icon;

  return (
    <header className="bg-white shadow-sm border-b border-gray-200 h-16 flex items-center justify-between px-4 sm:px-6 lg:px-8">
      {/* Left side - Menu toggle and search */}
      <div className="flex items-center">
        {/* Mobile menu button */}
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 rounded-md text-gray-400 hover:text-gray-500 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <Menu className="h-6 w-6" />
        </button>

        {/* Search bar */}
        <div className="hidden sm:block ml-4">
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search className="h-5 w-5 text-gray-400" />
            </div>
            <input
              type="text"
              placeholder="Search orders, customers..."
              className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md leading-5 bg-white text-gray-900 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
            />
          </div>
        </div>
      </div>

      {/* Right side - Status, notifications, and user menu */}
      <div className="flex items-center space-x-4">
        {/* Connection status */}
        <div className="hidden sm:flex items-center space-x-2 text-sm">
          <ConnectionIcon className={cn('h-4 w-4', connectionStatus.className)} />
          <span className={cn('font-medium', connectionStatus.className)}>
            {connectionStatus.text}
          </span>
        </div>

        {/* Notifications */}
        <div className="relative">
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="p-2 rounded-md text-gray-400 hover:text-gray-500 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 relative"
          >
            <Bell className="h-6 w-6" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 h-5 w-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                {unreadCount}
              </span>
            )}
          </button>

          {/* Notifications dropdown */}
          {showNotifications && (
            <div className="absolute right-0 mt-2 w-80 bg-white rounded-md shadow-lg ring-1 ring-black ring-opacity-5 z-50">
              <div className="py-1">
                <div className="px-4 py-2 border-b border-gray-200">
                  <h3 className="text-sm font-medium text-gray-900">
                    Notifications
                  </h3>
                </div>
                <div className="max-h-64 overflow-y-auto">
                  {notifications.map((notification) => (
                    <div
                      key={notification.id}
                      className={cn(
                        'px-4 py-3 hover:bg-gray-50 cursor-pointer border-b border-gray-100',
                        !notification.read && 'bg-blue-50'
                      )}
                    >
                      <div className="flex justify-between">
                        <p className="text-sm font-medium text-gray-900">
                          {notification.title}
                        </p>
                        <p className="text-xs text-gray-500">
                          {formatDetailedDate(notification.time)}
                        </p>
                      </div>
                      <p className="text-sm text-gray-600 mt-1">
                        {notification.message}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="px-4 py-2 border-t border-gray-200">
                  <button className="text-sm text-primary-600 hover:text-primary-700">
                    View all notifications
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* User menu */}
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center space-x-2 p-2 rounded-md text-gray-700 hover:text-gray-900 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <div className="h-8 w-8 bg-primary-600 rounded-full flex items-center justify-center">
              <User className="h-5 w-5 text-white" />
            </div>
            <span className="hidden sm:block text-sm font-medium">
              Restaurant Staff
            </span>
            <ChevronDown className="h-4 w-4" />
          </button>

          {/* User dropdown */}
          {showUserMenu && (
            <div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg ring-1 ring-black ring-opacity-5 z-50">
              <div className="py-1">
                <a
                  href="#"
                  className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  <div className="flex items-center">
                    <User className="h-4 w-4 mr-3" />
                    Profile
                  </div>
                </a>
                <a
                  href="#"
                  className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  <div className="flex items-center">
                    <Settings className="h-4 w-4 mr-3" />
                    Settings
                  </div>
                </a>
                <div className="border-t border-gray-100"></div>
                <a
                  href="#"
                  className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  <div className="flex items-center">
                    <LogOut className="h-4 w-4 mr-3" />
                    Sign out
                  </div>
                </a>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Click outside handlers */}
      {(showUserMenu || showNotifications) && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => {
            setShowUserMenu(false);
            setShowNotifications(false);
          }}
        />
      )}
    </header>
  );
};

export default Header;