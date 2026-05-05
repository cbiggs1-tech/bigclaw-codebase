"""Symbol translation between BigClaw internal format and Alpaca.

BigClaw stores tickers using the Yahoo/Finviz convention with hyphens for
class-share suffixes (BRK-B, BF-A). Alpaca uses dots (BRK.B, BF.A). Translate
at the Alpaca API boundary in both directions.
"""
import re

_HYPHEN_CLASS = re.compile(r'^([A-Z]+)-([A-Z])$')
_DOT_CLASS = re.compile(r'^([A-Z]+)\.([A-Z])$')


def to_alpaca(ticker: str) -> str:
    """Internal -> Alpaca: BF-A -> BF.A."""
    if not ticker:
        return ticker
    return _HYPHEN_CLASS.sub(r'\1.\2', ticker)


def from_alpaca(symbol: str) -> str:
    """Alpaca -> internal: BF.A -> BF-A."""
    if not symbol:
        return symbol
    return _DOT_CLASS.sub(r'\1-\2', symbol)
