class DatabaseError(Exception):
    """Base exception for database operations"""

    pass


class ConnectionError(DatabaseError):
    """Raised when database connection fails"""

    pass


class QueryError(DatabaseError):
    """Raised when a database query fails"""

    def __init__(self, query: str, params: tuple, original_error: Exception):
        self.query = query
        self.params = params
        self.original_error = original_error
        super().__init__(f"Query failed: {str(original_error)}")
