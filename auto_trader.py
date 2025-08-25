import asyncio
import re
import random
import os
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient, events
from pybit.unified_trading import HTTP
import decimal
import telegram

# .env 파일에서 환경 변수 로드
load_dotenv()

# 환경 변수에서 API 키 정보 가져오기
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
BYBIT_API_KEY = os.getenv('BYBIT_API_KEY')
BYBIT_SECRET_KEY = os.getenv('BYBIT_SECRET_KEY')
# TEST_CHANNEL_ID = int(os.getenv('TEST_CHANNEL_ID'))
TARGET_CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID'))
TELE_BYBIT_BOT_TOKEN = os.getenv('TELE_BYBIT_BOT_TOKEN')
TELE_BYBIT_LOG_CHAT_ID = os.getenv('TELE_BYBIT_LOG_CHAT_ID')


print("Application run...")

# Bybit와 Telegram 클라이언트 초기화
bybit_client = HTTP(
    testnet=False,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_SECRET_KEY
)
client = TelegramClient('my_session', TELEGRAM_API_ID, TELEGRAM_API_HASH)
bybit_bot = telegram.Bot(token=TELE_BYBIT_BOT_TOKEN)

print("Instance created")

# -----------------
# 텔레그램 메시지 파싱 함수
# -----------------
# (이 부분은 기존 코드와 동일)
def parse_telegram_message(message_text):
    """
    텔레그램 메시지 텍스트를 파싱하여 주문 정보를 추출합니다.
    """
    try:
        symbol_match = re.search(r'\$([A-Z0-9]+)', message_text)
        leverage_match = re.search(r'Leverage:\s*x(\d+)', message_text)
        fund_match = re.search(r'Fund:\s*(\d+)%', message_text)
        entry_match = re.search(r'Entry:\s*([\d]+xx|[\d]+x|\d+(?:\.\d+)?)', message_text)
        sl_match = re.search(r'Stop Loss:\s*([\d\.]+)', message_text)
        tp_matches = re.findall(r'TP\d+:\s*([\d\.]+)', message_text)
        position_type = "Buy" if "Long" in message_text else "Sell" if "Short" in message_text else None
        
        if not all([symbol_match, leverage_match, fund_match, entry_match, sl_match, tp_matches, position_type]):
            print("메시지 형식이 올바르지 않아 파싱에 실패했습니다.")
            return None

        symbol = symbol_match.group(1) + "USDT"
        leverage = int(leverage_match.group(1))
        fund_percentage = 0.05
        stop_loss = float(sl_match.group(1))
        targets = [float(tp) for tp in tp_matches]

        entry_price_str = entry_match.group(1)
        print("Entry price str:", entry_price_str)
        # entry_price = float(entry_price_str.replace('x', ''))
        # print("Initial entry price:", entry_price)

        if 'xx' in entry_price_str:
            base_price = int(entry_price_str.replace('xx', ''))
            random_digits = random.randint(0, 99)
            entry_price = decimal.Decimal(str(base_price * 100 + random_digits))
        elif entry_price_str.endswith('x'):
            if '.' in entry_price_str:
                # 0.84x 와 같은 소수점 케이스
                base_price = float(entry_price_str.replace('x', ''))
                random_digit = random.randint(0, 9)
                entry_price = float(str(base_price) + str(random_digit))
            else:
                # 451x 와 같은 정수 케이스
                base_price = int(entry_price_str.replace('x', ''))
                random_digit = random.randint(0, 9)
                entry_price = float(str(base_price) + str(random_digit))
        else:
            # x나 xx가 없는 경우 (예: 0.84 또는 451)
            entry_price = float(entry_price_str)

        print("Final entry price:", entry_price)
        return {
            'symbol': symbol,
            'side': position_type,
            'leverage': leverage,
            'fund_percentage': fund_percentage,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'targets': targets
        }
    except Exception as e:
        print(f"메시지 파싱 중 오류 발생: {e}")
        return None

# -----------------
# Bybit 주문 실행 함수
# -----------------
# (이 부분은 기존 코드와 동일)
def execute_bybit_order(order_info):
    """
    Bybit API를 사용하여 주문을 실행합니다.
    """
    print(f"Bybit 주문 실행 중: {order_info['symbol']}")
    try:
        # 1. 계좌 잔고 조회 및 주문 수량 계산
        wallet_balance = bybit_client.get_wallet_balance(accountType="UNIFIED")
        usdt_balance = next((item for item in wallet_balance['result']['list'][0]['coin'] if item['coin'] == 'USDT'), None)
        
        if usdt_balance:
            total_usdt = float(usdt_balance['equity'])
            trade_amount = total_usdt * order_info['fund_percentage']
            print("총 USDT 잔고:", total_usdt)
            print("거래에 사용할 USDT 금액:", trade_amount)
        else:
            print("USDT 잔고를 찾을 수 없습니다.")
            return

        # 총 거래 금액 (레버리지를 적용한 금액)
        total_trade_value = trade_amount * order_info['leverage']

        # BTC, ETH와 같은 종목의 주문 수량 계산 (코인 수량)
        order_qty = total_trade_value / float(order_info['entry_price'])
        print("총 거래 금액:", total_trade_value)
        print("계산된 주문 수량(코인):", order_qty)

        # 2. 종목 정보 조회 (가장 중요한 부분)
        instrument_info = bybit_client.get_instruments_info(
            category="linear",
            symbol=order_info['symbol']
        )
        # 종목별 Lot Size 정밀도 정보 추출
        lot_size_filter = instrument_info['result']['list'][0]['lotSizeFilter']
        qty_step = float(lot_size_filter['qtyStep'])
        
        # 3. 주문 수량을 정밀도에 맞게 조정
        # 수량을 qty_step의 배수로 맞춥니다.
        adjusted_qty = round(order_qty / qty_step) * qty_step
        
        # 4. 레버리지 설정 (이전 로직 유지)
        position_info = bybit_client.get_positions(
            category="linear",
            symbol=order_info['symbol']
        )
        current_leverage = int(position_info['result']['list'][0]['leverage'])

        if current_leverage != order_info['leverage']:
            bybit_client.set_leverage(
                category="linear",
                symbol=order_info['symbol'],
                buyLeverage=str(order_info['leverage']),
                sellLeverage=str(order_info['leverage'])
            )
            print(f"레버리지를 {order_info['leverage']}x로 설정했습니다.")

        # 5. 주문 실행 (조정된 수량 사용)
        order_result = bybit_client.place_order(
            category="linear",
            symbol=order_info['symbol'],
            side=order_info['side'],
            orderType="Limit",
            qty=str(adjusted_qty), # 조정된 수량 사용
            price=str(order_info['entry_price']),
            takeProfit=str(order_info['targets'][0]),
            stopLoss=str(order_info['stop_loss'])
        )

        # 6. 주문이 성공적으로 접수되면 봇으로 메시지 전송
        if order_result and order_result['retCode'] == 0:
            print("주문이 성공적으로 접수되었습니다.")
            print(order_result)

            # 주문 정보 요약 메시지 생성
            message_summary = (
                "📈 **자동 주문 접수 완료**\n"
                f"▪️ **종목:** {order_info['symbol']}\n"
                f"▪️ **포지션:** {order_info['side']}\n"
                f"▪️ **진입가:** {order_info['entry_price']}\n"
                f"▪️ **수량:** {adjusted_qty}\n"
                f"▪️ **레버리지:** {order_info['leverage']}x\n"
                f"▪️ **손절가:** {order_info['stop_loss']}\n"
                f"▪️ **목표가:** {', '.join(map(str, order_info['targets']))}"
            )

            # 봇을 통해 텔레그램으로 메시지 전송
            # 파싱된 order_info를 사용하여 메시지 생성 및 전송
            asyncio.run_coroutine_threadsafe(
                bybit_bot.send_message(
                    chat_id=TELE_BYBIT_LOG_CHAT_ID,
                    text=message_summary,
                    parse_mode='Markdown'
                ),
                asyncio.get_event_loop()
            )

        else:
            print("주문 접수 실패:", order_result)

    except Exception as e:
        print(f"Bybit 주문 중 오류 발생: {e}")
# -----------------
# 텔레그램 메시지 이벤트 핸들러
# -----------------
# (이 부분은 기존 코드와 동일)
async def my_event_handler(event):
    message_text = event.message.message
    print(f"\n새로운 메시지 감지:\n{message_text}")
    
    order_info = parse_telegram_message(message_text)
    
    if order_info:
        execute_bybit_order(order_info)

    if event.sender_id == TARGET_CHANNEL_ID:
    # if event.sender_id == TEST_CHANNEL_ID:
        now = datetime.now()
        print("Target spoke", "time:", now.date(), now.time())
    await asyncio.sleep(0) 
    

# -----------------
# 메인 함수 (스크립트 실행)
# -----------------
# (이 부분은 기존 코드와 동일)
async def main():
    await client.start()
    print("Connect start...")
    client.add_event_handler(my_event_handler, events.NewMessage(chats=TARGET_CHANNEL_ID))
    # client.add_event_handler(my_event_handler, events.NewMessage(chats=TEST_CHANNEL_ID))
    print("Listening for new massage")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())