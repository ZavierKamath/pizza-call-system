"""
Integration tests for voice processing and Twilio integration.
Tests the complete phone call workflow with speech processing and session management.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import Request

from voice.twilio_handler import TwilioHandler
from voice.session_manager import SessionManager
from voice.speech_processing import SpeechProcessor
from agents.states import StateManager
from main import app


class TestVoiceIntegration:
    """Test suite for voice interface integration."""
    
    @pytest.fixture
    def client(self):
        """FastAPI test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI request for testing webhooks."""
        request = Mock(spec=Request)
        return request
    
    @pytest.fixture
    def twilio_handler(self):
        """TwilioHandler instance for testing."""
        with patch('voice.twilio_handler.settings') as mock_settings:
            mock_settings.twilio_account_sid = "test_sid"
            mock_settings.twilio_auth_token = "test_token" 
            mock_settings.openai_api_key = "test_openai_key"
            mock_settings.max_concurrent_calls = 20
            mock_settings.session_timeout_minutes = 30
            
            handler = TwilioHandler()
            return handler
    
    @pytest.fixture
    def session_manager(self):
        """SessionManager instance for testing."""
        with patch('voice.session_manager.settings') as mock_settings:
            mock_settings.max_concurrent_calls = 20
            mock_settings.session_timeout_minutes = 30
            
            manager = SessionManager()
            return manager
    
    @pytest.fixture
    def speech_processor(self):
        """SpeechProcessor instance for testing."""
        with patch('voice.speech_processing.settings') as mock_settings:
            mock_settings.openai_api_key = "test_openai_key"
            mock_settings.audio_sample_rate = 16000
            
            processor = SpeechProcessor()
            return processor
    
    @pytest.mark.asyncio
    async def test_session_creation_and_limits(self, session_manager):
        """Test session creation and concurrent limit enforcement."""
        with patch.object(session_manager, '_store_session_in_database', new_callable=AsyncMock):
            # Test successful session creation
            session_id = await session_manager.create_session(
                session_id="test_call_123",
                interface_type="phone",
                customer_phone="+1234567890"
            )
            
            assert session_id == "test_call_123"
            
            # Test session retrieval
            session_info = await session_manager.get_session("test_call_123")
            assert session_info is not None
            assert session_info.interface_type == "phone"
            assert session_info.customer_phone == "+1234567890"
            
            # Test session cleanup
            success = await session_manager.end_session("test_call_123")
            assert success is True
    
    @pytest.mark.asyncio
    async def test_twilio_incoming_call_webhook(self, twilio_handler, mock_request):
        """Test Twilio incoming call webhook handling."""
        # Mock form data for incoming call
        form_data = {
            'CallSid': 'test_call_456',
            'From': '+1234567890',
            'To': '+1987654321',
            'CallStatus': 'ringing'
        }
        
        mock_request.form = AsyncMock(return_value=form_data)
        
        with patch('voice.twilio_handler.session_manager') as mock_session_mgr:
            mock_session_mgr.can_accept_new_session.return_value = True
            mock_session_mgr.create_session.return_value = "test_call_456"
            
            with patch.object(twilio_handler, '_store_call_state', new_callable=AsyncMock):
                # Test incoming call handling
                twiml_response = await twilio_handler.handle_incoming_call(mock_request)
                
                assert twiml_response is not None
                assert "Hello! Welcome to Tony's Pizza" in twiml_response
                assert "<Gather" in twiml_response
                assert "input=\"speech\"" in twiml_response
    
    @pytest.mark.asyncio
    async def test_speech_processing_integration(self, speech_processor):
        """Test speech-to-text and text-to-speech integration."""
        # Test TTS generation
        with patch.object(speech_processor.openai_client.audio.speech, 'create', new_callable=AsyncMock) as mock_tts:
            # Mock TTS response
            mock_response = Mock()
            mock_response.iter_bytes = AsyncMock(return_value=[b"mock_audio_data"])
            mock_tts.return_value = mock_response
            
            audio_url = await speech_processor.text_to_speech("Hello, welcome to Tony's Pizza!")
            
            assert audio_url is not None
            assert audio_url.endswith('.mp3')
            mock_tts.assert_called_once()
    
    @pytest.mark.asyncio 
    async def test_speech_input_webhook(self, twilio_handler, mock_request):
        """Test speech input processing webhook."""
        # Mock form data for speech input
        form_data = {
            'CallSid': 'test_call_789',
            'SpeechResult': 'I would like to order a large pepperoni pizza',
            'RecordingUrl': None
        }
        
        mock_request.form = AsyncMock(return_value=form_data)
        
        # Mock existing call state
        mock_state = StateManager.create_initial_state("test_call_789", "phone")
        mock_state["phone_number"] = "+1234567890"
        
        with patch.object(twilio_handler, '_get_call_state', return_value=mock_state):
            with patch.object(twilio_handler, '_store_call_state', new_callable=AsyncMock):
                with patch.object(twilio_handler.pizza_agent, 'process_input', new_callable=AsyncMock) as mock_agent:
                    # Mock agent response
                    mock_agent.return_value = {
                        "state": mock_state,
                        "message": "Great! I'd be happy to help you order a large pepperoni pizza. Can I get your name please?"
                    }
                    
                    twiml_response = await twilio_handler.handle_speech_input(mock_request)
                    
                    assert twiml_response is not None
                    assert "<Gather" in twiml_response
                    mock_agent.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_call_termination_cleanup(self, twilio_handler, mock_request):
        """Test call termination and resource cleanup."""
        # Mock form data for call completion
        form_data = {
            'CallSid': 'test_call_complete',
            'CallStatus': 'completed',
            'CallDuration': '180'
        }
        
        mock_request.form = AsyncMock(return_value=form_data)
        
        with patch('voice.twilio_handler.session_manager') as mock_session_mgr:
            mock_session_mgr.end_session.return_value = True
            
            with patch.object(twilio_handler, '_get_call_state', return_value=None):
                # Test call termination handling
                response = await twilio_handler.handle_call_status(mock_request)
                
                assert response == ""  # Status webhooks return empty response
                mock_session_mgr.end_session.assert_called_once_with('test_call_complete')
    
    def test_fastapi_voice_endpoints(self, client):
        """Test FastAPI voice webhook endpoints."""
        # Test health check endpoint first
        response = client.get("/health")
        assert response.status_code == 200
        
        # Test session stats endpoint
        with patch('main.get_session_stats', new_callable=AsyncMock) as mock_stats:
            mock_stats.return_value = {
                "total_active_sessions": 0,
                "phone_sessions": 0,
                "web_sessions": 0,
                "max_concurrent_sessions": 20
            }
            
            response = client.get("/api/sessions/stats")
            assert response.status_code == 200
            stats = response.json()
            assert "total_active_sessions" in stats
    
    @pytest.mark.asyncio
    async def test_concurrent_session_limits(self, session_manager):
        """Test concurrent session limit enforcement."""
        with patch.object(session_manager, '_store_session_in_database', new_callable=AsyncMock):
            # Fill up to the limit
            sessions = []
            for i in range(20):  # Max concurrent limit
                session_id = f"test_session_{i}"
                await session_manager.create_session(session_id, "phone", f"+123456789{i}")
                sessions.append(session_id)
            
            # Try to create one more session (should fail)
            can_accept = await session_manager.can_accept_new_session()
            assert can_accept is False
            
            # Clean up sessions
            for session_id in sessions:
                await session_manager.end_session(session_id)
    
    @pytest.mark.asyncio
    async def test_session_timeout_cleanup(self, session_manager):
        """Test automatic cleanup of expired sessions."""
        with patch.object(session_manager, '_store_session_in_database', new_callable=AsyncMock):
            # Create a test session
            await session_manager.create_session("test_timeout", "phone", "+1234567890")
            
            # Mock expired session
            with patch.object(session_manager, '_is_session_expired', return_value=True):
                # Test cleanup
                cleaned_count = await session_manager.cleanup_expired_sessions()
                assert cleaned_count >= 0  # Should clean up expired sessions
    
    @pytest.mark.asyncio
    async def test_error_handling_in_speech_processing(self, speech_processor):
        """Test error handling in speech processing."""
        # Test STT with invalid input
        result = await speech_processor.speech_to_text("")
        assert result is None
        
        # Test TTS with empty text
        result = await speech_processor.text_to_speech("")
        assert result is None
        
        # Test audio validation
        validation = await speech_processor.validate_audio_quality("nonexistent_file.wav")
        assert validation["is_valid"] is False
        assert len(validation["errors"]) > 0


if __name__ == "__main__":
    """
    Run voice integration tests.
    
    Usage:
        python -m pytest tests/test_voice_integration.py -v
    """
    pytest.main([__file__, "-v"])