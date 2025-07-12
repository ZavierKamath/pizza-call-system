"""
Pizza Agent - Voice-activated AI pizza ordering system
Main FastAPI application entry point
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from config.settings import settings


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager - handles startup and shutdown events
    """
    # Startup
    logger.info("Starting Pizza Agent application...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Redis URL: {settings.redis_url}")
    logger.info(f"Max concurrent calls: {settings.max_concurrent_calls}")
    
    # Initialize database connection (will be implemented in database module)
    # await init_database()
    
    # Initialize Redis connection (will be implemented in database module)
    # await init_redis()
    
    logger.info("Pizza Agent application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Pizza Agent application...")
    
    # Cleanup database connections
    # await cleanup_database()
    
    # Cleanup Redis connections
    # await cleanup_redis()
    
    logger.info("Pizza Agent application shutdown complete")


# Create FastAPI application instance
app = FastAPI(
    title="Pizza Agent API",
    description="Voice-activated AI agent system for pizza ordering using LangChain/LangGraph",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring and load balancers
    Returns application status and basic metrics
    """
    try:
        # Basic health check - can be extended to check database, Redis, etc.
        health_status = {
            "status": "healthy",
            "service": "pizza-agent",
            "version": "1.0.0",
            "environment": settings.environment,
            "max_concurrent_calls": settings.max_concurrent_calls,
            "delivery_radius_miles": settings.delivery_radius_miles
        }
        
        # TODO: Add actual health checks for:
        # - Database connectivity
        # - Redis connectivity  
        # - External API status (OpenAI, Twilio, Stripe)
        
        logger.debug("Health check successful")
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/")
async def root():
    """
    Root endpoint - basic API information
    """
    return {
        "message": "Pizza Agent API",
        "description": "Voice-activated AI pizza ordering system",
        "health_check": "/health",
        "documentation": "/docs"
    }


@app.get("/status")
async def get_status():
    """
    Status endpoint for basic application metrics
    """
    # TODO: Implement actual status tracking
    # This will include:
    # - Active call count
    # - Current system load
    # - Recent orders count
    # - Agent availability
    
    return {
        "active_calls": 0,  # Placeholder
        "max_calls": settings.max_concurrent_calls,
        "system_load": "normal",  # Placeholder
        "agent_status": "available"  # Placeholder
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """
    Custom 404 handler
    """
    return JSONResponse(
        status_code=404,
        content={"message": "Endpoint not found", "path": str(request.url.path)}
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """
    Custom 500 handler
    """
    logger.error(f"Internal server error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error", "error": str(exc) if settings.debug else "Server error"}
    )


# TODO: Add route includes for:
# - Voice interface endpoints (/voice/phone, /voice/web)
# - Dashboard API endpoints (/api/dashboard/*, /api/tickets/*)
# - Webhook endpoints (/webhooks/stripe, /webhooks/twilio)
#
# Example:
# from api.dashboard import router as dashboard_router
# app.include_router(dashboard_router, prefix="/api", tags=["dashboard"])


if __name__ == "__main__":
    """
    Run the application directly (for development)
    In production, use: uvicorn main:app --host 0.0.0.0 --port 8000
    """
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )