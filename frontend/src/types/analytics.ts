/**
 * Analytics and reporting type definitions.
 */

export interface PerformanceMetrics {
  period: 'hour' | 'day' | 'week' | 'month';
  start_date: string;
  end_date: string;
  total_orders: number;
  total_revenue: number;
  average_order_value: number;
  order_completion_rate: number;
  payment_success_rate: number;
  average_delivery_time: number;
  customer_satisfaction?: number;
}

export interface OrderVolumeData {
  timestamp: string;
  order_count: number;
  revenue: number;
  phone_orders: number;
  web_orders: number;
}

export interface DeliveryPerformanceData {
  zone: string;
  estimated_time: number;
  actual_time: number;
  accuracy_percentage: number;
  order_count: number;
}

export interface PaymentMetrics {
  total_processed: number;
  success_rate: number;
  failed_transactions: number;
  refund_rate: number;
  average_processing_time: number;
  payment_method_breakdown: {
    method: string;
    count: number;
    percentage: number;
  }[];
}

export interface PopularItem {
  name: string;
  size?: string;
  order_count: number;
  revenue: number;
  percentage_of_total: number;
}

export interface PeakHoursData {
  hour: number;
  order_count: number;
  average_delivery_time: number;
  driver_utilization: number;
}

export interface AnalyticsDashboard {
  current_metrics: PerformanceMetrics;
  order_volume_chart: OrderVolumeData[];
  delivery_performance: DeliveryPerformanceData[];
  payment_metrics: PaymentMetrics;
  popular_items: PopularItem[];
  peak_hours: PeakHoursData[];
  generated_at: string;
}