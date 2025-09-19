import asyncio
from datetime import datetime
import json
import os
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from api_clients import bybit_client, bybit_bot, TELE_BYBIT_BOT_TOKEN
from portfolio_manager import generate_report
from utils import MESSAGES, log_error_and_send_message
from database_manager import get_active_orders, get_db_connection, record_trade_result_db, update_filled_status

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
        
        conn = get_db_connection()
        report = generate_report(conn, period=period)
        conn.close()

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
        ],
        [
            InlineKeyboardButton("✨ 중복 기록 정리", callback_data="dup_cleanup")
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
            
            context.user_data['pnl_records'] = records
            context.user_data['selected_orders'] = []

            keyboard = []
            for idx, record in enumerate(records):
                pnl = float(record['closedPnl'])
                qty = float(record['closedSize'])
                created_time = datetime.fromtimestamp(int(record['createdTime']) / 1000).strftime('%m-%d %H:%M')
                
                button_text = f"PNL: {pnl:.2f} | QTY: {qty:.4f} | {created_time}"
                
                callback_data = json.dumps({'a': 'select_pnl', 'idx': idx})
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            if keyboard:
                keyboard.append([InlineKeyboardButton("✅ 선택 완료 및 저장", callback_data='{"a": "complete_pnl"}')])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await bybit_bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"📊 **{symbol}**의 최근 청산 주문 목록입니다.\nDB에 저장할 주문을 선택하세요:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await bybit_bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ 선택 가능한 기록이 없습니다."
                )
        else:
            await bybit_bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"⚠️ 종목 '{symbol}'의 청산 기록을 찾을 수 없습니다."
            )
    except Exception as e:
        log_error_and_send_message(f"오류 발생: {e}", exc=e, chat_id=update.effective_chat.id)

async def pnl_dup_command(update: Update, context):
    """
    DB의 trade_log 테이블에서 중복된 레코드를 정리하는 명령어
    """
    try:
        deleted_count = clean_up_duplicate_trade_log()
        
        if deleted_count > 0:
            message_text = f"✅ 중복된 거래 기록 {deleted_count}개를 삭제했습니다."
        else:
            message_text = "ℹ️ 중복된 거래 기록이 없습니다."

        await bybit_bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        log_error_and_send_message(
            f"중복 기록 정리 중 오류 발생: {e}",
            exc=e,
            chat_id=update.effective_chat.id
        )

async def button_callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    data = json.loads(query.data)
    action = data.get('a')

    if action == "select_pnl":
        idx = data.get('idx')
        pnl_records = context.user_data.get('pnl_records', [])
        selected_orders = context.user_data.get('selected_orders', [])

        if idx is not None and len(pnl_records) > idx:
            record_id = pnl_records[idx]['orderId']
            
            if record_id in selected_orders:
                selected_orders.remove(record_id)
            else:
                selected_orders.append(record_id)

            context.user_data['selected_orders'] = selected_orders
            
            updated_keyboard = []
            for r_idx, record in enumerate(pnl_records):
                pnl = float(record['closedPnl'])
                qty = float(record['closedSize'])
                created_time = datetime.fromtimestamp(int(record['createdTime']) / 1000).strftime('%m-%d %H:%M')
                
                prefix = "✅ " if record['orderId'] in selected_orders else ""
                button_text = f"{prefix}PNL: {pnl:.2f} | QTY: {qty:.4f} | {created_time}"
                
                callback_data = json.dumps({'a': 'select_pnl', 'idx': r_idx})
                updated_keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            updated_keyboard.append([InlineKeyboardButton("✅ 선택 완료 및 저장", callback_data='{"a": "complete_pnl"}')])
            
            reply_markup = InlineKeyboardMarkup(updated_keyboard)
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            
    elif action == "complete_pnl":
        pnl_records = context.user_data.get('pnl_records', [])
        selected_order_ids = context.user_data.get('selected_orders', [])

        if not selected_order_ids:
            await query.edit_message_text(text="⚠️ 저장할 기록을 선택하지 않았습니다. 다시 시도해주세요.")
            return

        selected_records = [rec for rec in pnl_records if rec['orderId'] in selected_order_ids]
        aggregated_data = aggregate_selected_orders(selected_records)

        context.user_data['aggregated_pnl_data'] = aggregated_data
        
        # 새로운 중복 제거 함수 호출
        is_duplicate = check_and_delete_duplicate_trade_log(aggregated_data)
        if is_duplicate:
            await query.edit_message_text(
                text="❌ 동일한 PNL 기록이 이미 존재합니다. 중복 기록은 삭제되었습니다."
            )
            return

        conn = get_db_connection()
        try:
            active_orders_to_show = [
                order for order in get_active_orders(conn).values() 
                if order['symbol'] == aggregated_data['symbol'] and not order['filled']
            ]

            keyboard = []
            if active_orders_to_show:
                for order in active_orders_to_show:
                    message_id = order['message_id']
                    button_text = f"📊 {order['symbol']} | {order['side']} | Entry: {order['entry_price']}"
                    callback_data = json.dumps({'a': 'select_active_order', 'msg_id': message_id})
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            keyboard.append([InlineKeyboardButton("❌ 연결하지 않고 PNL 기록만 저장", callback_data='{"a": "skip_active_order"}')])
            
            reply_markup = InlineKeyboardMarkup(keyboard)

            if active_orders_to_show:
                await query.edit_message_text(
                    text="✅ PNL 기록이 준비되었습니다. 이 PNL과 연결할 활성 주문을 선택하세요:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    text="⚠️ 해당 PNL과 연결할 활성 주문을 찾을 수 없습니다. PNL 기록만 저장합니다."
                )
                await query.answer()
                
                await handle_skip_active_order(query, context)
                return

        except Exception as e:
            log_error_and_send_message(f"활성 주문 목록 가져오는 중 오류 발생: {e}", exc=e, chat_id=query.message.chat_id)
        finally:
            conn.close()
    elif action == "select_active_order":
        msg_id = data.get('msg_id')
        aggregated_data = context.user_data.get('aggregated_pnl_data')

        if not aggregated_data:
            await query.edit_message_text(text="⚠️ PNL 기록 데이터가 유효하지 않습니다. 다시 시도해주세요.")
            return

        conn = get_db_connection()
        try:
            update_filled_status(conn, msg_id, 1)
            
            trade_data = {
                'symbol': aggregated_data['symbol'],
                'side': aggregated_data['side'],
                'entry_price': aggregated_data['entry_price'],
                'exit_price': aggregated_data['exit_price'],
                'qty': aggregated_data['qty'],
                'pnl': aggregated_data['pnl'],
                'fee': aggregated_data['fee'],
                'created_at': datetime.fromtimestamp(aggregated_data['created_at'] / 1000).isoformat()
            }
            record_trade_result_db(conn, trade_data)

            del context.user_data['pnl_records']
            del context.user_data['selected_orders']
            del context.user_data['aggregated_pnl_data']

            await query.edit_message_text(
                text=f"✅ 선택한 활성 주문({msg_id})이 '체결 완료' 상태로 변경되었으며, PNL 기록이 성공적으로 저장되었습니다."
            )

        except Exception as e:
            log_error_and_send_message(f"활성 주문 업데이트 중 오류 발생: {e}", exc=e, chat_id=query.message.chat_id)
        finally:
            conn.close()

    elif action == "skip_active_order":
        await handle_skip_active_order(query, context)
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
    elif callback_data == "dup_cleanup":
        await pnl_dup_command(update, context)

def aggregate_selected_orders(records):
    """
    선택된 closed order 기록들을 입력받아 하나의 합산된 포지션으로 반환합니다.
    """
    if not records:
        return None
    
    first_record = records[0]
    total_pnl = 0.0
    total_qty = 0.0
    total_fee = 0.0
    total_entry_value = 0.0
    total_exit_value = 0.0
    latest_created_time = 0
    
    for record in records:
        total_pnl += float(record['closedPnl'])
        total_qty += float(record['closedSize'])
        total_fee += float(record.get('openFee', 0)) + float(record.get('closeFee', 0))
        total_entry_value += float(record.get('cumEntryValue', 0))
        total_exit_value += float(record.get('cumExitValue', 0))
        latest_created_time = max(latest_created_time, int(record['createdTime']))
    
    aggregated_data = {
        'symbol': first_record['symbol'],
        'side': first_record['side'],
        'qty': total_qty,
        'pnl': total_pnl,
        'fee': total_fee,
        'created_at': latest_created_time,
    }
    
    if total_qty > 0:
        aggregated_data['entry_price'] = total_entry_value / total_qty
        aggregated_data['exit_price'] = total_exit_value / total_qty
    else:
        aggregated_data['entry_price'] = 0.0
        aggregated_data['exit_price'] = 0.0

    return aggregated_data

async def handle_skip_active_order(query, context):
    """
    PNL 기록만 저장하고 활성 주문을 건너뛰는 헬퍼 함수
    """
    aggregated_data = context.user_data.get('aggregated_pnl_data')

    if not aggregated_data:
        await query.edit_message_text(text="⚠️ PNL 기록 데이터가 유효하지 않습니다. 다시 시도해주세요.")
        return
    
    is_duplicate = check_and_delete_duplicate_trade_log(aggregated_data)
    if is_duplicate:
        await query.edit_message_text(
            text="❌ 동일한 PNL 기록이 이미 존재합니다. 중복 기록은 삭제되었습니다."
        )
        return

    conn = get_db_connection()
    try:
        trade_data = {
            'symbol': aggregated_data['symbol'],
            'side': aggregated_data['side'],
            'entry_price': aggregated_data['entry_price'],
            'exit_price': aggregated_data['exit_price'],
            'qty': aggregated_data['qty'],
            'pnl': aggregated_data['pnl'],
            'fee': aggregated_data['fee'],
            'created_at': datetime.fromtimestamp(aggregated_data['created_at'] / 1000).isoformat()
        }
        record_trade_result_db(conn, trade_data)

        del context.user_data['pnl_records']
        del context.user_data['selected_orders']
        del context.user_data['aggregated_pnl_data']

        await query.edit_message_text(
            text=f"✅ PNL 기록이 DB에 성공적으로 저장되었습니다. (활성 주문 건너뜀)"
        )
    except Exception as e:
        log_error_and_send_message(f"PNL 기록 저장 중 오류 발생: {e}", exc=e, chat_id=query.message.chat_id)
    finally:
        conn.close()

def check_and_delete_duplicate_trade_log(trade_data):
    """
    단일 trade_data에 대한 중복 레코드를 확인하고 삭제
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    pnl_rounded = round(trade_data['pnl'], 6)
    qty_rounded = round(trade_data['qty'], 6)
    created_at_dt = datetime.fromtimestamp(trade_data['created_at'] / 1000)
    created_at_str = created_at_dt.strftime('%Y-%m-%d %H:%M:%S')

    try:
        cursor.execute("""
            SELECT COUNT(*) FROM trade_log
            WHERE symbol = ? AND side = ? AND pnl = ? AND qty = ? AND created_at = ?
        """, (trade_data['symbol'], trade_data['side'], pnl_rounded, qty_rounded, created_at_str))
        count = cursor.fetchone()[0]

        if count > 0:
            print("❌ 중복 레코드가 발견되었습니다. 삭제합니다.")
            cursor.execute("""
                DELETE FROM trade_log
                WHERE symbol = ? AND side = ? AND pnl = ? AND qty = ? AND created_at = ?
            """, (trade_data['symbol'], trade_data['side'], pnl_rounded, qty_rounded, created_at_str))
            conn.commit()
            return True
        else:
            print("✅ 중복 레코드가 없습니다. 정상적으로 진행합니다.")
            return False

    except Exception as e:
        print(f"중복 레코드 확인 및 삭제 중 오류 발생: {e}")
        return False
    finally:
        conn.close()

def clean_up_duplicate_trade_log():
    """
    DB의 trade_log 테이블 전체를 스캔하여 중복된 레코드를 모두 삭제
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    deleted_count = 0
    try:
        # 중복된 레코드를 찾는 쿼리
        cursor.execute("""
            SELECT symbol, side, pnl, qty, created_at, MIN(rowid)
            FROM trade_log
            GROUP BY symbol, side, pnl, qty, created_at
            HAVING COUNT(*) > 1
        """)
        duplicates = cursor.fetchall()
        
        if not duplicates:
            print("ℹ️ DB에 중복된 레코드가 없습니다.")
            return 0

        # 중복된 각 그룹에서 가장 오래된 하나를 제외하고 모두 삭제
        for dup in duplicates:
            symbol, side, pnl, qty, created_at, min_rowid = dup
            cursor.execute("""
                DELETE FROM trade_log
                WHERE symbol = ? AND side = ? AND pnl = ? AND qty = ? AND created_at = ? AND rowid != ?
            """, (symbol, side, pnl, qty, created_at, min_rowid))
            deleted_count += cursor.rowcount
        
        conn.commit()
        print(f"✅ DB에서 중복된 레코드 {deleted_count}개를 삭제했습니다.")
        return deleted_count
    
    except Exception as e:
        print(f"전체 중복 레코드 정리 중 오류 발생: {e}")
        conn.rollback()
        return 0
    finally:
        conn.close()

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
    application.add_handler(CommandHandler("pnl_dup", pnl_dup_command))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    print("Telegram bot started...")
    application.run_polling(poll_interval=1)

if __name__ == "__main__":
    main()