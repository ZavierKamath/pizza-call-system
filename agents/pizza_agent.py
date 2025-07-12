"""
LangGraph pizza ordering agent with complete conversation flow.
Implements state-based conversation management with OpenAI integration.
"""

import os
import logging
import asyncio
from typing import Any, Dict, List, Optional, Union, Literal
from datetime import datetime
import re
import uuid

# LangGraph and LangChain imports
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

# Local imports
from .states import OrderState, StateManager, ValidationResult
from .prompts import PromptManager
from ..database import (
    create_session, update_session, get_session, 
    create_order, get_order, OrderManager
)
from ..validation import AddressValidator, OrderValidator, PaymentValidator
from ..agents.delivery_estimator import DeliveryEstimator
from ..config.logging_config import get_logger, log_session_operation

# Configure logging
logger = get_logger(__name__)


class PizzaOrderingAgent:
    """
    Main LangGraph agent for handling pizza ordering conversations.
    
    Manages the complete order flow from greeting to confirmation using
    StateGraph with proper state transitions and validation.
    """
    
    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Initialize the pizza ordering agent.
        
        Args:
            openai_api_key (str): OpenAI API key for LLM integration
        """
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError("OpenAI API key is required")
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            model="gpt-4",
            temperature=0.7,
            api_key=self.openai_api_key,
            max_tokens=500
        )
        
        # Initialize components
        self.state_manager = StateManager()
        self.prompt_manager = PromptManager()
        self.address_validator = AddressValidator()
        self.order_validator = OrderValidator()
        self.payment_validator = PaymentValidator()
        self.delivery_estimator = DeliveryEstimator()
        
        # Build the LangGraph workflow
        self.graph = self._build_graph()
        
        logger.info("PizzaOrderingAgent initialized successfully")
    
    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph StateGraph for conversation flow.
        
        Returns:
            StateGraph: Compiled graph ready for execution
        """
        # Create StateGraph with OrderState
        workflow = StateGraph(OrderState)
        
        # Add all conversation state nodes
        workflow.add_node("greeting", self._handle_greeting)
        workflow.add_node("collect_name", self._handle_collect_name)
        workflow.add_node("collect_address", self._handle_collect_address)
        workflow.add_node("collect_order", self._handle_collect_order)
        workflow.add_node("collect_payment_preference", self._handle_collect_payment_preference)
        workflow.add_node("validate_inputs", self._handle_validate_inputs)
        workflow.add_node("process_payment", self._handle_process_payment)
        workflow.add_node("estimate_delivery", self._handle_estimate_delivery)
        workflow.add_node("generate_ticket", self._handle_generate_ticket)
        workflow.add_node("confirmation", self._handle_confirmation)
        workflow.add_node("error", self._handle_error)
        
        # Define conversation flow with conditional edges
        workflow.add_edge(START, "greeting")
        
        # Greeting to name collection
        workflow.add_conditional_edges(
            "greeting",
            self._route_from_greeting,
            {
                "collect_name": "collect_name",
                "error": "error"
            }
        )
        
        # Name to address collection
        workflow.add_conditional_edges(
            "collect_name", 
            self._route_from_collect_name,
            {
                "collect_address": "collect_address",
                "collect_name": "collect_name",  # Retry if name invalid
                "error": "error"
            }
        )
        
        # Address to order collection
        workflow.add_conditional_edges(
            "collect_address",
            self._route_from_collect_address,
            {
                "collect_order": "collect_order",
                "collect_address": "collect_address",  # Retry if address invalid
                "error": "error"
            }
        )
        
        # Order to payment preference
        workflow.add_conditional_edges(
            "collect_order",
            self._route_from_collect_order,
            {
                "collect_payment_preference": "collect_payment_preference",
                "collect_order": "collect_order",  # Continue adding items
                "error": "error"
            }
        )
        
        # Payment preference to validation
        workflow.add_conditional_edges(
            "collect_payment_preference",
            self._route_from_payment_preference,
            {
                "validate_inputs": "validate_inputs",
                "collect_payment_preference": "collect_payment_preference",  # Retry
                "error": "error"
            }
        )
        
        # Validation to payment processing
        workflow.add_conditional_edges(
            "validate_inputs",
            self._route_from_validation,
            {
                "process_payment": "process_payment",
                "collect_name": "collect_name",      # Fix name issues
                "collect_address": "collect_address", # Fix address issues
                "collect_order": "collect_order",     # Fix order issues
                "error": "error"
            }
        )
        
        # Payment to delivery estimation
        workflow.add_conditional_edges(
            "process_payment",
            self._route_from_payment,
            {
                "estimate_delivery": "estimate_delivery",
                "collect_payment_preference": "collect_payment_preference",  # Retry payment
                "error": "error"
            }
        )
        
        # Delivery estimation to ticket generation
        workflow.add_edge("estimate_delivery", "generate_ticket")
        
        # Ticket generation to confirmation
        workflow.add_conditional_edges(
            "generate_ticket",
            self._route_from_ticket_generation,
            {
                "confirmation": "confirmation",
                "error": "error"
            }
        )
        
        # Confirmation to end
        workflow.add_edge("confirmation", END)
        
        # Error handling can route back to appropriate states
        workflow.add_conditional_edges(
            "error",
            self._route_from_error,
            {
                "greeting": "greeting",
                "collect_name": "collect_name",
                "collect_address": "collect_address", 
                "collect_order": "collect_order",
                "collect_payment_preference": "collect_payment_preference",
                "validate_inputs": "validate_inputs",
                "process_payment": "process_payment",
                END: END
            }
        )
        
        # Compile with memory checkpointer for state persistence
        memory = MemorySaver()
        return workflow.compile(checkpointer=memory)
    
    # Node handler implementations
    
    def _handle_greeting(self, state: OrderState) -> OrderState:
        """Handle initial customer greeting."""
        logger.info(f"Processing greeting for session {state.get('session_id')}")
        
        try:
            # Get system prompt for greeting
            prompt = self.prompt_manager.get_prompt_for_state("greeting", state)
            
            # Generate greeting response
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=state.get("user_input", "Hello"))
            ]
            
            response = self.llm.invoke(messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["agent_response"] = response.content
            updated_state["current_state"] = "greeting"
            updated_state["next_state"] = "collect_name"
            
            # Update conversation history
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "user", state.get("user_input", "Hello")
            )
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "assistant", response.content
            )
            
            log_session_operation(
                "greeting_processed", 
                state.get("session_id", "unknown"),
                {"response_length": len(response.content)}
            )
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Error in greeting handler: {e}")
            return self._handle_error_in_state(state, str(e))
    
    def _handle_collect_name(self, state: OrderState) -> OrderState:
        """Handle customer name collection."""
        logger.info(f"Collecting name for session {state.get('session_id')}")
        
        try:
            user_input = self.prompt_manager.sanitize_user_input(
                state.get("user_input", "")
            )
            
            # Extract name from user input
            extracted_name = self._extract_name_from_input(user_input)
            
            # Get appropriate prompt
            prompt = self.prompt_manager.get_prompt_for_state("collect_name", state)
            
            # Build conversation context
            context_messages = self._build_conversation_context(state)
            context_messages.extend([
                SystemMessage(content=prompt),
                HumanMessage(content=user_input)
            ])
            
            response = self.llm.invoke(context_messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["agent_response"] = response.content
            updated_state["current_state"] = "collect_name"
            
            # If we extracted a valid name, store it
            if extracted_name and self._validate_name(extracted_name):
                updated_state["customer_name"] = extracted_name
                updated_state["next_state"] = "collect_address"
                logger.info(f"Name collected: {extracted_name}")
            else:
                updated_state["next_state"] = "collect_name"  # Retry
                if extracted_name:
                    updated_state["last_error"] = f"Invalid name: {extracted_name}"
            
            # Update conversation history
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "user", user_input
            )
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "assistant", response.content
            )
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Error in collect_name handler: {e}")
            return self._handle_error_in_state(state, str(e))
    
    def _handle_collect_address(self, state: OrderState) -> OrderState:
        """Handle delivery address collection."""
        logger.info(f"Collecting address for session {state.get('session_id')}")
        
        try:
            user_input = self.prompt_manager.sanitize_user_input(
                state.get("user_input", "")
            )
            
            # Extract address components from input
            address_data = self._extract_address_from_input(user_input, state)
            
            # Get appropriate prompt
            prompt = self.prompt_manager.get_prompt_for_state("collect_address", state)
            
            # Build conversation context
            context_messages = self._build_conversation_context(state)
            context_messages.extend([
                SystemMessage(content=prompt),
                HumanMessage(content=user_input)
            ])
            
            response = self.llm.invoke(context_messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["agent_response"] = response.content
            updated_state["current_state"] = "collect_address"
            
            # Validate address if we have enough information
            if address_data and self._is_address_complete(address_data):
                validation_result = self.address_validator.validate_address(address_data)
                
                if validation_result["is_valid"]:
                    updated_state["address"] = address_data
                    updated_state["next_state"] = "collect_order"
                    logger.info(f"Address validated: {address_data}")
                else:
                    updated_state["next_state"] = "collect_address"  # Retry
                    updated_state["last_error"] = validation_result.get("error", "Invalid address")
            else:
                # Need more address information
                updated_state["next_state"] = "collect_address"
                if address_data:
                    # Partial address - store what we have
                    updated_state["address"] = {**updated_state.get("address", {}), **address_data}
            
            # Update conversation history
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "user", user_input
            )
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "assistant", response.content
            )
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Error in collect_address handler: {e}")
            return self._handle_error_in_state(state, str(e))
    
    def _handle_collect_order(self, state: OrderState) -> OrderState:
        """Handle pizza order collection."""
        logger.info(f"Collecting order for session {state.get('session_id')}")
        
        try:
            user_input = self.prompt_manager.sanitize_user_input(
                state.get("user_input", "")
            )
            
            # Extract pizza order from input
            pizza_order = self._extract_pizza_order_from_input(user_input, state)
            
            # Get appropriate prompt with menu context
            context = {**state, "available_menu": self.state_manager._get_default_menu()}
            prompt = self.prompt_manager.get_prompt_for_state("collect_order", context)
            
            # Build conversation context
            context_messages = self._build_conversation_context(state)
            context_messages.extend([
                SystemMessage(content=prompt),
                HumanMessage(content=user_input)
            ])
            
            response = self.llm.invoke(context_messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["agent_response"] = response.content
            updated_state["current_state"] = "collect_order"
            
            # Add pizza to order if valid
            if pizza_order:
                current_pizzas = updated_state.get("pizzas", [])
                current_pizzas.append(pizza_order)
                updated_state["pizzas"] = current_pizzas
                
                # Calculate running total
                updated_state["order_total"] = self.state_manager.calculate_order_total(updated_state)
                
                logger.info(f"Pizza added to order: {pizza_order}")
            
            # Determine next state based on user intent
            if self._user_wants_more_items(user_input):
                updated_state["next_state"] = "collect_order"  # Continue ordering
            elif updated_state.get("pizzas"):
                updated_state["next_state"] = "collect_payment_preference"
            else:
                updated_state["next_state"] = "collect_order"  # Need at least one pizza
            
            # Update conversation history
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "user", user_input
            )
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "assistant", response.content
            )
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Error in collect_order handler: {e}")
            return self._handle_error_in_state(state, str(e))
    
    def _handle_collect_payment_preference(self, state: OrderState) -> OrderState:
        """Handle payment method selection."""
        logger.info(f"Collecting payment preference for session {state.get('session_id')}")
        
        try:
            user_input = self.prompt_manager.sanitize_user_input(
                state.get("user_input", "")
            )
            
            # Extract payment preference
            payment_method = self._extract_payment_method_from_input(user_input)
            
            # Get appropriate prompt
            prompt = self.prompt_manager.get_prompt_for_state("collect_payment_preference", state)
            
            # Build conversation context
            context_messages = self._build_conversation_context(state)
            context_messages.extend([
                SystemMessage(content=prompt),
                HumanMessage(content=user_input)
            ])
            
            response = self.llm.invoke(context_messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["agent_response"] = response.content
            updated_state["current_state"] = "collect_payment_preference"
            
            # Store payment method if valid
            if payment_method in ["credit_card", "debit_card", "cash"]:
                updated_state["payment_method"] = payment_method
                updated_state["next_state"] = "validate_inputs"
                logger.info(f"Payment method selected: {payment_method}")
            else:
                updated_state["next_state"] = "collect_payment_preference"  # Retry
                if payment_method:
                    updated_state["last_error"] = f"Invalid payment method: {payment_method}"
            
            # Update conversation history
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "user", user_input
            )
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "assistant", response.content
            )
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Error in collect_payment_preference handler: {e}")
            return self._handle_error_in_state(state, str(e))
    
    def _handle_validate_inputs(self, state: OrderState) -> OrderState:
        """Handle comprehensive order validation."""
        logger.info(f"Validating inputs for session {state.get('session_id')}")
        
        try:
            # Perform comprehensive validation
            validation_results = self._perform_comprehensive_validation(state)
            
            # Get appropriate prompt
            prompt = self.prompt_manager.get_prompt_for_state("validate_inputs", state)
            
            # Build validation summary for LLM
            validation_summary = self._build_validation_summary(validation_results)
            
            # Build conversation context
            context_messages = self._build_conversation_context(state)
            context_messages.extend([
                SystemMessage(content=prompt + f"\n\nVALIDATION RESULTS:\n{validation_summary}"),
                HumanMessage(content=state.get("user_input", "Please validate my order"))
            ])
            
            response = self.llm.invoke(context_messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["agent_response"] = response.content
            updated_state["current_state"] = "validate_inputs"
            updated_state["validation_status"] = validation_results
            
            # Determine next state based on validation results
            if all(result["is_valid"] for result in validation_results.values()):
                updated_state["next_state"] = "process_payment"
                logger.info("All validations passed")
            else:
                # Route to appropriate collection state for fixing
                next_state = self._determine_validation_fix_state(validation_results)
                updated_state["next_state"] = next_state
                logger.warning(f"Validation failed, routing to: {next_state}")
            
            # Update conversation history
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "user", state.get("user_input", "Validation request")
            )
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "assistant", response.content
            )
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Error in validate_inputs handler: {e}")
            return self._handle_error_in_state(state, str(e))
    
    def _handle_process_payment(self, state: OrderState) -> OrderState:
        """Handle payment processing."""
        logger.info(f"Processing payment for session {state.get('session_id')}")
        
        try:
            payment_method = state.get("payment_method")
            order_total = state.get("order_total", 0.0)
            
            # Get appropriate prompt
            prompt = self.prompt_manager.get_prompt_for_state("process_payment", state)
            
            # Simulate payment processing based on method
            payment_result = self._process_payment_transaction(state)
            
            # Build conversation context
            context_messages = self._build_conversation_context(state)
            context_messages.extend([
                SystemMessage(content=prompt + f"\n\nPAYMENT RESULT: {payment_result}"),
                HumanMessage(content=f"Process {payment_method} payment for ${order_total:.2f}")
            ])
            
            response = self.llm.invoke(context_messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["agent_response"] = response.content
            updated_state["current_state"] = "process_payment"
            
            if payment_result["success"]:
                updated_state["next_state"] = "estimate_delivery"
                # Store payment confirmation
                if payment_method in ["credit_card", "debit_card"]:
                    updated_state["credit_card"] = {
                        "transaction_id": payment_result.get("transaction_id"),
                        "last_four": payment_result.get("last_four", "****")
                    }
                logger.info(f"Payment processed successfully: {payment_result}")
            else:
                updated_state["next_state"] = "collect_payment_preference"  # Retry payment
                updated_state["last_error"] = payment_result.get("error", "Payment failed")
                logger.warning(f"Payment failed: {payment_result}")
            
            # Update conversation history
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "assistant", response.content
            )
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Error in process_payment handler: {e}")
            return self._handle_error_in_state(state, str(e))
    
    def _handle_estimate_delivery(self, state: OrderState) -> OrderState:
        """Handle delivery time estimation."""
        logger.info(f"Estimating delivery for session {state.get('session_id')}")
        
        try:
            # Calculate delivery estimate
            delivery_estimate = self.delivery_estimator.estimate_delivery_time(
                state.get("address", {}),
                current_orders=self._get_current_order_count()
            )
            
            # Get appropriate prompt
            prompt = self.prompt_manager.get_prompt_for_state("estimate_delivery", state)
            
            # Build conversation context
            context_messages = self._build_conversation_context(state)
            context_messages.extend([
                SystemMessage(content=prompt),
                HumanMessage(content=f"Estimate delivery time to {state.get('address', {}).get('street', 'customer address')}")
            ])
            
            response = self.llm.invoke(context_messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["agent_response"] = response.content
            updated_state["current_state"] = "estimate_delivery"
            updated_state["delivery_time"] = delivery_estimate
            updated_state["next_state"] = "generate_ticket"
            
            logger.info(f"Delivery estimated: {delivery_estimate} minutes")
            
            # Update conversation history
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "assistant", response.content
            )
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Error in estimate_delivery handler: {e}")
            return self._handle_error_in_state(state, str(e))
    
    def _handle_generate_ticket(self, state: OrderState) -> OrderState:
        """Handle order ticket generation."""
        logger.info(f"Generating ticket for session {state.get('session_id')}")
        
        try:
            # Generate unique ticket ID
            ticket_id = self._generate_ticket_id()
            
            # Create order in database
            order_data = self._prepare_order_data_for_database(state, ticket_id)
            order = create_order(order_data)
            
            if not order:
                raise Exception("Failed to create order in database")
            
            # Get appropriate prompt
            prompt = self.prompt_manager.get_prompt_for_state("generate_ticket", state)
            
            # Build conversation context
            context_messages = self._build_conversation_context(state)
            context_messages.extend([
                SystemMessage(content=prompt),
                HumanMessage(content=f"Generate order ticket #{ticket_id}")
            ])
            
            response = self.llm.invoke(context_messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["agent_response"] = response.content
            updated_state["current_state"] = "generate_ticket"
            updated_state["ticket_id"] = ticket_id
            updated_state["next_state"] = "confirmation"
            
            logger.info(f"Ticket generated: {ticket_id}")
            
            # Update conversation history
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "assistant", response.content
            )
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Error in generate_ticket handler: {e}")
            return self._handle_error_in_state(state, str(e))
    
    def _handle_confirmation(self, state: OrderState) -> OrderState:
        """Handle final order confirmation."""
        logger.info(f"Confirming order for session {state.get('session_id')}")
        
        try:
            # Get appropriate prompt
            prompt = self.prompt_manager.get_prompt_for_state("confirmation", state)
            
            # Build conversation context
            context_messages = self._build_conversation_context(state)
            context_messages.extend([
                SystemMessage(content=prompt),
                HumanMessage(content="Confirm the order details")
            ])
            
            response = self.llm.invoke(context_messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["agent_response"] = response.content
            updated_state["current_state"] = "confirmation"
            updated_state["next_state"] = "complete"
            
            # Mark order as confirmed in database
            if updated_state.get("ticket_id"):
                # Update order status or create final confirmation
                pass
            
            logger.info(f"Order confirmed: {updated_state.get('ticket_id')}")
            
            # Update conversation history
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "assistant", response.content
            )
            
            # Log successful completion
            log_session_operation(
                "order_completed",
                state.get("session_id", "unknown"),
                {
                    "ticket_id": updated_state.get("ticket_id"),
                    "total": updated_state.get("order_total"),
                    "customer": updated_state.get("customer_name")
                }
            )
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Error in confirmation handler: {e}")
            return self._handle_error_in_state(state, str(e))
    
    def _handle_error(self, state: OrderState) -> OrderState:
        """Handle error states and recovery."""
        logger.warning(f"Handling error for session {state.get('session_id')}")
        
        try:
            error_message = state.get("last_error", "An unexpected error occurred")
            retry_count = state.get("retry_count", 0)
            
            # Get appropriate prompt
            prompt = self.prompt_manager.get_prompt_for_state("error", state)
            
            # Build conversation context
            context_messages = self._build_conversation_context(state)
            context_messages.extend([
                SystemMessage(content=prompt + f"\n\nERROR: {error_message}\nRETRY: {retry_count}"),
                HumanMessage(content="Handle the error and guide recovery")
            ])
            
            response = self.llm.invoke(context_messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["agent_response"] = response.content
            updated_state["current_state"] = "error"
            updated_state["retry_count"] = retry_count + 1
            
            # Determine recovery strategy
            if retry_count >= updated_state.get("max_retries", 3):
                # Too many retries, end conversation
                updated_state["next_state"] = "END"
            else:
                # Try to recover to appropriate state
                recovery_state = self._determine_error_recovery_state(state)
                updated_state["next_state"] = recovery_state
            
            logger.info(f"Error recovery: retry {retry_count}, next state: {updated_state['next_state']}")
            
            # Update conversation history
            updated_state = self.state_manager.update_conversation_history(
                updated_state, "assistant", response.content
            )
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Error in error handler: {e}")
            # Fatal error - end conversation
            state["agent_response"] = "I'm sorry, but I'm experiencing technical difficulties. Please call us directly at (555) 123-PIZZA."
            state["next_state"] = "END"
            return state
    
    # Helper methods for the agent
    
    def _handle_error_in_state(self, state: OrderState, error_message: str) -> OrderState:
        """Helper to handle errors within state handlers."""
        updated_state = state.copy()
        updated_state["last_error"] = error_message
        updated_state["error_count"] = updated_state.get("error_count", 0) + 1
        updated_state["next_state"] = "error"
        return updated_state
    
    def _build_conversation_context(self, state: OrderState) -> List:
        """Build conversation context from history."""
        messages = []
        
        # Get recent conversation history (last 5 exchanges)
        history = state.get("conversation_history", [])[-10:]
        
        for entry in history:
            if entry["role"] == "user":
                messages.append(HumanMessage(content=entry["message"]))
            elif entry["role"] == "assistant":
                messages.append(AIMessage(content=entry["message"]))
        
        return messages
    
    # Routing functions for conditional edges
    
    def _route_from_greeting(self, state: OrderState) -> str:
        """Route from greeting state."""
        if state.get("next_state") == "error":
            return "error"
        return "collect_name"
    
    def _route_from_collect_name(self, state: OrderState) -> str:
        """Route from collect_name state."""
        next_state = state.get("next_state", "error")
        if next_state in ["collect_address", "collect_name", "error"]:
            return next_state
        return "error"
    
    def _route_from_collect_address(self, state: OrderState) -> str:
        """Route from collect_address state."""
        next_state = state.get("next_state", "error")
        if next_state in ["collect_order", "collect_address", "error"]:
            return next_state
        return "error"
    
    def _route_from_collect_order(self, state: OrderState) -> str:
        """Route from collect_order state."""
        next_state = state.get("next_state", "error")
        if next_state in ["collect_payment_preference", "collect_order", "error"]:
            return next_state
        return "error"
    
    def _route_from_payment_preference(self, state: OrderState) -> str:
        """Route from collect_payment_preference state."""
        next_state = state.get("next_state", "error")
        if next_state in ["validate_inputs", "collect_payment_preference", "error"]:
            return next_state
        return "error"
    
    def _route_from_validation(self, state: OrderState) -> str:
        """Route from validate_inputs state."""
        next_state = state.get("next_state", "error")
        valid_states = ["process_payment", "collect_name", "collect_address", "collect_order", "error"]
        if next_state in valid_states:
            return next_state
        return "error"
    
    def _route_from_payment(self, state: OrderState) -> str:
        """Route from process_payment state."""
        next_state = state.get("next_state", "error")
        if next_state in ["estimate_delivery", "collect_payment_preference", "error"]:
            return next_state
        return "error"
    
    def _route_from_ticket_generation(self, state: OrderState) -> str:
        """Route from generate_ticket state."""
        next_state = state.get("next_state", "error")
        if next_state in ["confirmation", "error"]:
            return next_state
        return "error"
    
    def _route_from_error(self, state: OrderState) -> str:
        """Route from error state."""
        next_state = state.get("next_state", "END")
        valid_states = [
            "greeting", "collect_name", "collect_address", "collect_order",
            "collect_payment_preference", "validate_inputs", "process_payment", "END"
        ]
        if next_state in valid_states:
            return next_state
        return "END"
    
    # Input extraction and validation helpers
    
    def _extract_name_from_input(self, user_input: str) -> Optional[str]:
        """Extract customer name from user input."""
        # Simple name extraction - look for name patterns
        name_patterns = [
            r"my name is (\w+ \w+)",
            r"i'm (\w+ \w+)",
            r"this is (\w+ \w+)",
            r"(\w+ \w+)"  # Fallback - any two words
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, user_input.lower())
            if match:
                name = match.group(1).title()
                if len(name.split()) >= 1:  # At least one word
                    return name
        
        # If input looks like just a name
        words = user_input.strip().split()
        if 1 <= len(words) <= 3 and all(word.isalpha() for word in words):
            return " ".join(word.title() for word in words)
        
        return None
    
    def _validate_name(self, name: str) -> bool:
        """Validate if name is reasonable."""
        if not name or len(name) < 2 or len(name) > 50:
            return False
        
        # Check for reasonable characters
        if not re.match(r"^[a-zA-Z\s\-'\.]+$", name):
            return False
        
        return True
    
    def _extract_address_from_input(self, user_input: str, state: OrderState) -> Optional[Dict[str, Any]]:
        """Extract address components from user input."""
        # This is a simplified address extraction
        # In a real system, you'd use more sophisticated NLP
        
        address_data = {}
        input_lower = user_input.lower()
        
        # Look for street address patterns
        street_pattern = r"(\d+\s+[a-zA-Z\s]+(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|way|court|ct|place|pl))"
        street_match = re.search(street_pattern, user_input, re.IGNORECASE)
        if street_match:
            address_data["street"] = street_match.group(1)
        
        # Look for apartment/unit
        apt_pattern = r"(?:apt|apartment|unit|#)\s*([a-zA-Z0-9]+)"
        apt_match = re.search(apt_pattern, user_input, re.IGNORECASE)
        if apt_match:
            address_data["unit"] = apt_match.group(1)
        
        # Look for zip code
        zip_pattern = r"\b(\d{5}(?:-\d{4})?)\b"
        zip_match = re.search(zip_pattern, user_input)
        if zip_match:
            address_data["zip"] = zip_match.group(1)
        
        # Simple city extraction (this would need improvement)
        if "city" not in address_data:
            # Look for common city indicators
            words = user_input.replace(",", "").split()
            for i, word in enumerate(words):
                if word.lower() in ["city", "town"] and i > 0:
                    address_data["city"] = words[i-1].title()
                    break
        
        # Default state if not provided
        if "state" not in address_data:
            address_data["state"] = "CA"  # Default for demo
        
        return address_data if address_data else None
    
    def _is_address_complete(self, address_data: Dict[str, Any]) -> bool:
        """Check if address has minimum required components."""
        required = ["street"]
        return all(field in address_data and address_data[field] for field in required)
    
    def _extract_pizza_order_from_input(self, user_input: str, state: OrderState) -> Optional[Dict[str, Any]]:
        """Extract pizza order details from user input."""
        pizza_order = {}
        input_lower = user_input.lower()
        
        # Extract size
        size_patterns = {
            "small": ["small", "10", "10 inch", "personal"],
            "medium": ["medium", "12", "12 inch", "regular"],
            "large": ["large", "14", "14 inch", "big", "family"]
        }
        
        for size, patterns in size_patterns.items():
            if any(pattern in input_lower for pattern in patterns):
                pizza_order["size"] = size
                break
        
        # Extract crust
        if "thin" in input_lower:
            pizza_order["crust"] = "thin"
        elif "thick" in input_lower:
            pizza_order["crust"] = "thick"
        elif "stuffed" in input_lower:
            pizza_order["crust"] = "stuffed"
        else:
            pizza_order["crust"] = "thin"  # Default
        
        # Extract toppings
        menu = self.state_manager._get_default_menu()
        toppings = []
        
        for topping in menu["toppings"].keys():
            if topping in input_lower or topping.replace("_", " ") in input_lower:
                toppings.append(topping)
        
        pizza_order["toppings"] = toppings
        pizza_order["quantity"] = 1  # Default
        
        # Calculate price
        if "size" in pizza_order:
            base_price = menu["sizes"][pizza_order["size"]]["price"]
            topping_price = sum(menu["toppings"][t] for t in toppings)
            crust_price = 2.0 if pizza_order.get("crust") == "stuffed" else 0.0
            
            pizza_order["price"] = base_price + topping_price + crust_price
        
        return pizza_order if "size" in pizza_order else None
    
    def _extract_payment_method_from_input(self, user_input: str) -> Optional[str]:
        """Extract payment method from user input."""
        input_lower = user_input.lower()
        
        if any(word in input_lower for word in ["credit", "card", "visa", "mastercard", "amex"]):
            return "credit_card"
        elif any(word in input_lower for word in ["debit"]):
            return "debit_card"
        elif any(word in input_lower for word in ["cash", "money"]):
            return "cash"
        
        return None
    
    def _user_wants_more_items(self, user_input: str) -> bool:
        """Determine if user wants to add more items."""
        input_lower = user_input.lower()
        more_indicators = ["another", "more", "add", "also", "and"]
        done_indicators = ["done", "finished", "complete", "that's all", "nothing else"]
        
        if any(indicator in input_lower for indicator in done_indicators):
            return False
        if any(indicator in input_lower for indicator in more_indicators):
            return True
        
        return False  # Default to done
    
    def _perform_comprehensive_validation(self, state: OrderState) -> Dict[str, ValidationResult]:
        """Perform comprehensive validation of all order components."""
        results = {}
        
        # Validate customer name
        name = state.get("customer_name")
        results["name"] = ValidationResult(
            is_valid=bool(name and self._validate_name(name)),
            field_name="customer_name",
            error_message=None if name and self._validate_name(name) else "Invalid or missing customer name",
            suggested_fix="Please provide a valid name"
        )
        
        # Validate address
        address = state.get("address")
        if address:
            address_validation = self.address_validator.validate_address(address)
            results["address"] = ValidationResult(
                is_valid=address_validation["is_valid"],
                field_name="address",
                error_message=address_validation.get("error"),
                suggested_fix="Please provide a complete delivery address"
            )
        else:
            results["address"] = ValidationResult(
                is_valid=False,
                field_name="address",
                error_message="Missing delivery address",
                suggested_fix="Please provide your delivery address"
            )
        
        # Validate order
        pizzas = state.get("pizzas", [])
        results["order"] = ValidationResult(
            is_valid=len(pizzas) > 0,
            field_name="pizzas",
            error_message=None if pizzas else "No pizzas in order",
            suggested_fix="Please add at least one pizza to your order"
        )
        
        # Validate payment method
        payment_method = state.get("payment_method")
        results["payment"] = ValidationResult(
            is_valid=payment_method in ["credit_card", "debit_card", "cash"],
            field_name="payment_method",
            error_message=None if payment_method in ["credit_card", "debit_card", "cash"] else "Invalid payment method",
            suggested_fix="Please choose credit card, debit card, or cash"
        )
        
        return results
    
    def _build_validation_summary(self, validation_results: Dict[str, ValidationResult]) -> str:
        """Build a summary of validation results."""
        summary_parts = []
        
        for field, result in validation_results.items():
            status = "" if result["is_valid"] else ""
            summary_parts.append(f"{status} {field.title()}: {result['error_message'] or 'Valid'}")
        
        return "\n".join(summary_parts)
    
    def _determine_validation_fix_state(self, validation_results: Dict[str, ValidationResult]) -> str:
        """Determine which state to route to for fixing validation errors."""
        # Priority order for fixing validation issues
        if not validation_results["name"]["is_valid"]:
            return "collect_name"
        elif not validation_results["address"]["is_valid"]:
            return "collect_address"
        elif not validation_results["order"]["is_valid"]:
            return "collect_order"
        elif not validation_results["payment"]["is_valid"]:
            return "collect_payment_preference"
        else:
            return "error"
    
    def _process_payment_transaction(self, state: OrderState) -> Dict[str, Any]:
        """Simulate payment processing."""
        payment_method = state.get("payment_method")
        amount = state.get("order_total", 0.0)
        
        if payment_method == "cash":
            # Cash payment - no processing needed
            return {
                "success": True,
                "method": "cash",
                "amount": amount,
                "message": "Cash payment confirmed for delivery"
            }
        
        elif payment_method in ["credit_card", "debit_card"]:
            # Simulate card processing
            # In real implementation, integrate with Stripe or other processor
            transaction_id = f"txn_{uuid.uuid4().hex[:8]}"
            
            return {
                "success": True,
                "method": payment_method,
                "amount": amount,
                "transaction_id": transaction_id,
                "last_four": "1234",  # Mock card number
                "message": f"Payment of ${amount:.2f} processed successfully"
            }
        
        else:
            return {
                "success": False,
                "error": "Invalid payment method"
            }
    
    def _get_current_order_count(self) -> int:
        """Get current number of orders for delivery estimation."""
        # In real implementation, query database for active orders
        return 3  # Mock value
    
    def _generate_ticket_id(self) -> str:
        """Generate unique ticket ID."""
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        sequence = f"{uuid.uuid4().hex[:4].upper()}"
        return f"TP{date_str}{sequence}"
    
    def _prepare_order_data_for_database(self, state: OrderState, ticket_id: str) -> Dict[str, Any]:
        """Prepare order data for database insertion."""
        return {
            "customer_name": state.get("customer_name"),
            "phone_number": state.get("phone_number", ""),
            "address": str(state.get("address", {})),  # Convert to string for database
            "order_details": {
                "pizzas": state.get("pizzas", []),
                "ticket_id": ticket_id
            },
            "total_amount": state.get("order_total", 0.0),
            "estimated_delivery": state.get("delivery_time", 30),
            "payment_method": state.get("payment_method"),
            "payment_status": "completed" if state.get("payment_method") else "pending",
            "order_status": "confirmed",
            "interface_type": state.get("interface_type", "unknown")
        }
    
    def _determine_error_recovery_state(self, state: OrderState) -> str:
        """Determine best state for error recovery."""
        current_state = state.get("current_state", "greeting")
        
        # Try to recover to the current state or a safe previous state
        safe_states = ["greeting", "collect_name", "collect_address", "collect_order"]
        
        if current_state in safe_states:
            return current_state
        else:
            return "greeting"  # Safe fallback
    
    # Public interface methods
    
    async def process_message(self, session_id: str, user_input: str, 
                            interface_type: str = "web") -> Dict[str, Any]:
        """
        Process a user message and return agent response.
        
        Args:
            session_id (str): Unique session identifier
            user_input (str): User's input message
            interface_type (str): "phone" or "web"
            
        Returns:
            dict: Agent response and updated state information
        """
        try:
            logger.info(f"Processing message for session {session_id}")
            
            # Get or create session state
            session_state = get_session(session_id)
            
            if not session_state:
                # Create new session
                initial_state = self.state_manager.create_initial_state(session_id, interface_type)
                create_session(session_id, {
                    "interface_type": interface_type,
                    "agent_state": "greeting",
                    "order_data": initial_state
                })
                current_state = initial_state
            else:
                current_state = session_state.get("order_data", {})
            
            # Update state with user input
            current_state["user_input"] = user_input
            current_state["session_id"] = session_id
            
            # Process through LangGraph
            config = {"configurable": {"thread_id": session_id}}
            result = self.graph.invoke(current_state, config)
            
            # Update session in database
            update_session(session_id, {
                "agent_state": result.get("current_state"),
                "order_data": result
            })
            
            # Extract response for user
            response = {
                "message": result.get("agent_response", "I'm sorry, I didn't understand that."),
                "state": result.get("current_state"),
                "session_id": session_id,
                "order_summary": self._create_order_summary(result),
                "is_complete": result.get("current_state") == "confirmation"
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing message for session {session_id}: {e}")
            return {
                "message": "I'm sorry, I'm experiencing technical difficulties. Please try again.",
                "state": "error",
                "session_id": session_id,
                "order_summary": {},
                "is_complete": False
            }
    
    def _create_order_summary(self, state: OrderState) -> Dict[str, Any]:
        """Create a summary of current order for API response."""
        summary = {}
        
        if "customer_name" in state:
            summary["customer_name"] = state["customer_name"]
        
        if "address" in state:
            summary["address"] = state["address"]
        
        if "pizzas" in state:
            summary["pizzas"] = state["pizzas"]
            summary["pizza_count"] = len(state["pizzas"])
        
        if "order_total" in state:
            summary["total"] = state["order_total"]
        
        if "payment_method" in state:
            summary["payment_method"] = state["payment_method"]
        
        if "delivery_time" in state:
            summary["estimated_delivery"] = state["delivery_time"]
        
        if "ticket_id" in state:
            summary["ticket_id"] = state["ticket_id"]
        
        return summary
    
    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get current status of a session.
        
        Args:
            session_id (str): Session identifier
            
        Returns:
            dict: Session status information
        """
        try:
            session_data = get_session(session_id)
            
            if not session_data:
                return {"exists": False}
            
            order_data = session_data.get("order_data", {})
            
            return {
                "exists": True,
                "current_state": session_data.get("agent_state"),
                "interface_type": session_data.get("interface_type"),
                "summary": self.state_manager.get_state_summary(order_data),
                "order_details": self._create_order_summary(order_data)
            }
            
        except Exception as e:
            logger.error(f"Error getting session status for {session_id}: {e}")
            return {"exists": False, "error": str(e)}


# Export main class
__all__ = ["PizzaOrderingAgent"]