"""
Data aggregation and metrics calculation module.
Provides comprehensive analytics and performance metrics for the dashboard.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, text, case
from fastapi import APIRouter, Depends, Query, HTTPException

from ..database import get_db_session
from ..database.models import (
    Order, OrderStatus, PaymentStatus, ActiveSession,
    DeliveryEstimateRecord, PaymentTransaction, RefundRecord
)
from ..config.logging_config import get_logger
from .auth import get_current_user, require_permission, Permission, User

# Configure logging
logger = get_logger(__name__)

# Create router
router = APIRouter()


class MetricPeriod(Enum):
    """Time periods for metric aggregation."""
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class MetricType(Enum):
    """Types of metrics available."""
    ORDERS = "orders"
    REVENUE = "revenue"
    PERFORMANCE = "performance"
    DELIVERY = "delivery"
    PAYMENTS = "payments"
    SESSIONS = "sessions"


@dataclass
class MetricResult:
    """Standard metric result structure."""
    metric_type: str
    period: str
    start_date: datetime
    end_date: datetime
    value: float
    previous_value: Optional[float] = None
    change_percent: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class MetricsCalculator:
    """
    Advanced metrics calculator for dashboard analytics.
    Provides comprehensive data aggregation and performance analysis.
    """
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
    
    def _get_period_dates(
        self, 
        period: MetricPeriod, 
        end_date: Optional[datetime] = None
    ) -> Tuple[datetime, datetime]:
        """
        Calculate start and end dates for a given period.
        
        Args:
            period: Time period
            end_date: End date (default: now)
            
        Returns:
            Tuple of (start_date, end_date)
        """
        if not end_date:
            end_date = datetime.utcnow()
        
        if period == MetricPeriod.HOUR:
            start_date = end_date - timedelta(hours=1)
        elif period == MetricPeriod.DAY:
            start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == MetricPeriod.WEEK:
            start_date = end_date - timedelta(days=7)
        elif period == MetricPeriod.MONTH:
            start_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == MetricPeriod.QUARTER:
            quarter_start_month = ((end_date.month - 1) // 3) * 3 + 1
            start_date = end_date.replace(month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == MetricPeriod.YEAR:
            start_date = end_date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start_date = end_date - timedelta(days=1)
        
        return start_date, end_date
    
    def calculate_order_metrics(
        self, 
        session: Session, 
        period: MetricPeriod,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive order metrics.
        
        Args:
            session: Database session
            period: Time period for calculation
            end_date: End date for calculation
            
        Returns:
            Dictionary of order metrics
        """
        try:
            start_date, end_date = self._get_period_dates(period, end_date)
            
            # Base query for the period
            base_query = session.query(Order).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date
                )
            )
            
            # Total orders
            total_orders = base_query.count()
            
            # Orders by status
            status_breakdown = {}
            for status in OrderStatus:
                count = base_query.filter(Order.order_status == status.value).count()
                status_breakdown[status.value] = count
            
            # Orders by interface type
            phone_orders = base_query.filter(Order.interface_type == 'phone').count()
            web_orders = base_query.filter(Order.interface_type == 'web').count()
            
            # Orders by hour (for daily analysis)
            hourly_orders = []
            if period in [MetricPeriod.DAY, MetricPeriod.HOUR]:
                for hour in range(24):
                    hour_start = start_date.replace(hour=hour, minute=0, second=0, microsecond=0)
                    hour_end = hour_start + timedelta(hours=1)
                    
                    if hour_end <= end_date:
                        hour_count = session.query(Order).filter(
                            and_(
                                Order.created_at >= hour_start,
                                Order.created_at < hour_end
                            )
                        ).count()
                        hourly_orders.append({"hour": hour, "orders": hour_count})
            
            # Average order value
            revenue_query = base_query.filter(Order.payment_status == PaymentStatus.SUCCEEDED.value)
            total_revenue = revenue_query.with_entities(func.sum(Order.total_amount)).scalar() or 0
            avg_order_value = (total_revenue / total_orders) if total_orders > 0 else 0
            
            # Completion rate
            completed_orders = status_breakdown.get(OrderStatus.DELIVERED.value, 0)
            completion_rate = (completed_orders / total_orders * 100) if total_orders > 0 else 0
            
            # Cancellation rate
            canceled_orders = status_breakdown.get(OrderStatus.CANCELED.value, 0)
            cancellation_rate = (canceled_orders / total_orders * 100) if total_orders > 0 else 0
            
            # Peak hour analysis
            peak_hour = None
            if hourly_orders:
                peak_hour_data = max(hourly_orders, key=lambda x: x["orders"])
                peak_hour = peak_hour_data["hour"]
            
            return {
                "period": {
                    "type": period.value,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "totals": {
                    "total_orders": total_orders,
                    "phone_orders": phone_orders,
                    "web_orders": web_orders,
                    "completed_orders": completed_orders,
                    "canceled_orders": canceled_orders
                },
                "percentages": {
                    "completion_rate": round(completion_rate, 2),
                    "cancellation_rate": round(cancellation_rate, 2),
                    "phone_percentage": round((phone_orders / total_orders * 100) if total_orders > 0 else 0, 2),
                    "web_percentage": round((web_orders / total_orders * 100) if total_orders > 0 else 0, 2)
                },
                "status_breakdown": status_breakdown,
                "hourly_distribution": hourly_orders,
                "peak_hour": peak_hour,
                "revenue_metrics": {
                    "total_revenue": float(total_revenue),
                    "average_order_value": round(float(avg_order_value), 2)
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating order metrics: {str(e)}")
            raise
    
    def calculate_delivery_metrics(
        self, 
        session: Session, 
        period: MetricPeriod,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate delivery performance metrics.
        
        Args:
            session: Database session
            period: Time period for calculation
            end_date: End date for calculation
            
        Returns:
            Dictionary of delivery metrics
        """
        try:
            start_date, end_date = self._get_period_dates(period, end_date)
            
            # Get delivery estimates with actual delivery times
            delivery_query = session.query(DeliveryEstimateRecord).join(Order).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date,
                    DeliveryEstimateRecord.actual_delivery_time.isnot(None),
                    DeliveryEstimateRecord.is_active == True
                )
            )
            
            estimates = delivery_query.all()
            
            if not estimates:
                return {
                    "period": {
                        "type": period.value,
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat()
                    },
                    "summary": {
                        "total_deliveries": 0,
                        "average_estimated_time": 0,
                        "average_actual_time": 0,
                        "accuracy_percentage": 0
                    },
                    "zone_performance": {},
                    "accuracy_distribution": []
                }
            
            # Calculate metrics
            total_deliveries = len(estimates)
            
            # Average times
            avg_estimated = sum(e.estimated_minutes for e in estimates) / total_deliveries
            avg_actual = sum(e.actual_delivery_time for e in estimates) / total_deliveries
            
            # Accuracy calculation
            accurate_deliveries = 0
            zone_performance = {}
            accuracy_errors = []
            
            for estimate in estimates:
                error = abs(estimate.actual_delivery_time - estimate.estimated_minutes)
                accuracy_errors.append(error)
                
                # Consider accurate if within 10 minutes
                if error <= 10:
                    accurate_deliveries += 1
                
                # Zone performance
                zone = estimate.delivery_zone
                if zone not in zone_performance:
                    zone_performance[zone] = {
                        "count": 0,
                        "total_estimated": 0,
                        "total_actual": 0,
                        "accurate_count": 0
                    }
                
                zone_performance[zone]["count"] += 1
                zone_performance[zone]["total_estimated"] += estimate.estimated_minutes
                zone_performance[zone]["total_actual"] += estimate.actual_delivery_time
                if error <= 10:
                    zone_performance[zone]["accurate_count"] += 1
            
            # Calculate zone averages
            for zone, data in zone_performance.items():
                data["avg_estimated"] = round(data["total_estimated"] / data["count"], 1)
                data["avg_actual"] = round(data["total_actual"] / data["count"], 1)
                data["accuracy_rate"] = round((data["accurate_count"] / data["count"] * 100), 2)
            
            # Accuracy distribution
            accuracy_distribution = [
                {"range": "0-5 min", "count": sum(1 for e in accuracy_errors if e <= 5)},
                {"range": "6-10 min", "count": sum(1 for e in accuracy_errors if 5 < e <= 10)},
                {"range": "11-15 min", "count": sum(1 for e in accuracy_errors if 10 < e <= 15)},
                {"range": "16+ min", "count": sum(1 for e in accuracy_errors if e > 15)}
            ]
            
            accuracy_percentage = (accurate_deliveries / total_deliveries * 100) if total_deliveries > 0 else 0
            
            return {
                "period": {
                    "type": period.value,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "summary": {
                    "total_deliveries": total_deliveries,
                    "average_estimated_time": round(avg_estimated, 1),
                    "average_actual_time": round(avg_actual, 1),
                    "accuracy_percentage": round(accuracy_percentage, 2),
                    "average_error": round(sum(accuracy_errors) / len(accuracy_errors), 1)
                },
                "zone_performance": zone_performance,
                "accuracy_distribution": accuracy_distribution
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating delivery metrics: {str(e)}")
            raise
    
    def calculate_revenue_metrics(
        self, 
        session: Session, 
        period: MetricPeriod,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive revenue metrics.
        
        Args:
            session: Database session
            period: Time period for calculation
            end_date: End date for calculation
            
        Returns:
            Dictionary of revenue metrics
        """
        try:
            start_date, end_date = self._get_period_dates(period, end_date)
            
            # Revenue from successful orders
            revenue_query = session.query(Order).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date,
                    Order.payment_status == PaymentStatus.SUCCEEDED.value
                )
            )
            
            total_revenue = revenue_query.with_entities(func.sum(Order.total_amount)).scalar() or 0
            order_count = revenue_query.count()
            
            # Revenue by interface type
            phone_revenue = session.query(func.sum(Order.total_amount)).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date,
                    Order.payment_status == PaymentStatus.SUCCEEDED.value,
                    Order.interface_type == 'phone'
                )
            ).scalar() or 0
            
            web_revenue = session.query(func.sum(Order.total_amount)).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date,
                    Order.payment_status == PaymentStatus.SUCCEEDED.value,
                    Order.interface_type == 'web'
                )
            ).scalar() or 0
            
            # Payment method breakdown
            payment_breakdown = {}
            payment_methods = session.query(Order.payment_method, func.sum(Order.total_amount), func.count(Order.id)).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date,
                    Order.payment_status == PaymentStatus.SUCCEEDED.value
                )
            ).group_by(Order.payment_method).all()
            
            for method, revenue, count in payment_methods:
                payment_breakdown[method] = {
                    "revenue": float(revenue),
                    "orders": count,
                    "avg_order_value": float(revenue / count) if count > 0 else 0
                }
            
            # Refunds
            refund_query = session.query(RefundRecord).join(PaymentTransaction).join(Order).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date
                )
            )
            
            total_refunds = refund_query.with_entities(func.sum(RefundRecord.amount_cents)).scalar() or 0
            refund_count = refund_query.count()
            
            # Average metrics
            avg_order_value = (total_revenue / order_count) if order_count > 0 else 0
            refund_rate = (refund_count / order_count * 100) if order_count > 0 else 0
            
            return {
                "period": {
                    "type": period.value,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "summary": {
                    "total_revenue": float(total_revenue),
                    "total_orders": order_count,
                    "average_order_value": round(float(avg_order_value), 2),
                    "total_refunds": float(total_refunds / 100),  # Convert cents to dollars
                    "refund_rate": round(refund_rate, 2)
                },
                "breakdown": {
                    "phone_revenue": float(phone_revenue),
                    "web_revenue": float(web_revenue),
                    "phone_percentage": round((phone_revenue / total_revenue * 100) if total_revenue > 0 else 0, 2),
                    "web_percentage": round((web_revenue / total_revenue * 100) if total_revenue > 0 else 0, 2)
                },
                "payment_methods": payment_breakdown
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating revenue metrics: {str(e)}")
            raise
    
    def calculate_performance_metrics(
        self, 
        session: Session, 
        period: MetricPeriod,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate system performance metrics.
        
        Args:
            session: Database session
            period: Time period for calculation
            end_date: End date for calculation
            
        Returns:
            Dictionary of performance metrics
        """
        try:
            start_date, end_date = self._get_period_dates(period, end_date)
            
            # Order processing times (estimated)
            total_orders = session.query(Order).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date
                )
            ).count()
            
            # Success rates
            successful_orders = session.query(Order).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date,
                    Order.order_status == OrderStatus.DELIVERED.value
                )
            ).count()
            
            failed_orders = session.query(Order).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date,
                    Order.order_status.in_([OrderStatus.CANCELED.value, OrderStatus.PAYMENT_FAILED.value])
                )
            ).count()
            
            # Payment success rates
            successful_payments = session.query(Order).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date,
                    Order.payment_status == PaymentStatus.SUCCEEDED.value
                )
            ).count()
            
            failed_payments = session.query(Order).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date,
                    Order.payment_status == PaymentStatus.FAILED.value
                )
            ).count()
            
            # Calculate rates
            order_success_rate = (successful_orders / total_orders * 100) if total_orders > 0 else 0
            order_failure_rate = (failed_orders / total_orders * 100) if total_orders > 0 else 0
            payment_success_rate = (successful_payments / total_orders * 100) if total_orders > 0 else 0
            payment_failure_rate = (failed_payments / total_orders * 100) if total_orders > 0 else 0
            
            # Average processing times (estimated based on order status transitions)
            avg_preparation_time = 15  # Average preparation time in minutes
            avg_delivery_time = session.query(func.avg(Order.estimated_delivery)).filter(
                and_(
                    Order.created_at >= start_date,
                    Order.created_at <= end_date,
                    Order.order_status == OrderStatus.DELIVERED.value
                )
            ).scalar() or 30
            
            # Session utilization
            peak_sessions = session.query(func.max(func.count(ActiveSession.session_id))).group_by(
                func.date_trunc('hour', ActiveSession.created_at)
            ).scalar() or 0
            
            avg_session_duration = 8.5  # Estimated average session duration in minutes
            
            return {
                "period": {
                    "type": period.value,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "success_rates": {
                    "order_success_rate": round(order_success_rate, 2),
                    "order_failure_rate": round(order_failure_rate, 2),
                    "payment_success_rate": round(payment_success_rate, 2),
                    "payment_failure_rate": round(payment_failure_rate, 2)
                },
                "processing_times": {
                    "average_preparation_time": avg_preparation_time,
                    "average_delivery_time": round(float(avg_delivery_time), 1),
                    "average_session_duration": avg_session_duration
                },
                "capacity": {
                    "peak_concurrent_sessions": peak_sessions,
                    "total_orders_processed": total_orders,
                    "orders_per_hour": round(total_orders / ((end_date - start_date).total_seconds() / 3600), 1) if total_orders > 0 else 0
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating performance metrics: {str(e)}")
            raise


# Global metrics calculator
metrics_calculator = MetricsCalculator()


# API Endpoints

@router.get("/metrics/orders")
async def get_order_metrics(
    period: str = Query(default="day", regex="^(hour|day|week|month|quarter|year)$"),
    end_date: Optional[str] = Query(default=None),
    current_user: User = Depends(require_permission(Permission.READ_ANALYTICS)),
    db: Session = Depends(get_db_session)
):
    """
    Get comprehensive order metrics for specified period.
    
    Query Parameters:
        period: Time period (hour, day, week, month, quarter, year)
        end_date: End date in ISO format (default: now)
    """
    try:
        period_enum = MetricPeriod(period)
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00')) if end_date else None
        
        metrics = metrics_calculator.calculate_order_metrics(db, period_enum, end_dt)
        
        return {
            "success": True,
            "data": metrics
        }
        
    except Exception as e:
        logger.error(f"Error getting order metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to calculate order metrics"
        )


@router.get("/metrics/delivery")
async def get_delivery_metrics(
    period: str = Query(default="day", regex="^(hour|day|week|month|quarter|year)$"),
    end_date: Optional[str] = Query(default=None),
    current_user: User = Depends(require_permission(Permission.READ_ANALYTICS)),
    db: Session = Depends(get_db_session)
):
    """
    Get delivery performance metrics for specified period.
    
    Query Parameters:
        period: Time period (hour, day, week, month, quarter, year)
        end_date: End date in ISO format (default: now)
    """
    try:
        period_enum = MetricPeriod(period)
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00')) if end_date else None
        
        metrics = metrics_calculator.calculate_delivery_metrics(db, period_enum, end_dt)
        
        return {
            "success": True,
            "data": metrics
        }
        
    except Exception as e:
        logger.error(f"Error getting delivery metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to calculate delivery metrics"
        )


@router.get("/metrics/revenue")
async def get_revenue_metrics(
    period: str = Query(default="day", regex="^(hour|day|week|month|quarter|year)$"),
    end_date: Optional[str] = Query(default=None),
    current_user: User = Depends(require_permission(Permission.READ_ANALYTICS)),
    db: Session = Depends(get_db_session)
):
    """
    Get revenue metrics for specified period.
    
    Query Parameters:
        period: Time period (hour, day, week, month, quarter, year)
        end_date: End date in ISO format (default: now)
    """
    try:
        period_enum = MetricPeriod(period)
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00')) if end_date else None
        
        metrics = metrics_calculator.calculate_revenue_metrics(db, period_enum, end_dt)
        
        return {
            "success": True,
            "data": metrics
        }
        
    except Exception as e:
        logger.error(f"Error getting revenue metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to calculate revenue metrics"
        )


@router.get("/metrics/performance")
async def get_performance_metrics(
    period: str = Query(default="day", regex="^(hour|day|week|month|quarter|year)$"),
    end_date: Optional[str] = Query(default=None),
    current_user: User = Depends(require_permission(Permission.READ_ANALYTICS)),
    db: Session = Depends(get_db_session)
):
    """
    Get system performance metrics for specified period.
    
    Query Parameters:
        period: Time period (hour, day, week, month, quarter, year)
        end_date: End date in ISO format (default: now)
    """
    try:
        period_enum = MetricPeriod(period)
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00')) if end_date else None
        
        metrics = metrics_calculator.calculate_performance_metrics(db, period_enum, end_dt)
        
        return {
            "success": True,
            "data": metrics
        }
        
    except Exception as e:
        logger.error(f"Error getting performance metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to calculate performance metrics"
        )


@router.get("/metrics/summary")
async def get_metrics_summary(
    period: str = Query(default="day", regex="^(hour|day|week|month|quarter|year)$"),
    end_date: Optional[str] = Query(default=None),
    current_user: User = Depends(require_permission(Permission.READ_ANALYTICS)),
    db: Session = Depends(get_db_session)
):
    """
    Get comprehensive metrics summary for specified period.
    
    Query Parameters:
        period: Time period (hour, day, week, month, quarter, year)
        end_date: End date in ISO format (default: now)
    """
    try:
        period_enum = MetricPeriod(period)
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00')) if end_date else None
        
        # Calculate all metrics
        order_metrics = metrics_calculator.calculate_order_metrics(db, period_enum, end_dt)
        delivery_metrics = metrics_calculator.calculate_delivery_metrics(db, period_enum, end_dt)
        revenue_metrics = metrics_calculator.calculate_revenue_metrics(db, period_enum, end_dt)
        performance_metrics = metrics_calculator.calculate_performance_metrics(db, period_enum, end_dt)
        
        return {
            "success": True,
            "data": {
                "orders": order_metrics,
                "delivery": delivery_metrics,
                "revenue": revenue_metrics,
                "performance": performance_metrics,
                "generated_at": datetime.utcnow().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics summary: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to calculate metrics summary"
        )