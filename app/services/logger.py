"""
Centralized logging module for WhatsApp Calendar Bot
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.getcwd(), 'logs')
os.makedirs(logs_dir, exist_ok=True)

# Configure root logger
root_logger = logging.getLogger()
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
root_logger.setLevel(getattr(logging, log_level))

# Create console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_format)
root_logger.addHandler(console_handler)

# Create file handler for all logs
all_log_file = os.path.join(logs_dir, 'calendar_bot.log')
file_handler = RotatingFileHandler(all_log_file, maxBytes=10485760, backupCount=10)  # 10MB files, 10 backups max
file_handler.setLevel(logging.INFO)
file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_format)
root_logger.addHandler(file_handler)

# Create file handler for errors only
error_log_file = os.path.join(logs_dir, 'errors.log')
error_file_handler = RotatingFileHandler(error_log_file, maxBytes=10485760, backupCount=10)
error_file_handler.setLevel(logging.ERROR)
error_file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(pathname)s:%(lineno)d')
error_file_handler.setFormatter(error_file_format)
root_logger.addHandler(error_file_handler)

def get_logger(name):
    """Get a logger instance with the given name"""
    return logging.getLogger(name)

# Service-specific loggers
class ServiceLogger:
    """Logger for service-specific logs with context enrichment"""
    
    def __init__(self, service_name):
        self.logger = logging.getLogger(f"service.{service_name}")
        self.service_name = service_name
    
    def info(self, message, context=None):
        """Log info message with optional context"""
        if context:
            self.logger.info(f"{message} - context: {context}")
        else:
            self.logger.info(message)
    
    def error(self, message, error=None, context=None):
        """Log error message with exception details and optional context"""
        if error:
            if context:
                self.logger.error(f"{message}: {error} - context: {context}", exc_info=True)
            else:
                self.logger.error(f"{message}: {error}", exc_info=True)
        else:
            if context:
                self.logger.error(f"{message} - context: {context}")
            else:
                self.logger.error(message)
    
    def warning(self, message, context=None):
        """Log warning message with optional context"""
        if context:
            self.logger.warning(f"{message} - context: {context}")
        else:
            self.logger.warning(message)
    
    def debug(self, message, context=None):
        """Log debug message with optional context"""
        if context:
            self.logger.debug(f"{message} - context: {context}")
        else:
            self.logger.debug(message)
    
    def critical(self, message, error=None, context=None):
        """Log critical message with exception details and optional context"""
        if error:
            if context:
                self.logger.critical(f"{message}: {error} - context: {context}", exc_info=True)
            else:
                self.logger.critical(f"{message}: {error}", exc_info=True)
        else:
            if context:
                self.logger.critical(f"{message} - context: {context}")
            else:
                self.logger.critical(message)
                
# Create common service loggers
calendar_logger = ServiceLogger('google_calendar')
whatsapp_logger = ServiceLogger('whatsapp')
nlp_logger = ServiceLogger('nlp')
db_logger = ServiceLogger('database')
auth_logger = ServiceLogger('auth')
task_logger = ServiceLogger('task')