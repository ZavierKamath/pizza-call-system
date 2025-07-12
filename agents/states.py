"""
State definitions for the LangGraph pizza ordering agent.
Contains OrderState TypedDict and related state management utilities.
"""

from typing import List, Dict, Any, Optional, Union
from typing_extensions import TypedDict, NotRequired
from datetime import datetime
import logging

# Configure logging for state management
logger = logging.getLogger(__name__)


class OrderState(TypedDict):
    """
    Complete state schema for the pizza ordering conversation flow.
    
    Based on PRD specifications, this state tracks all customer information,
    order details, payment status, and conversation context throughout
    the entire ordering process.
    """
    
    # Customer Information
    customer_name: NotRequired[str]  # Customer's full name
    phone_number: NotRequired[str]   # Customer's phone number for contact
    
    # Address Information (stored as dict for flexibility)
    address: NotRequired[Dict[str, Any]]  # Complete delivery address
    # Example: {
    #     "street": "123 Main St",
    #     "city": "Anytown", 
    #     "state": "CA",
    #     "zip": "12345",
    #     "unit": "Apt 2B",  # Optional
    #     "delivery_instructions": "Ring doorbell twice"  # Optional
    # }
    
    # Order Details
    pizzas: NotRequired[List[Dict[str, Any]]]  # List of pizza configurations
    # Example: [
    #     {
    #         "size": "large",
    #         "crust": "thin", 
    #         "toppings": ["pepperoni", "mushrooms"],
    #         "quantity": 1,
    #         "price": 18.99,
    #         "special_instructions": "light sauce"
    #     }
    # ]
    
    # Payment Information
    payment_method: NotRequired[str]  # "credit_card", "cash", "debit_card"
    credit_card: NotRequired[Dict[str, Any]]  # Credit card details (tokenized)
    # Example: {
    #     "type": "visa",
    #     "last_four": "1234", 
    #     "token": "stripe_token_xyz",
    #     "cardholder_name": "John Doe"
    # }
    
    # Order Calculations
    order_total: NotRequired[float]  # Total order amount including tax/fees
    delivery_time: NotRequired[int]  # Estimated delivery time in minutes
    
    # Validation and Processing Status
    validation_status: NotRequired[Dict[str, Any]]  # Validation results for each field
    # Example: {
    #     "address_valid": True,
    #     "payment_valid": False,
    #     "order_complete": True,
    #     "validation_errors": ["Invalid credit card number"]
    # }
    
    # Order Tracking
    ticket_id: NotRequired[str]  # Unique order ticket identifier
    
    # Conversation Management
    conversation_history: NotRequired[List[Dict[str, Any]]]  # Full conversation log
    # Example: [
    #     {
    #         "timestamp": "2024-01-15T10:30:00Z",
    #         "role": "assistant", 
    #         "message": "Hello! Welcome to Tony's Pizza...",
    #         "state": "greeting"
    #     },
    #     {
    #         "timestamp": "2024-01-15T10:30:15Z",
    #         "role": "user",
    #         "message": "Hi, I'd like to order a pizza",
    #         "state": "greeting"
    #     }
    # ]
    
    # Interface and Session Information
    interface_type: NotRequired[str]  # "phone" or "web"
    session_id: NotRequired[str]     # Unique session identifier
    
    # Current Conversation State
    current_state: NotRequired[str]  # Current conversation state name
    next_state: NotRequired[str]     # Next intended state
    
    # Error Handling and Recovery
    error_count: NotRequired[int]    # Number of errors encountered
    last_error: NotRequired[str]     # Last error message
    retry_count: NotRequired[int]    # Number of retries for current operation
    
    # Additional Context
    user_input: NotRequired[str]     # Current user input being processed
    agent_response: NotRequired[str] # Agent's response to be sent
    
    # Menu and Configuration Context
    available_menu: NotRequired[Dict[str, Any]]  # Current menu options
    # Example: {
    #     "sizes": {"small": 12.99, "medium": 15.99, "large": 18.99},
    #     "toppings": {"pepperoni": 2.00, "mushrooms": 1.50, ...},
    #     "specials": [{"name": "Family Deal", "description": "...", "price": 25.99}]
    # }
    
    # Timing and Analytics
    conversation_start_time: NotRequired[str]  # ISO timestamp of conversation start
    last_interaction_time: NotRequired[str]    # ISO timestamp of last interaction
    
    # Agent Configuration
    max_retries: NotRequired[int]    # Maximum retry attempts per operation
    timeout_minutes: NotRequired[int] # Session timeout in minutes


class ConversationState(TypedDict):
    """
    Simplified state for tracking conversation flow and transitions.
    
    Used for lightweight state management and routing decisions.
    """
    current_state: str
    previous_state: Optional[str]
    next_state: Optional[str]
    can_transition: bool
    transition_reason: Optional[str]


class ValidationResult(TypedDict):
    """
    Structure for validation results across different input types.
    """
    is_valid: bool
    field_name: str
    error_message: Optional[str]
    suggested_fix: Optional[str]
    validation_details: NotRequired[Dict[str, Any]]


class StateManager:
    """
    Utility class for managing OrderState transitions and validation.
    
    Provides helper methods for state manipulation, validation,
    and conversation flow management.
    """
    
    # Define valid conversation states
    VALID_STATES = {
        "greeting",
        "collect_name", 
        "collect_address",
        "collect_order",
        "collect_payment_preference", 
        "validate_inputs",
        "process_payment",
        "estimate_delivery",
        "generate_ticket",
        "confirmation",
        "error",
        "complete"
    }
    
    # Define required fields for each state
    STATE_REQUIREMENTS = {
        "greeting": [],
        "collect_name": [],
        "collect_address": ["customer_name"],
        "collect_order": ["customer_name", "address"],
        "collect_payment_preference": ["customer_name", "address", "pizzas"],
        "validate_inputs": ["customer_name", "address", "pizzas", "payment_method"],
        "process_payment": ["customer_name", "address", "pizzas", "payment_method"],
        "estimate_delivery": ["customer_name", "address", "pizzas", "payment_method"],
        "generate_ticket": ["customer_name", "address", "pizzas", "payment_method", "order_total"],
        "confirmation": ["ticket_id", "order_total", "delivery_time"],
        "complete": ["ticket_id"]
    }
    
    @staticmethod
    def create_initial_state(session_id: str, interface_type: str) -> OrderState:
        """
        Create a new OrderState with initial values.
        
        Args:
            session_id (str): Unique session identifier
            interface_type (str): "phone" or "web"
            
        Returns:
            OrderState: Initialized state object
        """
        current_time = datetime.utcnow().isoformat() + 'Z'
        
        return OrderState(
            session_id=session_id,
            interface_type=interface_type,
            current_state="greeting",
            conversation_history=[],
            validation_status={},
            error_count=0,
            retry_count=0,
            conversation_start_time=current_time,
            last_interaction_time=current_time,
            max_retries=3,
            timeout_minutes=30,
            pizzas=[],
            available_menu=StateManager._get_default_menu()
        )
    
    @staticmethod
    def _get_default_menu() -> Dict[str, Any]:
        """Get the default pizza menu configuration."""
        return {
            "sizes": {
                "small": {"price": 12.99, "name": "Small (10\")"},
                "medium": {"price": 15.99, "name": "Medium (12\")"},
                "large": {"price": 18.99, "name": "Large (14\")"}
            },
            "toppings": {
                "pepperoni": 2.00,
                "mushrooms": 1.50,
                "sausage": 2.00,
                "peppers": 1.50,
                "onions": 1.00,
                "extra_cheese": 2.50,
                "olives": 1.50,
                "ham": 2.00,
                "pineapple": 1.50,
                "anchovies": 2.00
            },
            "crusts": {
                "thin": "Thin Crust",
                "thick": "Thick Crust", 
                "stuffed": "Stuffed Crust (+$2.00)"
            },
            "specials": [
                {
                    "name": "Pepperoni Lovers",
                    "description": "Extra pepperoni on large pizza",
                    "price": 19.99,
                    "size": "large"
                },
                {
                    "name": "Veggie Supreme", 
                    "description": "Mushrooms, peppers, onions, olives",
                    "price": 17.99,
                    "size": "medium"
                }
            ]
        }
    
    @staticmethod
    def validate_state_transition(state: OrderState, target_state: str) -> ValidationResult:
        """
        Validate if transition to target state is possible.
        
        Args:
            state (OrderState): Current state
            target_state (str): Desired next state
            
        Returns:
            ValidationResult: Validation outcome
        """
        if target_state not in StateManager.VALID_STATES:
            return ValidationResult(
                is_valid=False,
                field_name="target_state",
                error_message=f"Invalid target state: {target_state}",
                suggested_fix=f"Use one of: {', '.join(StateManager.VALID_STATES)}"
            )
        
        # Check if required fields are present for target state
        required_fields = StateManager.STATE_REQUIREMENTS.get(target_state, [])
        missing_fields = []
        
        for field in required_fields:
            if field not in state or not state[field]:
                missing_fields.append(field)
        
        if missing_fields:
            return ValidationResult(
                is_valid=False,
                field_name="required_fields",
                error_message=f"Missing required fields for {target_state}: {', '.join(missing_fields)}",
                suggested_fix=f"Collect the following information: {', '.join(missing_fields)}"
            )
        
        return ValidationResult(
            is_valid=True,
            field_name="state_transition",
            error_message=None,
            suggested_fix=None
        )
    
    @staticmethod
    def update_conversation_history(state: OrderState, role: str, message: str, 
                                   metadata: Dict[str, Any] = None) -> OrderState:
        """
        Add a new entry to conversation history.
        
        Args:
            state (OrderState): Current state
            role (str): "user" or "assistant" 
            message (str): Message content
            metadata (dict): Additional metadata
            
        Returns:
            OrderState: Updated state with new history entry
        """
        current_time = datetime.utcnow().isoformat() + 'Z'
        
        history_entry = {
            "timestamp": current_time,
            "role": role,
            "message": message,
            "state": state.get("current_state", "unknown")
        }
        
        if metadata:
            history_entry.update(metadata)
        
        # Initialize conversation_history if not present
        if "conversation_history" not in state:
            state["conversation_history"] = []
        
        state["conversation_history"].append(history_entry)
        state["last_interaction_time"] = current_time
        
        # Limit conversation history to last 50 entries
        if len(state["conversation_history"]) > 50:
            state["conversation_history"] = state["conversation_history"][-50:]
        
        return state
    
    @staticmethod
    def calculate_order_total(state: OrderState) -> float:
        """
        Calculate total order amount from pizzas and applicable fees.
        
        Args:
            state (OrderState): Current state with pizza orders
            
        Returns:
            float: Total order amount
        """
        if "pizzas" not in state or not state["pizzas"]:
            return 0.0
        
        subtotal = 0.0
        
        for pizza in state["pizzas"]:
            pizza_total = pizza.get("price", 0.0)
            quantity = pizza.get("quantity", 1)
            subtotal += pizza_total * quantity
        
        # Add tax (8.5%)
        tax = subtotal * 0.085
        
        # Add delivery fee ($2.99)
        delivery_fee = 2.99
        
        total = subtotal + tax + delivery_fee
        
        return round(total, 2)
    
    @staticmethod
    def get_state_summary(state: OrderState) -> str:
        """
        Get a human-readable summary of the current state.
        
        Args:
            state (OrderState): Current state
            
        Returns:
            str: Summary of current state
        """
        summary_parts = []
        
        # Basic info
        current_state = state.get("current_state", "unknown")
        summary_parts.append(f"State: {current_state}")
        
        # Customer info
        if "customer_name" in state:
            summary_parts.append(f"Customer: {state['customer_name']}")
        
        # Order info
        if "pizzas" in state and state["pizzas"]:
            pizza_count = len(state["pizzas"])
            summary_parts.append(f"Pizzas: {pizza_count}")
        
        # Total
        if "order_total" in state:
            summary_parts.append(f"Total: ${state['order_total']:.2f}")
        
        # Errors
        error_count = state.get("error_count", 0)
        if error_count > 0:
            summary_parts.append(f"Errors: {error_count}")
        
        return " | ".join(summary_parts)


# Export main components
__all__ = [
    "OrderState",
    "ConversationState", 
    "ValidationResult",
    "StateManager"
]