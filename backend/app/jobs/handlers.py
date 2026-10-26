"""Importing this module registers every job handler. The worker and tests both import it."""
from app.services import imports, personalize, qualify, research  # noqa: F401
