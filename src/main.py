import asyncio
from datetime import datetime
from telethon import events

# 다른 파일에서 필요한 것들을 불러옵니다.
from api_clients import client, TARGET_CHANNEL_ID, TEST_CHANNEL_ID
from message_parser import parse_telegram_message, parse_cancel_message
from trade_executor import execute_bybit_order, active_orders, bybit_client, cancel_bybit_order, send_bybit_cancel_msg

print("Application run...")
print("Instance created")

# -----------------
# 텔레그램 메시지 이벤트 핸들러
# -----------------
@client.on(events.NewMessage(chats=TARGET_CHANNEL_ID, outgoing=True))
async def my_event_handler(event):
    message_text = event.message.message

    # 'Cancel' 메시지인지 먼저 확인
    symbol_to_cancel = parse_cancel_message(message_text)
    if symbol_to_cancel:
        await cancel_bybit_order(symbol_to_cancel)
        return # 취소 메시지이므로 주문 로직은 실행하지 않음
    
    order_info = parse_telegram_message(message_text)
    
    if order_info:
        # 메시지 ID를 인수로 전달
        execute_bybit_order(order_info, event.id)

    now = datetime.now()
    print("Target spoke", "time:", now.date(), now.time())

##### 테스트용
@client.on(events.NewMessage(chats=TEST_CHANNEL_ID, outgoing=True))
async def my_event_handler(event):
    message_text = event.message.message

    # 'Cancel' 메시지인지 먼저 확인
    symbol_to_cancel = parse_cancel_message(message_text)
    if symbol_to_cancel:
        await cancel_bybit_order(symbol_to_cancel)
        return # 취소 메시지이므로 주문 로직은 실행하지 않음
    
    order_info = parse_telegram_message(message_text)
    
    if order_info:
        # 메시지 ID를 인수로 전달
        execute_bybit_order(order_info, event.id)    
    # --- 테스트용 채널 메시지 감지 ---
    if event.sender_id == TEST_CHANNEL_ID:
        now = datetime.now()
        print("------------Test Channal------------")
        print("Target spoke", "time:", now.date(), now.time())
    await asyncio.sleep(0) 
    # --- 테스트용 채널 메시지 감지 ---

@client.on(events.MessageEdited)
async def handle_edited_message(event):
    global active_orders
    
    message_id = event.id
    
    # 해당 메시지 ID의 주문 정보가 딕셔너리에 있는지 확인
    if message_id not in active_orders:
        return

    print(f"\n[알림] 기존 주문과 관련된 메시지가 수정되었습니다. ID: {message_id}")
    
    try:
        # 기존 주문 정보 가져오기
        existing_order_info = active_orders.pop(message_id, None)
        
        if not existing_order_info:
            print(f"오류: 기존 주문 정보를 찾을 수 없습니다. ID: {message_id}")
            return
            
        bybit_order_id = existing_order_info['orderId']
        symbol_to_cancel = existing_order_info['symbol']

        # 1. 기존 주문 취소
        cancel_result = bybit_client.cancel_order(
            category="linear",
            symbol=symbol_to_cancel,
            orderId=bybit_order_id
        )
        
        if cancel_result['retCode'] == 0:
            print(f"기존 주문 {bybit_order_id}가 성공적으로 취소되었습니다.")
            await send_bybit_cancel_msg(symbol_to_cancel)
        else:
            print(f"기존 주문 취소 실패: {cancel_result['retMsg']}")
            # 이미 체결된 주문이라 취소에 실패한 경우에도 재주문 로직은 계속 진행

        # 2. 수정된 메시지 내용 파싱
        updated_order_info = parse_telegram_message(event.message.message)
        if not updated_order_info:
            print("수정된 메시지 파싱에 실패하여 주문을 수정하지 않습니다.")
            return

        # 3. 새로운 주문 생성 (기존 execute_bybit_order 재사용)
        execute_bybit_order(updated_order_info, message_id)

    except Exception as e:
        print(f"주문 수정 중 오류 발생: {e}")

# -----------------
# 메인 함수 (스크립트 실행)
# -----------------
async def main():
    await client.start()
    print("Connect start...")
    print("Listening for new message...")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())