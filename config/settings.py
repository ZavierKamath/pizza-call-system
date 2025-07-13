"""
Pizza Agent Configuration Settings
Manages environment variables and application configuration using Pydantic BaseSettings
"""
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    Uses .env file when available, with sensible defaults for development
    """
    
    # =============================================================================
    # API KEYS & EXTERNAL SERVICES
    # =============================================================================
    
    # OpenAI API for LLM, speech processing
    openai_api_key: str = Field(..., description="OpenAI API key for LLM and speech processing")
    
    # Twilio for phone call handling
    twilio_account_sid: str = Field(..., description="Twilio Account SID for phone integration")
    twilio_auth_token: str = Field(..., description="Twilio Auth Token for phone integration")
    
    # Stripe for payment processing
    stripe_secret_key: str = Field(..., description="Stripe Secret Key for payment processing")
    stripe_publishable_key: Optional[str] = Field(None, description="Stripe Publishable Key for frontend")
    
    # Google Maps API for address validation
    google_maps_api_key: str = Field(..., description="Google Maps API key for address validation")
    
    # =============================================================================
    # DATABASE CONFIGURATION
    # =============================================================================
    
    # SQLite database configuration
    database_url: str = Field(
        default="sqlite:///./data/pizza_orders.db", 
        description="Database URL - SQLite file path"
    )
    
    # Redis configuration for session management
    redis_url: str = Field(
        default="redis://localhost:6379", 
        description="Redis connection URL for session storage"
    )
    
    # =============================================================================
    # APPLICATION SETTINGS
    # =============================================================================
    
    # Connection limits
    max_concurrent_calls: int = Field(
        default=20, 
        description="Maximum number of concurrent voice calls (phone + web)",
        ge=1, le=100
    )
    
    # Business logic settings
    delivery_radius_miles: int = Field(
        default=5, 
        description="Maximum delivery radius in miles from restaurant",
        ge=1, le=50
    )
    
    restaurant_address: str = Field(
        default="123 Main St, Anytown, ST 12345",
        description="Restaurant address for distance calculations"
    )
    
    # =============================================================================
    # SERVER CONFIGURATION
    # =============================================================================
    
    # Server host and port
    host: str = Field(default="0.0.0.0", description="FastAPI server host")
    port: int = Field(default=8000, description="FastAPI server port", ge=1000, le=65535)
    
    # Environment settings
    environment: str = Field(default="development", description="Environment mode")
    debug: bool = Field(default=True, description="Enable debug mode")
    
    # =============================================================================
    # SECURITY SETTINGS
    # =============================================================================
    
    # Security keys and tokens
    secret_key: str = Field(
        default="pizza-agent-dev-secret-key-change-in-production",
        description="Secret key for session encryption"
    )
    
    # Rate limiting
    rate_limit_per_second: int = Field(
        default=5, 
        description="Rate limit - requests per second per IP",
        ge=1, le=100
    )
    
    # Session configuration
    session_timeout_minutes: int = Field(
        default=30, 
        description="Session timeout in minutes",
        ge=1, le=480
    )
    
    # Dashboard API settings
    dashboard_api_key: Optional[str] = Field(
        None, 
        description="API key for dashboard authentication"
    )
    
    # JWT token settings
    jwt_secret_key: Optional[str] = Field(
        None, 
        description="JWT secret key for token signing"
    )
    
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm"
    )
    
    jwt_expiry_hours: int = Field(
        default=24,
        description="JWT token expiry in hours",
        ge=1, le=168
    )
    
    # =============================================================================
    # LOGGING CONFIGURATION
    # =============================================================================
    
    # Logging settings
    log_level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    log_file: Optional[str] = Field(None, description="Log file path - leave empty for console only")
    
    # =============================================================================
    # AUDIO PROCESSING SETTINGS
    # =============================================================================
    
    # Audio quality and processing
    audio_sample_rate: int = Field(default=16000, description="Audio sample rate for voice processing")
    audio_bitrate: int = Field(default=64000, description="Audio bitrate for voice calls")
    speech_timeout_seconds: int = Field(
        default=30, 
        description="Speech processing timeout in seconds",
        ge=5, le=120
    )
    
    # =============================================================================
    # BUSINESS LOGIC SETTINGS
    # =============================================================================
    
    # Delivery time estimation parameters
    base_delivery_time_minutes: int = Field(
        default=25, 
        description="Base delivery preparation time in minutes",
        ge=10, le=120
    )
    
    delivery_time_per_mile_minutes: int = Field(
        default=2, 
        description="Additional delivery time per mile",
        ge=1, le=10
    )
    
    delivery_time_per_order_minutes: int = Field(
        default=3, 
        description="Additional time per pending order",
        ge=0, le=15
    )
    
    # Order constraints
    max_pizzas_per_order: int = Field(
        default=10, 
        description="Maximum number of pizzas per order",
        ge=1, le=50
    )
    
    order_timeout_minutes: int = Field(
        default=60, 
        description="Order timeout before auto-cancellation",
        ge=15, le=480
    )
    
    # =============================================================================
    # COMPUTED PROPERTIES
    # =============================================================================
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.environment.lower() == "development"
    
    @property
    def database_echo(self) -> bool:
        """Enable SQLAlchemy query logging in debug mode"""
        return self.debug and self.is_development
    
    # =============================================================================
    # CONFIGURATION
    # =============================================================================
    
    model_config = {
        "env_file": ".env",  # Load from .env file if present
        "env_file_encoding": "utf-8",
        "case_sensitive": False,  # Allow case-insensitive environment variables
        "extra": "ignore",  # Ignore extra environment variables
        "validate_assignment": True,  # Validate on assignment
    }


# Create global settings instance
settings = Settings()


def get_settings() -> Settings:
    """
    Dependency function to get settings instance
    Useful for FastAPI dependency injection
    """
    return settings


# Development helper functions
def print_settings_summary():
    """
    Print a summary of current settings (for debugging)
    Masks sensitive information
    """
    print("=" * 60)
    print("PIZZA AGENT SETTINGS SUMMARY")
    print("=" * 60)
    print(f"Environment: {settings.environment}")
    print(f"Debug Mode: {settings.debug}")
    print(f"Server: {settings.host}:{settings.port}")
    print(f"Database: {settings.database_url}")
    print(f"Redis: {settings.redis_url}")
    print(f"Max Calls: {settings.max_concurrent_calls}")
    print(f"Delivery Radius: {settings.delivery_radius_miles} miles")
    print(f"Log Level: {settings.log_level}")
    print(f"OpenAI API: {' Set' if settings.openai_api_key else ' Missing'}")
    print(f"Twilio: {' Set' if settings.twilio_account_sid else ' Missing'}")
    print(f"Stripe: {' Set' if settings.stripe_secret_key else ' Missing'}")
    print(f"Google Maps: {' Set' if settings.google_maps_api_key else ' Missing'}")
    print("=" * 60)


if __name__ == "__main__":
    """
    Print settings summary when run directly
    Useful for debugging configuration
    """
    print_settings_summary()