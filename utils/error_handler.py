# utils/error_handler.py — Friendly error messages, no raw tracebacks shown to users
from __future__ import annotations
import logging
import functools
import streamlit as st

logger = logging.getLogger(__name__)


def safe_page(fn):
    """
    Decorator — wraps a Streamlit page function so any unhandled exception
    shows a friendly message instead of a raw Python traceback.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.error("Page error in %s: %s", fn.__name__, e, exc_info=True)
            st.error(
                "⚠️ Something went wrong loading this page. "
                "Please try refreshing, or contact your system administrator if the problem persists."
            )
            with st.expander("🔧 Technical details (for your administrator)"):
                st.code(str(e))
    return wrapper


def friendly_db_error(e: Exception, action: str = "complete this action") -> None:
    """Show a user-friendly message for database errors."""
    logger.error("DB error during '%s': %s", action, e)
    msg = str(e).lower()
    if "locked" in msg or "timeout" in msg:
        st.error("⚠️ The database is busy. Please wait a moment and try again.")
    elif "unique" in msg or "duplicate" in msg:
        st.error("⚠️ This record already exists. Please check for duplicates.")
    elif "no such table" in msg:
        st.error("⚠️ Database setup incomplete. Please restart the app.")
    elif "no such column" in msg:
        st.error("⚠️ Database needs updating. Please restart the app.")
    else:
        st.error(f"⚠️ Could not {action}. Please try again.")
