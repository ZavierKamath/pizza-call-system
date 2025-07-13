"""
Twilio webhook handler for incoming phone calls and TwiML responses.
Manages call state, recording, and integration with the pizza ordering agent.
"""

import logging
import uuid
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather, Say, Record
import asyncio

from ..config.settings import settings
from ..database.redis_client import get_redis_async
from ..agents.pizza_agent import PizzaOrderingAgent
from ..agents.states import StateManager, OrderState
from .session_manager import session_manager
from .speech_processing import speech_processor

# Configure logging for Twilio operations
logger = logging.getLogger(__name__)


class TwilioHandler:
    """
    Handles Twilio webhook requests and manages call state throughout the conversation.
    
    Integrates with the pizza ordering agent to provide voice-based ordering capabilities.
    Manages call recording, audio streaming, and session lifecycle.
    """
    
    def __init__(self):
        """Initialize Twilio handler with configured client and dependencies."""
        # Initialize Twilio client
        self.twilio_client = Client(
            settings.twilio_account_sid,
            settings.twilio_auth_token
        )
        
        # Initialize other components  
        self.pizza_agent = PizzaOrderingAgent(settings.openai_api_key)
        
        logger.info("TwilioHandler initialized successfully")
    
    async def handle_incoming_call(self, request: Request) -> str:
        """
        Handle incoming phone call webhook from Twilio.
        
        Creates new session and initiates conversation flow with TwiML response.
        
        Args:
            request (Request): FastAPI request object containing Twilio webhook data
            
        Returns:
            str: TwiML response XML for Twilio
        """
        try:
            # Extract call information from Twilio webhook
            form_data = await request.form()
            call_sid = form_data.get('CallSid')
            from_number = form_data.get('From')
            to_number = form_data.get('To')
            call_status = form_data.get('CallStatus')
            
            logger.info(f"Incoming call: {call_sid} from {from_number} to {to_number} status: {call_status}")
            
            # Check if we can accept new calls (concurrent limit)
            if not await session_manager.can_accept_new_session():
                logger.warning(f"Rejecting call {call_sid} - concurrent call limit reached")
                return self._create_busy_response()
            
            # Create new session for this call
            session_id = await session_manager.create_session(
                session_id=call_sid,
                interface_type="phone",
                customer_phone=from_number
            )
            
            # Initialize agent state for the new session
            initial_state = StateManager.create_initial_state(session_id, "phone")
            initial_state["phone_number"] = from_number
            
            # Store initial state in Redis
            await self._store_call_state(call_sid, initial_state)
            
            # Generate initial TwiML response with greeting
            response = self._create_greeting_response(call_sid)
            
            logger.info(f"Call {call_sid} accepted, session {session_id} created")
            return str(response)
            
        except Exception as e:
            logger.error(f"Error handling incoming call: {str(e)}")
            return self._create_error_response()
    
    async def handle_speech_input(self, request: Request) -> str:
        """
        Handle speech input from Twilio's speech recognition or recording.
        
        Processes the speech through our agent and returns appropriate TwiML response.
        
        Args:
            request (Request): FastAPI request containing speech data
            
        Returns:
            str: TwiML response XML for next action
        """
        try:
            form_data = await request.form()
            call_sid = form_data.get('CallSid')
            speech_result = form_data.get('SpeechResult')
            recording_url = form_data.get('RecordingUrl')
            
            logger.info(f"Speech input for call {call_sid}: speech_result={bool(speech_result)}, recording_url={bool(recording_url)}")
            
            # Retrieve current call state
            current_state = await self._get_call_state(call_sid)
            if not current_state:
                logger.error(f"No state found for call {call_sid}")
                return self._create_error_response()
            
            # Process speech input (either direct text or recording URL)
            user_input = speech_result
            if not user_input and recording_url:
                # Convert recording to text using our speech processor
                user_input = await speech_processor.speech_to_text(recording_url)
            
            if not user_input:
                logger.warning(f"No speech input detected for call {call_sid}")
                return self._create_no_input_response(call_sid)
            
            # Update state with user input
            current_state["user_input"] = user_input
            
            # Process input through pizza agent
            agent_response = await self.pizza_agent.process_input(current_state, user_input)
            
            # Update call state with agent response
            updated_state = agent_response.get("state", current_state)
            agent_message = agent_response.get("message", "I'm sorry, I didn't understand that.")
            
            # Store updated state
            await self._store_call_state(call_sid, updated_state)
            
            # Generate TwiML response based on agent output
            response = await self._create_agent_response(call_sid, agent_message, updated_state)
            
            logger.info(f"Processed speech for call {call_sid}, new state: {updated_state.get('current_state')}")
            return str(response)
            
        except Exception as e:
            logger.error(f"Error handling speech input: {str(e)}")
            return self._create_error_response()
    
    async def handle_call_status(self, request: Request) -> str:
        """
        Handle call status updates from Twilio (completed, busy, failed, etc.).
        
        Manages session cleanup and logging for call lifecycle events.
        
        Args:
            request (Request): FastAPI request with call status data
            
        Returns:
            str: Empty response (status updates don't need TwiML)
        """
        try:
            form_data = await request.form()
            call_sid = form_data.get('CallSid')
            call_status = form_data.get('CallStatus')
            call_duration = form_data.get('CallDuration')
            
            logger.info(f"Call status update: {call_sid} status: {call_status} duration: {call_duration}s")
            
            # Handle call completion/termination
            if call_status in ['completed', 'busy', 'failed', 'no-answer', 'canceled']:
                await self._handle_call_termination(call_sid, call_status, call_duration)
            
            return ""  # Status webhooks don't need TwiML response
            
        except Exception as e:
            logger.error(f"Error handling call status: {str(e)}")
            return ""
    
    async def handle_recording_completed(self, request: Request) -> str:
        """
        Handle completed recording webhook from Twilio.
        
        Processes the recording and continues conversation flow.
        
        Args:
            request (Request): FastAPI request with recording data
            
        Returns:
            str: TwiML response for continuing conversation
        """
        try:
            form_data = await request.form()
            call_sid = form_data.get('CallSid')
            recording_sid = form_data.get('RecordingSid')
            recording_url = form_data.get('RecordingUrl')
            recording_duration = form_data.get('RecordingDuration')
            
            logger.info(f"Recording completed for call {call_sid}: {recording_sid} duration: {recording_duration}s")
            
            # Process the recording through speech-to-text
            if recording_url:
                # This will be handled by handle_speech_input, so just acknowledge
                logger.info(f"Recording {recording_sid} ready for processing")
            
            return ""  # Recording completion doesn't need immediate TwiML response
            
        except Exception as e:
            logger.error(f"Error handling recording completion: {str(e)}")
            return ""
    
    def _create_greeting_response(self, call_sid: str) -> VoiceResponse:
        """
        Create initial greeting TwiML response for new calls.
        
        Args:
            call_sid (str): Twilio call identifier
            
        Returns:
            VoiceResponse: TwiML response with greeting and speech gathering
        """
        response = VoiceResponse()
        
        # Start call recording for quality and debugging
        response.record(
            action=f'/voice/recording-complete',
            method='POST',
            max_length=300,  # 5 minutes max recording
            play_beep=False,
            trim='do-not-trim'
        )
        
        # Greeting message with speech gathering
        gather = Gather(
            input='speech',
            action='/voice/speech',
            method='POST',
            speech_timeout='auto',
            language='en-US',
            enhanced=True,
            speech_model='experimental_conversations'
        )
        
        gather.say(
            "Hello! Welcome to Tony's Pizza. I'm your AI assistant and I'm ready to take your order. "
            "You can tell me what you'd like, and I'll help you place your order. What can I get for you today?",
            voice='alice',
            language='en-US'
        )
        
        response.append(gather)
        
        # Fallback if no speech detected
        response.say(
            "I didn't hear anything. Please call back when you're ready to order. Goodbye!",
            voice='alice',
            language='en-US'
        )
        response.hangup()
        
        return response
    
    async def _create_agent_response(self, call_sid: str, message: str, state: OrderState) -> VoiceResponse:
        """
        Create TwiML response based on agent message and current state.
        
        Args:
            call_sid (str): Twilio call identifier
            message (str): Agent's response message
            state (OrderState): Current conversation state
            
        Returns:
            VoiceResponse: TwiML response for continuing conversation
        """
        response = VoiceResponse()
        current_state = state.get('current_state', 'greeting')
        
        # Convert text to speech if needed
        audio_url = await speech_processor.text_to_speech(message)
        
        if current_state == 'complete':
            # Order complete - thank customer and hang up
            if audio_url:
                response.play(audio_url)
            else:
                response.say(message, voice='alice', language='en-US')
            response.hangup()
            
        elif current_state == 'error':
            # Error state - offer retry or hang up
            if audio_url:
                response.play(audio_url)
            else:
                response.say(message, voice='alice', language='en-US')
            
            gather = Gather(
                input='speech',
                action='/voice/speech',
                method='POST',
                speech_timeout='auto',
                language='en-US',
                enhanced=True,
                speech_model='experimental_conversations'
            )
            gather.say(
                "Would you like to try again or would you prefer to call back later?",
                voice='alice',
                language='en-US'
            )
            response.append(gather)
            
            response.say("Okay, please call back when you're ready. Goodbye!", voice='alice', language='en-US')
            response.hangup()
            
        else:
            # Continue conversation - play message and gather next input
            gather = Gather(
                input='speech',
                action='/voice/speech',
                method='POST',
                speech_timeout='auto',
                language='en-US',
                enhanced=True,
                speech_model='experimental_conversations',
                timeout=30
            )
            
            if audio_url:
                gather.play(audio_url)
            else:
                gather.say(message, voice='alice', language='en-US')
            
            response.append(gather)
            
            # Timeout fallback
            response.say(
                "I didn't hear a response. Please call back when you're ready to continue your order. Goodbye!",
                voice='alice',
                language='en-US'
            )
            response.hangup()
        
        return response
    
    def _create_busy_response(self) -> str:
        """Create TwiML response for when system is at capacity."""
        response = VoiceResponse()
        response.say(
            "Thank you for calling Tony's Pizza. We're currently experiencing high call volume. "
            "Please try calling back in a few minutes. You can also visit our website to place an order online. "
            "Thank you for your patience!",
            voice='alice',
            language='en-US'
        )
        response.hangup()
        return str(response)
    
    def _create_error_response(self) -> str:
        """Create TwiML response for system errors."""
        response = VoiceResponse()
        response.say(
            "I'm sorry, we're experiencing technical difficulties. "
            "Please try calling back in a few minutes or visit our website to place your order. "
            "Thank you for your patience!",
            voice='alice',
            language='en-US'
        )
        response.hangup()
        return str(response)
    
    def _create_no_input_response(self, call_sid: str) -> str:
        """Create TwiML response when no speech input is detected."""
        response = VoiceResponse()
        
        gather = Gather(
            input='speech',
            action='/voice/speech',
            method='POST',
            speech_timeout='auto',
            language='en-US',
            enhanced=True,
            speech_model='experimental_conversations'
        )
        
        gather.say(
            "I'm sorry, I didn't catch that. Could you please repeat what you'd like to order?",
            voice='alice',
            language='en-US'
        )
        
        response.append(gather)
        
        response.say(
            "I'm having trouble hearing you. Please call back with a better connection. Goodbye!",
            voice='alice',
            language='en-US'
        )
        response.hangup()
        
        return str(response)
    
    async def _store_call_state(self, call_sid: str, state: OrderState) -> None:
        """
        Store call state in Redis for session management.
        
        Args:
            call_sid (str): Twilio call identifier
            state (OrderState): Current state to store
        """
        try:
            redis_client = await get_redis_async()
            state_key = f"call_state:{call_sid}"
            
            # Store state with 30-minute expiration  
            with redis_client.get_connection() as conn:
                conn.setex(
                    state_key,
                    settings.session_timeout_minutes * 60,
                    str(state)  # Will be properly serialized in production
                )
            
            logger.debug(f"Stored state for call {call_sid}")
            
        except Exception as e:
            logger.error(f"Failed to store call state for {call_sid}: {str(e)}")
    
    async def _get_call_state(self, call_sid: str) -> Optional[OrderState]:
        """
        Retrieve call state from Redis.
        
        Args:
            call_sid (str): Twilio call identifier
            
        Returns:
            OrderState: Retrieved state or None if not found
        """
        try:
            redis_client = await get_redis_async()
            state_key = f"call_state:{call_sid}"
            
            with redis_client.get_connection() as conn:
                state_data = conn.get(state_key)
                if state_data:
                    # Parse state data (will use proper JSON serialization in production)
                    return eval(state_data)  # Temporary - will implement proper JSON handling
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to retrieve call state for {call_sid}: {str(e)}")
            return None
    
    async def _handle_call_termination(self, call_sid: str, call_status: str, call_duration: Optional[str]) -> None:
        """
        Handle call termination and cleanup.
        
        Args:
            call_sid (str): Twilio call identifier
            call_status (str): Final call status
            call_duration (str): Call duration in seconds
        """
        try:
            # Get final state for logging
            final_state = await self._get_call_state(call_sid)
            
            # Clean up session
            await session_manager.end_session(call_sid)
            
            # Log call completion
            logger.info(f"Call {call_sid} terminated: status={call_status}, duration={call_duration}s")
            
            if final_state:
                order_status = final_state.get('current_state', 'unknown')
                logger.info(f"Call {call_sid} final state: {order_status}")
                
                # If order was completed, ensure it's saved to database
                if order_status == 'complete' and 'ticket_id' in final_state:
                    logger.info(f"Order completed successfully: {final_state['ticket_id']}")
            
            # Clean up Redis state
            redis_client = await get_redis_async()
            with redis_client.get_connection() as conn:
                conn.delete(f"call_state:{call_sid}")
            
        except Exception as e:
            logger.error(f"Error handling call termination for {call_sid}: {str(e)}")


# Create global handler instance
twilio_handler = TwilioHandler()


# FastAPI route functions (to be imported by main application)
async def handle_incoming_call_webhook(request: Request) -> str:
    """FastAPI route handler for incoming call webhooks."""
    return await twilio_handler.handle_incoming_call(request)


async def handle_speech_webhook(request: Request) -> str:
    """FastAPI route handler for speech input webhooks."""
    return await twilio_handler.handle_speech_input(request)


async def handle_status_webhook(request: Request) -> str:
    """FastAPI route handler for call status webhooks."""
    return await twilio_handler.handle_call_status(request)


async def handle_recording_webhook(request: Request) -> str:
    """FastAPI route handler for recording completion webhooks."""
    return await twilio_handler.handle_recording_completed(request)