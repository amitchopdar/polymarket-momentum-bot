# 🤖 Polymarket BTC 5-Minute Prediction Bot

An autonomous, ultra-low-latency algorithmic prediction and trading bot for Polymarket 5-minute Bitcoin binary options (`btc-updown-5m-timestamp`).

---

## 🔒 **1. Security & Configuration Architecture**

To ensure **0.00% secret exposure** on public repositories:
- **Public Trading Parameters:** Configured directly in [`src/config.py`](file:///Users/kamalasahu/polymarket-bot/src/config.py) (Target prices, probability thresholds, stop-loss limits).
- **Private Secrets & Credentials:** Loaded dynamically via Environment Variables or a private `.env` file (Bot tokens, chat IDs, admin user lists, API keys).
- **Git Safety:** `.env`, `*.key`, `PolyDB.sqlite`, `venv/`, and logs are strictly ignored by `.gitignore`.

---

## ⚙️ **2. How to Update Configuration & Settings**

### **A. Updating Non-Sensitive Trading Parameters (Target Prices, Stop-Loss, Probability)**
Edit parameters in [`src/config.py`](file:///Users/kamalasahu/polymarket-bot/src/config.py):
* **`USER_TARGET_BUY_PRICE = 0.48`** — Target limit buy order price ($0.48 / $0.40).
* **`USER_STOP_LOSS_PRICE = 0.30`** — Stop loss exit price ($0.30 / $0.20).
* **`USER_MIN_MODEL_PROBABILITY = 0.51`** — Minimum directional probability confidence threshold (51.0%).
* **`USER_ORDER_TIMEOUT_SEC = 300.0`** — Unfilled limit buy order timeout cap (300 seconds / 5 minutes).

*To apply updates to Oracle Cloud:*
```bash
git commit -am "Update trading parameters"
git push origin main

# On Oracle server terminal:
cd ~/polymarket-bot && git pull && sudo systemctl restart polymarket-bot
```

---

### **B. Updating Private Secrets (Telegram Tokens, Admin User IDs, API Keys)**
Private secrets live in your private `.env` file on your server (`/home/ubuntu/polymarket-bot/.env`):

```ini
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE
TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE
TELEGRAM_AUTHORIZED_USER_IDS=USER_ID_1,USER_ID_2
```

*To update secrets on Oracle Cloud:*
1. SSH into server: `ssh -i /path/to/ssh-key.key ubuntu@152.67.66.51`
2. Edit private `.env`: `nano ~/polymarket-bot/.env`
3. Restart bot: `sudo systemctl restart polymarket-bot`

---

### **C. Quick Remote Control from Telegram (Zero Editing Required)**
From your phone on Telegram, send:
* **/status** — View live system health, active positions, model win rate, and current model PnL.
* **/pnl** — View lifetime net PnL summary.
* **/deactivate** — Temporarily pause live trading engine.
* **/activate** — Resume live trading engine.
* **/dryrun on** — Enable dry-run simulation mode.
* **/dryrun off** — Enable live trading mode.

---

## ⚡ **3. Local Execution Quickstart**

```bash
cd /Users/kamalasahu/polymarket-bot

# 1. Environment Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Run Test Suite (29 Tests - 100% Green)
PYTHONPATH=. pytest tests/ -v

# 3. Bootstrap History & Train Champion Model
PYTHONPATH=. python3 scripts/bootstrap_history.py
PYTHONPATH=. python3 scripts/train_model.py --force --trials 30

# 4. Run Bot Locally
PYTHONPATH=. python3 main.py
```

---

## ☁️ **4. Oracle Cloud Server Management (`152.67.66.51`)**

- **SSH Connection:**
  ```bash
  ssh -i /Users/kamalasahu/Downloads/ssh-key-2026-07-26.key ubuntu@152.67.66.51
  ```
- **Service Status & Logs:**
  ```bash
  sudo systemctl status polymarket-bot
  sudo journalctl -u polymarket-bot -f
  ```
- **Restart 24/7 Daemon:**
  ```bash
  sudo systemctl restart polymarket-bot
  ```
- **Flush SQLite WAL to Database:**
  ```bash
  sqlite3 ~/polymarket-bot/PolyDB.sqlite "PRAGMA wal_checkpoint(FULL);"
  ```
