"""
Performance monitoring and optimization for delivery estimation system.
Tracks estimation accuracy, API performance, and system metrics.
"""

import logging
import asyncio
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import statistics

from ..database import get_db_session
from ..database.models import DeliveryEstimateRecord, Order, OrderStatus
from ..database.redis_client import get_redis_async
from ..config.logging_config import get_logger
from ..config.settings import settings

# Configure logging
logger = get_logger(__name__)


class PerformanceMetric(Enum):
    """Performance metric types for delivery estimation."""
    ESTIMATION_ACCURACY = "estimation_accuracy"
    API_RESPONSE_TIME = "api_response_time"
    CACHE_HIT_RATE = "cache_hit_rate"
    ESTIMATION_COUNT = "estimation_count"
    ERROR_RATE = "error_rate"
    PEAK_LOAD_PERFORMANCE = "peak_load_performance"


@dataclass
class PerformanceData:
    """Performance data point."""
    metric_type: PerformanceMetric
    value: float
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class EstimationAccuracy:
    """Estimation accuracy analysis."""
    average_error_minutes: float
    median_error_minutes: float
    accuracy_within_5_min: float  # Percentage accurate within 5 minutes
    accuracy_within_10_min: float  # Percentage accurate within 10 minutes
    total_comparisons: int
    confidence_correlation: float  # How well confidence predicts accuracy


class DeliveryPerformanceMonitor:
    """
    Performance monitoring system for delivery estimation.
    
    Tracks accuracy, performance metrics, and provides optimization insights.
    """
    
    def __init__(self):
        """Initialize performance monitor."""
        self.performance_cache_ttl = 300  # 5 minutes cache
        self.metrics_retention_days = 30
        self.accuracy_check_interval = 3600  # 1 hour
        
        # Performance thresholds
        self.thresholds = {
            "api_response_time_ms": 2000,  # 2 seconds max
            "cache_hit_rate_min": 0.6,  # 60% minimum cache hit rate
            "estimation_accuracy_max_error": 10,  # 10 minutes max average error
            "error_rate_max": 0.05  # 5% maximum error rate
        }
        
        logger.info("DeliveryPerformanceMonitor initialized")
    
    async def track_estimation_performance(
        self, 
        estimation_time_ms: float,
        cache_hit: bool,
        confidence_score: float,
        estimation_id: Optional[str] = None
    ):
        """
        Track performance metrics for a single estimation.
        
        Args:
            estimation_time_ms (float): Time taken to calculate estimate in milliseconds
            cache_hit (bool): Whether the result came from cache
            confidence_score (float): Confidence score of the estimate
            estimation_id (str): Optional unique identifier for the estimation
        """
        try:
            # Track API response time
            await self._record_metric(
                PerformanceMetric.API_RESPONSE_TIME,
                estimation_time_ms,
                {"cache_hit": cache_hit, "confidence": confidence_score}
            )
            
            # Track cache performance
            cache_metric = 1.0 if cache_hit else 0.0
            await self._record_metric(
                PerformanceMetric.CACHE_HIT_RATE,
                cache_metric,
                {"estimation_id": estimation_id}
            )
            
            # Increment estimation count
            await self._record_metric(
                PerformanceMetric.ESTIMATION_COUNT,
                1.0,
                {"timestamp": datetime.utcnow().isoformat()}
            )
            
            # Check for performance alerts
            await self._check_performance_alerts(estimation_time_ms, cache_hit)
            
            logger.debug(f"Tracked estimation performance: {estimation_time_ms:.1f}ms, cache_hit: {cache_hit}")
            
        except Exception as e:
            logger.warning(f"Error tracking estimation performance: {e}")
    
    async def track_estimation_error(
        self, 
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Track estimation errors for monitoring.
        
        Args:
            error_type (str): Type of error (api_error, validation_error, etc.)
            error_message (str): Error message
            context (dict): Additional context about the error
        """
        try:
            await self._record_metric(
                PerformanceMetric.ERROR_RATE,
                1.0,
                {
                    "error_type": error_type,
                    "error_message": error_message,
                    "context": context or {}
                }
            )
            
            logger.warning(f"Estimation error tracked: {error_type} - {error_message}")
            
        except Exception as e:
            logger.error(f"Error tracking estimation error: {e}")
    
    async def analyze_estimation_accuracy(
        self, 
        timeframe_hours: int = 24
    ) -> EstimationAccuracy:
        """
        Analyze estimation accuracy by comparing estimates to actual delivery times.
        
        Args:
            timeframe_hours (int): Analysis timeframe in hours
            
        Returns:
            EstimationAccuracy: Accuracy analysis results
        """
        try:
            start_time = datetime.utcnow() - timedelta(hours=timeframe_hours)
            
            async with get_db_session() as session:
                # Get estimates with actual delivery times
                completed_orders = session.query(Order).join(DeliveryEstimateRecord).filter(
                    Order.order_status == OrderStatus.DELIVERED.value,
                    Order.updated_at >= start_time,
                    DeliveryEstimateRecord.actual_delivery_time.isnot(None)
                ).all()
                
                if not completed_orders:
                    logger.info("No completed orders with actual times found for accuracy analysis")
                    return EstimationAccuracy(0, 0, 0, 0, 0, 0)
                
                errors = []
                confidence_scores = []
                
                for order in completed_orders:
                    for estimate in order.delivery_estimates:
                        if estimate.actual_delivery_time and estimate.is_active:
                            # Calculate error (actual - estimated)
                            error = abs(estimate.actual_delivery_time - estimate.estimated_minutes)
                            errors.append(error)
                            confidence_scores.append(float(estimate.confidence_score))
                
                if not errors:
                    return EstimationAccuracy(0, 0, 0, 0, 0, 0)
                
                # Calculate accuracy metrics
                avg_error = statistics.mean(errors)
                median_error = statistics.median(errors)
                
                # Percentage within thresholds
                within_5_min = sum(1 for e in errors if e <= 5) / len(errors)
                within_10_min = sum(1 for e in errors if e <= 10) / len(errors)
                
                # Confidence correlation (simplified)
                confidence_correlation = self._calculate_confidence_correlation(errors, confidence_scores)
                
                accuracy = EstimationAccuracy(
                    average_error_minutes=avg_error,
                    median_error_minutes=median_error,
                    accuracy_within_5_min=within_5_min,
                    accuracy_within_10_min=within_10_min,
                    total_comparisons=len(errors),
                    confidence_correlation=confidence_correlation
                )
                
                # Store accuracy metric
                await self._record_metric(
                    PerformanceMetric.ESTIMATION_ACCURACY,
                    avg_error,
                    {
                        "median_error": median_error,
                        "accuracy_5min": within_5_min,
                        "accuracy_10min": within_10_min,
                        "total_comparisons": len(errors)
                    }
                )
                
                logger.info(f"Accuracy analysis: avg_error={avg_error:.1f}min, {within_5_min:.1%} within 5min")
                
                return accuracy
                
        except Exception as e:
            logger.error(f"Error analyzing estimation accuracy: {e}")
            return EstimationAccuracy(0, 0, 0, 0, 0, 0)
    
    async def get_performance_dashboard(self) -> Dict[str, Any]:
        """
        Get comprehensive performance dashboard data.
        
        Returns:
            dict: Performance metrics and analysis
        """
        try:
            dashboard = {
                "current_performance": await self._get_current_performance_metrics(),
                "accuracy_analysis": (await self.analyze_estimation_accuracy()).to_dict(),
                "api_performance": await self._get_api_performance_metrics(),
                "cache_performance": await self._get_cache_performance_metrics(),
                "error_summary": await self._get_error_summary(),
                "optimization_recommendations": await self._get_optimization_recommendations(),
                "generated_at": datetime.utcnow().isoformat()
            }
            
            logger.info("Generated performance dashboard")
            return dashboard
            
        except Exception as e:
            logger.error(f"Error generating performance dashboard: {e}")
            return {"error": str(e), "generated_at": datetime.utcnow().isoformat()}
    
    async def optimize_cache_strategy(self) -> Dict[str, Any]:
        """
        Analyze and optimize caching strategy for distance calculations.
        
        Returns:
            dict: Cache optimization recommendations
        """
        try:
            # Analyze cache hit patterns
            cache_stats = await self._analyze_cache_patterns()
            
            recommendations = []
            
            # Check hit rate
            if cache_stats.get("hit_rate", 0) < self.thresholds["cache_hit_rate_min"]:
                recommendations.append({
                    "type": "increase_cache_ttl",
                    "current_ttl": 3600,
                    "recommended_ttl": 7200,
                    "reason": "Low cache hit rate indicates cache expiry too frequent"
                })
            
            # Check for common address patterns
            if cache_stats.get("unique_addresses", 0) > cache_stats.get("total_requests", 0) * 0.8:
                recommendations.append({
                    "type": "precompute_common_areas",
                    "reason": "High unique address rate suggests benefit from area-based caching"
                })
            
            # Memory usage optimization
            if cache_stats.get("cache_size_mb", 0) > 100:
                recommendations.append({
                    "type": "implement_lru_eviction",
                    "reason": "Cache size growing large, implement LRU eviction"
                })
            
            optimization_result = {
                "current_stats": cache_stats,
                "recommendations": recommendations,
                "estimated_improvement": self._estimate_cache_improvement(recommendations)
            }
            
            logger.info(f"Cache optimization generated {len(recommendations)} recommendations")
            
            return optimization_result
            
        except Exception as e:
            logger.error(f"Error optimizing cache strategy: {e}")
            return {"error": str(e)}
    
    async def track_peak_load_performance(self) -> Dict[str, Any]:
        """
        Track performance during peak load periods.
        
        Returns:
            dict: Peak load performance analysis
        """
        try:
            current_hour = datetime.now().hour
            
            # Define peak hours
            is_peak = (11 <= current_hour <= 14) or (17 <= current_hour <= 21)
            
            if is_peak:
                # Get current load metrics
                load_metrics = await self._get_current_load_metrics()
                
                # Track peak performance
                await self._record_metric(
                    PerformanceMetric.PEAK_LOAD_PERFORMANCE,
                    load_metrics.get("response_time_avg", 0),
                    {
                        "hour": current_hour,
                        "concurrent_requests": load_metrics.get("concurrent_requests", 0),
                        "queue_length": load_metrics.get("queue_length", 0),
                        "error_rate": load_metrics.get("error_rate", 0)
                    }
                )
                
                # Check for performance degradation
                if load_metrics.get("response_time_avg", 0) > self.thresholds["api_response_time_ms"]:
                    await self._trigger_performance_alert("high_response_time", load_metrics)
                
                return {
                    "is_peak_period": True,
                    "performance_metrics": load_metrics,
                    "status": "monitoring"
                }
            else:
                return {
                    "is_peak_period": False,
                    "status": "normal_monitoring"
                }
                
        except Exception as e:
            logger.error(f"Error tracking peak load performance: {e}")
            return {"error": str(e)}
    
    def _calculate_confidence_correlation(
        self, 
        errors: List[float], 
        confidence_scores: List[float]
    ) -> float:
        """Calculate correlation between confidence scores and accuracy."""
        if len(errors) != len(confidence_scores) or len(errors) < 2:
            return 0.0
        
        try:
            # Simple correlation calculation
            # Higher confidence should correlate with lower errors
            paired_data = list(zip(confidence_scores, [-e for e in errors]))  # Negative error for correlation
            
            if len(paired_data) < 2:
                return 0.0
            
            # Calculate Pearson correlation coefficient
            n = len(paired_data)
            sum_x = sum(x for x, y in paired_data)
            sum_y = sum(y for x, y in paired_data)
            sum_xy = sum(x * y for x, y in paired_data)
            sum_x2 = sum(x * x for x, y in paired_data)
            sum_y2 = sum(y * y for x, y in paired_data)
            
            numerator = n * sum_xy - sum_x * sum_y
            denominator = ((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)) ** 0.5
            
            if denominator == 0:
                return 0.0
            
            correlation = numerator / denominator
            return max(-1.0, min(1.0, correlation))  # Clamp to [-1, 1]
            
        except Exception as e:
            logger.warning(f"Error calculating confidence correlation: {e}")
            return 0.0
    
    async def _record_metric(
        self, 
        metric_type: PerformanceMetric, 
        value: float, 
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Record performance metric in cache and database."""
        try:
            redis_client = await get_redis_async()
            
            metric_data = {
                "type": metric_type.value,
                "value": value,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": metadata or {}
            }
            
            # Store in Redis with TTL
            metric_key = f"delivery_metric:{metric_type.value}:{int(time.time())}"
            
            with redis_client.get_connection() as conn:
                conn.setex(metric_key, self.performance_cache_ttl, str(metric_data))
            
        except Exception as e:
            logger.warning(f"Error recording metric: {e}")
    
    async def _check_performance_alerts(self, response_time_ms: float, cache_hit: bool):
        """Check for performance alert conditions."""
        try:
            alerts = []
            
            if response_time_ms > self.thresholds["api_response_time_ms"]:
                alerts.append({
                    "type": "high_response_time",
                    "value": response_time_ms,
                    "threshold": self.thresholds["api_response_time_ms"]
                })
            
            # Check cache hit rate trend
            if not cache_hit:
                # This would check recent cache hit rate and alert if too low
                pass
            
            for alert in alerts:
                await self._trigger_performance_alert(alert["type"], alert)
                
        except Exception as e:
            logger.warning(f"Error checking performance alerts: {e}")
    
    async def _trigger_performance_alert(self, alert_type: str, alert_data: Dict[str, Any]):
        """Trigger performance alert notification."""
        try:
            logger.warning(f"Performance alert: {alert_type} - {alert_data}")
            
            # Store alert in Redis for dashboard
            redis_client = await get_redis_async()
            alert_key = f"delivery_alert:{alert_type}:{int(time.time())}"
            
            with redis_client.get_connection() as conn:
                conn.setex(alert_key, 3600, str(alert_data))  # 1 hour TTL
            
        except Exception as e:
            logger.error(f"Error triggering performance alert: {e}")
    
    # Placeholder methods for performance analysis
    async def _get_current_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        return {
            "avg_response_time_ms": 750,
            "cache_hit_rate": 0.72,
            "requests_per_hour": 245,
            "error_rate": 0.02
        }
    
    async def _get_api_performance_metrics(self) -> Dict[str, Any]:
        """Get API performance metrics."""
        return {
            "google_maps_avg_response": 1200,
            "database_avg_response": 45,
            "redis_avg_response": 5,
            "total_api_calls_24h": 1840
        }
    
    async def _get_cache_performance_metrics(self) -> Dict[str, Any]:
        """Get cache performance metrics."""
        return {
            "hit_rate": 0.72,
            "miss_rate": 0.28,
            "cache_size_mb": 15.4,
            "eviction_rate": 0.05
        }
    
    async def _get_error_summary(self) -> Dict[str, Any]:
        """Get error summary for past 24 hours."""
        return {
            "total_errors": 18,
            "api_errors": 12,
            "validation_errors": 4,
            "timeout_errors": 2,
            "error_rate": 0.02
        }
    
    async def _get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Get optimization recommendations."""
        return [
            {
                "type": "cache_optimization",
                "priority": "medium",
                "description": "Increase cache TTL for distance calculations",
                "estimated_impact": "15% improvement in response time"
            },
            {
                "type": "api_optimization", 
                "priority": "low",
                "description": "Batch geocoding requests for better efficiency",
                "estimated_impact": "10% reduction in API costs"
            }
        ]
    
    async def _analyze_cache_patterns(self) -> Dict[str, Any]:
        """Analyze cache usage patterns."""
        return {
            "hit_rate": 0.72,
            "unique_addresses": 892,
            "total_requests": 1240,
            "cache_size_mb": 15.4,
            "common_areas": ["downtown", "west_side", "university_district"]
        }
    
    def _estimate_cache_improvement(self, recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Estimate improvement from cache optimizations."""
        estimated_improvement = 0.15  # 15% improvement estimate
        
        return {
            "response_time_improvement": estimated_improvement,
            "cache_hit_rate_improvement": 0.10,
            "api_cost_reduction": 0.08
        }
    
    async def _get_current_load_metrics(self) -> Dict[str, Any]:
        """Get current system load metrics."""
        return {
            "response_time_avg": 850,
            "concurrent_requests": 12,
            "queue_length": 3,
            "error_rate": 0.03,
            "cpu_usage": 0.45,
            "memory_usage": 0.62
        }


# Add to EstimationAccuracy for serialization
EstimationAccuracy.to_dict = lambda self: {
    'average_error_minutes': self.average_error_minutes,
    'median_error_minutes': self.median_error_minutes,
    'accuracy_within_5_min': self.accuracy_within_5_min,
    'accuracy_within_10_min': self.accuracy_within_10_min,
    'total_comparisons': self.total_comparisons,
    'confidence_correlation': self.confidence_correlation
}


# Create global performance monitor instance
delivery_performance_monitor = DeliveryPerformanceMonitor()


# Export main components
__all__ = [
    "DeliveryPerformanceMonitor",
    "PerformanceData",
    "EstimationAccuracy",
    "PerformanceMetric",
    "delivery_performance_monitor"
]