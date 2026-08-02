# Polymarket Momentum Bot V2 - Standalone Odds Momentum Engine

High-frequency, tick-by-tick odds momentum trading bot for Polymarket 5-minute Bitcoin prediction markets.

---

## 🚀 Key Strategy Features

* **Tick-by-Tick Odds Momentum Detection:** Ingests live order book feeds from Polymarket CLOB WebSocket (`wss://ws-subscriptions-clob.polymarket.com/ws/market`) and maintains a 10-second sliding tick window.
* **10-Second Window Minimum Price Surge (`P_now - P_min_10s`):** Calculates $\Delta \text{Odds} = P_{\text{now}} - P_{\text{min\_10s}} \ge +0.15$ ($15$ cents) within 10 seconds.
* **Minimum Entry Odds Floor ($\ge \$0.65$):** Entry signal only fires if current ask price is $\ge \$0.65$ ($65$ cents).
* **Tiered Take-Profit (TP) & Stop-Loss (SL) Architecture:**
  * **Tier 1 (Entry $< \$0.75$):**  
    * **Take Profit:** $\text{Fill Price} + \$0.05$ ($+5$ cents gain).  
    * **Stop Loss:** $\text{Fill Price} - \$0.10$ ($-10$ cents drop).
  * **Tier 2 (Entry $\ge \$0.75$):**  
    * **Take Profit:** Fixed at **$\$0.995$** (or user-configured target).  
    * **Stop Loss:** Fixed at **$\$0.49$** ($49$ cents) (or user-configured target).
* **Automatic Candle Expiry Rollover:** Closes open positions on 5-minute candle boundaries as `EXPIRED` and unlocks position guard.
* **Real-Time Telegram Alerts:** Sends instant entry, exit, TP, SL, and expiry notifications to authorized chat IDs.
* **Isolated SQLite Database:** Tracks all trades in `PolyDB_V2.sqlite`.

---

## 📖 Step-by-Step Guide to Run Locally on Mac

### **Step 1: Open Terminal**
Press **`Cmd + Space`**, type **`Terminal`**, and press **Enter**.

### **Step 2: Navigate to V2 Directory**
```bash
cd /Users/kamalasahu/polymarket-bot-v2
```

### **Step 3: Run Unit Tests**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v
```

### **Step 4: Launch Bot**
```bash
PYTHONPATH=. python3 main.py
```

### **Step 5: Stop Bot**
Press **`Ctrl + C`** in your Terminal window for graceful shutdown.

---

## ☁️ End-to-End Oracle Cloud Docker Deployment Guide

Follow these steps to host **Polymarket Momentum Bot V2** as a separate Docker container on your **Oracle Cloud Server (`152.67.66.51`)**:

### **Phase 1: Local Mac Setup & GitHub Push**

1. **Commit & Push Code to GitHub from Mac Terminal:**
   ```bash
   cd /Users/kamalasahu/polymarket-bot-v2
   git add .
   git commit -m "Production Polymarket Momentum Bot Setup"
   git push -u origin main
   ```

---

### **Phase 2: Oracle Cloud Server Deployment (`152.67.66.51`)**

1. **SSH into Oracle Server:**
   ```bash
   ssh -i /Users/kamalasahu/Downloads/ssh-key-2026-07-26.key ubuntu@152.67.66.51
   ```

2. **Install Docker & Docker Compose (If needed):**
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y docker.io docker-compose-plugin
   sudo systemctl enable --now docker
   sudo usermod -aG docker ubuntu
   ```

3. **Clone Repo & Create `.env`:**
   ```bash
   cd /home/ubuntu
   git clone https://github.com/amitchopdar/polymarket-momentum-bot.git
   cd polymarket-momentum-bot

   cat << 'EOF' > .env
   EXECUTION_MODE="DRY_RUN"
   TELEGRAM_BOT_TOKEN="8827575847:AAHi642Hnf8r2Vk7_XyIQM8ygR-irdP1J3A"
   TELEGRAM_CHAT_ID="488798563,835915433"
   TELEGRAM_AUTHORIZED_USER_IDS="488798563,835915433"
   POLYMARKET_API_KEY=""
   POLYMARKET_SECRET=""
   POLYMARKET_PASSPHRASE=""
   POLYMARKET_PRIVATE_KEY=""
   EOF
   ```

4. **Build & Launch Container:**
   ```bash
   touch PolyDB_V2.sqlite
   docker compose up -d --build
   ```

---

### **Phase 3: Container Management & Logs**

* **View Live Container Logs:**
  ```bash
  docker logs -f polymarket-bot-v2
  ```
* **Check Running Containers:**
  ```bash
  docker ps
  ```
* **Restart Container:**
  ```bash
  docker compose restart
  ```
* **Pull GitHub Updates & Rebuild:**
  ```bash
  cd /home/ubuntu/polymarket-momentum-bot
  git pull
  docker compose up -d --build
  ```
