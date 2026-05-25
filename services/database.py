"""
Database service module for MySQL connection management.
Provides centralized database connection handling for the application.
"""

import mysql.connector as mysql
import logging
from typing import Optional

# Import config from parent directory
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config

logger = logging.getLogger(__name__)

# Global database connection
db_connection = None

def get_db_connection():
    """Get MySQL connection for DX spots"""
    global db_connection
    try:
        if db_connection is None or not db_connection.is_connected():
            db_connection = mysql.connect(
                host=config.DB_HOST,
                port=config.DB_PORT,
                user=config.DB_USER,
                password=config.DB_PASS,
                database=config.DB_NAME
            )
        return db_connection
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None
