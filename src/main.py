import asyncio
from datetime import datetime
from telethon import events
import telegram
import os

from api_clients import client, bybit_client, bybit_bot, TARGET_CHANNEL_ID, TEST_CHANNEL_ID, TELE_BYBIT_BOT_TOKEN, TELE_BYBIT_LOG_CHAT_ID
from message_parser import parse_telegram_message, parse_cancel_message, parse_dca_message
from portfolio_manager import generate_report
from trade_executor import execute_bybit_order, active_orders, bybit_client, cancel_bybit_order, send_bybit_failure_msg, send_bybit_cancel_msg, update_stop_loss_to_value, place_dca_order, update_stop_loss_to_tp1, update_stop_loss_to_tp2

from utils import MESSAGES


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
        existing_order = next((v for v in active_orders.values() if v['symbol'] == order_info['symbol'] and v['side'] == order_info['side']), None)

        if existing_order:
            print(MESSAGES['duplicate_order_warning'].format(symbol=order_info['symbol']))
            await send_bybit_failure_msg(order_info['symbol'], MESSAGES['duplicate_order_reason'])
            return

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

        cancel_result = bybit_client.cancel_order(
            category="linear",
            symbol=symbol_to_cancel,
            orderId=bybit_order_id
        )

        if cancel_result['retCode'] == 0:
            print(MESSAGES['order_cancel_success'].format(order_id=bybit_order_id))
            await send_bybit_cancel_msg(symbol_to_cancel)
            
            updated_order_info = parse_telegram_message(event.message.message)
            if updated_order_info:
                print(MESSAGES['new_order_from_edit'])
                await execute_bybit_order(updated_order_info, message_id)
            else:
                print(MESSAGES['edit_parsing_fail'])
                await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['edit_parsing_fail_alert'])

        else:
            print(MESSAGES['order_cancel_fail'].format(error_msg=cancel_result['retMsg']))
            await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['order_cancel_fail'].format(error_msg=cancel_result['retMsg']))
            
    except Exception as e:
        print(MESSAGES['order_edit_system_error'].format(error_msg=e))
        await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['order_edit_system_error'].format(error_msg=str(e)))


@client.on(events.NewMessage(chats=TARGET_CHANNEL_ID, func=lambda e: e.is_reply))
async def handle_dca_and_sl_update(event):
    global active_orders
    message_text = event.message.message.lower().replace(" ", "")
    
    dca_price, new_sl = parse_dca_message(event.message.message)

    if dca_price and new_sl:
        original_msg_id = event.reply_to_msg_id
        if original_msg_id in active_orders:
            order_info = active_orders[original_msg_id]
            print(MESSAGES['dca_sl_message_detected'].format(symbol=order_info['symbol']))
            await update_stop_loss_to_value(
                order_info['symbol'],
                order_info['side'],
                order_info['positionIdx'],
                new_sl
            )
            place_dca_order(order_info, dca_price)
        else:
            await send_bybit_failure_msg("DCA/SL", MESSAGES['order_not_found_message'].format(original_msg_id=original_msg_id))
        return

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


async def main():
    try:
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
        print(MESSAGES['initial_connection_error'].format(error_msg=e))

if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())