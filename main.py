"""
Polymarket BTC-5min Prediction Bot - Main Entry Point
"""

import sys
import time
import signal
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
from src.config import config
from src.database.connection import PolyDBManager, AsyncDBWriter
from src.ingestion.candle_cache import CandleCache
from src.ingestion.order_flow import OrderFlowTracker
from src.ingestion.binance_ws import BinanceWebSocketClient
from src.polymarket.token_resolver import PolymarketTokenResolver, MinuteOddsTracker
from src.polymarket.polymarket_ws import PolymarketWSClient
from src.ml.features import VectorFeaturePipeline
from src.ml.predictor import CalibratedLGBMPredictor
from src.execution.strategy import DryExecutionStrategy, LiveExecutionStrategy
from src.execution.risk_engine import RiskEngine
from src.execution.reconciler import StateReconciler
from src.notifications.notifier import TelegramNotifier
from src.notifications.telegram_bot import TelegramCommandRouter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("PolyBotMain")

class PolymarketBot:
    """
    Main bot orchestrator managing database, telemetry ingestion, ML inference, and execution lifecycle.
    """

    def __init__(self, db_path: str = "PolyDB.sqlite"):
        self.db_path = db_path
        self.db_manager = PolyDBManager(db_path=self.db_path)
        self.async_writer = AsyncDBWriter(self.db_manager)
        
        # Sprint 1 Ingestion Engine
        self.order_flow = OrderFlowTracker()
        self.candle_cache = CandleCache(maxlen=500)
        self.ws_client = BinanceWebSocketClient(
            on_kline_callback=self._handle_kline,
            on_depth_callback=self._handle_depth,
            on_liquidation_callback=self._handle_liquidation,
            on_reconnect_callback=self._handle_ws_reconnect
        )

        # Sprint 2 Polymarket WS Stream & Token Resolver
        self.polymarket_ws = PolymarketWSClient()
        self.token_resolver = PolymarketTokenResolver()
        self.minute_tracker = MinuteOddsTracker()
        self.feature_pipeline = VectorFeaturePipeline()
        self.predictor = CalibratedLGBMPredictor()

        # Sprint 3 Execution Engine, Risk Guards, Recovery & Notifications
        self.dry_strategy = DryExecutionStrategy(self.async_writer)
        self.execution_strategy = LiveExecutionStrategy(self.async_writer) if not config.is_dry_run() else self.dry_strategy
        self.risk_engine = RiskEngine(self.dry_strategy)
        self.reconciler = StateReconciler(db_path=self.db_path)
        self.notifier = TelegramNotifier()
        self.telegram_bot = TelegramCommandRouter(self.notifier, db_path=self.db_path)

        self.running = False
        self._last_preflight_sec = -1

    def _execute_ml_inference_cycle(self, candle: Dict[str, Any]) -> None:
        """
        Executes Sprint 2 ML Feature Extraction & Calibrated Prediction Inference on candle finalization.
        """
        candle_start = candle["Candle_Start"]
        history = self.candle_cache.get_history()

        # 1. Vectorized NumPy Feature Engineering (US2.1)
        features, feature_ms = self.feature_pipeline.extract_features(history)

        # 2. Calibrated LightGBM Prediction & Fail-Closed Guard (US2.2)
        signal, p_cal, p_uncal, tier, status = self.predictor.predict(features, feature_ms)

        logger.info(
            f"=== SPRINT 2 ML CYCLE === Candle: {candle_start} | "
            f"Signal: {signal} | P_cal: {p_cal:.4f} (P_uncal: {p_uncal:.4f}) | "
            f"Tier: {tier} | SLA Latency: {feature_ms:.2f}ms"
        )

        # 3. Sprint 3 Risk Engine & Trade Order Execution for New Active Candle (US3.1, US3.2)
        now_ts = int(time.time())
        curr_candle_sec = (now_ts // 300) * 300
        new_active_candle_start = datetime.fromtimestamp(curr_candle_sec, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        slug = f"btc-updown-5m-{curr_candle_sec}"

        if signal in ("UP", "DOWN"):
            tokens_tuple = self.token_resolver.get_or_resolve_candle_tokens(curr_candle_sec)
            if tokens_tuple:
                up_tok, dn_tok = tokens_tuple[0], tokens_tuple[1]
                up_bid, up_ask, dn_bid, dn_ask = self.polymarket_ws.get_live_bid_ask(up_tok, dn_tok)
                target_tok = up_tok if signal == "UP" else dn_tok
                target_ask = up_ask if signal == "UP" else dn_ask
                target_bid = up_bid if signal == "UP" else dn_bid

                pos = self.risk_engine.evaluate_and_execute_entry(
                    candle_start=new_active_candle_start,
                    slug=slug,
                    side=signal,
                    prob_cal=p_cal,
                    prob_uncal=p_uncal,
                    token_id=target_tok,
                    current_bid=target_bid,
                    current_ask=target_ask
                )
                if pos:
                    self.notifier.notify_signal(new_active_candle_start, signal, p_cal, p_uncal, config.target_buy_price)
                else:
                    self.dry_strategy.record_no_trade(new_active_candle_start, slug, p_cal, p_uncal, reason="RISK_GUARD_REJECT")
                    self.notifier.notify_no_trade(new_active_candle_start, p_cal, p_uncal, tier, "RISK_GUARD_REJECT")
        else:
            no_trade_reason = "VOLATILITY_SQUEEZE_CHOP" if tier == "VOLATILITY_CHOP" else "LOW_CONFIDENCE"
            self.dry_strategy.record_no_trade(new_active_candle_start, slug, p_cal, p_uncal, reason=no_trade_reason)
            self.notifier.notify_no_trade(new_active_candle_start, p_cal, p_uncal, tier, no_trade_reason)

        # 4. Polymarket Token Odds Settlement Recording for Completed Candle (US1.3.1)
        start_ts_ms = candle.get("start_ts_ms")
        if not start_ts_ms:
            try:
                dt = datetime.strptime(candle_start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                start_ts_ms = int(dt.timestamp() * 1000)
            except Exception:
                start_ts_ms = int(time.time() * 1000)

        # 4. Asynchronous 5-Second Polling Loop for 100% Pure Official Polymarket Settlement (No Fallbacks!)
        threading.Thread(
            target=self._poll_polymarket_settlement_loop,
            args=(start_ts_ms, candle_start, candle),
            daemon=True,
            name=f"SettlementPoller_{start_ts_ms}"
        ).start()

    def _poll_polymarket_settlement_loop(self, start_ts_ms: int, candle_start: str, candle: Dict[str, Any]) -> None:
        """
        Polls Polymarket Gamma API every 5 seconds until official 100% resolution is confirmed.
        ZERO synthetic guessing, zero fallback to Binance Close > Open!
        """
        logger.info(f"⏳ [SETTLEMENT POLLER] Initiated 5s polling loop for candle {candle_start}...")
        
        # Initial 15s wait to allow Polymarket Oracle time to post resolution
        time.sleep(15.0)
        
        max_attempts = 60  # Poll up to 5 minutes (60 * 5s)
        settlement = None

        for attempt in range(1, max_attempts + 1):
            if not getattr(self, "running", True):
                break

            resolved = self.token_resolver.retry_fallback_at_t0(start_ts_ms)
            settlement = self.token_resolver.fetch_resolved_market_settlement(start_ts_ms)
            open_prices = self.token_resolver.get_open_prices(start_ts_ms)

            if resolved and settlement:
                slug, up_tok, dn_tok = resolved
                up_p, dn_p = open_prices
                up_close, dn_close = settlement
                real_vol = self.token_resolver.cached_volumes.get(str(start_ts_ms), candle.get("Volume", 0.0))

                base_up_h = max(up_p, up_close)
                base_up_l = min(up_p, up_close)
                base_dn_h = max(dn_p, dn_close)
                base_dn_l = min(dn_p, dn_close)

                minute_dict = self.minute_tracker.get_dict(base_up_h, base_up_l, base_dn_h, base_dn_l)

                up_high = max([base_up_h] + [v for k, v in minute_dict.items() if "Up_High" in k])
                up_low = min([base_up_l] + [v for k, v in minute_dict.items() if "Up_Low" in k])
                dn_high = max([base_dn_h] + [v for k, v in minute_dict.items() if "Down_High" in k])
                dn_low = min([base_dn_l] + [v for k, v in minute_dict.items() if "Down_Low" in k])

                up_ohclv = (up_p, up_high, up_low, up_close, real_vol)
                dn_ohclv = (dn_p, dn_high, dn_low, dn_close, real_vol)

                self.token_resolver.record_odds_ohclv(
                    candle_start, up_tok, dn_tok, up_ohclv, dn_ohclv, minute_tracking=minute_dict, status="RESOLVED", async_writer=self.async_writer
                )
                self.minute_tracker.reset()

                # Determine 100% PURE official outcome (No fallback guessing!)
                actual_outcome = "UP" if up_close == 1.0 else "DOWN"

                logger.info(f"✓ [SETTLEMENT CONFIRMED] Official Polymarket Settlement for {candle_start}: Outcome={actual_outcome} (Attempt #{attempt})")

                # Sprint 3 Active Position Expiry Settlement
                active_pos = self.dry_strategy.active_positions.get(candle_start)
                if active_pos:
                    active_pos["Actual_Outcome"] = actual_outcome
                    if active_pos["Position_Status"] in ("PENDING", "OPEN"):
                        side = active_pos.get("Prediction_Side", "")
                        settlement_price = up_close if side == "UP" else dn_close
                        pos_closed = self.dry_strategy.execute_exit(
                            candle_start=candle_start,
                            token_id=active_pos.get("Token_Id", ""),
                            exit_price=settlement_price,
                            reason="END_OF_CANDLE",
                            actual_outcome=actual_outcome
                        )
                        if pos_closed:
                            self.notifier.notify_exit(candle_start, settlement_price, "END_OF_CANDLE", pos_closed.get("Pnl", 0.0))

                if self.async_writer:
                    now_dt = datetime.fromtimestamp(time.time(), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    # 1. Unconditionally update existing position row in Positions table
                    self.async_writer.enqueue_write(
                        "UPDATE Positions SET Actual_Outcome = ?, Updated_At = ? WHERE Candle_Start = ?;",
                        (actual_outcome, now_dt, candle_start)
                    )
                    # 2. Insert fallback NO_TRADE row if no position row was previously created for this candle
                    sql_fallback = """
                        INSERT OR IGNORE INTO Positions (
                            Candle_Start, Prob_Cal, Prob_Uncal, Slug, Prediction_Side, Actual_Outcome,
                            Entry_Timestamp, Target_Price, Target_Quantity, Position_Status, Cancel_Reason, Updated_At
                        ) VALUES (?, 0.50, 0.50, ?, 'NO_TRADE', ?, ?, 0.0, 0.0, 'NO_TRADE', 'SETTLED', ?);
                    """
                    self.async_writer.enqueue_write(sql_fallback, (candle_start, slug, actual_outcome, now_dt, now_dt))
                    self.async_writer.flush_and_checkpoint()
                    logger.info(f"💾 [WAL CHECKPOINT] Flushed SQLite WAL & Actual_Outcome='{actual_outcome}' to PolyDB.sqlite disk for candle {candle_start}.")
                return

            time.sleep(5.0)

        # If 5-minute timeout reached without official resolution:
        logger.warning(f"⚠ [SETTLEMENT POLLER TIMEOUT] Polymarket oracle resolution pending after 5m for candle {candle_start}. Recording Status='API_FAILURE'.")
        self.token_resolver.record_odds_ohclv(
            candle_start, "FETCH_FAILED", "FETCH_FAILED", status="API_FAILURE", async_writer=self.async_writer
        )
        self.minute_tracker.reset()

    def _handle_kline(self, kline_data: Dict[str, Any]) -> None:
        """
        Processes real-time kline message.
        """
        candle = self.candle_cache.update_kline(kline_data, self.order_flow, self.async_writer)
        self._log_live_status_if_needed(candle)

        if kline_data.get("x", False):
            logger.info(f"=== CANDLE FINALIZED === {candle['Candle_Start']} | Close: ${candle['Close']} | OBI: {candle['Obi']}")
            self._execute_ml_inference_cycle(candle)

    def _handle_depth(self, bids: List[list], asks: List[list]) -> None:
        """
        Processes real-time depth updates to compute Order Book Imbalance (OBI).
        """
        self.order_flow.process_depth(bids, asks)
        latest_candle = self.candle_cache.get_latest()
        if latest_candle:
            self._log_live_status_if_needed(latest_candle)

    def _log_live_status_if_needed(self, candle: Dict[str, Any]) -> None:
        """
        Logs real-time price, OBI & 100% Live Polymarket WebSocket Order Book Bid/Ask spread every 3 seconds.
        """
        now = time.time()
        if not hasattr(self, "_last_tick_log") or (now - self._last_tick_log) >= 3.0:
            self._last_tick_log = now
            current_obi = self.order_flow.get_current_obi()
            spot_price = self.order_flow.get_current_spot_price() or candle["Close"]

            start_ts_ms = candle.get("start_ts_ms", int(now * 1000))
            candle_start_sec = (start_ts_ms // 1000 // 300) * 300
            ongoing_slug = f"btc-updown-5m-{candle_start_sec}"
            
            # Parametric token lookup for current active bet (fail-safe on-the-spot resolution)
            tokens_tuple = self.token_resolver.get_or_resolve_candle_tokens(candle_start_sec)
            up_tok = tokens_tuple[0] if tokens_tuple else None
            dn_tok = tokens_tuple[1] if tokens_tuple else None

            # Fetch 100% Live Order Book Bid/Ask from Polymarket WebSocket stream
            up_bid, up_ask, dn_bid, dn_ask = self.polymarket_ws.get_live_bid_ask(up_tok, dn_tok)
            
            if up_bid is not None and up_ask is not None:
                mid_up = round((up_bid + up_ask) / 2.0, 3)
                mid_dn = round((dn_bid + dn_ask) / 2.0, 3)
                
                # Update live minute-by-minute High/Low tracker with live WS mid-prices
                self.minute_tracker.update_tick(int(now), mid_up, mid_dn, candle_start_sec)

                logger.info(
                    f"[LIVE STREAM TICK] BTC Spot: ${spot_price:,.2f} | "
                    f"OBI: {current_obi:+.4f} | "
                    f"Ongoing Bet ({ongoing_slug}) [WS STREAM]: UP (Bid: ${up_bid:.3f} / Ask: ${up_ask:.3f}) | DOWN (Bid: ${dn_bid:.3f} / Ask: ${dn_ask:.3f}) | "
                    f"5m Candle Start: {candle['Candle_Start']} | Vol: {candle['Volume']:.2f}"
                )
            else:
                logger.info(
                    f"[LIVE STREAM TICK] BTC Spot: ${spot_price:,.2f} | "
                    f"OBI: {current_obi:+.4f} | "
                    f"Ongoing Bet ({ongoing_slug}) [WS STREAM]: Polymarket Odds: [WAITING FOR WS TICK] | "
                    f"5m Candle Start: {candle['Candle_Start']} | Vol: {candle['Volume']:.2f}"
                )

            # Sprint 3 Real-time Position Monitoring (Fill Verification & Stop-Loss Monitoring)
            for c_start, pos in list(self.dry_strategy.active_positions.items()):
                if pos["Position_Status"] in ("PENDING", "OPEN"):
                    side = pos.get("Prediction_Side", "")
                    tok_id = pos.get("Token_Id", "")
                    b_val = up_bid if side == "UP" else dn_bid
                    a_val = up_ask if side == "UP" else dn_ask
                    prev_st = pos["Position_Status"]

                    pos_updated = self.dry_strategy.check_and_update_positions(c_start, tok_id, b_val, a_val)
                    if pos_updated:
                        new_st = pos_updated["Position_Status"]
                        if prev_st == "PENDING" and new_st == "OPEN":
                            self.notifier.notify_fill(
                                c_start, side, pos_updated["Average_Fill_Price"],
                                pos_updated["Filled_Quantity"], pos_updated["Transaction_Price"]
                            )
                        elif prev_st == "OPEN" and new_st == "CLOSED" and pos_updated.get("Exit_Reason") == "STOP_LOSS":
                            self.notifier.notify_stop_loss(c_start, pos_updated["Exit_Price"], pos_updated["Pnl"])

    def _handle_liquidation(self, side: str, qty: float, price: float) -> None:
        """
        Processes liquidation events.
        """
        self.order_flow.process_liquidation(side, qty, price)

    def _handle_ws_reconnect(self) -> None:
        """
        Triggers REST warmup/backfill gap repair on WebSocket reconnect.
        """
        logger.info("WebSocket reconnected. Executing REST warmup/backfill gap repair...")
        self.candle_cache.warmup_from_rest(symbol="BTCUSDT", interval="5m", limit=500, async_writer=self.async_writer)

    def start(self) -> None:
        """
        Initializes database, warms up cache, and starts background services.
        """
        logger.info("==================================================")
        logger.info(" Starting Polymarket BTC-5min Prediction Bot ")
        logger.info(f" Execution Mode: {'[SIMULATION DRY-RUN]' if config.is_dry_run() else '[LIVE TRADING]'}")
        logger.info("==================================================")
        
        # 1. Initialize SQLite Database & Tables (Sprint 0)
        logger.info(f"Initializing PolyDB database at '{self.db_path}'...")
        self.db_manager.init_db()
        logger.info("Database schemas (BTC_OHCLV, Odds_OHCLV, Positions) active in WAL mode.")

        # 2. Start Async DB Queue Writer
        logger.info("Starting AsyncDBWriter background thread worker...")
        self.async_writer.start()

        # 3. Sprint 3 Telegram Notifier & Command Router Workers
        self.notifier.start()
        self.telegram_bot.start()

        # 4. Sprint 3 Cold-Start Boot Reconciler
        self.reconciler.reconcile_on_boot(self.dry_strategy, self.risk_engine)

        # 5. Warm up CandleCache via REST API & populate database (Sprint 1)
        logger.info("Executing initial Binance REST API candle cache warmup and database seeding...")
        self.candle_cache.warmup_from_rest(symbol="BTCUSDT", interval="5m", limit=500, async_writer=self.async_writer)

        # 6. Start Binance Futures WebSocket Client (Sprint 1)
        logger.info("Connecting to Binance Futures WebSockets (@kline_5m, @depth10@100ms, @forceOrder)...")
        self.ws_client.start()

        # 7. Start Polymarket CLOB WebSocket Client (Sprint 2)
        logger.info("Connecting to Polymarket CLOB WebSocket stream (wss://ws-subscriptions-clob.polymarket.com)...")
        self.polymarket_ws.start()

        # 8. Check Polymarket API & CLOB Connection Health (Sprint 2)
        logger.info("Verifying Polymarket Gamma & CLOB API connections...")
        self.token_resolver.check_polymarket_health()

        # Immediately subscribe to current active candle contract if resolved
        now_ts = int(time.time())
        curr_candle_ts_ms = (now_ts // 300) * 300 * 1000
        curr_tokens = self.token_resolver.resolve_next_candle_tokens(curr_candle_ts_ms)
        if curr_tokens:
            self.polymarket_ws.subscribe_tokens(curr_tokens[1], curr_tokens[2])
            time.sleep(0.4)  # 0.4s WS warmup pause for initial book snapshot frame

        self.running = True
        logger.info("Bot engine initialized successfully. Real-time stream ingestion, ML Engine & Execution active.")

    def stop(self) -> None:
        """
        Gracefully stops background services and flushes pending writes.
        """
        logger.info("Initiating graceful shutdown...")
        self.running = False

        if hasattr(self, "telegram_bot"):
            logger.info("Stopping Telegram command router...")
            self.telegram_bot.stop()

        if hasattr(self, "notifier"):
            logger.info("Stopping Telegram notifier...")
            self.notifier.stop()

        if hasattr(self, "polymarket_ws"):
            logger.info("Stopping Polymarket WebSocket client...")
            self.polymarket_ws.stop()

        if hasattr(self, "ws_client"):
            logger.info("Stopping Binance WebSocket client...")
            self.ws_client.stop(timeout=3.0)

        if hasattr(self, "async_writer"):
            logger.info("Flushing pending database write queue...")
            self.async_writer.stop(timeout=5.0)

        if hasattr(self, "db_manager"):
            self.db_manager.close_thread_connection()

        logger.info("Shutdown complete. Polymarket Bot stopped.")

    def run_loop(self) -> None:
        """
        Main execution loop listening for system signals and orchestrating components.
        """
        self.start()

        def signal_handler(sig, frame):
            logger.info(f"Signal {sig} received.")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            logger.info("Press Ctrl+C in your terminal to stop the bot.")
            while self.running:
                now_ts = int(time.time())
                now_sec = now_ts % 300

                # T-5s Pre-Flight Token Resolution Trigger (at 4m55s / 295s into interval)
                if now_sec == 295 and self._last_preflight_sec != now_ts:
                    self._last_preflight_sec = now_ts
                    curr_candle_ts_ms = (now_ts // 300) * 300 * 1000
                    curr_tok_info = self.token_resolver.cached_tokens.get(str(curr_candle_ts_ms))
                    curr_up = curr_tok_info[1] if curr_tok_info else None
                    curr_dn = curr_tok_info[2] if curr_tok_info else None

                    next_candle_ts_ms = (curr_candle_ts_ms // 1000 + 300) * 1000
                    logger.info("T-5s Pre-Flight Trigger Fired. Resolving Polymarket token contract IDs...")
                    resolved = self.token_resolver.resolve_next_candle_tokens(next_candle_ts_ms)
                    next_up = resolved[1] if resolved else None
                    next_dn = resolved[2] if resolved else None

                    # Subscribe to BOTH current active candle tokens AND upcoming candle tokens
                    self.polymarket_ws.subscribe_tokens(curr_up, curr_dn, next_up, next_dn)

                # Wall-clock 5m boundary finalization check
                finalized_candle = self.candle_cache.check_clock_boundary(self.order_flow, self.async_writer)
                if finalized_candle:
                    self._execute_ml_inference_cycle(finalized_candle)

                    # Boundary Handoff: Re-subscribe with new active candle tokens FIRST (indices 0 & 1)
                    # to force Polymarket WS server to return full book snapshot frame immediately for new candle
                    new_active_ts_ms = (now_ts // 300) * 300 * 1000
                    new_tok_info = self.token_resolver.cached_tokens.get(str(new_active_ts_ms))
                    if not new_tok_info:
                        # Fallback on-the-spot resolution if cache miss
                        res = self.token_resolver.retry_fallback_at_t0(new_active_ts_ms)
                        if res:
                            new_tok_info = res

                    if new_tok_info:
                        new_up, new_dn = new_tok_info[1], new_tok_info[2]
                        self.polymarket_ws.reconnect_for_tokens(new_up, new_dn)

                time.sleep(1.0)
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            logger.error(f"Unexpected error in bot main loop: {e}", exc_info=True)
            self.stop()


def main():
    bot = PolymarketBot()
    bot.run_loop()


if __name__ == "__main__":
    main()
