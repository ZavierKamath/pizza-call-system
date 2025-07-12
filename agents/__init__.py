"""
Agents package for the pizza ordering system.

Contains the LangGraph pizza ordering agent with state management,
conversation flow, and all supporting components.
"""

# Import core components that don't require LangChain
from .states import OrderState, StateManager, ConversationState, ValidationResult
from .prompts import PromptManager
from .delivery_estimator import DeliveryEstimator

# Package metadata
__version__ = "1.0.0"
__author__ = "Pizza Agent Development Team"

# Conditionally import the main agent (requires LangChain dependencies)
try:
    from .pizza_agent import PizzaOrderingAgent
    _AGENT_AVAILABLE = True
except ImportError as e:
    PizzaOrderingAgent = None
    _AGENT_AVAILABLE = False

# Export components
__all__ = [
    "OrderState",
    "StateManager", 
    "ConversationState",
    "ValidationResult",
    "PromptManager",
    "DeliveryEstimator"
]

# Add main agent to exports if available
if _AGENT_AVAILABLE:
    __all__.append("PizzaOrderingAgent")