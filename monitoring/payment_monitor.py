"""
Payment status tracking and monitoring system.
Provides real-time payment metrics, status monitoring, and alerting.
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from database import get_db_session
from database.models import PaymentTransaction, PaymentStatus, Order, OrderStatus
from database.redis_client import get_redis_async
from config.logging_config import get_logger
from config.settings import settings

# Configure logging
logger = get_logger(__name__)


class PaymentMetricType(Enum):
    """Payment metric types for monitoring."""
    TRANSACTION_COUNT = "transaction_count"
    SUCCESS_RATE = "success_rate"
    FAILURE_RATE = "failure_rate"
    AVERAGE_AMOUNT = "average_amount"
    TOTAL_VOLUME = "total_volume"
    PROCESSING_TIME = "processing_time"
    RETRY_RATE = "retry_rate"


@dataclass
class PaymentMetric:
    """Payment metric data structure."""
    metric_type: PaymentMetricType
    value: float
    timestamp: datetime
    timeframe: str  # e.g., "1h", "24h", "7d"
    additional_data: Optional[Dict[str, Any]] = None


@dataclass
class PaymentAlert:
    """Payment alert data structure."""
    alert_type: str
    severity: str  # "low", "medium", "high", "critical"
    message: str
    payment_intent_id: Optional[str] = None
    order_id: Optional[str] = None
    timestamp: datetime = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class PaymentMonitor:
    """
    Payment monitoring system for tracking payment status and metrics.
    
    Provides real-time monitoring, alerting, and metrics collection
    for all payment processing activities.
    """
    
    def __init__(self):
        """Initialize payment monitoring system."""
        self.alert_thresholds = {
            "failure_rate_high": 0.15,  # 15% failure rate threshold
            "processing_time_high": 30.0,  # 30 seconds processing time
            "retry_rate_high": 0.25,  # 25% retry rate threshold
            "suspicious_volume": 10000.0,  # $10k+ single transaction
            "rapid_failures": 5  # 5 failures in 5 minutes
        }
        
        self.metric_cache_ttl = 300  # 5 minutes cache for metrics
        self.alert_cooldown = 3600  # 1 hour cooldown between similar alerts
        
        logger.info("PaymentMonitor initialized successfully")
    
    async def track_payment_status(
        self, 
        payment_intent_id: str, 
        status: str, 
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """
        Track payment status change with monitoring and alerting.
        
        Args:
            payment_intent_id (str): Payment intent ID
            status (str): New payment status
            additional_data (dict): Additional tracking data
        """
        try:
            logger.info(f"Tracking payment status: {payment_intent_id} -> {status}")
            
            # Update payment tracking in Redis
            await self._update_payment_tracking(payment_intent_id, status, additional_data)
            
            # Check for alert conditions
            await self._check_payment_alerts(payment_intent_id, status, additional_data)
            
            # Update real-time metrics
            await self._update_payment_metrics(payment_intent_id, status, additional_data)
            
            # Log payment event for audit trail
            await self._log_payment_event(payment_intent_id, status, additional_data)
            
        except Exception as e:
            logger.error(f"Error tracking payment status: {e}")
    
    async def get_payment_metrics(
        self, 
        timeframe: str = "24h",
        metric_types: Optional[List[PaymentMetricType]] = None
    ) -> Dict[str, PaymentMetric]:
        """
        Get payment metrics for specified timeframe.
        
        Args:
            timeframe (str): Time range ("1h", "24h", "7d", "30d")
            metric_types (list): Specific metrics to retrieve
            
        Returns:
            dict: Payment metrics by type
        """
        try:
            # Check cache first
            cached_metrics = await self._get_cached_metrics(timeframe)
            if cached_metrics:
                logger.debug(f"Returning cached metrics for {timeframe}")
                return cached_metrics
            
            # Calculate metrics from database
            metrics = await self._calculate_payment_metrics(timeframe, metric_types)
            
            # Cache results
            await self._cache_metrics(timeframe, metrics)
            
            logger.info(f"Generated payment metrics for {timeframe}: {len(metrics)} metrics")
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting payment metrics: {e}")
            return {}
    
    async def get_payment_status_dashboard(self) -> Dict[str, Any]:
        """
        Get comprehensive payment status dashboard data.
        
        Returns:
            dict: Dashboard data with metrics, alerts, and status
        """
        try:
            dashboard_data = {
                "overview": await self._get_payment_overview(),
                "recent_metrics": await self.get_payment_metrics("1h"),
                "daily_metrics": await self.get_payment_metrics("24h"),
                "active_alerts": await self._get_active_alerts(),
                "recent_transactions": await self._get_recent_transactions(),
                "status_breakdown": await self._get_status_breakdown(),
                "performance_indicators": await self._get_performance_indicators(),
                "generated_at": datetime.utcnow().isoformat()
            }
            
            logger.info("Generated payment status dashboard")
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Error generating payment dashboard: {e}")
            return {"error": str(e), "generated_at": datetime.utcnow().isoformat()}
    
    async def monitor_payment_health(self) -> Dict[str, Any]:
        """
        Monitor overall payment system health with automated checks.
        
        Returns:
            dict: Health status and recommendations
        """
        try:
            health_checks = {
                "stripe_connectivity": await self._check_stripe_connectivity(),
                "database_connectivity": await self._check_database_connectivity(),
                "redis_connectivity": await self._check_redis_connectivity(),
                "payment_processing": await self._check_payment_processing_health(),
                "webhook_processing": await self._check_webhook_health(),
                "error_rates": await self._check_error_rates(),
                "performance_metrics": await self._check_performance_metrics()
            }
            
            # Calculate overall health score
            health_score = await self._calculate_health_score(health_checks)
            
            health_status = {
                "overall_health": health_score,
                "status": "healthy" if health_score >= 0.9 else "warning" if health_score >= 0.7 else "critical",
                "checks": health_checks,
                "recommendations": await self._generate_health_recommendations(health_checks),
                "last_checked": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Payment health check completed: {health_score:.2f} score")
            return health_status
            
        except Exception as e:
            logger.error(f"Error monitoring payment health: {e}")
            return {
                "overall_health": 0.0,
                "status": "error",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }
    
    async def _update_payment_tracking(
        self, 
        payment_intent_id: str, 
        status: str, 
        additional_data: Optional[Dict[str, Any]]
    ):
        """Update payment tracking in Redis cache."""
        try:
            redis_client = await get_redis_async()
            tracking_key = f"payment_tracking:{payment_intent_id}"
            
            tracking_data = {
                "payment_intent_id": payment_intent_id,
                "status": status,
                "updated_at": datetime.utcnow().isoformat(),
                "additional_data": additional_data or {}
            }
            
            with redis_client.get_connection() as conn:
                conn.setex(tracking_key, 86400, str(tracking_data))  # 24 hour TTL
            
        except Exception as e:
            logger.warning(f"Error updating payment tracking: {e}")
    
    async def _check_payment_alerts(
        self, 
        payment_intent_id: str, 
        status: str, 
        additional_data: Optional[Dict[str, Any]]
    ):
        """Check for alert conditions and trigger alerts if needed."""
        try:
            alerts = []
            
            # Check for payment failure
            if status == PaymentStatus.FAILED.value:
                failure_code = additional_data.get("failure_code") if additional_data else None
                alerts.append(PaymentAlert(
                    alert_type="payment_failure",
                    severity="medium",
                    message=f"Payment failed: {payment_intent_id} ({failure_code})",
                    payment_intent_id=payment_intent_id,
                    metadata={"failure_code": failure_code}
                ))
            
            # Check for high-value transactions
            if additional_data and "amount" in additional_data:
                amount = additional_data["amount"]
                if amount > self.alert_thresholds["suspicious_volume"]:
                    alerts.append(PaymentAlert(
                        alert_type="high_value_transaction",
                        severity="high",
                        message=f"High-value transaction detected: ${amount:.2f}",
                        payment_intent_id=payment_intent_id,
                        metadata={"amount": amount}
                    ))
            
            # Check for rapid failure patterns
            await self._check_rapid_failures(payment_intent_id, status, alerts)
            
            # Process alerts
            for alert in alerts:
                await self._process_alert(alert)
                
        except Exception as e:
            logger.error(f"Error checking payment alerts: {e}")
    
    async def _check_rapid_failures(self, payment_intent_id: str, status: str, alerts: List[PaymentAlert]):
        """Check for rapid failure patterns."""
        try:
            if status != PaymentStatus.FAILED.value:
                return
            
            # Check failure count in last 5 minutes
            five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
            
            async with get_db_session() as session:
                recent_failures = session.query(PaymentTransaction).filter(
                    PaymentTransaction.status == PaymentStatus.FAILED.value,
                    PaymentTransaction.updated_at >= five_minutes_ago
                ).count()
                
                if recent_failures >= self.alert_thresholds["rapid_failures"]:
                    alerts.append(PaymentAlert(
                        alert_type="rapid_failures",
                        severity="critical",
                        message=f"Rapid payment failures detected: {recent_failures} in 5 minutes",
                        metadata={"failure_count": recent_failures, "timeframe": "5min"}
                    ))
        
        except Exception as e:
            logger.warning(f"Error checking rapid failures: {e}")
    
    async def _process_alert(self, alert: PaymentAlert):
        """Process and store alert."""
        try:
            # Check alert cooldown
            if await self._is_alert_on_cooldown(alert):
                return
            
            logger.warning(f"Payment alert [{alert.severity}]: {alert.message}")
            
            # Store alert in database/cache
            await self._store_alert(alert)
            
            # Send notifications based on severity
            if alert.severity in ["high", "critical"]:
                await self._send_alert_notification(alert)
            
            # Set alert cooldown
            await self._set_alert_cooldown(alert)
            
        except Exception as e:
            logger.error(f"Error processing alert: {e}")
    
    async def _calculate_payment_metrics(
        self, 
        timeframe: str, 
        metric_types: Optional[List[PaymentMetricType]]
    ) -> Dict[str, PaymentMetric]:
        """Calculate payment metrics from database."""
        try:
            # Parse timeframe
            hours = self._parse_timeframe(timeframe)
            start_time = datetime.utcnow() - timedelta(hours=hours)
            
            metrics = {}
            
            async with get_db_session() as session:
                # Get base query for timeframe
                base_query = session.query(PaymentTransaction).filter(
                    PaymentTransaction.created_at >= start_time
                )
                
                total_transactions = base_query.count()
                
                if total_transactions > 0:
                    # Calculate success rate
                    successful_transactions = base_query.filter(
                        PaymentTransaction.status == PaymentStatus.SUCCEEDED.value
                    ).count()
                    
                    success_rate = successful_transactions / total_transactions
                    
                    metrics[PaymentMetricType.TRANSACTION_COUNT.value] = PaymentMetric(
                        metric_type=PaymentMetricType.TRANSACTION_COUNT,
                        value=total_transactions,
                        timestamp=datetime.utcnow(),
                        timeframe=timeframe
                    )
                    
                    metrics[PaymentMetricType.SUCCESS_RATE.value] = PaymentMetric(
                        metric_type=PaymentMetricType.SUCCESS_RATE,
                        value=success_rate,
                        timestamp=datetime.utcnow(),
                        timeframe=timeframe
                    )
                    
                    metrics[PaymentMetricType.FAILURE_RATE.value] = PaymentMetric(
                        metric_type=PaymentMetricType.FAILURE_RATE,
                        value=1.0 - success_rate,
                        timestamp=datetime.utcnow(),
                        timeframe=timeframe
                    )
                    
                    # Calculate volume metrics
                    volume_query = base_query.filter(
                        PaymentTransaction.status == PaymentStatus.SUCCEEDED.value
                    )
                    
                    total_volume = sum(
                        (tx.amount_cents / 100) for tx in volume_query.all()
                    )
                    
                    average_amount = total_volume / successful_transactions if successful_transactions > 0 else 0
                    
                    metrics[PaymentMetricType.TOTAL_VOLUME.value] = PaymentMetric(
                        metric_type=PaymentMetricType.TOTAL_VOLUME,
                        value=total_volume,
                        timestamp=datetime.utcnow(),
                        timeframe=timeframe
                    )
                    
                    metrics[PaymentMetricType.AVERAGE_AMOUNT.value] = PaymentMetric(
                        metric_type=PaymentMetricType.AVERAGE_AMOUNT,
                        value=average_amount,
                        timestamp=datetime.utcnow(),
                        timeframe=timeframe
                    )
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating payment metrics: {e}")
            return {}
    
    async def _get_payment_overview(self) -> Dict[str, Any]:
        """Get payment system overview."""
        try:
            async with get_db_session() as session:
                # Today's metrics
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                
                today_transactions = session.query(PaymentTransaction).filter(
                    PaymentTransaction.created_at >= today_start
                ).count()
                
                today_successful = session.query(PaymentTransaction).filter(
                    PaymentTransaction.created_at >= today_start,
                    PaymentTransaction.status == PaymentStatus.SUCCEEDED.value
                ).count()
                
                today_volume = sum(
                    (tx.amount_cents / 100) for tx in session.query(PaymentTransaction).filter(
                        PaymentTransaction.created_at >= today_start,
                        PaymentTransaction.status == PaymentStatus.SUCCEEDED.value
                    ).all()
                )
                
                overview = {
                    "today_transactions": today_transactions,
                    "today_successful": today_successful,
                    "today_volume": today_volume,
                    "today_success_rate": (today_successful / today_transactions) if today_transactions > 0 else 0,
                    "active_processing": session.query(PaymentTransaction).filter(
                        PaymentTransaction.status == PaymentStatus.PROCESSING.value
                    ).count(),
                    "pending_payments": session.query(PaymentTransaction).filter(
                        PaymentTransaction.status == PaymentStatus.PENDING.value
                    ).count()
                }
                
                return overview
        
        except Exception as e:
            logger.error(f"Error getting payment overview: {e}")
            return {}
    
    def _parse_timeframe(self, timeframe: str) -> int:
        """Parse timeframe string to hours."""
        timeframe_map = {
            "1h": 1,
            "24h": 24,
            "7d": 168,
            "30d": 720
        }
        return timeframe_map.get(timeframe, 24)
    
    async def _get_cached_metrics(self, timeframe: str) -> Optional[Dict[str, PaymentMetric]]:
        """Get cached metrics if available."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"payment_metrics:{timeframe}"
            
            with redis_client.get_connection() as conn:
                cached_data = conn.get(cache_key)
                if cached_data:
                    # Return cached metrics (implementation details omitted)
                    return None  # Placeholder
                    
        except Exception as e:
            logger.warning(f"Error getting cached metrics: {e}")
        
        return None
    
    async def _cache_metrics(self, timeframe: str, metrics: Dict[str, PaymentMetric]):
        """Cache calculated metrics."""
        try:
            redis_client = await get_redis_async()
            cache_key = f"payment_metrics:{timeframe}"
            
            with redis_client.get_connection() as conn:
                conn.setex(cache_key, self.metric_cache_ttl, str(metrics))
                
        except Exception as e:
            logger.warning(f"Error caching metrics: {e}")
    
    async def _update_payment_metrics(
        self, 
        payment_intent_id: str, 
        status: str, 
        additional_data: Optional[Dict[str, Any]]
    ):
        """Update real-time payment metrics."""
        try:
            redis_client = await get_redis_async()
            
            with redis_client.get_connection() as conn:
                # Update status counters
                status_key = f"payment_status_count:{status}"
                conn.incr(status_key)
                conn.expire(status_key, 86400)  # 24 hour expiry
                
                # Update hourly metrics
                hour_key = datetime.utcnow().strftime("%Y%m%d%H")
                hourly_key = f"payment_hourly:{hour_key}"
                conn.incr(hourly_key)
                conn.expire(hourly_key, 172800)  # 48 hour expiry
                
        except Exception as e:
            logger.warning(f"Error updating real-time metrics: {e}")
    
    async def _log_payment_event(
        self, 
        payment_intent_id: str, 
        status: str, 
        additional_data: Optional[Dict[str, Any]]
    ):
        """Log payment event for audit trail."""
        try:
            event_data = {
                "payment_intent_id": payment_intent_id,
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
                "additional_data": additional_data or {}
            }
            
            logger.info(f"Payment event logged: {event_data}")
            
        except Exception as e:
            logger.warning(f"Error logging payment event: {e}")
    
    async def _check_stripe_connectivity(self) -> Dict[str, Any]:
        """Check Stripe API connectivity."""
        try:
            from payment.stripe_client import stripe_client
            
            # Simple API test
            test_result = await stripe_client._test_api_connection()
            
            return {
                "status": "healthy" if test_result else "unhealthy",
                "last_checked": datetime.utcnow().isoformat(),
                "response_time": 0.1  # Placeholder
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }
    
    async def _check_database_connectivity(self) -> Dict[str, Any]:
        """Check database connectivity."""
        try:
            async with get_db_session() as session:
                session.execute("SELECT 1")
                
            return {
                "status": "healthy",
                "last_checked": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }
    
    async def _check_redis_connectivity(self) -> Dict[str, Any]:
        """Check Redis connectivity."""
        try:
            redis_client = await get_redis_async()
            
            with redis_client.get_connection() as conn:
                conn.ping()
                
            return {
                "status": "healthy",
                "last_checked": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }
    
    async def _check_payment_processing_health(self) -> Dict[str, Any]:
        """Check payment processing health."""
        try:
            # Check recent payment success rate
            metrics = await self.get_payment_metrics("1h")
            success_rate = metrics.get(PaymentMetricType.SUCCESS_RATE.value)
            
            if success_rate and success_rate.value < 0.8:  # Less than 80% success rate
                status = "warning"
            elif success_rate and success_rate.value < 0.5:  # Less than 50% success rate
                status = "critical"
            else:
                status = "healthy"
                
            return {
                "status": status,
                "success_rate": success_rate.value if success_rate else 0,
                "last_checked": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }
    
    async def _check_webhook_health(self) -> Dict[str, Any]:
        """Check webhook processing health."""
        try:
            # Check recent webhook processing
            # This would check webhook event processing metrics
            
            return {
                "status": "healthy",
                "last_checked": datetime.utcnow().isoformat(),
                "processed_events_1h": 0  # Placeholder
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }
    
    async def _check_error_rates(self) -> Dict[str, Any]:
        """Check system error rates."""
        try:
            metrics = await self.get_payment_metrics("1h")
            failure_rate = metrics.get(PaymentMetricType.FAILURE_RATE.value)
            
            error_rate = failure_rate.value if failure_rate else 0
            
            if error_rate > self.alert_thresholds["failure_rate_high"]:
                status = "warning"
            else:
                status = "healthy"
                
            return {
                "status": status,
                "error_rate": error_rate,
                "threshold": self.alert_thresholds["failure_rate_high"],
                "last_checked": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }
    
    async def _check_performance_metrics(self) -> Dict[str, Any]:
        """Check performance metrics."""
        try:
            # Check average processing times, queue lengths, etc.
            
            return {
                "status": "healthy",
                "avg_processing_time": 2.5,  # Placeholder
                "queue_length": 0,  # Placeholder
                "last_checked": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }
    
    async def _calculate_health_score(self, health_checks: Dict[str, Dict[str, Any]]) -> float:
        """Calculate overall health score."""
        try:
            total_checks = len(health_checks)
            healthy_checks = sum(
                1 for check in health_checks.values() 
                if check.get("status") == "healthy"
            )
            
            return healthy_checks / total_checks if total_checks > 0 else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating health score: {e}")
            return 0.0
    
    async def _generate_health_recommendations(self, health_checks: Dict[str, Dict[str, Any]]) -> List[str]:
        """Generate health recommendations based on checks."""
        recommendations = []
        
        try:
            for check_name, check_data in health_checks.items():
                status = check_data.get("status")
                
                if status == "error":
                    recommendations.append(f"Fix {check_name} connectivity issue")
                elif status == "warning":
                    recommendations.append(f"Monitor {check_name} performance")
                    
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
        
        return recommendations
    
    # Additional helper methods for alert management
    async def _is_alert_on_cooldown(self, alert: PaymentAlert) -> bool:
        """Check if alert is on cooldown."""
        return False  # Placeholder implementation
    
    async def _store_alert(self, alert: PaymentAlert):
        """Store alert in database."""
        pass  # Placeholder implementation
    
    async def _send_alert_notification(self, alert: PaymentAlert):
        """Send alert notification."""
        pass  # Placeholder implementation
    
    async def _set_alert_cooldown(self, alert: PaymentAlert):
        """Set alert cooldown."""
        pass  # Placeholder implementation
    
    async def _get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts."""
        return []  # Placeholder implementation
    
    async def _get_recent_transactions(self) -> List[Dict[str, Any]]:
        """Get recent transaction summary."""
        return []  # Placeholder implementation
    
    async def _get_status_breakdown(self) -> Dict[str, int]:
        """Get payment status breakdown."""
        return {}  # Placeholder implementation
    
    async def _get_performance_indicators(self) -> Dict[str, Any]:
        """Get key performance indicators."""
        return {}  # Placeholder implementation


# Create global payment monitor instance
payment_monitor = PaymentMonitor()


# Export main components
__all__ = [
    "PaymentMonitor", 
    "PaymentMetric", 
    "PaymentAlert", 
    "PaymentMetricType",
    "payment_monitor"
]