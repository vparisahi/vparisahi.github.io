import sys
import os

# Make sure the current directory is on the path
sys.path.append(os.path.dirname(__file__))

from portfolio_greeting import get_message


def test_message_runs():
    msg = get_message()
    assert isinstance(msg, str)
