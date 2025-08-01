# Pizza Agent - Voice-Activated AI Pizza Ordering System

Voice-activated AI agent system for pizza ordering using LangChain/LangGraph. Handles complete order lifecycle from customer call to restaurant fulfillment with real-time validation, delivery time estimation, and multi-interface support (phone + web).

## Features

- **Voice Ordering**: Phone and web-based voice ordering using Twilio and WebRTC
- **AI Conversation**: Natural language processing with LangChain/LangGraph
- **Payment Processing**: Secure payment handling with Stripe integration
- **Address Validation**: Google Maps API for address verification and delivery radius checking
- **Real-time Dashboard**: Restaurant staff interface for order monitoring
- **Session Management**: Redis-based session storage with connection pooling
- **Delivery Estimation**: Intelligent delivery time calculation based on distance and current load

## Quick Start

### Prerequisites

- Python 3.9+
- Docker and Docker Compose
- API keys for: OpenAI, Twilio, Stripe, Google Maps

### Installation

1. **Clone and navigate to the project**:
   ```bash
   cd pizza_agent
   ```

2. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual API keys
   ```

3. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Start Redis with Docker**:
   ```bash
   docker-compose up redis -d
   ```

5. **Run the application**:
   ```bash
   python main.py
   ```

   Or using uvicorn directly:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

6. **Verify installation**:
   - API: http://localhost:8000
   - Health check: http://localhost:8000/health
   - API docs: http://localhost:8000/docs

## Environment Configuration

### Required API Keys

```bash
# OpenAI API for LLM and speech processing
OPENAI_API_KEY=sk-your-openai-api-key-here

# Twilio for phone call handling
TWILIO_ACCOUNT_SID=ACyour-twilio-account-sid-here
TWILIO_AUTH_TOKEN=your-twilio-auth-token-here

# Stripe for payment processing
STRIPE_SECRET_KEY=sk_test_your-stripe-secret-key-here

# Google Maps API for address validation
GOOGLE_MAPS_API_KEY=AIza-your-google-maps-api-key-here
```

### Database Setup

The application uses SQLite for simplicity and Redis for session management:

```bash
# Database configuration
DATABASE_URL=sqlite:///./data/pizza_orders.db
REDIS_URL=redis://localhost:6379
```

### Application Settings

```bash
# System limits
MAX_CONCURRENT_CALLS=20
DELIVERY_RADIUS_MILES=5

# Restaurant configuration
RESTAURANT_ADDRESS=123 Main St, Anytown, ST 12345
```

## Docker Deployment

### Full Stack with Docker Compose

```bash
# Start all services (Redis + Pizza Agent + Frontend)
docker-compose up -d

# View logs
docker-compose logs -f pizza-agent

# Stop all services
docker-compose down
```

### Redis Only

```bash
# Start just Redis for development
docker-compose up redis -d
```

## Project Structure

```
pizza_agent/
   agents/                    # LangGraph agent implementation
      pizza_agent.py        # Main agent logic
      states.py             # State definitions
      prompts.py            # System prompts
      delivery_estimator.py # Delivery time calculation
   voice/                     # Voice interface handling
      twilio_handler.py     # Phone integration
      webrtc_handler.py     # Web voice calls
      speech_processing.py  # STT/TTS processing
      session_manager.py    # Connection management
   validation/                # Input validation system
      address_validator.py  # Address validation
      payment_validator.py  # Payment validation
      order_validator.py    # Order validation
   database/                  # Data persistence
      models.py             # SQLAlchemy models
      redis_client.py       # Redis operations
   payment/                   # Payment processing
      stripe_client.py      # Stripe integration
   api/                       # REST API endpoints
      dashboard.py          # Dashboard API
      webhooks.py           # Payment webhooks
   frontend/                  # React dashboard
      src/
          components/       # React components
          services/         # API client
   config/                    # Configuration management
      settings.py           # Environment settings
   tests/                     # Test suite
   main.py                   # FastAPI application
   requirements.txt          # Python dependencies
   docker-compose.yml        # Docker configuration
   README.md                 # This file
```

## API Endpoints

### Health and Status

- `GET /health` - Health check with system status
- `GET /status` - Application metrics and call status
- `GET /` - API information

### Voice Interfaces (To be implemented)

- `POST /voice/phone` - Twilio webhook for phone calls
- `POST /voice/web` - WebRTC endpoint for web calls

### Dashboard API (To be implemented)

- `GET /api/dashboard/status` - Agent status and metrics
- `GET /api/tickets/active` - Active orders
- `POST /api/tickets/{id}/complete` - Mark order complete

### Webhooks (To be implemented)

- `POST /webhooks/stripe` - Stripe payment events
- `POST /webhooks/twilio` - Twilio call events

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest

# Run with coverage
pytest --cov=pizza_agent
```

### Configuration Testing

```bash
# Test configuration loading
python config/settings.py
```

### Debugging

Set debug mode in your `.env` file:

```bash
DEBUG=true
LOG_LEVEL=DEBUG
```

## System Requirements

### Hardware (On-Premise Deployment)

- **RAM**: 8GB minimum
- **CPU**: 4 cores minimum
- **Storage**: 100GB
- **Network**: 100Mbps+ internet connection

### Software Dependencies

- Python 3.9+
- Redis 7+
- Docker & Docker Compose (optional)

## Performance Targets

| Metric | Target |
|--------|---------|
| Response Time | < 2 seconds per turn |
| Concurrent Calls | 20 maximum |
| Uptime | 99% |
| Call Quality | < 5% dropped calls |
| Order Accuracy | > 95% validation success |

## Security Features

- PCI DSS compliance via Stripe tokenization
- Input sanitization and validation
- Rate limiting (5 requests/second per IP)
- Session timeout management (30 minutes)
- Secure API endpoints with authentication
- Audio data encryption in transit

## Support

For issues, questions, or contributions:

1. Check the API documentation at `/docs`
2. Review logs for error details
3. Ensure all environment variables are properly configured
4. Verify external API connectivity (OpenAI, Twilio, Stripe, Google Maps)

## License

[Add your license information here]

---

**Status**: Initial project setup complete 
**Next Steps**: Implement LangGraph agent core structure (Task 3)