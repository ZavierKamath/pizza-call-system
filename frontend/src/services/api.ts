/**
 * Core API client configuration with interceptors and error handling.
 * Provides centralized HTTP client for all API communications.
 */

import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import toast from 'react-hot-toast';

import { API_BASE_URL } from '@/utils/constants';
import type { ApiResponse } from '@/types';

// Create axios instance with default configuration
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 seconds
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for adding auth tokens and logging
api.interceptors.request.use(
  (config) => {
    // Add authentication token if available
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Add request timestamp for debugging
    config.metadata = { startTime: new Date() };

    // Log request in development
    if (process.env.NODE_ENV === 'development') {
      console.log(`🚀 API Request: ${config.method?.toUpperCase()} ${config.url}`, {
        params: config.params,
        data: config.data,
      });
    }

    return config;
  },
  (error) => {
    console.error('Request interceptor error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor for error handling and logging
api.interceptors.response.use(
  (response: AxiosResponse) => {
    // Calculate request duration
    const duration = new Date().getTime() - response.config.metadata?.startTime?.getTime();

    // Log response in development
    if (process.env.NODE_ENV === 'development') {
      console.log(`✅ API Response: ${response.config.method?.toUpperCase()} ${response.config.url}`, {
        status: response.status,
        duration: `${duration}ms`,
        data: response.data,
      });
    }

    return response;
  },
  (error) => {
    const duration = error.config?.metadata?.startTime 
      ? new Date().getTime() - error.config.metadata.startTime.getTime()
      : 0;

    // Log error in development
    if (process.env.NODE_ENV === 'development') {
      console.error(`❌ API Error: ${error.config?.method?.toUpperCase()} ${error.config?.url}`, {
        status: error.response?.status,
        duration: `${duration}ms`,
        message: error.message,
        data: error.response?.data,
      });
    }

    // Handle specific error cases
    if (error.response) {
      const { status, data } = error.response;

      switch (status) {
        case 401:
          // Unauthorized - redirect to login
          localStorage.removeItem('auth_token');
          if (!window.location.pathname.includes('/login')) {
            toast.error('Session expired. Please log in again.');
            window.location.href = '/login';
          }
          break;

        case 403:
          // Forbidden
          toast.error('You do not have permission to perform this action.');
          break;

        case 404:
          // Not found
          if (!error.config?.url?.includes('/api/')) {
            toast.error('The requested resource was not found.');
          }
          break;

        case 422:
          // Validation error
          if (data?.message) {
            toast.error(data.message);
          } else {
            toast.error('Please check your input and try again.');
          }
          break;

        case 429:
          // Rate limited
          toast.error('Too many requests. Please slow down and try again.');
          break;

        case 500:
        case 502:
        case 503:
        case 504:
          // Server errors
          toast.error('Server error. Please try again later.');
          break;

        default:
          // Generic error message
          const errorMessage = data?.message || data?.error || 'An unexpected error occurred.';
          toast.error(errorMessage);
      }

      // Return structured error for component handling
      return Promise.reject({
        status,
        message: data?.message || data?.error || error.message,
        data: data,
        original: error,
      });
    } else if (error.request) {
      // Network error
      toast.error('Network error. Please check your connection.');
      return Promise.reject({
        status: 0,
        message: 'Network error',
        original: error,
      });
    } else {
      // Request setup error
      toast.error('Request failed. Please try again.');
      return Promise.reject({
        status: 0,
        message: error.message,
        original: error,
      });
    }
  }
);

// Generic API request function
export const apiRequest = async <T = any>(
  config: AxiosRequestConfig
): Promise<ApiResponse<T>> => {
  try {
    const response = await api.request<ApiResponse<T>>(config);
    return response.data;
  } catch (error: any) {
    throw error;
  }
};

// Convenience methods for common HTTP operations
export const apiGet = <T = any>(
  url: string,
  params?: Record<string, any>
): Promise<ApiResponse<T>> => {
  return apiRequest<T>({
    method: 'GET',
    url,
    params,
  });
};

export const apiPost = <T = any>(
  url: string,
  data?: any,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> => {
  return apiRequest<T>({
    method: 'POST',
    url,
    data,
    ...config,
  });
};

export const apiPut = <T = any>(
  url: string,
  data?: any,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> => {
  return apiRequest<T>({
    method: 'PUT',
    url,
    data,
    ...config,
  });
};

export const apiPatch = <T = any>(
  url: string,
  data?: any,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> => {
  return apiRequest<T>({
    method: 'PATCH',
    url,
    data,
    ...config,
  });
};

export const apiDelete = <T = any>(
  url: string,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> => {
  return apiRequest<T>({
    method: 'DELETE',
    url,
    ...config,
  });
};

// File upload helper
export const apiUpload = <T = any>(
  url: string,
  file: File,
  onProgress?: (progress: number) => void
): Promise<ApiResponse<T>> => {
  const formData = new FormData();
  formData.append('file', file);

  return apiRequest<T>({
    method: 'POST',
    url,
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(progress);
      }
    },
  });
};

// Health check endpoint
export const checkApiHealth = async (): Promise<boolean> => {
  try {
    await apiGet('/health');
    return true;
  } catch (error) {
    return false;
  }
};

export default api;