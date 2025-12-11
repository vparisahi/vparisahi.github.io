from portfolio_greeting import get_message


def test_message_runs():
    # Just make sure we can call the function without error.
    msg = get_message()
    assert isinstance(msg, str)
