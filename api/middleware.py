"""
Middleware for API rate limiting, error handling, and request processing.
Provides comprehensive request/response handling for the dashboard API.
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
from datetime import datetime, timedelta
from collections import defaultdict, deque

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config.logging_config import get_logger
from ..config.settings import settings

# Configure logging
logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with configurable limits per endpoint and user.
    """
    
    def __init__(
        self,
        app,
        default_calls: int = 100,
        default_period: int = 3600,  # 1 hour
        storage_cleanup_interval: int = 300  # 5 minutes
    ):
        super().__init__(app)
        
        # Rate limiting configuration
        self.default_calls = default_calls
        self.default_period = default_period
        
        # Storage for request tracking
        self.request_counts: Dict[str, deque] = defaultdict(deque)
        self.storage_cleanup_interval = storage_cleanup_interval
        self.last_cleanup = time.time()
        
        # Endpoint-specific rate limits
        self.endpoint_limits = {
            "/api/ws": (1000, 3600),  # WebSocket connections
            "/api/dashboard/status": (200, 3600),  # Dashboard status
            "/api/tickets/active": (100, 3600),  # Active tickets
            "/api/metrics/": (50, 3600),  # Metrics endpoints
            "/api/auth/": (10, 900),  # Authentication endpoints (15 min)
        }
        
        # Excluded paths (no rate limiting)
        self.excluded_paths = {
            "/health",
            "/docs",
            "/openapi.json",
            "/favicon.ico"
        }
        
        logger.info("Rate limiting middleware initialized")
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request with rate limiting checks.
        
        Args:
            request: Incoming request
            call_next: Next middleware in chain
            
        Returns:
            Response object
        """
        try:
            # Skip rate limiting for excluded paths
            if request.url.path in self.excluded_paths:
                return await call_next(request)
            
            # Get client identifier
            client_id = self._get_client_id(request)
            
            # Get rate limit for this endpoint
            calls_limit, period = self._get_rate_limit(request.url.path)
            
            # Check rate limit
            if not self._is_request_allowed(client_id, calls_limit, period):
                logger.warning(f"Rate limit exceeded for client {client_id} on {request.url.path}")
                
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "Rate limit exceeded",
                        "message": f"Too many requests. Limit: {calls_limit} per {period} seconds",
                        "retry_after": period
                    },
                    headers={"Retry-After": str(period)}
                )
            
            # Record the request
            self._record_request(client_id)
            
            # Clean up old records periodically
            await self._cleanup_if_needed()
            
            # Process request
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Add rate limiting headers
            remaining = self._get_remaining_requests(client_id, calls_limit, period)
            response.headers["X-RateLimit-Limit"] = str(calls_limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + period)
            response.headers["X-Process-Time"] = str(round(process_time, 4))
            
            return response
            
        except Exception as e:
            logger.error(f"Rate limiting middleware error: {str(e)}")
            # Continue processing on middleware error
            return await call_next(request)
    
    def _get_client_id(self, request: Request) -> str:
        """
        Extract client identifier from request.
        
        Args:
            request: Incoming request
            
        Returns:
            Client identifier string
        """
        # Try to get user ID from authorization header
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # Use a hash of the token as client ID
            import hashlib
            token = auth_header[7:]
            return f"token_{hashlib.md5(token.encode()).hexdigest()[:16]}"
        
        # Fall back to IP address
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        
        return f"ip_{ip}"
    
    def _get_rate_limit(self, path: str) -> tuple:
        """
        Get rate limit for specific endpoint.
        
        Args:
            path: Request path
            
        Returns:
            Tuple of (calls_limit, period_seconds)
        """
        # Check for exact match
        if path in self.endpoint_limits:
            return self.endpoint_limits[path]
        
        # Check for prefix match
        for endpoint_prefix, limits in self.endpoint_limits.items():
            if path.startswith(endpoint_prefix):
                return limits
        
        # Return default limits
        return self.default_calls, self.default_period
    
    def _is_request_allowed(self, client_id: str, calls_limit: int, period: int) -> bool:
        """
        Check if request is within rate limits.
        
        Args:
            client_id: Client identifier
            calls_limit: Maximum calls allowed
            period: Time period in seconds
            
        Returns:
            True if request is allowed, False otherwise
        """
        current_time = time.time()
        cutoff_time = current_time - period
        
        # Get client's request history
        requests = self.request_counts[client_id]
        
        # Remove old requests
        while requests and requests[0] <= cutoff_time:
            requests.popleft()
        
        # Check if under limit
        return len(requests) < calls_limit
    
    def _record_request(self, client_id: str):
        """
        Record a request for the client.
        
        Args:
            client_id: Client identifier
        """
        current_time = time.time()
        self.request_counts[client_id].append(current_time)
    
    def _get_remaining_requests(self, client_id: str, calls_limit: int, period: int) -> int:
        """
        Get remaining requests for client.
        
        Args:
            client_id: Client identifier
            calls_limit: Maximum calls allowed
            period: Time period in seconds
            
        Returns:
            Number of remaining requests
        """
        current_time = time.time()
        cutoff_time = current_time - period
        
        # Get client's request history
        requests = self.request_counts[client_id]
        
        # Remove old requests
        while requests and requests[0] <= cutoff_time:
            requests.popleft()
        
        return max(0, calls_limit - len(requests))
    
    async def _cleanup_if_needed(self):
        """Clean up old request records periodically."""
        current_time = time.time()
        
        if current_time - self.last_cleanup > self.storage_cleanup_interval:
            await self._cleanup_old_records()
            self.last_cleanup = current_time
    
    async def _cleanup_old_records(self):
        """Clean up old request records to prevent memory leaks."""
        try:
            current_time = time.time()
            cutoff_time = current_time - (24 * 3600)  # 24 hours
            
            clients_to_remove = []
            
            for client_id, requests in self.request_counts.items():
                # Remove old requests
                while requests and requests[0] <= cutoff_time:
                    requests.popleft()
                
                # Mark empty clients for removal
                if not requests:
                    clients_to_remove.append(client_id)
            
            # Remove empty clients
            for client_id in clients_to_remove:
                del self.request_counts[client_id]
            
            logger.debug(f"Cleaned up rate limiting data: removed {len(clients_to_remove)} empty clients")
            
        except Exception as e:
            logger.error(f"Error cleaning up rate limiting data: {str(e)}")


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Global error handling middleware for API requests.
    """
    
    def __init__(self, app):
        super().__init__(app)
        logger.info("Error handling middleware initialized")
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request with comprehensive error handling.
        
        Args:
            request: Incoming request
            call_next: Next middleware in chain
            
        Returns:
            Response object
        """
        try:
            start_time = time.time()
            
            # Process request
            response = await call_next(request)
            
            # Log request details
            process_time = time.time() - start_time
            self._log_request(request, response.status_code, process_time)
            
            return response
            
        except HTTPException as e:
            # Handle FastAPI HTTP exceptions
            return self._handle_http_exception(request, e)
            
        except Exception as e:
            # Handle unexpected errors
            return self._handle_unexpected_error(request, e)
    
    def _log_request(self, request: Request, status_code: int, process_time: float):
        """
        Log request details.
        
        Args:
            request: Request object
            status_code: Response status code
            process_time: Processing time in seconds
        """
        try:
            log_data = {
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "process_time": round(process_time, 4),
                "client_ip": getattr(request.client, 'host', 'unknown') if request.client else 'unknown',
                "user_agent": request.headers.get("user-agent", "unknown")
            }
            
            if status_code >= 400:
                logger.warning(f"Request failed: {log_data}")
            elif process_time > 5.0:  # Log slow requests
                logger.warning(f"Slow request: {log_data}")
            else:
                logger.debug(f"Request completed: {log_data}")
                
        except Exception as e:
            logger.error(f"Error logging request: {str(e)}")
    
    def _handle_http_exception(self, request: Request, exc: HTTPException) -> JSONResponse:
        """
        Handle FastAPI HTTP exceptions.
        
        Args:
            request: Request object
            exc: HTTP exception
            
        Returns:
            JSON response
        """
        try:
            error_id = f"err_{int(time.time())}_{id(request)}"
            
            logger.warning(f"HTTP Exception {error_id}: {exc.status_code} - {exc.detail}")
            
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": True,
                    "error_id": error_id,
                    "message": exc.detail,
                    "status_code": exc.status_code,
                    "timestamp": datetime.utcnow().isoformat(),
                    "path": request.url.path
                },
                headers=getattr(exc, 'headers', None)
            )
            
        except Exception as e:
            logger.error(f"Error handling HTTP exception: {str(e)}")
            return self._fallback_error_response(request)
    
    def _handle_unexpected_error(self, request: Request, exc: Exception) -> JSONResponse:
        """
        Handle unexpected errors.
        
        Args:
            request: Request object
            exc: Exception
            
        Returns:
            JSON response
        """
        try:
            error_id = f"err_{int(time.time())}_{id(request)}"
            
            logger.error(f"Unexpected error {error_id}: {str(exc)}", exc_info=True)
            
            # Determine if we should expose error details
            show_details = settings.debug or settings.environment == "development"
            
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": True,
                    "error_id": error_id,
                    "message": "Internal server error occurred",
                    "details": str(exc) if show_details else "Contact support with error ID",
                    "status_code": 500,
                    "timestamp": datetime.utcnow().isoformat(),
                    "path": request.url.path
                }
            )
            
        except Exception as e:
            logger.error(f"Error handling unexpected error: {str(e)}")
            return self._fallback_error_response(request)
    
    def _fallback_error_response(self, request: Request) -> JSONResponse:
        """
        Fallback error response when error handling itself fails.
        
        Args:
            request: Request object
            
        Returns:
            Basic JSON error response
        """
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": True,
                "message": "A critical error occurred",
                "status_code": 500,
                "timestamp": datetime.utcnow().isoformat()
            }
        )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Request logging middleware for API monitoring and debugging.
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.excluded_paths = {"/health", "/docs", "/openapi.json", "/favicon.ico"}
        logger.info("Request logging middleware initialized")
    
    async def dispatch(self, request: Request, call_next):
        """
        Log request and response details.
        
        Args:
            request: Incoming request
            call_next: Next middleware in chain
            
        Returns:
            Response object
        """
        # Skip logging for health checks and static files
        if request.url.path in self.excluded_paths:
            return await call_next(request)
        
        try:
            start_time = time.time()
            request_id = f"req_{int(start_time)}_{id(request)}"
            
            # Log request start
            logger.info(f"Request {request_id} started: {request.method} {request.url.path}")
            
            # Process request
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log request completion
            logger.info(
                f"Request {request_id} completed: "
                f"{response.status_code} in {process_time:.4f}s"
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            logger.error(f"Request logging middleware error: {str(e)}")
            return await call_next(request)


# Export middleware classes
__all__ = [
    "RateLimitMiddleware",
    "ErrorHandlingMiddleware", 
    "RequestLoggingMiddleware"
]