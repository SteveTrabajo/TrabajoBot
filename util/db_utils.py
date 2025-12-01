"""
db_utils.py
==========
Utilities for database operations, including retry logic and transaction management.
Designed to work with the connection pool in db.py
"""

import functools
import logging

logger = logging.getLogger("TrabajoBot")


def db_retry(max_retries=3):
    """
    Decorator for database operations that need retry logic.
    Retries the operation on transient errors.
    
    Uses the connection pool's automatic transaction cleanup,
    so no need to manually manage BEGIN/COMMIT/ROLLBACK.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            retry_count = 0
            last_error = None
            
            while retry_count < max_retries:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    error_msg = str(e).lower()
                    
                    # Retry on transient errors
                    if any(err in error_msg for err in [
                        "transactionretrywithprotorefresherror",
                        "connection refused",
                        "connection reset",
                        "deadline exceeded"
                    ]) and retry_count < max_retries - 1:
                        retry_count += 1
                        logger.warning(f"Transient error, retrying ({retry_count}/{max_retries}): {e}")
                        continue
                    
                    # Non-retryable error or max retries exceeded
                    raise
            
            if last_error:
                raise last_error
                
        return wrapper
    return decorator
