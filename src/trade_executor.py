import asyncio
from datetime import datetime
import decimal
import time
from api_clients import bybit_client, bybit_bot, TELE_BYBIT_LOG_CHAT_ID
from message_parser import parse_telegram_message, parse_cancel_message
from portfolio_manager import record_trade_result
from utils import MESSAGES, log_error_and_send_message
from database_manager import get_active_orders, save_active_order, delete_active_order, record_trade_result_db

# 메시지 ID와 주문 정보를 매핑할 전역 딕셔너리 (이제 DB에서 불러와서 사용)
# active_orders = {} # 이 전역 변수는 이제 사용하지 않습니다.

# 이미 청산 모니터링이 시작된 메시지 ID를 추적하는 set
monitored_trade_ids = set()

# 종목명 스케일링 인자 리스트
SCALING_FACTORS = [1000, 10000, 100000]

async def send_bybit_summary_msg(order_info, adjusted_qty, order_result):
    """Bybit 주문 결과를 텔레그램 봇으로 전송"""
    message_summary = (
        MESSAGES['order_summary_title'] + "\n\n"
        f"🚀 **Symbol:** ${order_info['symbol']}\n"
        f"📌 **Position:** {order_info['side']}\n"
        f"⚙️ **Leverage:** {order_info['leverage']}x\n"
        f"🎯 **Entry:** {order_info['entry_price']}\n"
        f"💰 **Qty:** {round(adjusted_qty)}\n\n"
        f"🎯 **TP:** {', '.join(map(str, order_info['targets']))}\n"
        f"🛑 **SL:** {order_info['stop_loss']}"
    )

    await bybit_bot.send_message(
        chat_id=TELE_BYBIT_LOG_CHAT_ID,
        text=message_summary,
        parse_mode='Markdown'
    )

async def send_bybit_cancel_msg(symbol):
    """Bybit 주문 취소 완료 메시지를 텔레그램 봇으로 전송"""
    message_summary = (
        MESSAGES['order_cancel_complete'] + "\n"
        f"🚀 **Symbol:** ${symbol}\n"
    )

    await bybit_bot.send_message(
        chat_id=TELE_BYBIT_LOG_CHAT_ID,
        text=message_summary,
        parse_mode='Markdown'
    )

async def record_trade_result_on_close(symbol, message_id):
    """
    포지션이 청산될 때까지 모니터링하고, 청산되면 거래 결과를 기록하고 active_orders에서 제거합니다.
    """
    print(MESSAGES['monitor_position_close'].format(symbol=symbol))
    
    # 이전에 열린 포지션이 있는지 확인하는 플래그
    is_position_open = False
    
    try: # try 블록 추가
        while True:
            try:
                positions_info = bybit_client.get_positions(category="linear", symbol=symbol)
                
                if positions_info['retCode'] == 0 and positions_info['result']['list']:
                    position = positions_info['result']['list'][0]
                    
                    # 포지션이 열렸는지 확인
                    if float(position['size']) > 0:
                        is_position_open = True
                    
                    # 포지션이 열린 후 닫혔는지 확인
                    if is_position_open and float(position['size']) == 0:
                        print(MESSAGES['position_closed_success'].format(symbol=symbol))
                        
                        closed_pnl_info = bybit_client.get_closed_pnl(category="linear", symbol=symbol, limit=1)
                        
                        if closed_pnl_info['retCode'] == 0 and closed_pnl_info['result']['list']:
                            closed_trade_data = closed_pnl_info['result']['list'][0]
                            
                            trade_result = {
                                'symbol': closed_trade_data['symbol'],
                                'side': closed_trade_data['side'],
                                'entry_price': float(closed_trade_data['avgEntryPrice']),
                                'exit_price': float(closed_trade_data['avgExitPrice']),
                                'qty': float(closed_trade_data['closedSize']),
                                'pnl': float(closed_trade_data['closedPnl']),
                                'created_at': datetime.fromtimestamp(int(closed_trade_data['createdTime']) / 1000).isoformat()
                            }
                            
                            record_trade_result_db(trade_result) # DB에 기록
                            
                            delete_active_order(message_id) # DB에서 삭제
                            print(f"✅ 포지션 청산 완료 후, active_orders DB에서 {symbol} 주문을 제거했습니다.")
                                
                            print(MESSAGES['trade_record_saved_success'].format(symbol=symbol))
                            await bybit_bot.send_message(
                                chat_id=TELE_BYBIT_LOG_CHAT_ID,
                                text=MESSAGES['trade_closed_pnl_message'].format(symbol=symbol, pnl=trade_result['pnl'])
                            )
                        else:
                            print(MESSAGES['trade_record_fetch_fail'].format(symbol=symbol))
                            
                        return
            except Exception as e:
                print(MESSAGES['position_monitor_error'].format(error_msg=e))
                
            await asyncio.sleep(5)
    finally: # finally 블록 추가
        if message_id in monitored_trade_ids:
            monitored_trade_ids.remove(message_id)

def execute_bybit_order(order_info, message_id):
    """
    Bybit API를 사용하여 주문을 실행합니다.
    """
    # active_orders 전역 변수 사용 제거
    
    # === 소수점 종목 자동 변환 로직 추가 ===
    original_symbol = order_info['symbol']
    
    try:
        # 1. 먼저 원래 종목명으로 주문을 시도
        print(f"Bybit 주문 실행 중: {original_symbol}")
        
        # 'NOW' 진입가일 경우 시장가 주문
        if order_info['entry_price'] == 'NOW':
            order_type = "Market"
            order_price = None
        else:
            order_type = "Limit"
            order_price = str(order_info['entry_price'])

        # 1-1. 계좌 잔고 조회 및 주문 수량 계산 (로직 유지)
        wallet_balance = bybit_client.get_wallet_balance(accountType="UNIFIED")
        usdt_balance = next((item for item in wallet_balance['result']['list'][0]['coin'] if item['coin'] == 'USDT'), None)
        if not usdt_balance:
            log_error_and_send_message(MESSAGES['usdt_balance_not_found'])
            return

        total_usdt = float(usdt_balance['equity'])
        trade_amount = total_usdt * order_info['fund_percentage']

        if order_info['entry_price'] == 'NOW':
            # Entry NOW일 때 종목별 레버리지 설정 로직 추가
            symbol = original_symbol
            if symbol == 'BTCUSDT' or symbol == 'ETHUSDT':
                order_info['leverage'] = 100
            elif symbol == 'SOLUSDT':
                order_info['leverage'] = 35
            else:
                order_info['leverage'] = 10
            
            ticker_info = bybit_client.get_tickers(category="linear", symbol=original_symbol)
            current_price = float(ticker_info['result']['list'][0]['lastPrice'])
            order_qty = (trade_amount * order_info['leverage']) / current_price
        else:
            order_qty = (trade_amount * order_info['leverage']) / float(order_info['entry_price'])

        # 1-2. 종목 정보 조회 및 주문 수량 정밀도 조정 (로직 유지)
        instrument_info = bybit_client.get_instruments_info(category="linear", symbol=original_symbol)
        lot_size_filter = instrument_info['result']['list'][0]['lotSizeFilter']
        qty_step = float(lot_size_filter['qtyStep'])
        adjusted_qty = round(order_qty / qty_step) * qty_step
        adjusted_qty_decimal = decimal.Decimal(adjusted_qty)
        precision = len(str(qty_step).split('.')[1]) if '.' in str(qty_step) else 0
        quantized_qty = adjusted_qty_decimal.quantize(decimal.Decimal('0.' + '0'*precision))

        # 1-3. 레버리지 설정 (로직 유지)
        try:
            position_info = bybit_client.get_positions(category="linear", symbol=original_symbol)
            current_leverage = int(position_info['result']['list'][0]['leverage']) if position_info['retCode'] == 0 and position_info['result']['list'] else 0
            
            # 현재 레버리지와 요청된 레버리지가 다를 경우에만 설정
            if float(current_leverage) != order_info['leverage']:
                bybit_client.set_leverage(
                    category="linear",
                    symbol=original_symbol,
                    buyLeverage=str(order_info['leverage']),
                    sellLeverage=str(order_info['leverage'])
                )
            else:
                print("ℹ️ 레버리지가 이미 설정된 값과 동일합니다. 변경을 건너뜁니다.")
        
        except Exception as e:
            error_message = str(e)
            # 레버리지 관련 에러인지 확인
            if 'leverage invalid' in error_message or 'leverage not modified' in error_message:
                print(f"⚠️ 레버리지 설정 오류 발생. 최대 레버리지를 확인합니다.")
                # 종목 정보 조회
                instrument_info = bybit_client.get_instruments_info(category="linear", symbol=original_symbol)
                if instrument_info['retCode'] == 0 and instrument_info['result']['list']:
                    max_leverage = instrument_info['result']['list'][0]['leverageFilter']['maxLeverage']
                    
                    if order_info['leverage'] > float(max_leverage):
                        # 요청 레버리지 조정
                        order_info['leverage'] = float(max_leverage)
                        print(MESSAGES['leverage_exceeded_warning'].format(
                            requested_leverage=int(order_info['leverage']),
                            max_leverage=max_leverage
                        ))
                    
                    # 레버리지를 재조정했더라도, 현재 포지션의 레버리지와 비교하여 불필요한 호출을 막음
                    position_info_after_adjust = bybit_client.get_positions(category="linear", symbol=original_symbol)
                    current_leverage_after_adjust = int(position_info_after_adjust['result']['list'][0]['leverage']) if position_info_after_adjust['retCode'] == 0 and position_info_after_adjust['result']['list'] else 0

                    if float(current_leverage_after_adjust) != order_info['leverage']:
                        bybit_client.set_leverage(
                            category="linear",
                            symbol=original_symbol,
                            buyLeverage=str(order_info['leverage']),
                            sellLeverage=str(order_info['leverage'])
                        )
                    else:
                        print("ℹ️ 레버리지 자동 조정 후 확인 결과, 이미 설정된 값과 동일합니다. 변경을 건너뜁니다.")

                else:
                    print("종목 정보를 가져오는 데 실패했습니다. 레버리지 자동 조정 불가.")
                    log_error_and_send_message(
                        f"레버리지 조정을 위한 종목 정보 가져오기 실패.",
                        exc=e
                    )
                    return
            else:
                # 레버리지 관련 오류가 아닌 경우
                log_error_and_send_message(
                    f"Bybit 레버리지 설정 중 알 수 없는 오류 발생.",
                    exc=e
                )
                return

        # 1-4. 주문 실행
        order_result = bybit_client.place_order(
            category="linear",
            symbol=original_symbol,
            side=order_info['side'],
            orderType=order_type,
            qty=str(quantized_qty),
            price=order_price,
            takeProfit=str(order_info['targets'][0]),
            stopLoss=str(order_info['stop_loss'])
        )
    
    except Exception as e:
        # 2. 주문이 실패했을 경우, 특히 종목명 오류(10001)일 때 스케일링을 시도
        error_message = str(e)
        if '10001' in error_message:
            print(MESSAGES['scaling_attempt'].format(original_symbol=original_symbol))
            
            # 2-1. 스케일링된 종목명으로 주문 재시도
            found_symbol = None
            for factor in SCALING_FACTORS:
                symbol_to_check = f"{factor}{original_symbol}"
                
                try:
                    # 종목 유효성 검증
                    instrument_info = bybit_client.get_instruments_info(category="linear", symbol=symbol_to_check)
                    if instrument_info['retCode'] == 0 and instrument_info['result']['list']:
                        # 주문 정보 업데이트
                        order_info['symbol'] = symbol_to_check
                        if order_info['entry_price'] != 'NOW':
                            order_info['entry_price'] *= factor
                            print(MESSAGES['scaled_entry_price'].format(entry_price=order_info['entry_price']))
                        order_info['stop_loss'] *= factor
                        order_info['targets'] = [tp * factor for tp in order_info['targets']]

                        # 레버리지 설정 및 재계산 (수정된 로직 적용)
                        try:
                            position_info_scaled = bybit_client.get_positions(category="linear", symbol=symbol_to_check)
                            current_leverage_scaled = float(position_info_scaled['result']['list'][0]['leverage']) if position_info_scaled['retCode'] == 0 and position_info_scaled['result']['list'] else 0
                            
                            if float(current_leverage_scaled) != float(order_info['leverage']):
                                bybit_client.set_leverage(
                                    category="linear",
                                    symbol=symbol_to_check,
                                    buyLeverage=str(order_info['leverage']),
                                    sellLeverage=str(order_info['leverage'])
                                )
                            else:
                                print(f"ℹ️ {symbol_to_check}의 레버리지가 이미 설정된 값과 동일합니다. 변경을 건너뜁니다.")
                        except Exception as lev_e:
                            lev_error_message = str(lev_e)
                            if 'leverage invalid' in lev_error_message or 'leverage not modified' in lev_error_message:
                                print(f"⚠️ {symbol_to_check} 레버리지 설정 오류 발생. 최대 레버리지를 확인합니다.")
                                instrument_info_lev = bybit_client.get_instruments_info(category="linear", symbol=symbol_to_check)
                                if instrument_info_lev['retCode'] == 0 and instrument_info_lev['result']['list']:
                                    max_leverage = instrument_info_lev['result']['list'][0]['leverageFilter']['maxLeverage']
                                    if float(order_info['leverage']) > float(max_leverage):
                                        order_info['leverage'] = float(max_leverage)
                                        print(MESSAGES['leverage_exceeded_warning'].format(
                                            requested_leverage=int(order_info['leverage']),
                                            max_leverage=max_leverage
                                        ))
                                    
                                    # 레버리지를 재조정했더라도, 현재 포지션의 레버리지와 비교하여 불필요한 호출을 막음
                                    position_info_after_adjust = bybit_client.get_positions(category="linear", symbol=symbol_to_check)
                                    current_leverage_after_adjust = float(position_info_after_adjust['result']['list'][0]['leverage']) if position_info_after_adjust['retCode'] == 0 and position_info_after_adjust['result']['list'] else 0

                                    if float(current_leverage_after_adjust) != float(order_info['leverage']):
                                        bybit_client.set_leverage(
                                            category="linear",
                                            symbol=symbol_to_check,
                                            buyLeverage=str(order_info['leverage']),
                                            sellLeverage=str(order_info['leverage'])
                                        )
                                    else:
                                        print("ℹ️ 레버리지 자동 조정 후 확인 결과, 이미 설정된 값과 동일합니다. 변경을 건너뜁니다.")

                                else:
                                    print("종목 정보를 가져오는 데 실패했습니다. 레버리지 자동 조정 불가.")
                                    raise lev_e
                            else:
                                print(f"Bybit 레버리지 설정 중 알 수 없는 오류 발생: {lev_e}")
                                raise lev_e
                        
                        # 주문 수량 재계산
                        if order_info['entry_price'] == 'NOW':
                            ticker_info = bybit_client.get_tickers(category="linear", symbol=symbol_to_check)
                            current_price = float(ticker_info['result']['list'][0]['lastPrice'])
                            order_qty = (trade_amount * order_info['leverage']) / current_price
                        else:
                            # 스케일링된 가격과 레버리지로 주문 수량 다시 계산
                            order_qty = (trade_amount * order_info['leverage']) / float(order_info['entry_price'])
                        
                        lot_size_filter = instrument_info['result']['list'][0]['lotSizeFilter']
                        qty_step = float(lot_size_filter['qtyStep'])
                        max_qty = float(lot_size_filter['maxOrderQty'])
                        
                        if order_qty > max_qty:
                            print(MESSAGES['qty_exceeded_warning'].format(calculated_qty=order_qty, max_qty=max_qty))
                            adjusted_qty = max_qty
                        else:
                            adjusted_qty = round(order_qty / qty_step) * qty_step
                        
                        adjusted_qty_decimal = decimal.Decimal(adjusted_qty)
                        precision = len(str(qty_step).split('.')[1]) if '.' in str(qty_step) else 0
                        quantized_qty = adjusted_qty_decimal.quantize(decimal.Decimal('0.' + '0' * precision))
                        
                        # 재주문 실행
                        order_result = bybit_client.place_order(
                            category="linear",
                            symbol=order_info['symbol'],
                            side=order_info['side'],
                            orderType=order_type,
                            qty=str(quantized_qty),
                            price=order_info['entry_price'],
                            takeProfit=str(order_info['targets'][0]),
                            stopLoss=str(order_info['stop_loss'])
                        )
                        
                        if order_result and order_result['retCode'] == 0:
                            found_symbol = order_info['symbol']
                            print(MESSAGES['scaled_symbol_found_success'].format(found_symbol=found_symbol))
                            break # 루프 종료
                            
                    else:
                        print(MESSAGES['scaled_symbol_not_found'].format(symbol=symbol_to_check))

                except Exception as inner_e:
                    print(MESSAGES['scaled_reorder_error'], inner_e)
                    
            # 2-2. 스케일링 시도 후 성공 여부 확인
            if not found_symbol:
                log_error_and_send_message(
                    MESSAGES['all_scaling_failed'].format(original_symbol=original_symbol),
                    exc=e
                )
                return
            
        else: # 다른 종류의 오류일 경우
            log_error_and_send_message(
                MESSAGES['order_edit_system_error'].format(error_msg=e),
                exc=e
            )
            return

    # 3. 주문 성공 시 후속 로직 실행
    if order_result and order_result['retCode'] == 0:
        print(MESSAGES['order_accepted'])

        # 주문 ID를 order_result에서 추출
        bybit_order_id = order_result['result']['orderId']
        
        # 주문이 체결된 후 포지션 정보를 가져옵니다.
        time.sleep(1) # 포지션 업데이트 대기
        positions_info = bybit_client.get_positions(category="linear", symbol=order_info['symbol'])
        if positions_info['retCode'] == 0 and positions_info['result']['list']:
            # position_data = positions_info['result']['list'][0]
            # print(f"포지션 정보: {position_data}")
            # position_side = position_data['side']
            # print(f"포지션: {position_side}")
            # position_idx = position_data['positionIdx']
            
            # ✅ 수정: DB 저장을 위해 message_id를 포함하여 주문 정보를 딕셔너리에 담음
            order_data_to_save = {
                'message_id': message_id,
                'symbol': order_info['symbol'],
                'side': order_info['side'], # ✅ 이 부분을 이렇게 변경합니다.
                'entry_price': order_info['entry_price'],
                'targets': order_info['targets'],
                # 나머지 필드는 그대로 유지
                'positionIdx': None, # 체결되지 않았으므로 None으로 설정
                'orderId': bybit_order_id,
                'fund_percentage': order_info['fund_percentage'],
                'leverage': order_info['leverage'],
                'original_message': order_info['original_message']
            }
            save_active_order(order_data_to_save) # 데이터베이스에 저장
            
            # 텔레그램 요약 메시지 전송
            asyncio.run_coroutine_threadsafe(
                send_bybit_summary_msg(order_info, adjusted_qty, order_result),
                asyncio.get_event_loop()
            )

        else:
            log_error_and_send_message(
                MESSAGES['position_info_error']
            )

    else:
        # 이전에 처리되지 않은 다른 주문 실패
        log_error_and_send_message(
            f"{MESSAGES['order_failed']} {order_result['retMsg']}"
        )

            # ✅ 포지션 청산 모니터링 시작 (message_id 전달)
        if message_id not in monitored_trade_ids:
            monitored_trade_ids.add(message_id) # 모니터링 시작
            asyncio.run_coroutine_threadsafe(
                record_trade_result_on_close(order_info['symbol'], message_id),
                asyncio.get_event_loop()
            )
            

async def cancel_bybit_order(symbol_to_cancel):
    """
    지정된 종목의 미체결 주문을 모두 취소합니다.
    """
    # active_orders 전역 변수 사용 제거
    
    try:
        # Bybit API를 통해 해당 종목의 모든 미체결 주문을 취소합니다.
        cancel_all_result = bybit_client.cancel_all_orders(
            category="linear",
            symbol=symbol_to_cancel
        )

        if cancel_all_result['retCode'] == 0:
            if cancel_all_result['result']['list']:
                print(MESSAGES['cancel_all_success'].format(symbol=symbol_to_cancel))
                await send_bybit_cancel_msg(symbol_to_cancel)

                # ✅ 수정: DB에서 해당 종목 주문 삭제
                active_orders_from_db = get_active_orders()
                orders_to_remove = [msg_id for msg_id, order_info in active_orders_from_db.items() if order_info['symbol'] == symbol_to_cancel]
                for msg_id in orders_to_remove:
                    delete_active_order(msg_id)
            else:
                log_error_and_send_message(
                    MESSAGES['no_open_order_to_cancel'],
                    chat_id=TELE_BYBIT_LOG_CHAT_ID
                )
        else:
            log_error_and_send_message(
                MESSAGES['cancel_fail'].format(symbol=symbol_to_cancel, error_msg=cancel_all_result['retMsg']),
                chat_id=TELE_BYBIT_LOG_CHAT_ID
            )

    except Exception as e:
        log_error_and_send_message(
            MESSAGES['cancel_system_error'].format(error_msg=e),
            exc=e
        )


async def update_stop_loss_to_entry(symbol, side, position_idx, entry_price):
    """
    지정된 주문의 Stop Loss를 진입가로 수정합니다.
    """
    try:
        # Entry NOW 주문일 경우 현재 시장 가격을 SL로 설정
        if entry_price == "NOW":
            ticker_info = bybit_client.get_tickers(category="linear", symbol=symbol)
            if ticker_info['retCode'] == 0 and ticker_info['result']['list']:
                current_price = float(ticker_info['result']['list'][0]['lastPrice'])
                new_sl = str(current_price)
                await bybit_bot.send_message(
                    chat_id=TELE_BYBIT_LOG_CHAT_ID,
                    text=MESSAGES['sl_move_to_market_price'].format(price=new_sl)
                )
            else:
                log_error_and_send_message(
                    "현재 가격 정보를 가져오는 데 실패했습니다.",
                    chat_id=TELE_BYBIT_LOG_CHAT_ID
                )
                return
        else:
            new_sl = str(entry_price)

        amend_result = bybit_client.set_trading_stop(
            category="linear",
            symbol=symbol,
            side=side,
            positionIdx=position_idx,
            stopLoss=new_sl
        )
        
        if amend_result['retCode'] == 0:
            print(MESSAGES['sl_update_success'].format(symbol=symbol, new_sl=new_sl))
            await bybit_bot.send_message(
                chat_id=TELE_BYBIT_LOG_CHAT_ID,
                text=MESSAGES['sl_update_complete'].format(symbol=symbol, new_sl=new_sl)
            )
        else:
            log_error_and_send_message(
                MESSAGES['sl_update_fail_reason'].format(error_msg=amend_result['retMsg']),
                chat_id=TELE_BYBIT_LOG_CHAT_ID
            )
            
    except Exception as e:
        log_error_and_send_message(
            MESSAGES['sl_update_system_error'].format(error_msg=e),
            exc=e
        )

async def update_stop_loss_to_tp1(symbol, side, position_idx, tp1_price):
    """
    지정된 주문의 Stop Loss를 TP1 가격으로 수정합니다.
    """
    try:
        new_sl = str(tp1_price)
        amend_result = bybit_client.set_trading_stop(
            category="linear",
            symbol=symbol,
            side=side,
            positionIdx=position_idx,
            stopLoss=new_sl
        )
        
        if amend_result['retCode'] == 0:
            print(MESSAGES['sl_update_success'].format(symbol=symbol, new_sl=new_sl))
            await bybit_bot.send_message(
                chat_id=TELE_BYBIT_LOG_CHAT_ID,
                text=MESSAGES['sl_update_complete'].format(symbol=symbol, new_sl=new_sl)
            )
        else:
            log_error_and_send_message(
                MESSAGES['sl_update_fail_reason'].format(error_msg=amend_result['retMsg']),
                chat_id=TELE_BYBIT_LOG_CHAT_ID
            )
            
    except Exception as e:
        log_error_and_send_message(
            MESSAGES['sl_update_system_error'].format(error_msg=e),
            exc=e
        )
        
async def update_stop_loss_to_tp2(symbol, side, position_idx, tp2_price):
    """
    지정된 주문의 Stop Loss를 TP2 가격으로 수정합니다.
    """
    try:
        new_sl = str(tp2_price)
        amend_result = bybit_client.set_trading_stop(
            category="linear",
            symbol=symbol,
            side=side,
            positionIdx=position_idx,
            stopLoss=new_sl
        )
        
        if amend_result['retCode'] == 0:
            print(MESSAGES['sl_update_success'].format(symbol=symbol, new_sl=new_sl))
            await bybit_bot.send_message(
                chat_id=TELE_BYBIT_LOG_CHAT_ID,
                text=MESSAGES['sl_update_complete'].format(symbol=symbol, new_sl=new_sl)
            )
        else:
            log_error_and_send_message(
                MESSAGES['sl_update_fail_reason'].format(error_msg=amend_result['retMsg']),
                chat_id=TELE_BYBIT_LOG_CHAT_ID
            )
            
    except Exception as e:
        log_error_and_send_message(
            MESSAGES['sl_update_system_error'].format(error_msg=e),
            exc=e
        )

async def update_stop_loss_to_value(symbol, side, position_idx, new_sl_price):
    """
    지정된 주문의 Stop Loss를 특정 가격으로 수정합니다.
    """
    try:
        amend_result = bybit_client.set_trading_stop(
            category="linear",
            symbol=symbol,
            side=side,
            positionIdx=position_idx,
            stopLoss=str(new_sl_price)
        )

        if amend_result['retCode'] == 0:
            print(MESSAGES['sl_update_success'].format(symbol=symbol, new_sl=new_sl_price))
            await bybit_bot.send_message(
                chat_id=TELE_BYBIT_LOG_CHAT_ID,
                text=MESSAGES['sl_update_complete'].format(symbol=symbol, new_sl=new_sl_price)
            )
        elif amend_result['retCode'] == 34040:
            # ErrCode 34040은 "not modified"를 의미하며, 이미 동일한 값으로 설정되어 있다는 뜻입니다.
            print(f"ℹ️ SL 값이 이미 {new_sl_price}로 설정되어 있어 변경을 건너뜁니다. (ErrCode: 34040)")
            await bybit_bot.send_message(
                chat_id=TELE_BYBIT_LOG_CHAT_ID,
                text=f"ℹ️ **{symbol}** SL 값 변경 실패\n사유: `이미 설정된 값과 동일`"
            )
        else:
            log_error_and_send_message(
                MESSAGES['sl_update_fail_reason'].format(error_msg=amend_result['retMsg']),
                chat_id=TELE_BYBIT_LOG_CHAT_ID
            )

    except Exception as e:
        log_error_and_send_message(
            MESSAGES['sl_update_system_error'].format(error_msg=e),
            exc=e
        )

# DCA 주문을 실행하는 함수
def place_dca_order(order_info, dca_price):
    """
    DCA (Dollar-Cost Averaging) 주문을 실행합니다.
    """
    try:
        # ✅ 수정: 추가한 'dca_order_placed' 키 사용
        print(MESSAGES['dca_order_placed'].format(symbol=order_info['symbol'], price=dca_price))
    
        # 재고 잔액 및 거래량 계산
        wallet_balance = bybit_client.get_wallet_balance(accountType="UNIFIED")
        usdt_balance = next((item for item in wallet_balance['result']['list'][0]['coin'] if item['coin'] == 'USDT'), None)
        total_usdt = float(usdt_balance['equity'])
        trade_amount = total_usdt * order_info['fund_percentage']
        
        # 'leverage' 오류 해결
        order_qty = (trade_amount * order_info['leverage']) / dca_price

        # 정밀도 조정
        instrument_info = bybit_client.get_instruments_info(category="linear", symbol=order_info['symbol'])
        lot_size_filter = instrument_info['result']['list'][0]['lotSizeFilter']
        qty_step = float(lot_size_filter['qtyStep'])
        adjusted_qty = round(order_qty / qty_step) * qty_step
        adjusted_qty_decimal = decimal.Decimal(adjusted_qty)
        precision = len(str(qty_step).split('.')[1]) if '.' in str(qty_step) else 0
        quantized_qty = adjusted_qty_decimal.quantize(decimal.Decimal('0.' + '0' * precision))

        # DCA 주문 실행
        bybit_client.place_order(
            category="linear",
            symbol=order_info['symbol'],
            side=order_info['side'], # 동일한 방향
            orderType="Limit",
            qty=str(quantized_qty),
            price=str(dca_price)
        )
        # ✅ 수정: 추가한 'dca_order_success' 키 사용
        print(MESSAGES['dca_order_success'])

    except Exception as e:
        # ✅ 수정: 추가한 'dca_order_error' 키 사용
        log_error_and_send_message(
            MESSAGES['dca_order_fail'].format(error_msg=e),
            exc=e
        )