"""Tarayıcı ayarları — telefonda GitHub Secrets ile ezilebilir."""

import os

BITGET_BASE = "https://api.bitget.com"
PRODUCT_TYPE = "USDT-FUTURES"

# 15m kaldıraç için daha erken sinyal, 1H daha az gürültü
TIMEFRAME = os.getenv("TIMEFRAME", "15m")
CANDLE_LIMIT = 120

# Önce hacimle süz, sonra mum çek (Actions süresini tutar)
MIN_USDT_VOLUME_24H = float(os.getenv("MIN_USDT_VOLUME_24H", "2000000"))
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "80"))

# 6.5 / 7 eşiğin
ALERT_SCORE = float(os.getenv("ALERT_SCORE", "7.0"))
STRONG_SCORE = float(os.getenv("STRONG_SCORE", "7.6"))
MAX_ALERTS_PER_RUN = int(os.getenv("MAX_ALERTS_PER_RUN", "3"))

# Aynı coin+yön tekrar spam olmasın
ALERT_COOLDOWN_MIN = int(os.getenv("ALERT_COOLDOWN_MIN", "180"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

STATE_PATH = os.getenv("STATE_PATH", "docs/state.json")
LATEST_PATH = os.getenv("LATEST_PATH", "docs/latest.json")

# 300$ hesap — risk yüzde ile gider, kaldıraç tavanı var
ACCOUNT_EQUITY = float(os.getenv("ACCOUNT_EQUITY", "300"))
RISK_PCT_LOW = float(os.getenv("RISK_PCT_LOW", "0.01"))      # %1 = $3
RISK_PCT_MID = float(os.getenv("RISK_PCT_MID", "0.015"))     # %1.5 = $4.5
RISK_PCT_HIGH = float(os.getenv("RISK_PCT_HIGH", "0.02"))    # %2 = $6
MAX_LEVERAGE_LOW = int(os.getenv("MAX_LEVERAGE_LOW", "3"))
MAX_LEVERAGE_MID = int(os.getenv("MAX_LEVERAGE_MID", "5"))
MAX_LEVERAGE_HIGH = int(os.getenv("MAX_LEVERAGE_HIGH", "5"))
MAX_LEVERAGE_BTC = int(os.getenv("MAX_LEVERAGE_BTC", "8"))
MIN_MARGIN_USD = float(os.getenv("MIN_MARGIN_USD", "15"))
