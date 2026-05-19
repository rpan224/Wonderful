"""API-layer configuration."""
from pipeline.config import DB_PATH  # the pipeline writes it, the API reads it

# Minimum rapidfuzz score (0-100) to accept a fuzzy match. 80 tolerates
# 1-2 character typos (Bukalest -> Bucharest) but rejects unrelated words.
FUZZY_THRESHOLD = 80

# Pagination defaults for list endpoints.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

__all__ = ["DB_PATH", "FUZZY_THRESHOLD", "DEFAULT_LIMIT", "MAX_LIMIT"]
