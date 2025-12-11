from portfolio_greeting import get_message


def test_message_contains_portfolio():
    msg = get_message()
    assert "Pari" in msg
    assert "Portfolio" in msg
