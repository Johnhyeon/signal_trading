import os
from dotenv import load_dotenv
from telethon import TelegramClient
from pybit.unified_trading import HTTP
import telegram

# .env 파일에서 환경 변수 로드
load_dotenv()

# 환경 변수에서 API 키 정보 가져오기
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
BYBIT_API_KEY = os.getenv('BYBIT_API_KEY')
BYBIT_SECRET_KEY = os.getenv('BYBIT_SECRET_KEY')
TARGET_CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID'))
TELE_BYBIT_BOT_TOKEN = os.getenv('TELE_BYBIT_BOT_TOKEN')
TELE_BYBIT_LOG_CHAT_ID = int(os.getenv('TELE_BYBIT_LOG_CHAT_ID'))

# --- 테스트용 채널 ID (필요시 사용)
TEST_CHANNEL_ID = int(os.getenv('TEST_CHANNEL_ID'))

# Bybit 클라이언트 초기화
bybit_client = HTTP(
    testnet=False,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_SECRET_KEY
)
# 텔레그램 유저 클라이언트 초기화
client = TelegramClient('my_session', TELEGRAM_API_ID, TELEGRAM_API_HASH)
# 텔레그램 봇 클라이언트 초기화
bybit_bot = telegram.Bot(token=TELE_BYBIT_BOT_TOKEN)

# 다른 모듈에서 사용하기 위해 변수를 노출시킵니다.
__all__ = ['bybit_client', 'client', 'bybit_bot', 'TARGET_CHANNEL_ID', 'TELE_BYBIT_LOG_CHAT_ID']