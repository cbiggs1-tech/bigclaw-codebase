"""Portfolio management for BigClaw AI - Paper trading system.

Provides persistent storage for mock portfolios with:
- Multiple portfolios (each with its own investment style)
- Holdings tracking with buy price, date, and style rationale
- Transaction history
- Performance calculations
"""

import os
import sqlite3
import logging
from datetime import datetime
import sys as _sys
_sys.path.insert(0, str(Path("/home/cbiggs90/bigclaw-ai/scripts")))
from trade_recorder import record_trade

from typing import Optional
import json

logger = logging.getLogger(__name__)

# Database location - in the src directory for simplicity
DB_PATH = os.path.join(os.path.dirname(__file__), "portfolios.db")


def get_db_connection(immediate=False):
    """Get a database connection with row factory.

    Args:
        immediate: If True, use BEGIN IMMEDIATE for write safety.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    if immediate:
        conn.execute("BEGIN IMMEDIATE")
    return conn


def init_database():
    """Initialize the database schema."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Portfolios table - each portfolio has a style and cash balance
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            investment_style TEXT NOT NULL,
            starting_cash REAL NOT NULL DEFAULT 100000,
            current_cash REAL NOT NULL DEFAULT 100000,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            report_channel TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)

    # Holdings table - current positions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            avg_cost REAL NOT NULL,
            first_bought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_bought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            rationale TEXT,
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
            UNIQUE(portfolio_id, ticker)
        )
    """)

    # Transactions table - all buy/sell history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            shares REAL NOT NULL,
            price REAL NOT NULL,
            total_value REAL NOT NULL,
            rationale TEXT,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
        )
    """)

    # Daily snapshots for performance tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            snapshot_date DATE NOT NULL,
            total_value REAL NOT NULL,
            cash REAL NOT NULL,
            holdings_value REAL NOT NULL,
            daily_return REAL,
            total_return REAL,
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
            UNIQUE(portfolio_id, snapshot_date)
        )
    """)

    # Pending orders table - stop loss, limit buy, limit sell
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            order_type TEXT NOT NULL,
            trigger_price REAL NOT NULL,
            shares REAL,
            amount REAL,
            rationale TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            triggered_at TIMESTAMP,
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
        )
    """)

    # Trailing stops — style-specific stop-loss tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trailing_stops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            high_water_mark REAL NOT NULL,
            hwm_date TEXT NOT NULL,
            trail_pct REAL NOT NULL,
            trigger_price REAL NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            triggered_at TIMESTAMP,
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
            UNIQUE(portfolio_id, ticker)
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Portfolio database initialized")


class Portfolio:
    """Represents a single portfolio."""

    def __init__(self, portfolio_id: int):
        self.id = portfolio_id
        self._load()

    def _load(self):
        """Load portfolio data from database."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM portfolios WHERE id = ?", (self.id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise ValueError(f"Portfolio {self.id} not found")

        self.name = row["name"]
        self.investment_style = row["investment_style"]
        self.starting_cash = row["starting_cash"]
        self.current_cash = row["current_cash"]
        self.created_at = row["created_at"]
        self.report_channel = row["report_channel"]
        self.is_active = bool(row["is_active"])

    def get_holdings(self) -> list[dict]:
        """Get all current holdings."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ticker, shares, avg_cost, first_bought_at, last_bought_at, rationale
            FROM holdings
            WHERE portfolio_id = ? AND shares > 0
            ORDER BY ticker
        """, (self.id,))
        holdings = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return holdings

    def get_holding(self, ticker: str) -> Optional[dict]:
        """Get a specific holding."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ticker, shares, avg_cost, first_bought_at, last_bought_at, rationale
            FROM holdings
            WHERE portfolio_id = ? AND ticker = ? AND shares > 0
        """, (self.id, ticker.upper()))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def buy(self, ticker: str, shares: float, price: float, rationale: str = "") -> dict:
        """Execute a buy order via the canonical trade_recorder.

        All cash/holdings writes go through record_trade so cash is recomputed
        from the transactions log (no additive drift). Action recorded as
        lowercase 'buy' to match the rest of the codebase.
        """
        ticker = ticker.upper()
        total_cost = shares * price

        if total_cost > self.current_cash:
            return {
                "success": False,
                "error": f"Insufficient cash. Need ${total_cost:,.2f}, have ${self.current_cash:,.2f}",
            }

        # Fetch analyst target at entry for target-price discipline
        target_price = None
        try:
            import yfinance as _yf
            _info = _yf.Ticker(ticker).info or {}
            target_price = _info.get("targetMeanPrice")
        except Exception:
            pass
        ok = record_trade(
            self.id, self.name, ticker, "buy", shares, price, total_cost, rationale,
            target_price=target_price,
            target_source="yfinance_mean" if target_price else None,
        )
        if not ok:
            return {"success": False, "error": "DB recording failed"}

        # Re-read current_cash (recomputed by record_trade)
        conn = get_db_connection()
        row = conn.execute("SELECT current_cash FROM portfolios WHERE id = ?", (self.id,)).fetchone()
        conn.close()
        self.current_cash = row["current_cash"]

        return {
            "success": True,
            "action": "BUY",
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "total_cost": total_cost,
            "remaining_cash": self.current_cash,
        }


    def sell(self, ticker: str, shares: float, price: float, rationale: str = "") -> dict:
        """Execute a sell order via the canonical trade_recorder.

        Same delegation pattern as buy(). Computes sell_all from current
        holdings to use DELETE on full close, decrement on partial.
        """
        ticker = ticker.upper()
        total_value = shares * price

        # Look up current holdings to determine sell_all
        conn = get_db_connection()
        row = conn.execute(
            "SELECT shares FROM holdings WHERE portfolio_id = ? AND ticker = ?",
            (self.id, ticker),
        ).fetchone()
        conn.close()

        if not row or row["shares"] < shares - 0.001:
            held = row["shares"] if row else 0
            return {
                "success": False,
                "error": f"Insufficient shares. Have {held}, trying to sell {shares}",
            }

        sell_all = (shares >= row["shares"] - 0.001)

        ok = record_trade(
            self.id, self.name, ticker, "sell", shares, price, total_value, rationale,
            sell_all=sell_all,
        )
        if not ok:
            return {"success": False, "error": "DB recording failed"}

        # Re-read current_cash (recomputed by record_trade)
        conn = get_db_connection()
        row = conn.execute("SELECT current_cash FROM portfolios WHERE id = ?", (self.id,)).fetchone()
        conn.close()
        self.current_cash = row["current_cash"]

        return {
            "success": True,
            "action": "SELL",
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "total_value": total_value,
            "remaining_cash": self.current_cash,
        }


    def get_transactions(self, limit: int = 20) -> list[dict]:
        """Get recent transactions."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ticker, action, shares, price, total_value, rationale, executed_at
            FROM transactions
            WHERE portfolio_id = ?
            ORDER BY executed_at DESC
            LIMIT ?
        """, (self.id, limit))
        transactions = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return transactions

    def calculate_total_value(self, current_prices: dict[str, float]) -> dict:
        """Calculate total portfolio value given current prices.

        Args:
            current_prices: Dict of ticker -> current price

        Returns:
            Dict with value breakdown
        """
        holdings = self.get_holdings()
        holdings_value = 0
        positions = []

        for h in holdings:
            ticker = h["ticker"]
            price = current_prices.get(ticker, h["avg_cost"])  # Use avg cost if price unavailable
            value = h["shares"] * price
            cost_basis = h["shares"] * h["avg_cost"]
            gain = value - cost_basis
            gain_pct = (gain / cost_basis * 100) if cost_basis > 0 else 0

            holdings_value += value
            positions.append({
                "ticker": ticker,
                "shares": h["shares"],
                "avg_cost": h["avg_cost"],
                "current_price": price,
                "value": value,
                "gain": gain,
                "gain_pct": gain_pct,
                "first_bought_at": h.get("first_bought_at")
            })

        total_value = self.current_cash + holdings_value
        total_return = total_value - self.starting_cash
        total_return_pct = (total_return / self.starting_cash * 100)

        return {
            "cash": self.current_cash,
            "holdings_value": holdings_value,
            "total_value": total_value,
            "total_return": total_return,
            "total_return_pct": total_return_pct,
            "positions": positions
        }

    def save_daily_snapshot(self, total_value: float, holdings_value: float):
        """Save a daily snapshot for performance tracking."""
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get yesterday's snapshot for daily return calc
        cursor.execute("""
            SELECT total_value FROM daily_snapshots
            WHERE portfolio_id = ?
            ORDER BY snapshot_date DESC LIMIT 1
        """, (self.id,))
        last = cursor.fetchone()
        last_value = last["total_value"] if last else self.starting_cash

        daily_return = ((total_value - last_value) / last_value * 100) if last_value > 0 else 0
        total_return = ((total_value - self.starting_cash) / self.starting_cash * 100)

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO daily_snapshots
                (portfolio_id, snapshot_date, total_value, cash, holdings_value, daily_return, total_return)
                VALUES (?, DATE('now'), ?, ?, ?, ?, ?)
            """, (self.id, total_value, self.current_cash, holdings_value, daily_return, total_return))
            conn.commit()
        except Exception as e:
            logger.error(f"Snapshot error: {e}")
        finally:
            conn.close()


# Portfolio manager functions

def create_portfolio(
    name: str,
    investment_style: str,
    starting_cash: float = 100000,
    report_channel: str = None
) -> Portfolio:
    """Create a new portfolio."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO portfolios (name, investment_style, starting_cash, current_cash, report_channel)
            VALUES (?, ?, ?, ?, ?)
        """, (name, investment_style, starting_cash, starting_cash, report_channel))
        conn.commit()
        portfolio_id = cursor.lastrowid
        logger.info(f"Created portfolio '{name}' with ID {portfolio_id}")
        return Portfolio(portfolio_id)
    except sqlite3.IntegrityError:
        raise ValueError(f"Portfolio '{name}' already exists")
    finally:
        conn.close()


def get_portfolio(name: str) -> Optional[Portfolio]:
    """Get a portfolio by name."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM portfolios WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return Portfolio(row["id"])
    return None


def get_portfolio_by_id(portfolio_id: int) -> Optional[Portfolio]:
    """Get a portfolio by ID."""
    try:
        return Portfolio(portfolio_id)
    except ValueError:
        return None


def list_portfolios() -> list[dict]:
    """List all portfolios."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, investment_style, starting_cash, current_cash, created_at, is_active, report_channel,
               COALESCE(purchase_status, 'active') as purchase_status
        FROM portfolios
        ORDER BY created_at DESC
    """)
    portfolios = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return portfolios


def get_active_portfolios() -> list[Portfolio]:
    """Get all active portfolios for autonomous trading."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM portfolios WHERE is_active = 1")
    rows = cursor.fetchall()
    conn.close()
    return [Portfolio(row["id"]) for row in rows]


def delete_portfolio(name: str) -> bool:
    """Delete a portfolio and all its data."""
    conn = get_db_connection(immediate=True)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM portfolios WHERE name = ?", (name,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    portfolio_id = row["id"]

    cursor.execute("DELETE FROM daily_snapshots WHERE portfolio_id = ?", (portfolio_id,))
    cursor.execute("DELETE FROM transactions WHERE portfolio_id = ?", (portfolio_id,))
    cursor.execute("DELETE FROM holdings WHERE portfolio_id = ?", (portfolio_id,))
    cursor.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))

    conn.commit()
    conn.close()
    logger.info(f"Deleted portfolio '{name}'")
    return True


# Order management functions

def create_pending_order(
    portfolio_id: int,
    ticker: str,
    order_type: str,
    trigger_price: float,
    shares: float = None,
    amount: float = None,
    rationale: str = ""
) -> int:
    """Create a pending order (stop_loss, limit_buy, limit_sell).

    Returns the order ID.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO pending_orders (portfolio_id, ticker, order_type, trigger_price, shares, amount, rationale)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (portfolio_id, ticker.upper(), order_type, trigger_price, shares, amount, rationale))

    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"Created {order_type} order #{order_id} for {ticker} at ${trigger_price}")
    return order_id


def get_pending_orders(portfolio_id: int = None, status: str = "active") -> list[dict]:
    """Get pending orders, optionally filtered by portfolio."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if portfolio_id:
        cursor.execute("""
            SELECT po.*, p.name as portfolio_name
            FROM pending_orders po
            JOIN portfolios p ON po.portfolio_id = p.id
            WHERE po.portfolio_id = ? AND po.status = ?
            ORDER BY po.created_at DESC
        """, (portfolio_id, status))
    else:
        cursor.execute("""
            SELECT po.*, p.name as portfolio_name
            FROM pending_orders po
            JOIN portfolios p ON po.portfolio_id = p.id
            WHERE po.status = ?
            ORDER BY po.created_at DESC
        """, (status,))

    orders = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return orders


def get_order_by_id(order_id: int) -> Optional[dict]:
    """Get a specific order by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT po.*, p.name as portfolio_name
        FROM pending_orders po
        JOIN portfolios p ON po.portfolio_id = p.id
        WHERE po.id = ?
    """, (order_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def cancel_pending_order(order_id: int) -> bool:
    """Cancel a pending order."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT status FROM pending_orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()

    if not row or row["status"] != "active":
        conn.close()
        return False

    cursor.execute(
        "UPDATE pending_orders SET status = 'cancelled' WHERE id = ?",
        (order_id,)
    )
    conn.commit()
    conn.close()

    logger.info(f"Cancelled order #{order_id}")
    return True


def mark_order_triggered(order_id: int):
    """Mark an order as triggered/executed."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE pending_orders SET status = 'triggered', triggered_at = CURRENT_TIMESTAMP WHERE id = ?",
        (order_id,)
    )
    conn.commit()
    conn.close()


# Initialize database on module load
init_database()
