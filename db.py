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
from contextlib import contextmanager
from typing import Optional, List, Any

logger = logging.getLogger("TrabajoBot")

load_dotenv()


class Database:
    """
    Database connection pool manager for CockroachDB.
    Provides thread-safe connection pooling with automatic cleanup.
    Use get_database() instead of constructing this directly, so the
    whole bot shares one pool.
    """

    def __init__(self):
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
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            self.connection_pool = None
            raise

    @contextmanager
    def get_connection(self):
        """
        Context manager for getting a connection from the pool.

        The server (CockroachDB) closes idle connections, so a pooled connection
        may be dead by the time it's handed out. We probe each one on checkout and
        discard dead ones, and recycle broken connections on return, so callers
        never see a stale connection.
        """
        if not self.connection_pool:
            raise Exception("Connection pool not initialized")

        conn = self._checkout_live_connection()
        try:
            yield conn
        except Error as e:
            logger.error(f"Database error: {e}")
            raise
        finally:
            broken = conn.closed != 0
            try:
                if not broken:
                    conn.rollback()
            except Exception:
                broken = True
            try:
                self.connection_pool.putconn(conn, close=broken)
            except Exception as e:
                logger.error(f"Error returning connection to pool: {e}")

    def _checkout_live_connection(self, attempts: int = 5):
        """Get a connection from the pool, discarding any the server has already closed."""
        last_error = None
        for _ in range(attempts):
            conn = self.connection_pool.getconn()
            try:
                conn.autocommit = False
                conn.rollback()  # resets session state and fails fast if the connection is dead
                return conn
            except Exception as e:
                last_error = e
                logger.warning(f"Discarding stale database connection: {e}")
                try:
                    self.connection_pool.putconn(conn, close=True)
                except Exception:
                    pass
        raise Exception(f"Could not obtain a live database connection: {last_error}")

    def execute(self, query: str, params: tuple = None, commit: bool = False, fetch: str = None) -> Optional[Any]:
        """
        Execute a query with automatic connection management.

        Args:
            query: SQL query to execute
            params: Query parameters (default: None)
            commit: Whether to commit after execution (default: False)
            fetch: 'one' to return a single row dict, 'all' to return a list of row dicts,
                   None to return nothing (default: None)

        Returns:
            None, a single row dict, or a list of row dicts depending on fetch

        Raises:
            Exception: on database error
        """
        if not query:
            raise ValueError("Query cannot be empty")

        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            logger.debug(f"Executing query: {query} | params: {params}")
            cursor.execute(query, params or ())

            result = None
            if fetch == 'one':
                result = cursor.fetchone()
            elif fetch == 'all':
                result = cursor.fetchall() or []

            if commit:
                conn.commit()
                logger.debug("Query committed successfully")

            return result

    def execute_transaction(self, queries: List[tuple]) -> None:
        """
        Execute multiple queries in a single transaction.

        Args:
            queries: List of (query, params) tuples

        Raises:
            Exception: on database error (connection cleanup and rollback handled by get_connection)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            for query, params in queries:
                logger.debug(f"Executing: {query} | params: {params}")
                cursor.execute(query, params or ())
            conn.commit()
            logger.debug(f"Transaction with {len(queries)} queries committed successfully")

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
            
            result = self.execute(check_query, (table_name,), fetch='one')
            
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


_db: Optional[Database] = None


def get_database() -> Database:
    """Get the shared database instance, creating it on first use"""
    global _db
    if _db is None:
        _db = Database()
    return _db
