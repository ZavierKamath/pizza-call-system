"""
Pizza Agent - Voice-activated AI pizza ordering system
Main FastAPI application entry point
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, Dict, Any
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
    
    # Create audio directory for TTS files
    audio_dir = "static/audio"
    os.makedirs(audio_dir, exist_ok=True)
    logger.info(f"Audio directory created: {audio_dir}")
    
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
    allow_origins=[
        "http://localhost:3000",    # React development server
        "http://127.0.0.1:3000",   # Local development
        "http://localhost:5173",   # Vite development server
        "http://127.0.0.1:5173",   # Vite local
        "https://pizza-dashboard.vercel.app",  # Production frontend (example)
        "https://pizza-dashboard.netlify.app", # Alternative production (example)
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "accept",
        "accept-encoding", 
        "authorization",
        "content-type",
        "dnt",
        "origin",
        "user-agent",
        "x-csrftoken",
        "x-requested-with",
    ],
    expose_headers=[
        "x-ratelimit-limit",
        "x-ratelimit-remaining", 
        "x-ratelimit-reset",
        "x-process-time",
        "x-request-id"
    ]
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


# Import voice interface handlers
from voice.twilio_handler import (
    handle_incoming_call_webhook,
    handle_speech_webhook, 
    handle_status_webhook,
    handle_recording_webhook
)
from voice.session_manager import get_session_stats
from fastapi.responses import PlainTextResponse


# Voice interface routes for Twilio webhooks
@app.post("/voice/incoming", response_class=PlainTextResponse)
async def twilio_incoming_call(request: Request):
    """
    Webhook endpoint for incoming Twilio calls.
    Returns TwiML response for call handling.
    """
    try:
        twiml_response = await handle_incoming_call_webhook(request)
        return PlainTextResponse(content=twiml_response, media_type="application/xml")
    except Exception as e:
        logger.error(f"Error in incoming call webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Call processing error")


@app.post("/voice/speech", response_class=PlainTextResponse)
async def twilio_speech_input(request: Request):
    """
    Webhook endpoint for speech input from Twilio.
    Processes speech and returns TwiML response.
    """
    try:
        twiml_response = await handle_speech_webhook(request)
        return PlainTextResponse(content=twiml_response, media_type="application/xml")
    except Exception as e:
        logger.error(f"Error in speech webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Speech processing error")


@app.post("/voice/status", response_class=PlainTextResponse)
async def twilio_call_status(request: Request):
    """
    Webhook endpoint for call status updates from Twilio.
    Handles call completion, termination, etc.
    """
    try:
        await handle_status_webhook(request)
        return PlainTextResponse(content="", media_type="text/plain")
    except Exception as e:
        logger.error(f"Error in status webhook: {str(e)}")
        return PlainTextResponse(content="", media_type="text/plain")


@app.post("/voice/recording-complete", response_class=PlainTextResponse)
async def twilio_recording_complete(request: Request):
    """
    Webhook endpoint for recording completion from Twilio.
    Handles recording processing.
    """
    try:
        await handle_recording_webhook(request)
        return PlainTextResponse(content="", media_type="text/plain")
    except Exception as e:
        logger.error(f"Error in recording webhook: {str(e)}")
        return PlainTextResponse(content="", media_type="text/plain")


# Session management API endpoints
@app.get("/api/sessions/stats")
async def get_session_statistics():
    """
    Get current session management statistics.
    """
    try:
        stats = await get_session_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting session stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get session statistics")


@app.post("/api/sessions/cleanup")
async def cleanup_sessions_endpoint():
    """
    Manually trigger cleanup of expired sessions.
    """
    try:
        from voice.session_manager import cleanup_sessions
        cleaned_count = await cleanup_sessions()
        return {"message": f"Cleaned up {cleaned_count} expired sessions"}
    except Exception as e:
        logger.error(f"Error cleaning up sessions: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to cleanup sessions")


@app.post("/api/sessions/reset")
async def reset_session_counter():
    """
    Reset the session counter and clear all active sessions (for development/testing).
    """
    try:
        from voice.session_manager import session_manager
        from database.redis_client import get_redis_async
        
        # Reset Redis counter and clear active sessions set
        redis_client = await get_redis_async()
        with redis_client.get_connection() as conn:
            conn.set(session_manager.session_count_key, 0)
            conn.delete(session_manager.active_sessions_key)
        
        # Also clear database active sessions
        from database.connection import db_manager
        from database.models import ActiveSession
        with db_manager.get_session() as db_session:
            db_session.query(ActiveSession).delete()
            db_session.commit()
        
        return {"message": "All session data reset to 0"}
    except Exception as e:
        logger.error(f"Error resetting session data: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to reset session data")


# Payment webhook endpoints
@app.post("/webhooks/stripe")
async def stripe_webhook_handler(request: Request, background_tasks: BackgroundTasks):
    """
    Stripe webhook endpoint for payment event processing.
    Handles payment status updates, failures, and disputes.
    """
    try:
        from api.webhooks import handle_stripe_webhook
        result = await handle_stripe_webhook(request, background_tasks)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Stripe webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


@app.get("/api/payments/methods")
async def get_supported_payment_methods():
    """
    Get supported payment methods and configuration.
    """
    try:
        from payment.stripe_client import stripe_client
        methods_info = await stripe_client.payment_validator.get_supported_payment_methods()
        return methods_info
    except Exception as e:
        logger.error(f"Error getting payment methods: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get payment methods")


@app.post("/api/payments/intent")
async def create_payment_intent_endpoint(
    amount: float,
    customer_info: Optional[Dict[str, Any]] = None,
    order_info: Optional[Dict[str, Any]] = None
):
    """
    Create a payment intent for order processing.
    """
    try:
        from payment.stripe_client import create_payment_intent
        result = await create_payment_intent(amount, customer_info, order_info)
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("errors", ["Payment intent creation failed"]))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating payment intent: {str(e)}")
        raise HTTPException(status_code=500, detail="Payment intent creation failed")


@app.post("/api/payments/{payment_intent_id}/confirm")
async def confirm_payment_endpoint(payment_intent_id: str):
    """
    Confirm a payment intent.
    """
    try:
        from payment.stripe_client import confirm_payment
        result = await confirm_payment(payment_intent_id)
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("errors", ["Payment confirmation failed"]))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming payment: {str(e)}")
        raise HTTPException(status_code=500, detail="Payment confirmation failed")


# Include dashboard API routes
from api.dashboard import router as dashboard_router
from api.websocket_endpoints import router as websocket_router
from api.metrics import router as metrics_router

app.include_router(dashboard_router, prefix="/api", tags=["dashboard"])
app.include_router(websocket_router, prefix="/api", tags=["websocket"])
app.include_router(metrics_router, prefix="/api", tags=["metrics"])

# Add middleware for rate limiting and error handling
from api.middleware import RateLimitMiddleware, ErrorHandlingMiddleware, RequestLoggingMiddleware

# Mount static files for TTS audio
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add middleware in reverse order (last added = first executed)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(RateLimitMiddleware, default_calls=1000, default_period=3600)


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