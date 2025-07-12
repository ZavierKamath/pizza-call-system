"""
Winston-style logging configuration for the pizza ordering system.
Provides structured logging with multiple levels, formatters, and handlers.
"""

import os
import logging
import logging.handlers
from datetime import datetime
from typing import Dict, Any
import json


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    
    Outputs log records in JSON format for easy parsing and analysis.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        
        Args:
            record (LogRecord): Log record to format
            
        Returns:
            str: JSON formatted log message
        """
        # Create base log entry
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields from log record
        extra_fields = {
            key: value for key, value in record.__dict__.items()
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                'thread', 'threadName', 'processName', 'process', 'message'
            }
        }
        
        if extra_fields:
            log_entry['extra'] = extra_fields
        
        return json.dumps(log_entry, default=str)


class DatabaseLoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter for database operations with context information.
    
    Adds database-specific context to log messages for better traceability.
    """
    
    def __init__(self, logger: logging.Logger, context: Dict[str, Any]):
        """
        Initialize adapter with database context.
        
        Args:
            logger (Logger): Base logger instance
            context (dict): Database context information
        """
        super().__init__(logger, context)
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """
        Process log message with database context.
        
        Args:
            msg (str): Log message
            kwargs (dict): Keyword arguments
            
        Returns:
            tuple: Processed message and kwargs
        """
        # Add database context to extra fields
        extra = kwargs.get('extra', {})
        extra.update(self.extra)
        kwargs['extra'] = extra
        
        return msg, kwargs


class LoggingManager:
    """
    Central logging management for the pizza ordering system.
    
    Configures and manages loggers with Winston-style functionality including
    multiple transports, log levels, and structured output.
    """
    
    def __init__(self):
        """Initialize logging manager with default configuration."""
        self.loggers: Dict[str, logging.Logger] = {}
        self.log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        self.log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        self.console_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        # Ensure log directory exists
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Configure root logger
        self._configure_root_logger()
    
    def _configure_root_logger(self) -> None:
        """Configure the root logger with handlers and formatters."""
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.log_level))
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # Console handler with colored output
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, self.log_level))
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # File handlers for different log levels
        self._add_file_handlers(root_logger)
    
    def _add_file_handlers(self, logger: logging.Logger) -> None:
        """
        Add file handlers for different log levels.
        
        Args:
            logger (Logger): Logger to add handlers to
        """
        # General application log (all levels)
        app_handler = logging.handlers.RotatingFileHandler(
            os.path.join(self.log_dir, 'pizza_agent.log'),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        app_handler.setLevel(logging.DEBUG)
        app_handler.setFormatter(JSONFormatter())
        logger.addHandler(app_handler)
        
        # Error log (errors only)
        error_handler = logging.handlers.RotatingFileHandler(
            os.path.join(self.log_dir, 'errors.log'),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JSONFormatter())
        logger.addHandler(error_handler)
        
        # Database operations log
        db_handler = logging.handlers.RotatingFileHandler(
            os.path.join(self.log_dir, 'database.log'),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        db_handler.setLevel(logging.DEBUG)
        db_handler.setFormatter(JSONFormatter())
        
        # Add filter to only log database-related messages
        db_handler.addFilter(lambda record: 'database' in record.name.lower())
        logger.addHandler(db_handler)
        
        # Session operations log
        session_handler = logging.handlers.RotatingFileHandler(
            os.path.join(self.log_dir, 'sessions.log'),
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3
        )
        session_handler.setLevel(logging.INFO)
        session_handler.setFormatter(JSONFormatter())
        
        # Add filter for session-related messages
        session_handler.addFilter(lambda record: 'session' in record.name.lower() or 'redis' in record.name.lower())
        logger.addHandler(session_handler)
    
    def get_logger(self, name: str, context: Dict[str, Any] = None) -> logging.Logger:
        """
        Get or create a logger with optional context.
        
        Args:
            name (str): Logger name
            context (dict): Optional context for database operations
            
        Returns:
            Logger: Configured logger instance
        """
        if name in self.loggers:
            return self.loggers[name]
        
        logger = logging.getLogger(name)
        
        # Add context adapter for database loggers
        if context and ('database' in name.lower() or 'redis' in name.lower()):
            adapter = DatabaseLoggerAdapter(logger, context)
            self.loggers[name] = adapter
            return adapter
        
        self.loggers[name] = logger
        return logger
    
    def get_database_logger(self, operation: str = None, table: str = None) -> DatabaseLoggerAdapter:
        """
        Get a database-specific logger with operation context.
        
        Args:
            operation (str): Database operation type (create, read, update, delete)
            table (str): Database table name
            
        Returns:
            DatabaseLoggerAdapter: Logger with database context
        """
        context = {}
        if operation:
            context['operation'] = operation
        if table:
            context['table'] = table
        
        logger = logging.getLogger('pizza_agent.database')
        return DatabaseLoggerAdapter(logger, context)
    
    def get_redis_logger(self, operation: str = None) -> DatabaseLoggerAdapter:
        """
        Get a Redis-specific logger with operation context.
        
        Args:
            operation (str): Redis operation type (session, cache, cleanup)
            
        Returns:
            DatabaseLoggerAdapter: Logger with Redis context
        """
        context = {}
        if operation:
            context['operation'] = operation
            context['service'] = 'redis'
        
        logger = logging.getLogger('pizza_agent.redis')
        return DatabaseLoggerAdapter(logger, context)
    
    def log_database_operation(self, operation: str, table: str, details: Dict[str, Any] = None, level: str = 'INFO') -> None:
        """
        Log database operation with structured data.
        
        Args:
            operation (str): Type of database operation
            table (str): Database table involved
            details (dict): Additional operation details
            level (str): Log level
        """
        logger = self.get_database_logger(operation, table)
        log_level = getattr(logging, level.upper())
        
        message = f"Database {operation} on {table}"
        extra = {
            'operation_type': 'database',
            'database_operation': operation,
            'table': table
        }
        
        if details:
            extra.update(details)
        
        logger.log(log_level, message, extra=extra)
    
    def log_session_operation(self, operation: str, session_id: str, details: Dict[str, Any] = None, level: str = 'INFO') -> None:
        """
        Log session operation with structured data.
        
        Args:
            operation (str): Type of session operation
            session_id (str): Session identifier
            details (dict): Additional operation details
            level (str): Log level
        """
        logger = self.get_redis_logger('session')
        log_level = getattr(logging, level.upper())
        
        message = f"Session {operation}: {session_id}"
        extra = {
            'operation_type': 'session',
            'session_operation': operation,
            'session_id': session_id
        }
        
        if details:
            extra.update(details)
        
        logger.log(log_level, message, extra=extra)
    
    def log_connection_status(self, service: str, status: str, details: Dict[str, Any] = None) -> None:
        """
        Log connection status changes.
        
        Args:
            service (str): Service name (database, redis)
            status (str): Connection status
            details (dict): Additional connection details
        """
        logger_name = f'pizza_agent.{service}'
        logger = self.get_logger(logger_name)
        
        message = f"{service.title()} connection {status}"
        extra = {
            'operation_type': 'connection',
            'service': service,
            'status': status
        }
        
        if details:
            extra.update(details)
        
        level = logging.INFO if status in ['connected', 'initialized'] else logging.WARNING
        logger.log(level, message, extra=extra)
    
    def set_log_level(self, level: str) -> None:
        """
        Change the log level for all loggers.
        
        Args:
            level (str): New log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        log_level = getattr(logging, level.upper())
        self.log_level = level.upper()
        
        # Update root logger
        logging.getLogger().setLevel(log_level)
        
        # Update all handlers
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setLevel(log_level)
    
    def get_log_stats(self) -> Dict[str, Any]:
        """
        Get logging statistics for monitoring.
        
        Returns:
            dict: Logging configuration and statistics
        """
        return {
            'log_level': self.log_level,
            'log_directory': self.log_dir,
            'active_loggers': list(self.loggers.keys()),
            'handlers_count': len(logging.getLogger().handlers),
            'log_files': [
                'pizza_agent.log',
                'errors.log',
                'database.log',
                'sessions.log'
            ]
        }


# Global logging manager instance
logging_manager = LoggingManager()


def get_logger(name: str, context: Dict[str, Any] = None) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Args:
        name (str): Logger name
        context (dict): Optional context for database operations
        
    Returns:
        Logger: Configured logger
    """
    return logging_manager.get_logger(name, context)


def get_database_logger(operation: str = None, table: str = None) -> DatabaseLoggerAdapter:
    """
    Get database logger with context.
    
    Args:
        operation (str): Database operation type
        table (str): Database table name
        
    Returns:
        DatabaseLoggerAdapter: Database logger with context
    """
    return logging_manager.get_database_logger(operation, table)


def get_redis_logger(operation: str = None) -> DatabaseLoggerAdapter:
    """
    Get Redis logger with context.
    
    Args:
        operation (str): Redis operation type
        
    Returns:
        DatabaseLoggerAdapter: Redis logger with context
    """
    return logging_manager.get_redis_logger(operation)


def log_database_operation(operation: str, table: str, details: Dict[str, Any] = None, level: str = 'INFO') -> None:
    """Log database operation with structured data."""
    logging_manager.log_database_operation(operation, table, details, level)


def log_session_operation(operation: str, session_id: str, details: Dict[str, Any] = None, level: str = 'INFO') -> None:
    """Log session operation with structured data."""
    logging_manager.log_session_operation(operation, session_id, details, level)


def log_connection_status(service: str, status: str, details: Dict[str, Any] = None) -> None:
    """Log connection status changes."""
    logging_manager.log_connection_status(service, status, details)