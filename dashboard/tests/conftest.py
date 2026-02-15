"""Shared test fixtures"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add dashboard/ to sys.path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Mock streamlit (register in sys.modules BEFORE any imports)
# This ensures that lib/auth.py and other modules see the mock
mock_st = MagicMock()
mock_st.session_state = {}

# Create proper decorator mocks that accept function arguments
def cache_data_decorator(**kwargs):
    def decorator(func):
        return func
    return decorator

def cache_resource_decorator(func):
    return func

mock_st.cache_data = cache_data_decorator
mock_st.cache_resource = cache_resource_decorator
mock_st.user = MagicMock()
mock_st.user.is_logged_in = False
mock_st.user.email = None

# Mock UI functions (called at module level in pages)
mock_st.header = MagicMock()
mock_st.caption = MagicMock()
mock_st.divider = MagicMock()
mock_st.markdown = MagicMock()
mock_st.selectbox = MagicMock(return_value="viewer")  # Default role
mock_st.text_input = MagicMock(return_value="")  # Return empty string by default
mock_st.button = MagicMock(return_value=False)  # Return False for button clicks
mock_st.checkbox = MagicMock(return_value=False)  # Return False for checkboxes

# Mock st.columns to dynamically create the correct number of columns
def mock_columns(spec):
    """Return tuple of mock columns based on spec (list of proportions)"""
    return tuple(MagicMock() for _ in spec)

mock_st.columns = mock_columns
mock_st.container = MagicMock()
mock_st.progress = MagicMock()
mock_st.data_editor = MagicMock()
mock_st.expander = MagicMock()
mock_st.error = MagicMock()
mock_st.info = MagicMock()
mock_st.toast = MagicMock()
mock_st.stop = MagicMock()
mock_st.rerun = MagicMock()

# Mock column_config
mock_st.column_config = MagicMock()
mock_st.column_config.LinkColumn = MagicMock()
mock_st.column_config.SelectboxColumn = MagicMock()
mock_st.column_config.TextColumn = MagicMock()
mock_st.column_config.NumberColumn = MagicMock()

# Mock navigation
mock_st.navigation = MagicMock()

# Mock sidebar as context manager
sidebar_mock = MagicMock()
sidebar_mock.__enter__ = MagicMock(return_value=sidebar_mock)
sidebar_mock.__exit__ = MagicMock(return_value=False)
mock_st.sidebar = sidebar_mock

# Mock container as context manager
container_mock = MagicMock()
container_mock.__enter__ = MagicMock(return_value=container_mock)
container_mock.__exit__ = MagicMock(return_value=False)
mock_st.container.return_value = container_mock

# Mock expander as context manager
expander_mock = MagicMock()
expander_mock.__enter__ = MagicMock(return_value=expander_mock)
expander_mock.__exit__ = MagicMock(return_value=False)
mock_st.expander.return_value = expander_mock

# Mock form as context manager
def mock_form_fn(*args, **kwargs):
    form_mock = MagicMock()
    form_mock.__enter__ = MagicMock(return_value=form_mock)
    form_mock.__exit__ = MagicMock(return_value=False)
    return form_mock

mock_st.form = mock_form_fn

# Mock popover as context manager
def mock_popover_fn(label):
    popover_mock = MagicMock()
    popover_mock.__enter__ = MagicMock(return_value=popover_mock)
    popover_mock.__exit__ = MagicMock(return_value=False)
    return popover_mock

mock_st.popover = mock_popover_fn

mock_st.subheader = MagicMock()
mock_st.success = MagicMock()
mock_st.form_submit_button = MagicMock()
mock_st.iterrows = MagicMock()

sys.modules["streamlit"] = mock_st
sys.modules["streamlit.components"] = MagicMock()
sys.modules["streamlit.components.v1"] = MagicMock()

import pytest


@pytest.fixture(autouse=True)
def mock_streamlit():
    """Reset Streamlit mock state before each test"""
    # Reset session_state and user state for each test
    mock_st.session_state = {}
    mock_st.user = MagicMock()
    mock_st.user.is_logged_in = False
    mock_st.user.email = None
    yield mock_st
