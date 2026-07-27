"""
Global Application Configuration & Risk Settings (Sprint 3: US3.1)
Manages environment variables, execution modes, trade parameters, risk thresholds, and Telegram credentials.
"""

import os
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

def parse_int_list(raw: str) -> List[int]:
    if not raw:
        return []
    res = []
    for item in raw.split(","):
        item = item.strip()
        if item.isdigit():
            res.append(int(item))
    return res

# ==============================================================================
# POLYMARKET BOT CONFIGURATION (Single Source of Truth)
# Edit your parameters directly here, or set environment variables.
# ==============================================================================

# 1. Execution Mode ('DRY_RUN' for simulation, 'LIVE' for real trading)
USER_EXECUTION_MODE = "DRY_RUN"

# 2. Risk & Execution Boundaries
USER_TARGET_BUY_PRICE = 0.48       # Target limit buy price ($0.40)
USER_STOP_LOSS_PRICE = 0.30        # Stop loss sell price ($0.20)
USER_MIN_MODEL_PROBABILITY = 0.5001  # Minimum model directional confidence threshold (55.0%)
USER_MAX_POSITION_SIZE_USD = 2.0  # Max position size per trade ($50.0)
USER_MIN_L2_DEPTH_SHARES = 10.0    # Min order book liquidity depth
USER_MAX_SLIPPAGE_TOLERANCE = 0.02 # Max slippage tolerance (2%)
USER_SLA_LATENCY_LIMIT_MS = 100.0  # Max SLA latency limit (100 ms)
USER_ORDER_TIMEOUT_SEC = 300.0     # Order timeout cap (300 seconds / 5 minutes)
USER_MIN_REQUIRED_WIN_RATE = 0.55  # Minimum model win rate (55.0%) required for production promotion

# Auto-load local .env file if present
_env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env_file):
    try:
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())
    except Exception:
        pass

# 3. Telegram Notifications & Remote Command Router (Loaded via Environment / .env)
USER_TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
USER_TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# List of authorized admin Telegram User IDs allowed to issue remote slash commands
_auth_ids_env = os.getenv("TELEGRAM_AUTHORIZED_USER_IDS", "")
USER_TELEGRAM_AUTHORIZED_USER_IDS = [int(x.strip()) for x in _auth_ids_env.split(",") if x.strip().isdigit()]

# 4. Polymarket Live Wallet & API Credentials (Required ONLY for LIVE mode)
USER_POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")
USER_POLYMARKET_SECRET = os.getenv("POLYMARKET_SECRET", "")
USER_POLYMARKET_PASSPHRASE = os.getenv("POLYMARKET_PASSPHRASE", "")
USER_POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")
# ==============================================================================


@dataclass
class AppConfig:
    """
    Centralized bot configuration object.
    Supports dry-run toggle, risk parameters, API endpoints, database settings, and Telegram controls.
    """
    # Environment & Risk Toggles (US3.1)
    execution_mode: str = field(default_factory=lambda: os.getenv("EXECUTION_MODE", USER_EXECUTION_MODE).upper())
    dry_run: bool = field(default_factory=lambda: os.getenv("EXECUTION_MODE", USER_EXECUTION_MODE).upper() == "DRY_RUN")
    trading_active: bool = True
    
    # Database Settings
    db_path: str = "PolyDB.sqlite"
    busy_timeout_ms: int = 30000

    # Exchange & Stream Settings
    symbol: str = "BTCUSDT"
    candle_interval: str = "5m"
    binance_ws_url: str = "wss://fstream.binance.com/stream?streams=btcusdt@kline_5m/btcusdt@depth10@100ms/btcusdt@forceOrder"
    binance_rest_url: str = "https://fapi.binance.com/fapi/v1/klines"
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com/events"
    polymarket_clob_url: str = "https://clob.polymarket.com"

    # Execution & Risk Boundaries (US3.2)
    target_buy_price: float = field(default_factory=lambda: float(os.getenv("TARGET_BUY_PRICE", str(USER_TARGET_BUY_PRICE))))
    target_entry_price: float = field(default_factory=lambda: float(os.getenv("TARGET_BUY_PRICE", str(USER_TARGET_BUY_PRICE))))
    stop_loss_price: float = field(default_factory=lambda: float(os.getenv("STOP_LOSS_PRICE", str(USER_STOP_LOSS_PRICE))))
    min_model_probability: float = field(default_factory=lambda: float(os.getenv("MIN_MODEL_PROBABILITY", str(USER_MIN_MODEL_PROBABILITY))))
    max_position_size_usd: float = field(default_factory=lambda: float(os.getenv("MAX_POSITION_SIZE_USD", str(USER_MAX_POSITION_SIZE_USD))))
    min_l2_depth_shares: float = field(default_factory=lambda: float(os.getenv("MIN_L2_DEPTH_SHARES", str(USER_MIN_L2_DEPTH_SHARES))))
    max_slippage_tolerance: float = field(default_factory=lambda: float(os.getenv("MAX_SLIPPAGE_TOLERANCE", str(USER_MAX_SLIPPAGE_TOLERANCE))))
    sla_latency_limit_ms: float = field(default_factory=lambda: float(os.getenv("SLA_LATENCY_LIMIT_MS", str(USER_SLA_LATENCY_LIMIT_MS))))
    order_timeout_sec: float = field(default_factory=lambda: float(os.getenv("ORDER_TIMEOUT_SEC", str(USER_ORDER_TIMEOUT_SEC))))
    min_required_win_rate: float = field(default_factory=lambda: float(os.getenv("MIN_REQUIRED_WIN_RATE", str(USER_MIN_REQUIRED_WIN_RATE))))

    # Notification & Remote Commands (US4.2, US4.3)
    telegram_enabled: bool = True
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "") or USER_TELEGRAM_BOT_TOKEN)
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "") or USER_TELEGRAM_CHAT_ID)
    telegram_authorized_user_ids: List[int] = field(
        default_factory=lambda: parse_int_list(os.getenv("TELEGRAM_AUTHORIZED_USER_IDS", "")) or USER_TELEGRAM_AUTHORIZED_USER_IDS
    )

    # Polymarket Live Wallet & API Credentials
    polymarket_api_key: str = field(default_factory=lambda: os.getenv("POLYMARKET_API_KEY", "") or USER_POLYMARKET_API_KEY)
    polymarket_secret: str = field(default_factory=lambda: os.getenv("POLYMARKET_SECRET", "") or USER_POLYMARKET_SECRET)
    polymarket_passphrase: str = field(default_factory=lambda: os.getenv("POLYMARKET_PASSPHRASE", "") or USER_POLYMARKET_PASSPHRASE)
    polymarket_private_key: str = field(default_factory=lambda: os.getenv("POLYMARKET_PRIVATE_KEY", "") or USER_POLYMARKET_PRIVATE_KEY)

    def is_dry_run(self) -> bool:
        return self.execution_mode == "DRY_RUN" or self.dry_run

    def set_execution_mode(self, mode: str) -> bool:
        mode_upper = mode.upper()
        if mode_upper in ("DRY_RUN", "LIVE"):
            self.execution_mode = mode_upper
            self.dry_run = (mode_upper == "DRY_RUN")
            logger.info(f"✓ Execution mode set to: {self.execution_mode}")
            return True
        return False

    def set_trading_active(self, active: bool) -> None:
        self.trading_active = active
        status_str = "ACTIVE" if active else "DEACTIVATED"
        logger.info(f"✓ Bot trading engine status set to: {status_str}")

# Global config instance
config = AppConfig()
