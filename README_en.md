# 📈 Telegram-based Automated Trading Bot

An automated trading bot that detects signals from a Telegram channel and executes trades on Bybit Futures. The bot parses specific Telegram messages, manages orders in real-time via the Bybit API, and sends all results to a log channel.

---
## ✨ Key Features

### 🔔 Real-time Telegram Message Detection
Monitors trading signal messages from a designated channel.

### 🧩 Flexible Message Parsing
Extracts key information like Symbol, Entry Price, Leverage, Stop Loss, and Take Profit from various signal formats using regular expressions.

### ⚡ Automatic Order Execution
Automatically executes Market or Limit orders based on the parsed information.

### 📊 Automated Order Quantity Calculation
Calculates order quantity automatically based on your account balance and the `Fund` percentage specified in the signal.

### 🔄 Order Modification & Cancellation
- Modifies orders by canceling the old one and placing a new one when a signal message is edited.
- Instantly cancels pending orders with a simple "Cancel" command.
- Moves Stop Loss to the entry price with the "Move SL = entry" command.
- Moves Stop Loss to TP1 with the "Move SL = TP1" command.
- Moves Stop Loss to TP2 with the "Move SL = TP2" command.

### 📡 Real-time Notifications
Sends trade execution and failure results to a dedicated Telegram log channel.

### 🛑 Duplicate Order Prevention
Automatically filters out duplicate trades for the same symbol.

### 💹 Portfolio Management (New Feature)
All trade records are saved in the `log/trade_log.json` file, which is used to generate statistical reports on total P&L, win rate, and more.

---
## 🛠️ Environment Setup

This project requires a `.env` file for configuration. Create a `.env` file in the project's root directory and enter the following values:
```
TELEGRAM_API_ID=
TELEGRAM_API_HASH=''
BYBIT_API_KEY=''
BYBIT_SECRET_KEY=''
TARGET_CHANNEL_ID=
TELE_BYBIT_BOT_TOKEN=
TELE_BYBIT_LOG_CHAT_ID=
TEST_CHANNEL_ID=
LANG_CODE='ko'  # Set to 'ko' or 'en' for language selection
```
**Note:** All messages and comments in the code are now managed separately in JSON files within the `lang/` directory.

### 🔑 How to Get .env Values

#### 1️⃣ Telegram API ID & HASH
1. Access [My Telegram API](https://my.telegram.org/) and log in.
2. Go to "API development tools" → "Create a new application".
<img width="457" height="180" alt="image" src="https://github.com/user-attachments/assets/a9d2e683-d45c-4420-9875-9a82af8e62bb" />
3. After creation, find your `api_id` and `api_hash`.
<img width="852" height="1137" alt="image" src="https://github.com/user-attachments/assets/81ec453b-45e7-4252-bc15-2b7b6758d81b" />
4. Enter the issued `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` into the `.env` file.

#### 2️⃣ Bybit API KEY & SECRET KEY
1. Log in to your Bybit account.
2. Go to "Account & Security" → "API Management".
<img width="372" height="665" alt="image" src="https://github.com/user-attachments/assets/6d55f5a1-32bc-4725-8579-d382f38e2cd3" />
<img width="1679" height="553" alt="image" src="https://github.com/user-attachments/assets/d7a9580f-1cdf-4f7d-b744-9098d9b1cf0c" />
3. Create a new API key and grant it "Trade" and "Account/Wallet" permissions.
<img width="1159" height="816" alt="image" src="https://github.com/user-attachments/assets/48f6b137-8734-404b-8ca5-1ec477811c70" />
4. Enter the issued `BYBIT_API_KEY` and `BYBIT_SECRET_KEY` into the `.env` file.

#### 3️⃣ Telegram Bot Token (TELE_BYBIT_BOT_TOKEN)
[ko: https://blog.naver.com/lifelectronics/223198582215]
[en: https://youtu.be/aupKH_J1xc0]
1. Search for `@BotFather` on Telegram.
2. Send the `/newbot` command to create a new bot.
3. Enter the issued HTTP API token into the `.env` file.

#### 4️⃣ Telegram Channel ID (TARGET_CHANNEL_ID, TEST_CHANNEL_ID, TELE_BYBIT_LOG_CHAT_ID)
1. Access [Telegram Web](https://web.telegram.org/) (login required) and get the channel ID from the URL.
2. For public channels, the ID starts with `-100`.  [ex) -1002340123456]
3. You can also use the `@get_id_bot` bot. Type `/get_id` to get the channel ID.
4. To add a test channel, create a new channel in the Telegram app and get its ID.
5. Enter the issued Channel ID into the `.env` file.

## 🚀 How to Run
### need to set venv in project path
https://www.w3schools.com/python/python_virtualenv.asp

### Install Packages
`pip install -r requirements.txt`

### Run
`python main.py`

### Or Run with .bat file
Modify the project path and virtual environment path inside the file before running.

`@echo off`
`rem D:\.. to your project root full path`
`cd "D:\..\signal_trading"`
`rem 'trading' virtual env Activation (Python venv Scripts path)`
`call "D:\..\signal_trading\venv\Scripts\activate"`
`rem move src`
`cd src`
`rem run main.py`
`python main.py`
`rem venv deactivate`
`call deactivate`
`pause`

# ⚠️ Disclaimer

This project is created for educational and research purposes only.
If you plan to use it for live trading, please thoroughly test it in a testnet environment.
Cryptocurrency trading involves high risk, and the user is solely responsible for all outcomes.
