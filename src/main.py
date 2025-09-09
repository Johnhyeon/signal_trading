import asyncio
from datetime import datetime
import os
from telethon import events
import telegram
# import os # dotenv를 사용하지 않으므로 제거

from api_clients import client, bybit_client, bybit_bot, TARGET_CHANNEL_ID, TEST_CHANNEL_ID, TELE_BYBIT_LOG_CHAT_ID
from message_parser import parse_telegram_message, parse_cancel_message, parse_dca_message
from portfolio_manager import generate_report
from trade_executor import execute_bybit_order, active_orders, bybit_client, cancel_bybit_order, send_bybit_failure_msg, send_bybit_cancel_msg, update_stop_loss_to_value, place_dca_order, update_stop_loss_to_tp1, update_stop_loss_to_tp2

# 수정: utils.py에서 MESSAGES 변수 임포트
from utils import MESSAGES

# print(MESSAGES['application_run_message'])
# print(MESSAGES['instance_created_message'])

# -----------------
# 텔레그램 메시지 이벤트 핸들러
# -----------------
@client.on(events.NewMessage(chats=TARGET_CHANNEL_ID))
async def my_event_handler(event):
    
    message_text = event.message.message
    print(f"\n{MESSAGES['new_message_detected']}\n{message_text}")

    if event.is_reply:
        print(MESSAGES['reply_message_warning'])
        return
    
    # 'Cancel' 메시지인지 먼저 확인
    symbol_to_cancel = parse_cancel_message(message_text)
    if symbol_to_cancel:
        await cancel_bybit_order(symbol_to_cancel)
        return # 취소 메시지이므로 주문 로직은 실행하지 않음
    
    order_info = parse_telegram_message(message_text)
    
    if order_info:
        # ✅ 수정: 중복 주문 방지 필터링 조건 강화 (종목명 + 포지션 방향)
        existing_order = next((v for v in active_orders.values() if v['symbol'] == order_info['symbol'] and v['side'] == order_info['side']), None)

        if existing_order:
            print(MESSAGES['duplicate_order_warning'].format(symbol=order_info['symbol']))
            # 사용자에게 알림 메시지를 보내는 것도 좋은 방법입니다.
            await send_bybit_failure_msg(order_info['symbol'], MESSAGES['duplicate_order_reason'])
            return
        
        # 메시지 ID를 인수로 전달
        execute_bybit_order(order_info, event.id)

    now = datetime.now()
    print("Target spoke", "time:", now.date(), now.time())

@client.on(events.MessageEdited(chats=TARGET_CHANNEL_ID))
async def handle_edited_message(event):
    global active_orders
    message_id = event.id
    message_text = event.message.message
    print(f"\n{MESSAGES['edited_message_detected']}\n{message_text}")

    if message_id not in active_orders:
        return

    print(MESSAGES['edited_message_alert'].format(message_id=message_id))
    
    try:
        existing_order_info = active_orders.pop(message_id, None)
        
        if not existing_order_info:
            print(MESSAGES['order_info_not_found_error'].format(message_id=message_id))
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
            print(MESSAGES['order_cancel_success'].format(order_id=bybit_order_id))
            await send_bybit_cancel_msg(symbol_to_cancel)
            
            # 2. 취소가 성공한 경우에만 새로운 메시지 파싱 및 주문 실행
            updated_order_info = parse_telegram_message(event.message.message)
            if updated_order_info:
                print(MESSAGES['new_order_from_edit'])
                # execute_bybit_order가 async 함수로 변경되었다고 가정
                await execute_bybit_order(updated_order_info, message_id)
            else:
                print(MESSAGES['edit_parsing_fail'])
                # 이 경우 기존 주문이 취소된 상태이므로 사용자에게 알려주는 것이 중요
                await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['edit_parsing_fail_alert'])

        else:
            # 3. 기존 주문 취소 실패 (이미 체결 또는 기타 사유)
            print(MESSAGES['order_cancel_fail'].format(error_msg=cancel_result['retMsg']))
            
            # 취소 실패 메시지 전송
            await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['order_cancel_fail'].format(error_msg=cancel_result['retMsg']))
            # 이미 체결된 주문에 대한 메시지 처리가 필요하면 추가 로직 구현
            
    except Exception as e:
        print(MESSAGES['order_edit_system_error'].format(error_msg=e))
        await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['order_edit_system_error'].format(error_msg=str(e)))

# ✅ DCA 및 SL 수정 이벤트 핸들러 추가
@client.on(events.NewMessage(chats=TARGET_CHANNEL_ID, func=lambda e: e.is_reply))
async def handle_dca_and_sl_update(event):
    global active_orders
    message_text = event.message.message.lower().replace(" ", "")
    
    # DCA 및 SL 메시지 파싱 시도
    dca_price, new_sl = parse_dca_message(event.message.message)

    if dca_price and new_sl:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            print(MESSAGES['dca_sl_message_detected'].format(symbol=order_info['symbol']))
            # SL 수정
            await update_stop_loss_to_value(
                order_info['symbol'],
                order_info['side'],
                order_info['positionIdx'],
                new_sl
            )
            # DCA 주문 실행
            place_dca_order(order_info, dca_price)
        else:
            await send_bybit_failure_msg("DCA/SL", MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id))
        return

    # 기존 SL 이동 로직 유지
    if 'movesl=entry' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            await update_stop_loss_to_value(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['entry_price'])
        else:
            await send_bybit_failure_msg("SL", MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id))
    
    elif 'movesl=tp1' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            if len(order_info['targets']) >= 1:
                await update_stop_loss_to_value(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['targets'][0])
            else:
                await send_bybit_failure_msg("SL", MESSAGES['tp1_not_found'])
        else:
            await send_bybit_failure_msg("SL", MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id))
    
    elif 'movesl=tp2' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            if len(order_info['targets']) >= 2:
                await update_stop_loss_to_value(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['targets'][1])
            else:
                await send_bybit_failure_msg("SL", MESSAGES['tp2_not_found'])
        else:
            await send_bybit_failure_msg("SL", MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id))

@client.on(events.NewMessage(chats=TARGET_CHANNEL_ID, func=lambda e: e.is_reply and 'cancel' in e.message.message.lower()))
async def handle_cancel_reply(event):
    global active_orders
    original_msg_id = event.reply_to_msg_id
    print(MESSAGES['cancel_message_detected'].format(original_msg_id=original_msg_id))
    
    if original_msg_id in active_orders:
        order_info = active_orders[original_msg_id]
        symbol = order_info['symbol']
        print(MESSAGES['cancel_message_info'].format(symbol=symbol))
        await cancel_bybit_order(symbol)
    else:
        print(MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id))
        await send_bybit_failure_msg("Cancel", MESSAGES['no_open_order_to_cancel'])

#=======================================================================================================================================#
##### 테스트용
@client.on(events.NewMessage(chats=TEST_CHANNEL_ID))
async def my_event_handler(event):
    # ✅ 봇 자신이 보낸 메시지 무시
    bot_info = await bybit_bot.get_me()
    if event.sender_id == bot_info.id:
        return

    message_text = event.message.message
    print(f"\n새로운 메시지 감지:\n{message_text}")

    # ✅ 'PF' 메시지 감지 및 포트폴리오 리포트 전송
    message_parts = message_text.strip().lower().split()
    if message_parts[0] == 'pf':
        period = 'all'
        if len(message_parts) > 1:
            if message_parts[1] == 'monty':
                period = 'month'
            elif message_parts[1] == 'week':
                period = 'week'
            elif message_parts[1] == 'day':
                period = 'day'
        
        report = generate_report(period=period)
        await bybit_bot.send_message(
            chat_id=TEST_CHANNEL_ID,
            text=report,
            parse_mode='Markdown'
        )
        return
    
    # ✅ 답장 메시지인 경우 바로 종료
    if event.is_reply:
        print(MESSAGES['reply_message_warning'])
        return
    

    order_info = parse_telegram_message(message_text)
    
    if order_info:
        # ✅ 중복 주문 방지 필터링 조건 추가
        # active_orders 딕셔너리에서 현재 종목이 이미 주문되었는지 확인합니다.
        existing_symbol = next((v['symbol'] for v in active_orders.values() if v['symbol'] == order_info['symbol']), None)

        if existing_symbol:
            print(MESSAGES['duplicate_order_warning'].format(symbol=order_info['symbol']))
            # 사용자에게 알림 메시지를 보내는 것도 좋은 방법입니다.
            await send_bybit_failure_msg(order_info['symbol'], MESSAGES['duplicate_order_reason'])
            return

        # 메시지 ID를 인수로 전달
        execute_bybit_order(order_info, event.id)
    
    # --- 테스트용 채널 메시지 감지 ---
    if event.sender_id == TEST_CHANNEL_ID:
        now = datetime.now()
        print(MESSAGES['test_channel_info'])
        print("Target spoke", "time:", now.date(), now.time())
    await asyncio.sleep(0) 
    # --- 테스트용 채널 메시지 감지 ---

@client.on(events.MessageEdited(chats=TEST_CHANNEL_ID))
async def handle_edited_message(event):
    global active_orders
    message_id = event.id
    message_text = event.message.message
    print(f"\n{MESSAGES['edited_message_detected']}\n{message_text}")

    if message_id not in active_orders:
        return

    print(MESSAGES['edited_message_alert'].format(message_id=message_id))
    
    try:
        existing_order_info = active_orders.pop(message_id, None)
        
        if not existing_order_info:
            print(MESSAGES['order_info_not_found_error'].format(message_id=message_id))
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
            print(MESSAGES['order_cancel_success'].format(order_id=bybit_order_id))
            await send_bybit_cancel_msg(symbol_to_cancel)
            
            # 2. 취소가 성공한 경우에만 새로운 메시지 파싱 및 주문 실행
            updated_order_info = parse_telegram_message(event.message.message)
            if updated_order_info:
                print(MESSAGES['new_order_from_edit'])
                # execute_bybit_order가 async 함수로 변경되었다고 가정
                await execute_bybit_order(updated_order_info, message_id)
            else:
                print(MESSAGES['edit_parsing_fail'])
                # 이 경우 기존 주문이 취소된 상태이므로 사용자에게 알려주는 것이 중요
                await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['edit_parsing_fail_alert'])

        else:
            # 3. 기존 주문 취소 실패 (이미 체결 또는 기타 사유)
            print(MESSAGES['order_cancel_fail'].format(error_msg=cancel_result['retMsg']))
            
            # 취소 실패 메시지 전송
            await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['order_cancel_fail'].format(error_msg=cancel_result['retMsg']))
            # 이미 체결된 주문에 대한 메시지 처리가 필요하면 추가 로직 구현
            
    except Exception as e:
        print(MESSAGES['order_edit_system_error'].format(error_msg=e))
        await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['order_edit_system_error'].format(error_msg=str(e)))

@client.on(events.NewMessage(chats=TEST_CHANNEL_ID, func=lambda e: e.is_reply))
async def handle_dca_and_sl_update(event):
    global active_orders
    message_text = event.message.message.lower().replace(" ", "")

    dca_price, new_sl = parse_dca_message(event.message.message)

    if dca_price and new_sl:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            print(MESSAGES['dca_sl_message_detected'].format(symbol=order_info['symbol']))
            # SL 수정
            await update_stop_loss_to_value(
                order_info['symbol'],
                order_info['side'],
                order_info['positionIdx'],
                new_sl
            )
            # DCA 주문 실행
            place_dca_order(order_info, dca_price)
        else:
            await send_bybit_failure_msg("DCA/SL", MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id))
        return

    # 기존 SL 이동 로직 유지
    if 'movesl=entry' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            await update_stop_loss_to_value(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['entry_price'])
        else:
            await send_bybit_failure_msg("SL", MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id))
    
    elif 'movesl=tp1' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            if len(order_info['targets']) >= 1:
                await update_stop_loss_to_value(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['targets'][0])
            else:
                await send_bybit_failure_msg("SL", MESSAGES['tp1_not_found'])
        else:
            await send_bybit_failure_msg("SL", MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id))
    
    elif 'movesl=tp2' in message_text:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            if len(order_info['targets']) >= 2:
                await update_stop_loss_to_value(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['targets'][1])
            else:
                await send_bybit_failure_msg("SL", MESSAGES['tp2_not_found'])
        else:
            await send_bybit_failure_msg("SL", MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id))

@client.on(events.NewMessage(chats=TEST_CHANNEL_ID, func=lambda e: e.is_reply and 'cancel' in e.message.message.lower()))
async def handle_cancel_reply(event):
    global active_orders
    original_msg_id = event.reply_to_msg_id
    print(MESSAGES['cancel_message_detected'].format(original_msg_id=original_msg_id))
    
    if original_msg_id in active_orders:
        order_info = active_orders[original_msg_id]
        symbol = order_info['symbol']
        print(MESSAGES['cancel_message_info'].format(symbol=symbol))
        await cancel_bybit_order(symbol)
    else:
        print(MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id))
        await send_bybit_failure_msg("Cancel", MESSAGES['no_open_order_to_cancel'])

#=======================================================================================================================================#


# -----------------
# 메인 함수 (스크립트 실행)
# -----------------
async def main():
    # .env 파일 경로 설정
    dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')

    # .env 파일이 없으면 생성
    if not os.path.exists(dotenv_path):
        with open(dotenv_path, 'w') as f:
            f.write("# 환경 설정\n")
            f.write("TELEGRAM_API_ID=\n")
            f.write("TELEGRAM_API_HASH=''\n")
            f.write("BYBIT_API_KEY=''\n")
            f.write("BYBIT_SECRET_KEY=''\n")
            f.write("TARGET_CHANNEL_ID=\n")
            f.write("TELE_BYBIT_BOT_TOKEN=\n")
            f.write("TELE_BYBIT_LOG_CHAT_ID=\n")
            f.write("TEST_CHANNEL_ID=\n")
            f.write("LANG_CODE='ko' # 'ko' or 'en'\n")
        
        print("\n" + "="*50)
        print("⚠️ .env 파일이 존재하지 않아 자동으로 생성했습니다. ⚠️")
        print("⚠️ 생성된 .env 파일을 열고, 필수 API 키를 입력한 후 다시 실행해주세요. ⚠️")
        print("="*50 + "\n")
        return # 프로그램 종료
    
    await client.start()
    print("Connect start...")
    if os.getenv('LANG_CODE') == 'ko':
        print("🌏 Now Selected language: KO")
    elif os.getenv('LANG_CODE') == 'en':
        print("🌎 Now Selected language: EN")
    print(MESSAGES['application_run_message'])
    print(MESSAGES['instance_created_message'])

    # --- 연결 상태 확인 로직 추가 ---
    try:
        # Bybit 연결 상태 확인
        balance = bybit_client.get_wallet_balance(accountType="UNIFIED")
        if balance['retCode'] == 0:
            print(MESSAGES['bybit_api_connection_success'])
        else:
            print(MESSAGES['bybit_api_connection_failure'].format(error_msg=balance['retMsg']))

        # 텔레그램 봇 연결 상태 확인 (봇 정보 가져오기)
        bot_info = await bybit_bot.get_me()
        print(MESSAGES['telegram_bot_connection_success'].format(username=bot_info.username))
        
        # 시작 메시지를 로그 채널로 전송
        await bybit_bot.send_message(
            chat_id=TELE_BYBIT_LOG_CHAT_ID,
            text=MESSAGES['bot_start_message']
        )
        
        # ✅ 테스트 채널로 시작 메시지 전송
        await bybit_bot.send_message(
            chat_id=TEST_CHANNEL_ID,
            text=MESSAGES['test_channel_info'] + "\n" + MESSAGES['bot_start_message']
        )
        
        # 텔레그램 채널 접근 권한 확인
        try:
            channel = await client.get_entity(TARGET_CHANNEL_ID)
            test_channel = await client.get_entity(TEST_CHANNEL_ID)
            print(MESSAGES['telegram_channel_access_success'].format(channel_name=channel.title))
            print(MESSAGES['telegram_channel_access_success'].format(channel_name=test_channel.title))
        except Exception as e:
            print(MESSAGES['telegram_channel_access_failure'].format(error_msg=e))

    except Exception as e:
        print(MESSAGES['initial_connection_error'].format(error_msg=e))
        # 오류 메시지를 로그 채널로 전송
        await bybit_bot.send_message(
            chat_id=TELE_BYBIT_LOG_CHAT_ID,
            text=MESSAGES['bot_failure_message'].format(error_msg=e)
        )
    # --- 연결 상태 확인 로직 추가 끝 ---
    
    print(MESSAGES['listening_message'])
    now = datetime.now()
    print(MESSAGES['program_start'], "time:", now.date(), now.time())
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())