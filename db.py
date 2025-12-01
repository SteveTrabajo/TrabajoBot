"""
db.py
=====
Provides a Database connection pool for CockroachDB using psycopg2.
Implements efficient connection pooling with automatic cleanup and retry logic.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool, Error
from dotenv import load_dotenv
import logging
import threading
from contextlib import contextmanager
from typing import Optional, Dict, List, Any

logger = logging.getLogger("TrabajoBot")

load_dotenv()


class Database:
    """
    Database connection pool manager for CockroachDB.
    Provides thread-safe connection pooling with automatic cleanup.
    """
    
    _instance: Optional['Database'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Ensure singleton pattern for Database"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize connection pool (runs only once)"""
        if self._initialized:
            return
            
        self.host = os.getenv("DB_HOST")
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASS")
        self.database = os.getenv("DB_NAME")
        self.port = int(os.getenv("DB_PORT", 26257))
        
        # Connection pool parameters
        self.min_connections = 2
        self.max_connections = 10
        
        logger.info("Initializing database connection pool...")
        
        try:
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                self.min_connections,
                self.max_connections,
                host=self.host,
                user=self.user,
                password=self.password,
                dbname=self.database,
                port=self.port,
                sslmode='require',
                connect_timeout=10
            )
            logger.info(f"Connection pool created: {self.min_connections}-{self.max_connections} connections")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            self.connection_pool = None
            self._initialized = True
            raise

    @contextmanager
    def get_connection(self):
        """
        Context manager for getting a connection from the pool.
        Automatically returns connection to pool and handles cleanup.
        """
        if not self.connection_pool:
            raise Exception("Connection pool not initialized")
        
        conn = None
        try:
            conn = self.connection_pool.getconn()
            # Ensure connection is in autocommit mode off (for explicit transaction control)
            conn.autocommit = False
            # Reset connection state
            conn.rollback()
            yield conn
        except Error as e:
            logger.error(f"Database error: {e}")
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise
        finally:
            if conn:
                try:
                    # Clean up any pending transaction
                    if not conn.closed:
                        conn.rollback()
                        self.connection_pool.putconn(conn)
                except Exception as e:
                    logger.error(f"Error returning connection to pool: {e}")
                    # Connection is broken, close it
                    try:
                        conn.close()
                    except:
                        pass

    def execute(self, query: str, params: tuple = None, commit: bool = False) -> Optional[Any]:
        """
        Execute a query with automatic connection management.
        
        Args:
            query: SQL query to execute
            params: Query parameters (default: None)
            commit: Whether to commit after execution (default: False)
        
        Returns:
            Cursor object for result fetching
        """
        if not query:
            logger.error("Query is empty")
            return None
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                try:
                    logger.debug(f"Executing query: {query} | params: {params}")
                    cursor.execute(query, params or ())
                    
                    if commit:
                        conn.commit()
                        logger.debug("Query committed successfully")
                    
                    return cursor
                except Exception as e:
                    logger.error(f"Query execution failed: {e}")
                    raise
        except Exception as e:
            logger.error(f"Database operation failed: {e}")
            return None

    def fetchone(self, cursor) -> Optional[Dict]:
        """Fetch one row from cursor"""
        if cursor is None:
            return None
        try:
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error fetching one row: {e}")
            return None

    def fetchall(self, cursor) -> List[Dict]:
        """Fetch all rows from cursor"""
        if cursor is None:
            return []
        try:
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error fetching all rows: {e}")
            return []

    def execute_transaction(self, queries: List[tuple]) -> bool:
        """
        Execute multiple queries in a single transaction.
        
        Args:
            queries: List of (query, params) tuples
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                try:
                    for query, params in queries:
                        logger.debug(f"Executing: {query} | params: {params}")
                        cursor.execute(query, params or ())
                    
                    conn.commit()
                    logger.debug(f"Transaction with {len(queries)} queries committed successfully")
                    return True
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Transaction failed, rolled back: {e}")
                    raise
        except Exception as e:
            logger.error(f"Transaction execution failed: {e}")
            return False

    def ensure_table_exists(self, table_name: str, creation_query: str) -> bool:
        """
        Ensures the specified table exists in the database.
        
        Args:
            table_name: Name of the table to check
            creation_query: SQL query to create the table if it doesn't exist
        
        Returns:
            True if table exists or was created, False otherwise
        """
        try:
            check_query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = %s
            );
            """
            
            cursor = self.execute(check_query, (table_name,))
            result = self.fetchone(cursor)
            
            if result and result.get("exists"):
                logger.info(f"Table '{table_name}' already exists.")
                return True
            
            # Table doesn't exist, create it
            logger.info(f"Table '{table_name}' does not exist. Creating...")
            self.execute(creation_query, commit=True)
            logger.info(f"Table '{table_name}' created successfully.")
            return True
            
        except Exception as e:
            logger.error(f"Error ensuring table exists: {e}")
            return False

    def close_pool(self):
        """Close all connections in the pool"""
        if self.connection_pool:
            try:
                self.connection_pool.closeall()
                logger.info("Connection pool closed")
            except Exception as e:
                logger.error(f"Error closing connection pool: {e}")

    def __del__(self):
        """Cleanup on object destruction"""
        self.close_pool()


# Singleton instance
_db_instance = None

def get_database() -> Database:
    """Get the singleton database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
