/**
 * Loading spinner component with different sizes and variants.
 * Provides consistent loading states across the application.
 */

import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/utils';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  variant?: 'primary' | 'secondary' | 'white';
  className?: string;
  text?: string;
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = 'md',
  variant = 'primary',
  className,
  text,
}) => {
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-6 w-6',
    lg: 'h-8 w-8',
    xl: 'h-12 w-12',
  };

  const variantClasses = {
    primary: 'text-primary-600',
    secondary: 'text-gray-600',
    white: 'text-white',
  };

  const textSizeClasses = {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-lg',
    xl: 'text-xl',
  };

  if (text) {
    return (
      <div className={cn('flex items-center justify-center space-x-2', className)}>
        <Loader2
          className={cn(
            'animate-spin',
            sizeClasses[size],
            variantClasses[variant]
          )}
        />
        <span className={cn(textSizeClasses[size], variantClasses[variant])}>
          {text}
        </span>
      </div>
    );
  }

  return (
    <Loader2
      className={cn(
        'animate-spin',
        sizeClasses[size],
        variantClasses[variant],
        className
      )}
    />
  );
};

export default LoadingSpinner;