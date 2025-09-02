import asyncio
from datetime import datetime
from telethon import events
import telegram

from api_clients import client, bybit_client, bybit_bot, TARGET_CHANNEL_ID, TEST_CHANNEL_ID, TELE_BYBIT_LOG_CHAT_ID
from message_parser import parse_telegram_message, parse_cancel_message
# update_stop_loss_to_entry 함수를 import합니다.
from trade_executor import execute_bybit_order, active_orders, bybit_client, cancel_bybit_order, send_bybit_failure_msg, send_bybit_cancel_msg, update_stop_loss_to_entry, update_stop_loss_to_tp1, update_stop_loss_to_tp2

print("Application run...")
print("Instance created")

# -----------------
# 텔레그램 메시지 이벤트 핸들러
# -----------------
@client.on(events.NewMessage(chats=TARGET_CHANNEL_ID))
async def my_event_handler(event):
    
    message_text = event.message.message
    print(f"\n새로운 메시지 감지:\n{message_text}")

    if event.is_reply:
        print("⚠️ 답장 메시지는 SL 핸들러에서 처리됩니다.")
        return
    
    # 'Cancel' 메시지인지 먼저 확인
    symbol_to_cancel = parse_cancel_message(message_text)
    if symbol_to_cancel:
        await cancel_bybit_order(symbol_to_cancel)
        return # 취소 메시지이므로 주문 로직은 실행하지 않음
    
    order_info = parse_telegram_message(message_text)
    
    if order_info:
        # ✅ 중복 주문 방지 필터링 조건 추가
        # active_orders 딕셔너리에서 현재 종목이 이미 주문되었는지 확인합니다.
        existing_symbol = next((v['symbol'] for v in active_orders.values() if v['symbol'] == order_info['symbol']), None)

        if existing_symbol:
            print(f"⚠️ **{order_info['symbol']}**에 대한 기존 주문이 있어 새로운 주문을 실행하지 않습니다.")
            # 사용자에게 알림 메시지를 보내는 것도 좋은 방법입니다.
            await send_bybit_failure_msg(order_info['symbol'], "기존 주문이 이미 존재합니다.")
            return

        # 메시지 ID를 인수로 전달
        execute_bybit_order(order_info, event.id)
    
    # if order_info:
    #     # 메시지 ID를 인수로 전달
    #     execute_bybit_order(order_info, event.id)

    now = datetime.now()
    print("Target spoke", "time:", now.date(), now.time())

@client.on(events.MessageEdited(chats=TARGET_CHANNEL_ID))
async def handle_edited_message(event):
    global active_orders
    message_id = event.id
    message_text = event.message.message
    print(f"\n메시지 수정 감지:\n{message_text}")

    if message_id not in active_orders:
        return

    print(f"\n[알림] 기존 주문과 관련된 메시지가 수정되었습니다. ID: {message_id}")
    
    try:
        existing_order_info = active_orders.pop(message_id, None)
        
        if not existing_order_info:
            print(f"오류: 기존 주문 정보를 찾을 수 없습니다. ID: {message_id}")
            return
            
        bybit_order_id = existing_order_info['orderId']
        symbol_to_cancel = existing_order_info['symbol']

        # 1. 기존 주문 취소 시도
        cancel_result = bybit_client.cancel_order(
            category="linear",
            symbol=symbol_to_cancel,
            orderId=bybit_order_id
        )

        if cancel_result['retCode'] == 0:
            print(f"기존 주문 {bybit_order_id}가 성공적으로 취소되었습니다.")
            await send_bybit_cancel_msg(symbol_to_cancel)
            
            # 2. 취소가 성공한 경우에만 새로운 메시지 파싱 및 주문 실행
            updated_order_info = parse_telegram_message(event.message.message)
            if updated_order_info:
                print("수정된 내용으로 새로운 주문을 생성합니다.")
                # execute_bybit_order가 async 함수로 변경되었다고 가정
                await execute_bybit_order(updated_order_info, message_id)
            else:
                print("수정된 메시지 파싱에 실패하여 주문을 수정하지 않습니다.")
                # 이 경우 기존 주문이 취소된 상태이므로 사용자에게 알려주는 것이 중요
                await send_bybit_failure_msg(symbol_to_cancel, "수정된 메시지 파싱 실패. 기존 주문 취소만 완료되었습니다.")

        else:
            # 3. 기존 주문 취소 실패 (이미 체결 또는 기타 사유)
            print(f"기존 주문 취소 실패: {cancel_result['retMsg']}")
            
            # 취소 실패 메시지 전송
            await send_bybit_failure_msg(symbol_to_cancel, f"기존 주문 취소 실패: {cancel_result['retMsg']}")
            # 이미 체결된 주문에 대한 메시지 처리가 필요하면 추가 로직 구현
            
    except Exception as e:
        print(f"주문 수정 중 오류 발생: {e}")
        await send_bybit_failure_msg(symbol_to_cancel, f"시스템 오류: {str(e)}")

# ✅ SL을 진입가로 변경하는 이벤트 핸들러 추가
# `reply_to` 속성을 사용하여 메시지가 답장인지 확인합니다.
@client.on(events.NewMessage(chats=TARGET_CHANNEL_ID, func=lambda e: e.is_reply))
async def handle_move_sl(event):
    global active_orders
    message_text = event.message.message.lower().replace(" ", "")
    
    # 'move sl = entry' 메시지인지 확인 (대소문자 무시)
    if 'movesl=entry' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            # 수정된 부분: orderId 대신 positionIdx와 side 사용
            await update_stop_loss_to_entry(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['entry_price'])
        else:
            await send_bybit_failure_msg("SL", f"원본 주문 정보를 찾을 수 없습니다. 메시지 ID: {original_msg_id}")

    elif 'movesl=tp1' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            if len(order_info['targets']) >= 1:
                # 수정된 부분: orderId 대신 positionIdx와 side 사용
                await update_stop_loss_to_tp1(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['targets'][0])
            else:
                await send_bybit_failure_msg("SL", f"TP1 가격 정보가 없습니다.")
        else:
            await send_bybit_failure_msg("SL", f"원본 주문 정보를 찾을 수 없습니다. 메시지 ID: {original_msg_id}")

    elif 'movesl=tp2' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            if len(order_info['targets']) >= 2:
                # 수정된 부분: orderId 대신 positionIdx와 side 사용
                await update_stop_loss_to_tp2(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['targets'][1])
            else:
                await send_bybit_failure_msg("SL", f"TP2 가격 정보가 없습니다.")
        else:
            await send_bybit_failure_msg("SL", f"원본 주문 정보를 찾을 수 없습니다. 메시지 ID: {original_msg_id}")

@client.on(events.NewMessage(chats=TARGET_CHANNEL_ID, func=lambda e: e.is_reply and 'cancel' in e.message.message.lower()))
async def handle_cancel_reply(event):
    global active_orders
    original_msg_id = event.reply_to_msg_id
    print(f"\n'Cancel' 답장 메시지 감지. 원본 메시지 ID: {original_msg_id}")
    
    if original_msg_id in active_orders:
        order_info = active_orders[original_msg_id]
        symbol = order_info['symbol']
        print(f"답장으로 온 'Cancel' 메시지 감지. {symbol} 주문을 취소합니다.")
        await cancel_bybit_order(symbol)
    else:
        print(f"⚠️ 원본 주문 정보를 찾을 수 없습니다. 메시지 ID: {original_msg_id}")
        await send_bybit_failure_msg("Cancel", "취소할 주문 정보를 찾을 수 없습니다.")

#=======================================================================================================================================#
##### 테스트용
@client.on(events.NewMessage(chats=TEST_CHANNEL_ID))
async def my_event_handler(event):
    message_text = event.message.message
    print(f"\n새로운 메시지 감지:\n{message_text}")
    
    # ✅ 답장 메시지인 경우 바로 종료
    if event.is_reply:
        print("⚠️ 답장 메시지는 다른 핸들러에서 처리됩니다.")
        return

    # # 'Cancel' 메시지인지 먼저 확인
    # symbol_to_cancel = parse_cancel_message(message_text)
    # if symbol_to_cancel:
    #     await cancel_bybit_order(symbol_to_cancel)
    #     return # 취소 메시지이므로 주문 로직은 실행하지 않음
    
    order_info = parse_telegram_message(message_text)
    
    if order_info:
        # ✅ 중복 주문 방지 필터링 조건 추가
        # active_orders 딕셔너리에서 현재 종목이 이미 주문되었는지 확인합니다.
        existing_symbol = next((v['symbol'] for v in active_orders.values() if v['symbol'] == order_info['symbol']), None)

        if existing_symbol:
            print(f"⚠️ **{order_info['symbol']}**에 대한 기존 주문이 있어 새로운 주문을 실행하지 않습니다.")
            # 사용자에게 알림 메시지를 보내는 것도 좋은 방법입니다.
            await send_bybit_failure_msg(order_info['symbol'], "기존 주문이 이미 존재합니다.")
            return

        # 메시지 ID를 인수로 전달
        execute_bybit_order(order_info, event.id)
    
    # if order_info:
    #     # 메시지 ID를 인수로 전달
    #     execute_bybit_order(order_info, event.id)    
    # # --- 테스트용 채널 메시지 감지 ---
    if event.sender_id == TEST_CHANNEL_ID:
        now = datetime.now()
        print("------------Test Channal------------")
        print("Target spoke", "time:", now.date(), now.time())
    await asyncio.sleep(0) 
    # --- 테스트용 채널 메시지 감지 ---

@client.on(events.MessageEdited(chats=TEST_CHANNEL_ID))
async def handle_edited_message(event):
    global active_orders
    message_id = event.id
    message_text = event.message.message
    print(f"\n메시지 수정 감지:\n{message_text}")

    if message_id not in active_orders:
        return

    print(f"\n[알림] 기존 주문과 관련된 메시지가 수정되었습니다. ID: {message_id}")
    
    try:
        existing_order_info = active_orders.pop(message_id, None)
        
        if not existing_order_info:
            print(f"오류: 기존 주문 정보를 찾을 수 없습니다. ID: {message_id}")
            return
            
        bybit_order_id = existing_order_info['orderId']
        symbol_to_cancel = existing_order_info['symbol']

        # 1. 기존 주문 취소 시도
        cancel_result = bybit_client.cancel_order(
            category="linear",
            symbol=symbol_to_cancel,
            orderId=bybit_order_id
        )

        if cancel_result['retCode'] == 0:
            print(f"기존 주문 {bybit_order_id}가 성공적으로 취소되었습니다.")
            await send_bybit_cancel_msg(symbol_to_cancel)
            
            # 2. 취소가 성공한 경우에만 새로운 메시지 파싱 및 주문 실행
            updated_order_info = parse_telegram_message(event.message.message)
            if updated_order_info:
                print("수정된 내용으로 새로운 주문을 생성합니다.")
                # execute_bybit_order가 async 함수로 변경되었다고 가정
                await execute_bybit_order(updated_order_info, message_id)
            else:
                print("수정된 메시지 파싱에 실패하여 주문을 수정하지 않습니다.")
                # 이 경우 기존 주문이 취소된 상태이므로 사용자에게 알려주는 것이 중요
                await send_bybit_failure_msg(symbol_to_cancel, "수정된 메시지 파싱 실패. 기존 주문 취소만 완료되었습니다.")

        else:
            # 3. 기존 주문 취소 실패 (이미 체결 또는 기타 사유)
            print(f"기존 주문 취소 실패: {cancel_result['retMsg']}")
            
            # 취소 실패 메시지 전송
            await send_bybit_failure_msg(symbol_to_cancel, f"기존 주문 취소 실패: {cancel_result['retMsg']}")
            # 이미 체결된 주문에 대한 메시지 처리가 필요하면 추가 로직 구현
            
    except Exception as e:
        print(f"주문 수정 중 오류 발생: {e}")
        await send_bybit_failure_msg(symbol_to_cancel, f"시스템 오류: {str(e)}")

@client.on(events.NewMessage(chats=TEST_CHANNEL_ID, func=lambda e: e.is_reply))
async def handle_move_sl(event):
    global active_orders
    message_text = event.message.message.lower().replace(" ", "")
    
    # 'move sl = entry' 메시지인지 확인 (대소문자 무시)
    if 'movesl=entry' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            # 수정된 부분: orderId 대신 positionIdx와 side 사용
            await update_stop_loss_to_entry(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['entry_price'])
        else:
            await send_bybit_failure_msg("SL", f"원본 주문 정보를 찾을 수 없습니다. 메시지 ID: {original_msg_id}")

    elif 'movesl=tp1' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            if len(order_info['targets']) >= 1:
                # 수정된 부분: orderId 대신 positionIdx와 side 사용
                await update_stop_loss_to_tp1(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['targets'][0])
            else:
                await send_bybit_failure_msg("SL", f"TP1 가격 정보가 없습니다.")
        else:
            await send_bybit_failure_msg("SL", f"원본 주문 정보를 찾을 수 없습니다. 메시지 ID: {original_msg_id}")

    elif 'movesl=tp2' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            if len(order_info['targets']) >= 2:
                # 수정된 부분: orderId 대신 positionIdx와 side 사용
                await update_stop_loss_to_tp2(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['targets'][1])
            else:
                await send_bybit_failure_msg("SL", f"TP2 가격 정보가 없습니다.")
        else:
            await send_bybit_failure_msg("SL", f"원본 주문 정보를 찾을 수 없습니다. 메시지 ID: {original_msg_id}")

@client.on(events.NewMessage(chats=TEST_CHANNEL_ID, func=lambda e: e.is_reply and 'cancel' in e.message.message.lower()))
async def handle_cancel_reply(event):
    global active_orders
    original_msg_id = event.reply_to_msg_id
    print(f"\n'Cancel' 답장 메시지 감지. 원본 메시지 ID: {original_msg_id}")
    
    if original_msg_id in active_orders:
        order_info = active_orders[original_msg_id]
        symbol = order_info['symbol']
        print(f"답장으로 온 'Cancel' 메시지 감지. {symbol} 주문을 취소합니다.")
        await cancel_bybit_order(symbol)
    else:
        print(f"⚠️ 원본 주문 정보를 찾을 수 없습니다. 메시지 ID: {original_msg_id}")
        await send_bybit_failure_msg("Cancel", "취소할 주문 정보를 찾을 수 없습니다.")

#=======================================================================================================================================#


# -----------------
# 메인 함수 (스크립트 실행)
# -----------------
async def main():
    await client.start()
    print("Connect start...")

    # --- 연결 상태 확인 로직 추가 ---
    try:
        # Bybit 연결 상태 확인
        balance = bybit_client.get_wallet_balance(accountType="UNIFIED")
        if balance['retCode'] == 0:
            print("✅ Bybit API 연결 성공!")
        else:
            print(f"❌ Bybit API 연결 실패: {balance['retMsg']}")

        # 텔레그램 봇 연결 상태 확인 (봇 정보 가져오기)
        bot_info = await bybit_bot.get_me()
        print(f"✅ 텔레그램 봇 연결 성공: @{bot_info.username}")
        
        # 시작 메시지를 로그 채널로 전송
        await bybit_bot.send_message(
            chat_id=TELE_BYBIT_LOG_CHAT_ID,
            text="📈 **트레이딩 봇 가동 시작**\nBybit 및 텔레그램 API 연결 성공."
        )
        # 텔레그램 채널 접근 권한 확인
        try:
            channel = await client.get_entity(TARGET_CHANNEL_ID)
            test_channel = await client.get_entity(TEST_CHANNEL_ID)
            print(f"✅ 텔레그램 채널 '{channel.title}' 접근 가능. 메시지 수신 준비 완료.")
            print(f"✅ 텔레그램 채널 '{test_channel.title}' 접근 가능. 메시지 수신 준비 완료.")
        except Exception as e:
            print(f"❌ 텔레그램 채널 접근 실패. 메시지 수신이 불가능할 수 있습니다. 오류: {e}")

    except Exception as e:
        print(f"❌ 초기 연결 확인 중 오류 발생: {e}")
        # 오류 메시지를 로그 채널로 전송
        await bybit_bot.send_message(
            chat_id=TELE_BYBIT_LOG_CHAT_ID,
            text=f"⚠️ **트레이딩 봇 가동 실패**\n오류: {e}"
        )
    # --- 연결 상태 확인 로직 추가 끝 ---
    
    print("Listening for new message...")
    now = datetime.now()
    print("Program Start", "time:", now.date(), now.time())
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())