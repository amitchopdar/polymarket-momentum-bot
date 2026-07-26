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
USER_MIN_MODEL_PROBABILITY = 0.5001  # Minimum model directional confidence (51%)
USER_MAX_POSITION_SIZE_USD = 2.0  # Max position size per trade ($50.0)
USER_MIN_L2_DEPTH_SHARES = 10.0    # Min order book liquidity depth
USER_MAX_SLIPPAGE_TOLERANCE = 0.02 # Max slippage tolerance (2%)
USER_SLA_LATENCY_LIMIT_MS = 100.0  # Max SLA latency limit (100 ms)

# 3. Telegram Notifications & Remote Command Router
USER_TELEGRAM_BOT_TOKEN = "8842999811:AAFtjgxVUFMIRxF77auE4TnM7g0PhyB7D1Q"       # Paste your Bot Token here (e.g. "7123456789:AAFx...")
USER_TELEGRAM_CHAT_ID = "488798563"         # Primary Chat ID for real-time trade alerts (e.g. "987654321")

# List of authorized admin Telegram User IDs allowed to issue remote slash commands
# Example for single admin: USER_TELEGRAM_AUTHORIZED_USER_IDS = [987654321]
# Example for multiple admins: USER_TELEGRAM_AUTHORIZED_USER_IDS = [987654321, 123456789, 555666777]
USER_TELEGRAM_AUTHORIZED_USER_IDS = [488798563]

# 4. Polymarket Live Wallet & API Credentials (Required ONLY for LIVE mode)
USER_POLYMARKET_API_KEY = ""
USER_POLYMARKET_SECRET = ""
USER_POLYMARKET_PASSPHRASE = ""
USER_POLYMARKET_PRIVATE_KEY = ""
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
