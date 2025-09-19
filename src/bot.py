import asyncio
from datetime import datetime
import json
import os
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from api_clients import bybit_client, bybit_bot, TELE_BYBIT_BOT_TOKEN, TELE_BYBIT_LOG_CHAT_ID
from portfolio_manager import generate_report
from trade_executor import send_bybit_summary_msg
from utils import MESSAGES, log_error_and_send_message
from database_manager import get_active_orders, get_db_connection, record_trade_result_db

# 봇 명령어 처리 함수들
async def open_orders_command(update: Update, context):
    try:
        print("API 호출: bybit_client.get_open_orders(category='linear', settleCoin='USDT')")
        orders_info = bybit_client.get_open_orders(category="linear", settleCoin="USDT")
        print(f"API 응답: {orders_info}")

        if orders_info['retCode'] == 0 and orders_info['result']['list']:
            filtered_orders = [
                order for order in orders_info['result']['list']
                if order.get('orderType') in ['Limit']
            ]
            
            if filtered_orders:
                message_text = MESSAGES['open_orders_title'] + "\n\n"
                for order in filtered_orders:
                    symbol = order['symbol']
                    ticker_info = bybit_client.get_tickers(category="linear", symbol=symbol)
                    current_price = "정보 없음"
                    if ticker_info['retCode'] == 0 and ticker_info['result']['list']:
                        current_price = ticker_info['result']['list'][0]['lastPrice']

                    message_text += (
                        f"**{MESSAGES['symbol']}:** {symbol} | **{MESSAGES['side']}:** {order['side']}\n"
                        f"**{MESSAGES['qty']}:** {order['qty']} | **{MESSAGES['price']}:** {order['price']} | **{MESSAGES['current_price']}:** {current_price}\n\n"
                    )
            else:
                message_text = MESSAGES['no_open_orders']
        else:
            message_text = MESSAGES['no_open_orders']

        await bybit_bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        log_error_and_send_message(
            f"오류 발생: {e}",
            exc=e,
            chat_id=update.effective_chat.id
        )

async def positions_command(update: Update, context):
    try:
        print("API 호출: bybit_client.get_positions(category='linear', settleCoin='USDT')")
        positions_info = bybit_client.get_positions(category="linear", settleCoin="USDT")
        print(f"API 응답: {positions_info}")
        
        if positions_info['retCode'] == 0 and positions_info['result']['list']:
            message_text = MESSAGES['positions_title'] + "\n\n"
            found_position = False
            total_unrealized_pnl = 0.0
            for position in positions_info['result']['list']:
                if float(position['size']) > 0:
                    found_position = True
                    symbol = position['symbol']
                    ticker_info = bybit_client.get_tickers(category="linear", symbol=symbol)
                    current_price = "정보 없음"
                    if ticker_info['retCode'] == 0 and ticker_info['result']['list']:
                        current_price = ticker_info['result']['list'][0]['lastPrice']

                    pnl_value_str = position.get('unrealisedPnl', '0')
                    try:
                        pnl_value = float(pnl_value_str)
                        total_unrealized_pnl += pnl_value
                    except (ValueError, TypeError):
                        pnl_value = 0.0
                    
                    message_text += (
                        f"**{MESSAGES['symbol']}:** {symbol} | **{MESSAGES['side']}:** {position['side']}\n"
                        f"**{MESSAGES['qty']}:** {position['size']} | **{MESSAGES['entry_price']}:** {position['avgPrice']}\n"
                        f"**{MESSAGES['current_price']}:** {current_price}\n"
                        f"**{MESSAGES['unrealized_pnl']}:** {pnl_value}\n\n"
                    )
            
            if found_position:
                message_text += f"**{MESSAGES['total_unrealized_pnl']}:** `{total_unrealized_pnl:.2f}` USDT\n"
            else:
                message_text = MESSAGES['no_positions']

        else:
            message_text = MESSAGES['no_positions']

        await bybit_bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        log_error_and_send_message(
            f"오류 발생: {e}",
            exc=e,
            chat_id=update.effective_chat.id
        )

async def price_command(update: Update, context):
    try:
        if not context.args:
            await bybit_bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ 사용법: /price [심볼명] (예: /price BTC)"
            )
            return

        symbol = context.args[0].upper() + "USDT"
        ticker_info = bybit_client.get_tickers(category="linear", symbol=symbol)
        
        if ticker_info['retCode'] == 0 and ticker_info['result']['list']:
            data = ticker_info['result']['list'][0]
            price = data['lastPrice']
            change = float(data['price24hPcnt']) * 100
            
            message_text = (
                f"📈 **{symbol} 실시간 시세**\n"
                f"▪️ **가격:** `{price}` USDT\n"
                f"▪️ **24시간 등락폭:** `{change:.2f}%`"
            )
        else:
            message_text = f"⚠️ 종목 '{symbol}'의 정보를 찾을 수 없습니다."

        await bybit_bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        log_error_and_send_message(
            f"오류 발생: {e}",
            exc=e,
            chat_id=update.effective_chat.id
        )

async def pf_command(update: Update, context):
    try:
        message_parts = context.args
        period = 'all'
        if message_parts:
            if message_parts[0] == 'week':
                period = 'week'
            elif message_parts[0] == 'day':
                period = 'day'
        
        report = generate_report(period=period)
        await bybit_bot.send_message(
            chat_id=update.effective_chat.id,
            text=report,
            parse_mode='Markdown'
        )
    except Exception as e:
        log_error_and_send_message(
            f"오류 발생: {e}",
            exc=e,
            chat_id=update.effective_chat.id
        )

async def balance_command(update: Update, context):
    try:
        balance_info = bybit_client.get_wallet_balance(accountType="UNIFIED")
        
        if balance_info['retCode'] == 0:
            usdt_balance_data = next((item for item in balance_info['result']['list'][0]['coin'] if item['coin'] == 'USDT'), None)
            
            if usdt_balance_data:
                total_balance = float(usdt_balance_data.get('walletBalance') or 0.0)
                available_balance = float(usdt_balance_data.get('availableToWithdraw') or 0.0)
                
                message_text = (
                    f"{MESSAGES['balance_title']}\n\n"
                    f"▪️ **{MESSAGES['total_balance']}:** `{total_balance:.2f}` USDT\n"
                    f"▪️ **{MESSAGES['available_balance']}:** `{available_balance:.2f}` USDT"
                )
            else:
                message_text = MESSAGES['usdt_balance_not_found']
        else:
            message_text = f"⚠️ 잔고 정보를 가져오는 데 실패했습니다: {balance_info['retMsg']}"

        await bybit_bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        log_error_and_send_message(
            f"오류 발생: {e}",
            exc=e,
            chat_id=update.effective_chat.id
        )
        
async def cancel_all_command(update: Update, context):
    try:
        print("API 호출: bybit_client.get_open_orders(category='linear', settleCoin='USDT')")
        orders_info = bybit_client.get_open_orders(category='linear', settleCoin='USDT')
        print(f"API 응답: {orders_info}")

        if orders_info['retCode'] == 0 and orders_info['result']['list']:
            orders_to_cancel = [
                order for order in orders_info['result']['list']
                if order.get('orderType') in ['Limit']
            ]
            
            if orders_to_cancel:
                for order in orders_to_cancel:
                    try:
                        bybit_client.cancel_order(
                            category='linear',
                            symbol=order['symbol'],
                            orderId=order['orderId']
                        )
                        print(f"✅ 주문 취소 완료: {order['orderId']}")
                    except Exception as e:
                        print(f"⚠️ 주문 취소 실패: {order['orderId']}, 오류: {e}")
                message_text = MESSAGES['cancel_all_success']
            else:
                message_text = MESSAGES['no_open_order_to_cancel']
        else:
            message_text = f"{MESSAGES['cancel_all_fail']}: {orders_info.get('retMsg', '알 수 없는 오류')}"
        
        await bybit_bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        log_error_and_send_message(
            f"오류 발생: {e}",
            exc=e,
            chat_id=update.effective_chat.id
        )

async def history_command(update: Update, context):
    try:
        limit = 5
        if context.args:
            try:
                limit = int(context.args[0])
            except (ValueError, IndexError):
                await bybit_bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=MESSAGES['invalid_history_limit_usage']
                )
                return

        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM trade_log ORDER BY created_at DESC LIMIT ?", (limit,))
        trade_history = cursor.fetchall()
        conn.close()

        if not trade_history:
            message_text = MESSAGES['no_trade_history']
        else:
            message_text = MESSAGES['history_title'] + "\n\n"
            
            for trade in trade_history:
                symbol = trade['symbol']
                side = trade['side']
                pnl = trade['pnl']
                created_at = trade['created_at'].split('T')[0]
                
                message_text += (
                    f"**{MESSAGES['symbol']}:** {symbol} | **{MESSAGES['side']}:** {side}\n"
                    f"**{MESSAGES['unrealized_pnl']}:** {float(pnl):.2f} USDT | **{MESSAGES['date']}:** {created_at}\n\n"
                )

        await bybit_bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        log_error_and_send_message(
            f"오류 발생: {e}",
            exc=e,
            chat_id=update.effective_chat.id
        )

async def health_command(update: Update, context):
    try:
        health_check = bybit_client.get_wallet_balance(accountType="UNIFIED")
        
        if health_check['retCode'] == 0:
            status_text = MESSAGES['health_status_ok']
        else:
            status_text = f"{MESSAGES['health_status_fail']}: {health_check.get('retMsg', '알 수 없는 오류')}"
            
        message_text = (
            f"**{MESSAGES['health_title']}**\n"
            f"▪️ **{MESSAGES['bybit_api']}:** {status_text}\n"
            f"▪️ **{MESSAGES['telegram_bot']}:** {MESSAGES['health_status_ok']}\n"
        )

        await bybit_bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        log_error_and_send_message(
            f"오류 발생: {e}",
            exc=e,
            chat_id=update.effective_chat.id
        )
        
async def menu_command(update: Update, context):
    keyboard = [
        [
            InlineKeyboardButton(MESSAGES['menu_open_orders'], callback_data="open_orders"),
            InlineKeyboardButton(MESSAGES['menu_positions'], callback_data="positions")
        ],
        [
            InlineKeyboardButton(MESSAGES['menu_balance'], callback_data="balance"),
            InlineKeyboardButton(MESSAGES['menu_pf'], callback_data="pf")
        ],
        [
            InlineKeyboardButton(MESSAGES['menu_history'], callback_data="history"),
            InlineKeyboardButton(MESSAGES['menu_health'], callback_data="health")
        ],
        [
            InlineKeyboardButton(MESSAGES['menu_cancel_all'], callback_data="cancel_all")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await bybit_bot.send_message(
        chat_id=update.effective_chat.id,
        text=MESSAGES['menu_title'],
        reply_markup=reply_markup
    )

async def pnl_add_command(update: Update, context):
    try:
        if not context.args:
            await bybit_bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ 사용법: /pnl_add [심볼명] (예: /pnl_add BTC)"
            )
            return

        symbol = context.args[0].upper() + 'USDT'
        response = bybit_client.get_closed_pnl(category="linear", symbol=symbol, limit=5)

        if response['retCode'] == 0 and response['result']['list']:
            records = response['result']['list']
            keyboard = []
            
            # 봇 메모리(context.user_data)에 임시로 기록 저장
            context.user_data['pnl_records'] = records

            for idx, record in enumerate(records):
                pnl = float(record['closedPnl'])
                created_time = datetime.fromtimestamp(int(record['createdTime']) / 1000).strftime('%m-%d %H:%M')
                button_text = f"PNL: {pnl:.2f} | {created_time}"
                
                # 콜백 데이터에는 인덱스와 액션만 담습니다.
                callback_data = json.dumps({'a': 'add_pnl', 'idx': idx})
                
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            if keyboard:
                reply_markup = InlineKeyboardMarkup(keyboard)
                await bybit_bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"📊 **{symbol}**의 최근 청산 기록입니다. DB에 저장할 기록을 선택하세요:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await bybit_bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ 청산 기록을 찾을 수 없습니다."
                )
        else:
            await bybit_bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"⚠️ 종목 '{symbol}'의 청산 기록을 찾을 수 없습니다."
            )

    except Exception as e:
        log_error_and_send_message(f"오류 발생: {e}", exc=e, chat_id=update.effective_chat.id)

async def button_callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    data = json.loads(callback_data)
    action = data.get('a')

    if action == "add_pnl":
        idx = data.get('idx')
        
        # 메모리(context.user_data)에서 기록을 불러옵니다.
        records = context.user_data.get('pnl_records', [])
        
        if idx is not None and len(records) > idx:
            record = records[idx]
            conn = get_db_connection()
            try:
                # DB 저장에 필요한 데이터로 변환
                trade_data = {
                    'symbol': record['symbol'],
                    'side': record['side'],
                    'entry_price': float(record['avgEntryPrice']),
                    'exit_price': float(record['avgExitPrice']),
                    'qty': float(record['closedSize']),
                    'pnl': float(record['closedPnl']),
                    'fee': float(record.get('openFee', 0)) + float(record.get('closeFee', 0)),
                    'created_at': datetime.fromtimestamp(int(record['createdTime']) / 1000).isoformat()
                }
                
                record_trade_result_db(conn, trade_data)
                
                # 성공 메시지
                await query.edit_message_text(text=f"✅ PNL 기록이 DB에 성공적으로 저장되었습니다:\n`{trade_data['symbol']}` - `{trade_data['pnl']:.2f}` USDT")
                
                # 저장 후 메모리에서 기록 삭제 (선택 사항)
                if 'pnl_records' in context.user_data:
                    del context.user_data['pnl_records']

            except Exception as e:
                log_error_and_send_message(f"DB 저장 중 오류 발생: {e}", exc=e, chat_id=query.message.chat_id)
            finally:
                conn.close()
        else:
            await query.edit_message_text(text="⚠️ 해당 기록을 찾을 수 없습니다. 다시 시도해주세요.")
    elif callback_data == "open_orders":
        await open_orders_command(update, context)
    elif callback_data == "positions":
        await positions_command(update, context)
    elif callback_data == "balance":
        await balance_command(update, context)
    elif callback_data == "pf":
        await pf_command(update, context)
    elif callback_data == "history":
        await history_command(update, context)
    elif callback_data == "health":
        await health_command(update, context)
    elif callback_data == "cancel_all":
        await cancel_all_command(update, context)

def main():
    application = Application.builder().token(TELE_BYBIT_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("open_orders", open_orders_command))
    application.add_handler(CommandHandler("positions", positions_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("pf", pf_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("cancel_all", cancel_all_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("pnl_add", pnl_add_command))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    print("Telegram bot started...")
    application.run_polling(poll_interval=1)

if __name__ == "__main__":
    main()