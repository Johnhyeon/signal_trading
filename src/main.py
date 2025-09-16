import asyncio
from datetime import datetime
from telethon import events
import telegram
import os

from api_clients import client, bybit_client, bybit_bot, TARGET_CHANNEL_ID, TEST_CHANNEL_ID, TELE_BYBIT_BOT_TOKEN, TELE_BYBIT_LOG_CHAT_ID
from message_parser import parse_telegram_message, parse_cancel_message, parse_dca_message
from portfolio_manager import generate_report
from trade_executor import execute_bybit_order, monitored_trade_ids, bybit_client, cancel_bybit_order, update_stop_loss_to_value, place_dca_order, update_stop_loss_to_tp1, update_stop_loss_to_tp2
from utils import MESSAGES, log_error_and_send_message
from database_manager import setup_database, get_active_orders

# 메시지 ID와 주문 정보를 매핑할 전역 딕셔너리
active_orders = {}

# -----------------
# 텔레그램 메시지 이벤트 핸들러 (Telethon 클라이언트)
# -----------------
@client.on(events.NewMessage(chats=TARGET_CHANNEL_ID))
async def my_event_handler(event):
    
    message_text = event.message.message
    print(f"\n{MESSAGES['new_message_detected']}\n{message_text}")

    if event.is_reply:
        print(MESSAGES['reply_message_warning'])
        return
    
    symbol_to_cancel = parse_cancel_message(message_text)
    if symbol_to_cancel:
        await cancel_bybit_order(symbol_to_cancel)
        return
    
    order_info = parse_telegram_message(message_text)
    
    if order_info:
        # DB에서 최신 활성 주문 정보 불러오기
        current_active_orders = get_active_orders()
        existing_order = next((v for v in current_active_orders.values() if v['symbol'] == order_info['symbol'] and v['side'] == order_info['side'] and not v['filled']), None)

        if existing_order:
            print(MESSAGES['duplicate_order_warning'].format(symbol=order_info['symbol']))
            log_error_and_send_message(
                MESSAGES['duplicate_order_reason'],
                chat_id=TELE_BYBIT_LOG_CHAT_ID
            )
            return

        execute_bybit_order(order_info, event.id)

    now = datetime.now()
    print("Target spoke", "time:", now.date(), now.time())


@client.on(events.MessageEdited(chats=TARGET_CHANNEL_ID))
async def handle_edited_message(event):
    message_id = event.id
    message_text = event.message.message
    print(f"\n{MESSAGES['edited_message_detected']}\n{message_text}")

    # DB에서 최신 활성 주문 정보 불러오기
    current_active_orders = get_active_orders()

    if message_id not in current_active_orders:
        return
    
    if current_active_orders[message_id]['original_message'] == message_text:
        print("⚠️ 메시지 내용이 변경되지 않았으므로 주문 수정 작업을 건너뛰겠습니다.")
        return

    print(MESSAGES['edited_message_alert'].format(message_id=message_id))
    
    try:
        existing_order_info = current_active_orders.pop(message_id, None)
        
        if not existing_order_info:
            print(MESSAGES['order_info_not_found_error'].format(message_id=message_id))
            return
            
        bybit_order_id = existing_order_info['orderId']
        symbol_to_cancel = existing_order_info['symbol']

        cancel_result = bybit_client.cancel_order(
            category="linear",
            symbol=symbol_to_cancel,
            orderId=bybit_order_id
        )

        if cancel_result['retCode'] == 0:
            print(MESSAGES['order_cancel_success'].format(order_id=bybit_order_id))
            
            updated_order_info = parse_telegram_message(event.message.message)
            if updated_order_info:
                print(MESSAGES['new_order_from_edit'])
                execute_bybit_order(updated_order_info, message_id)
            else:
                print(MESSAGES['edit_parsing_fail'])
                log_error_and_send_message(
                    MESSAGES['edit_parsing_fail_alert'],
                    chat_id=TELE_BYBIT_LOG_CHAT_ID
                )

        else:
            log_error_and_send_message(
                MESSAGES['order_cancel_fail'].format(error_msg=cancel_result['retMsg']),
                chat_id=TELE_BYBIT_LOG_CHAT_ID
            )
            
    except Exception as e:
        log_error_and_send_message(
            MESSAGES['order_edit_system_error'].format(error_msg=e),
            exc=e
        )

@client.on(events.NewMessage(chats=TARGET_CHANNEL_ID, func=lambda e: e.is_reply))
async def handle_dca_and_sl_update(event):
    message_text = event.message.message.lower().replace(" ", "")
    original_msg_id = event.reply_to_msg_id
    
    # DB에서 최신 활성 주문 정보 불러오기
    current_active_orders = get_active_orders()

    dca_price, new_sl = parse_dca_message(event.message.message)
    if dca_price and new_sl:
        if original_msg_id in current_active_orders:
            order_info = current_active_orders[original_msg_id]
            print(MESSAGES['dca_sl_message_detected'].format(symbol=order_info['symbol']))
            await update_stop_loss_to_value(
                order_info['symbol'],
                order_info['side'],
                order_info['positionIdx'],
                new_sl
            )
            place_dca_order(order_info, dca_price)
        else:
            log_error_and_send_message(
                MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id),
                chat_id=TELE_BYBIT_LOG_CHAT_ID
            )
        return

    # ✅ 수정된 로직: 'movesl' 키워드를 정확히 파싱합니다.
    if 'movesl=entry' in message_text:
        await handle_movesl_command(original_msg_id, 'entry')


async def handle_movesl_command(original_msg_id, target_sl):
    """
    movesl=entry, movesl=tp1, movesl=tp2 메시지를 처리하는 헬퍼 함수
    """
    # DB에서 최신 활성 주문 정보 불러오기
    current_active_orders = get_active_orders()

    if original_msg_id not in current_active_orders:
        log_error_and_send_message(
            MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id),
            chat_id=TELE_BYBIT_LOG_CHAT_ID
        )
        return
        
    order_info = current_active_orders[original_msg_id]
    
    # 포지션이 열려있는지 확인
    try:
        positions_info = bybit_client.get_positions(category="linear", symbol=order_info['symbol'])
        if positions_info['retCode'] == 0 and positions_info['result']['list']:
            position_size = float(positions_info['result']['list'][0]['size'])
            
            if position_size > 0:
                # 포지션이 있으면 SL 업데이트
                if target_sl == 'entry':
                    await update_stop_loss_to_value(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['entry_price'])
                return
            
    except Exception as e:
        log_error_and_send_message(f"포지션 정보 확인 중 오류 발생: {e}", exc=e)
        return

    # 포지션이 없으면 미체결 주문 취소
    print(f"포지션이 열리지 않았습니다. {order_info['symbol']}의 미체결 주문을 취소합니다.")
    await cancel_bybit_order(order_info['symbol'])


@client.on(events.NewMessage(chats=TARGET_CHANNEL_ID, func=lambda e: e.is_reply and 'cancel' in e.message.message.lower()))
async def handle_cancel_reply(event):
    original_msg_id = event.reply_to_msg_id
    print(MESSAGES['cancel_message_detected'].format(original_msg_id=original_msg_id))
    
    # DB에서 최신 활성 주문 정보 불러오기
    current_active_orders = get_active_orders()

    if original_msg_id in current_active_orders:
        order_info = current_active_orders[original_msg_id]
        symbol = order_info['symbol']
        print(MESSAGES['cancel_message_info'].format(symbol=symbol))
        await cancel_bybit_order(symbol)
        return

    try:
        original_message = await client.get_messages(TARGET_CHANNEL_ID, ids=original_msg_id)
        if original_message:
            parsed_order_info = parse_telegram_message(original_message.text)
            if parsed_order_info and 'symbol' in parsed_order_info:
                symbol_to_cancel = parsed_order_info['symbol']
                print(f"✅ active_orders에 없지만, 원본 메시지에서 심볼({symbol_to_cancel})을 파싱했습니다. Bybit 주문 취소를 시도합니다.")
                await cancel_bybit_order(symbol_to_cancel)
                return
    except Exception as e:
        log_error_and_send_message(f"원본 메시지 파싱 중 오류 발생: {e}", exc=e)
    
    log_error_and_send_message(
        MESSAGES['no_open_order_to_cancel'],
        chat_id=TELE_BYBIT_LOG_CHAT_ID
    )

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
        # DB에서 최신 활성 주문 정보 불러오기
        current_active_orders = get_active_orders()
        existing_symbol = next((v['symbol'] for v in current_active_orders.values() if v['symbol'] == order_info['symbol']), None)

        if existing_symbol:
            print(MESSAGES['duplicate_order_warning'].format(symbol=order_info['symbol']))
            log_error_and_send_message(
                MESSAGES['duplicate_order_reason'],
                chat_id=TELE_BYBIT_LOG_CHAT_ID
            )
            return

        execute_bybit_order(order_info, event.id)
    
    if event.sender_id == TEST_CHANNEL_ID:
        now = datetime.now()
        print(MESSAGES['test_channel_info'])
        print("Target spoke", "time:", now.date(), now.time())
    await asyncio.sleep(0) 

@client.on(events.MessageEdited(chats=TEST_CHANNEL_ID))
async def handle_edited_message(event):
    message_id = event.id
    message_text = event.message.message
    print(f"\n{MESSAGES['edited_message_detected']}\n{message_text}")

    # DB에서 최신 활성 주문 정보 불러오기
    current_active_orders = get_active_orders()

    if message_id not in current_active_orders:
        return

    if current_active_orders[message_id]['original_message'] == message_text:
        print("⚠️ 메시지 내용이 변경되지 않았으므로 주문 수정 작업을 건너뛰겠습니다.")
        return

    print(MESSAGES['edited_message_alert'].format(message_id=message_id))
    
    try:
        existing_order_info = current_active_orders.pop(message_id, None)
        
        if not existing_order_info:
            print(MESSAGES['order_info_not_found_error'].format(message_id=message_id))
            return
            
        bybit_order_id = existing_order_info['orderId']
        symbol_to_cancel = existing_order_info['symbol']

        cancel_result = bybit_client.cancel_order(
            category="linear",
            symbol=symbol_to_cancel,
            orderId=bybit_order_id
        )

        if cancel_result['retCode'] == 0:
            print(MESSAGES['order_cancel_success'].format(order_id=bybit_order_id))
            
            updated_order_info = parse_telegram_message(event.message.message)
            if updated_order_info:
                print(MESSAGES['new_order_from_edit'])
                execute_bybit_order(updated_order_info, message_id)
            else:
                print(MESSAGES['edit_parsing_fail'])
                log_error_and_send_message(
                    MESSAGES['edit_parsing_fail_alert'],
                    chat_id=TELE_BYBIT_LOG_CHAT_ID
                )

        else:
            print(MESSAGES['order_cancel_fail'].format(error_msg=cancel_result['retMsg']))
            
            log_error_and_send_message(
                MESSAGES['order_cancel_fail'].format(error_msg=cancel_result['retMsg']),
                chat_id=TELE_BYBIT_LOG_CHAT_ID
            )
            
    except Exception as e:
        log_error_and_send_message(
            MESSAGES['order_edit_system_error'].format(error_msg=e),
            exc=e
        )

@client.on(events.NewMessage(chats=TEST_CHANNEL_ID, func=lambda e: e.is_reply))
async def handle_dca_and_sl_update(event):
    message_text = event.message.message.lower().replace(" ", "")
    original_msg_id = event.reply_to_msg_id
    
    # DB에서 최신 활성 주문 정보 불러오기
    current_active_orders = get_active_orders()

    # ✅ 수정된 로직: 'movesl' 키워드를 정확히 파싱합니다.
    if 'movesltoentry' in message_text:
        await handle_movesl_command_test(original_msg_id, 'entry')
    elif 'movesltotp1' in message_text:
        await handle_movesl_command_test(original_msg_id, 'tp1')
    elif 'movesltotp2' in message_text:
        await handle_movesl_command_test(original_msg_id, 'tp2')

    dca_price, new_sl = parse_dca_message(event.message.message)
    if dca_price and new_sl:
        if original_msg_id in current_active_orders:
            order_info = current_active_orders[original_msg_id]
            print(MESSAGES['dca_sl_message_detected'].format(symbol=order_info['symbol']))
            await update_stop_loss_to_value(
                order_info['symbol'],
                order_info['side'],
                order_info['positionIdx'],
                new_sl
            )
            place_dca_order(order_info, dca_price)
        else:
            log_error_and_send_message(
                MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id),
                chat_id=TELE_BYBIT_LOG_CHAT_ID
            )
        return


async def handle_movesl_command_test(original_msg_id, target_sl):
    """
    movesl=entry, movesl=tp1, movesl=tp2 메시지를 처리하는 헬퍼 함수
    """
    # DB에서 최신 활성 주문 정보 불러오기
    current_active_orders = get_active_orders()
    
    if original_msg_id not in current_active_orders:
        log_error_and_send_message(
            MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id),
            chat_id=TELE_BYBIT_LOG_CHAT_ID
        )
        return
        
    order_info = current_active_orders[original_msg_id]
    
    # 포지션이 열려있는지 확인
    try:
        positions_info = bybit_client.get_positions(category="linear", symbol=order_info['symbol'])
        print(positions_info)
        if positions_info['retCode'] == 0 and positions_info['result']['list']:
            print(positions_info['result']['list'])
            position_size = float(positions_info['result']['list'][0]['size'])
            
            if position_size > 0:
                # 포지션이 있으면 SL 업데이트
                if target_sl == 'entry':
                    print("entry로 이동")
                    await update_stop_loss_to_value(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['entry_price'])
                elif target_sl == 'tp1':
                    if len(order_info['targets']) >= 1:
                        await update_stop_loss_to_value(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['targets'][0])
                    else:
                        log_error_and_send_message(MESSAGES['tp1_not_found'], chat_id=TELE_BYBIT_LOG_CHAT_ID)
                elif target_sl == 'tp2':
                    if len(order_info['targets']) >= 2:
                        await update_stop_loss_to_value(order_info['symbol'], order_info['side'], order_info['positionIdx'], order_info['targets'][1])
                    else:
                        log_error_and_send_message(MESSAGES['tp2_not_found'], chat_id=TELE_BYBIT_LOG_CHAT_ID)
                return
            
    except Exception as e:
        log_error_and_send_message(f"포지션 정보 확인 중 오류 발생: {e}", exc=e)
        return

    # 포지션이 없으면 미체결 주문 취소
    print(f"포지션이 열리지 않았습니다. {order_info['symbol']}의 미체결 주문을 취소합니다.")
    await cancel_bybit_order(order_info['symbol'])


@client.on(events.NewMessage(chats=TEST_CHANNEL_ID, func=lambda e: e.is_reply and 'cancel' in e.message.message.lower()))
async def handle_cancel_reply(event):
    original_msg_id = event.reply_to_msg_id
    print(MESSAGES['cancel_message_detected'].format(original_msg_id=original_msg_id))
    
    # DB에서 최신 활성 주문 정보 불러오기
    current_active_orders = get_active_orders()

    if original_msg_id in current_active_orders:
        order_info = current_active_orders[original_msg_id]
        symbol = order_info['symbol']
        print(MESSAGES['cancel_message_info'].format(symbol=symbol))
        await cancel_bybit_order(symbol)
        return

    try:
        original_message = await client.get_messages(TEST_CHANNEL_ID, ids=original_msg_id)
        if original_message:
            parsed_order_info = parse_telegram_message(original_message.text)
            if parsed_order_info and 'symbol' in parsed_order_info:
                symbol_to_cancel = parsed_order_info['symbol']
                print(f"✅ active_orders에 없지만, 원본 메시지에서 심볼({symbol_to_cancel})을 파싱했습니다. Bybit 주문 취소를 시도합니다.")
                await cancel_bybit_order(symbol_to_cancel)
                return
    except Exception as e:
        log_error_and_send_message(f"원본 메시지 파싱 중 오류 발생: {e}", exc=e)
    
    log_error_and_send_message(
        MESSAGES['no_open_order_to_cancel'],
        chat_id=TELE_BYBIT_LOG_CHAT_ID
    )

#=======================================================================================================================================#

async def main():
    try:
        # ✅ 추가: DB 설정 함수 호출
        setup_database()
        print("✅ 데이터베이스 설정 완료.")
        
        # ✅ 수정: 파일에서 불러오는 대신 DB에서 불러오기
        global active_orders
        loaded_orders = get_active_orders()
        active_orders.update(loaded_orders)
        for message_id in active_orders.keys():
            monitored_trade_ids.add(message_id)
        print("✅ 이전에 저장된 활성 주문 정보를 성공적으로 불러왔습니다.")

        await client.start()
        print("Telethon client started...")
        print(MESSAGES['application_run_message'])
        
        try:
            channel = await client.get_entity(TARGET_CHANNEL_ID)
            test_channel = await client.get_entity(TEST_CHANNEL_ID)
            print(MESSAGES['telegram_channel_access_success'].format(channel_name=channel.title))
            print(MESSAGES['telegram_channel_access_success'].format(channel_name=test_channel.title))
        except Exception as e:
            print(MESSAGES['telegram_channel_access_failure'].format(error_msg=e))
        
        print(MESSAGES['listening_message'])
        now = datetime.now()
        print(MESSAGES['program_start'], "time:", now.date(), now.time())
        await client.run_until_disconnected()

    except Exception as e:
        log_error_and_send_message(
            MESSAGES['initial_connection_error'].format(error_msg=e),
            exc=e
        )

if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())