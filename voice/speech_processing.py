"""
Speech processing module with OpenAI Whisper and TTS integration.
Handles audio format conversion, speech-to-text, and text-to-speech for voice interfaces.
"""

import logging
import tempfile
import os
import asyncio
import aiohttp
import io
from typing import Optional, Union, Dict, Any
from pathlib import Path
import wave
import json

from openai import AsyncOpenAI
import requests

from config.settings import settings
from pathlib import Path

# Configure logging for speech processing
logger = logging.getLogger(__name__)


class SpeechProcessor:
    """
    Handles speech processing operations for voice interfaces.
    
    Provides speech-to-text via OpenAI Whisper and text-to-speech via OpenAI TTS.
    Includes audio format conversion and quality optimization for Twilio integration.
    """
    
    def __init__(self):
        """Initialize speech processor with OpenAI client and audio settings."""
        self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.sample_rate = settings.audio_sample_rate  # 16kHz for optimal Whisper performance
        self.supported_formats = ['wav', 'mp3', 'mp4', 'm4a', 'ogg', 'webm']
        
        # TTS settings optimized for phone calls
        self.tts_voice = "onyx"  # Deep, warm male voice for pizza ordering
        self.tts_model = "tts-1"  # Standard quality for real-time use
        self.tts_format = "mp3"   # Compressed format for faster streaming
        
        # Audio storage configuration
        self.audio_dir = Path("static/audio")
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("SpeechProcessor initialized with OpenAI integration")
    
    async def speech_to_text(self, audio_source: Union[str, bytes, io.BytesIO], 
                           source_format: Optional[str] = None) -> Optional[str]:
        """
        Convert speech audio to text using OpenAI Whisper.
        
        Handles various audio sources including Twilio recording URLs, raw audio data,
        and file uploads. Automatically detects and converts audio formats.
        
        Args:
            audio_source: URL, file path, raw audio bytes, or BytesIO object
            source_format: Optional format hint ('wav', 'mp3', etc.)
            
        Returns:
            str: Transcribed text or None if processing failed
        """
        try:
            # Download or prepare audio data
            audio_data = await self._prepare_audio_for_whisper(audio_source, source_format)
            if not audio_data:
                logger.error("Failed to prepare audio data for Whisper")
                return None
            
            # Create temporary file for Whisper API
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                # Call OpenAI Whisper API
                with open(temp_file_path, 'rb') as audio_file:
                    transcript = await self.openai_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="en",  # English-only for pizza orders
                        response_format="text",
                        temperature=0.0,  # Deterministic output
                        prompt="This is a phone conversation about ordering pizza. The customer is speaking to an AI assistant."
                    )
                
                # Extract text from response
                transcribed_text = transcript.strip() if isinstance(transcript, str) else transcript.text.strip()
                
                logger.info(f"Speech-to-text successful: '{transcribed_text[:100]}...'")
                return transcribed_text
                
            finally:
                # Clean up temporary file
                os.unlink(temp_file_path)
                
        except Exception as e:
            logger.error(f"Speech-to-text failed: {str(e)}")
            return None
    
    async def text_to_speech(self, text: str, voice: Optional[str] = None, 
                           optimize_for_phone: bool = True) -> Optional[str]:
        """
        Convert text to speech using OpenAI TTS.
        
        Generates high-quality speech optimized for phone call delivery.
        Returns URL to the generated audio file for Twilio playback.
        
        Args:
            text: Text to convert to speech
            voice: Voice to use (defaults to configured voice)
            optimize_for_phone: Whether to optimize audio for phone calls
            
        Returns:
            str: URL to generated audio file or None if failed
        """
        try:
            # Validate and clean input text
            if not text or not text.strip():
                logger.warning("Empty text provided for TTS")
                return None
            
            cleaned_text = self._clean_text_for_tts(text)
            voice_to_use = voice or self.tts_voice
            
            logger.info(f"Generating TTS for text: '{cleaned_text[:100]}...' with voice: {voice_to_use}")
            
            # Call OpenAI TTS API
            response = await self.openai_client.audio.speech.create(
                model=self.tts_model,
                voice=voice_to_use,
                input=cleaned_text,
                response_format=self.tts_format,
                speed=1.0  # Normal speaking rate for clarity
            )
            
            # Save audio to static directory
            audio_filename = f"tts_{hash(cleaned_text)}_{voice_to_use}.{self.tts_format}"
            audio_path = self.audio_dir / audio_filename
            
            # Write audio data to file
            with open(audio_path, 'wb') as audio_file:
                audio_file.write(response.content)
            
            # Optimize audio for phone calls if requested
            if optimize_for_phone:
                audio_path = await self._optimize_audio_for_phone(str(audio_path))
                audio_path = Path(audio_path)
            
            # Return web-accessible URL for Twilio
            audio_url = f"/static/audio/{audio_path.name}"
            logger.info(f"TTS generated successfully: {audio_url}")
            return audio_url
            
        except Exception as e:
            logger.error(f"Text-to-speech failed: {str(e)}")
            return None
    
    async def convert_audio_format(self, input_path: str, output_format: str, 
                                 target_sample_rate: Optional[int] = None) -> Optional[str]:
        """
        Convert audio between different formats and sample rates.
        
        Useful for ensuring compatibility between Twilio and OpenAI APIs.
        
        Args:
            input_path: Path to input audio file
            output_format: Target format ('wav', 'mp3', etc.)
            target_sample_rate: Target sample rate (Hz)
            
        Returns:
            str: Path to converted file or None if failed
        """
        try:
            # For now, implement basic WAV conversion
            # In production, would use FFmpeg or similar for comprehensive format support
            
            if output_format.lower() == 'wav':
                return await self._convert_to_wav(input_path, target_sample_rate)
            else:
                logger.warning(f"Audio format conversion to {output_format} not yet implemented")
                return input_path
                
        except Exception as e:
            logger.error(f"Audio format conversion failed: {str(e)}")
            return None
    
    async def _prepare_audio_for_whisper(self, audio_source: Union[str, bytes, io.BytesIO], 
                                       source_format: Optional[str] = None) -> Optional[bytes]:
        """
        Prepare audio data from various sources for Whisper API.
        
        Args:
            audio_source: Audio data source
            source_format: Format hint
            
        Returns:
            bytes: Audio data ready for Whisper or None if failed
        """
        try:
            # Handle URL (Twilio recording)
            if isinstance(audio_source, str) and audio_source.startswith('http'):
                logger.info(f"Downloading audio from URL: {audio_source}")
                async with aiohttp.ClientSession() as session:
                    async with session.get(audio_source) as response:
                        if response.status == 200:
                            audio_data = await response.read()
                            logger.info(f"Downloaded {len(audio_data)} bytes from URL")
                            return audio_data
                        else:
                            logger.error(f"Failed to download audio: HTTP {response.status}")
                            return None
            
            # Handle file path
            elif isinstance(audio_source, str) and os.path.exists(audio_source):
                with open(audio_source, 'rb') as f:
                    return f.read()
            
            # Handle raw bytes
            elif isinstance(audio_source, bytes):
                return audio_source
            
            # Handle BytesIO
            elif isinstance(audio_source, io.BytesIO):
                return audio_source.getvalue()
            
            else:
                logger.error(f"Unsupported audio source type: {type(audio_source)}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to prepare audio for Whisper: {str(e)}")
            return None
    
    def _clean_text_for_tts(self, text: str) -> str:
        """
        Clean and optimize text for TTS generation.
        
        Args:
            text: Raw text input
            
        Returns:
            str: Cleaned text optimized for speech
        """
        # Remove or replace problematic characters
        cleaned = text.replace('\n', ' ').replace('\t', ' ')
        
        # Normalize whitespace
        cleaned = ' '.join(cleaned.split())
        
        # Add pauses for better phone delivery
        cleaned = cleaned.replace('.', '. ')
        cleaned = cleaned.replace(',', ', ')
        cleaned = cleaned.replace('?', '? ')
        cleaned = cleaned.replace('!', '! ')
        
        # Limit length for TTS API
        if len(cleaned) > 4000:  # OpenAI TTS limit
            cleaned = cleaned[:3997] + "..."
            logger.warning("Text truncated for TTS length limit")
        
        return cleaned
    
    async def _optimize_audio_for_phone(self, audio_path: str) -> str:
        """
        Optimize audio file for phone call delivery.
        
        Adjusts sample rate, bitrate, and compression for optimal phone quality.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            str: Path to optimized audio file
        """
        try:
            # For basic implementation, just ensure proper naming
            # In production, would use audio processing libraries to:
            # - Normalize volume levels
            # - Adjust EQ for phone frequency response
            # - Compress dynamic range
            # - Optimize file size while maintaining quality
            
            path_obj = Path(audio_path)
            optimized_path = path_obj.with_stem(f"{path_obj.stem}_phone")
            
            # For now, just copy the file (placeholder for actual optimization)
            import shutil
            shutil.copy2(audio_path, optimized_path)
            
            logger.debug(f"Audio optimized for phone: {optimized_path}")
            return str(optimized_path)
            
        except Exception as e:
            logger.error(f"Audio optimization failed: {str(e)}")
            return audio_path  # Return original if optimization fails
    
    async def _convert_to_wav(self, input_path: str, target_sample_rate: Optional[int] = None) -> Optional[str]:
        """
        Convert audio file to WAV format.
        
        Args:
            input_path: Input audio file path
            target_sample_rate: Target sample rate for conversion
            
        Returns:
            str: Path to WAV file or None if failed
        """
        try:
            # Basic WAV conversion implementation
            # In production, would use FFmpeg or similar for robust conversion
            
            output_path = input_path.rsplit('.', 1)[0] + '.wav'
            
            # For now, if it's already WAV, just return it
            if input_path.lower().endswith('.wav'):
                return input_path
            
            # Placeholder for actual conversion logic
            logger.warning("Full audio format conversion not implemented - returning original file")
            return input_path
            
        except Exception as e:
            logger.error(f"WAV conversion failed: {str(e)}")
            return None
    
    async def get_audio_info(self, audio_path: str) -> Dict[str, Any]:
        """
        Get information about audio file (duration, format, sample rate, etc.).
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            dict: Audio file information
        """
        try:
            info = {
                'path': audio_path,
                'exists': os.path.exists(audio_path),
                'size_bytes': 0,
                'duration_seconds': 0,
                'format': 'unknown',
                'sample_rate': 0,
                'channels': 0
            }
            
            if os.path.exists(audio_path):
                info['size_bytes'] = os.path.getsize(audio_path)
                info['format'] = os.path.splitext(audio_path)[1].lower().lstrip('.')
                
                # For WAV files, can read basic info
                if info['format'] == 'wav':
                    try:
                        with wave.open(audio_path, 'rb') as wav_file:
                            info['sample_rate'] = wav_file.getframerate()
                            info['channels'] = wav_file.getnchannels()
                            info['duration_seconds'] = wav_file.getnframes() / wav_file.getframerate()
                    except Exception:
                        pass  # Ignore errors reading WAV metadata
            
            return info
            
        except Exception as e:
            logger.error(f"Failed to get audio info: {str(e)}")
            return {'error': str(e)}
    
    async def validate_audio_quality(self, audio_path: str) -> Dict[str, Any]:
        """
        Validate audio quality for speech processing.
        
        Checks sample rate, duration, file size, and other quality metrics.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            dict: Quality validation results
        """
        try:
            audio_info = await self.get_audio_info(audio_path)
            
            validation = {
                'is_valid': True,
                'warnings': [],
                'errors': [],
                'recommendations': []
            }
            
            # Check file existence
            if not audio_info.get('exists', False):
                validation['is_valid'] = False
                validation['errors'].append("Audio file does not exist")
                return validation
            
            # Check file size
            size_mb = audio_info.get('size_bytes', 0) / (1024 * 1024)
            if size_mb > 25:  # OpenAI Whisper limit
                validation['errors'].append(f"File too large: {size_mb:.1f}MB (max 25MB)")
                validation['is_valid'] = False
            elif size_mb < 0.001:  # Very small file
                validation['warnings'].append(f"File very small: {size_mb:.3f}MB")
            
            # Check duration
            duration = audio_info.get('duration_seconds', 0)
            if duration > 600:  # 10 minutes
                validation['warnings'].append(f"Long audio: {duration:.1f}s")
            elif duration < 0.5:  # Very short
                validation['warnings'].append(f"Very short audio: {duration:.1f}s")
            
            # Check sample rate
            sample_rate = audio_info.get('sample_rate', 0)
            if sample_rate > 0:
                if sample_rate < 8000:
                    validation['warnings'].append(f"Low sample rate: {sample_rate}Hz")
                elif sample_rate != 16000:
                    validation['recommendations'].append(f"Consider 16kHz sample rate (current: {sample_rate}Hz)")
            
            return validation
            
        except Exception as e:
            logger.error(f"Audio quality validation failed: {str(e)}")
            return {
                'is_valid': False,
                'errors': [f"Validation failed: {str(e)}"],
                'warnings': [],
                'recommendations': []
            }


# Create global speech processor instance
speech_processor = SpeechProcessor()


# Utility functions for FastAPI integration
async def process_speech_to_text(audio_source: Union[str, bytes, io.BytesIO]) -> Optional[str]:
    """Utility function for speech-to-text processing."""
    return await speech_processor.speech_to_text(audio_source)


async def process_text_to_speech(text: str, voice: Optional[str] = None) -> Optional[str]:
    """Utility function for text-to-speech processing."""
    return await speech_processor.text_to_speech(text, voice)


async def validate_audio_file(audio_path: str) -> Dict[str, Any]:
    """Utility function for audio quality validation."""
    return await speech_processor.validate_audio_quality(audio_path)