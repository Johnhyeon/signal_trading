import asyncio
from datetime import datetime
import decimal
import time
from api_clients import bybit_client, bybit_bot, TELE_BYBIT_LOG_CHAT_ID
from message_parser import parse_telegram_message, parse_cancel_message
from portfolio_manager import record_trade_result
# 수정: main.py 대신 utils.py에서 메시지 변수 임포트
from utils import MESSAGES

# 메시지 ID와 주문 정보를 매핑할 전역 딕셔너리
active_orders = {}

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

async def send_bybit_failure_msg(symbol, reason):
    """
    Bybit 주문 실패 메시지를 텔레그램 봇으로 전송합니다.
    """
    message_summary = (
        MESSAGES['order_fail_title'].format(symbol=symbol) + "\n"
        f"▪️ **사유:** `{reason}`"
    )

    await bybit_bot.send_message(
        chat_id=TELE_BYBIT_LOG_CHAT_ID,
        text=message_summary,
        parse_mode='Markdown'
    )

async def record_trade_result_on_close(symbol):
    """
    포지션이 청산될 때까지 모니터링하고, 청산되면 거래 결과를 기록합니다.
    """
    print(MESSAGES['monitor_position_close'].format(symbol=symbol))
    
    # 이전에 열린 포지션이 있는지 확인하는 플래그
    is_position_open = False
    
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
                    
                    # 닫힌 PNL 정보 가져오기
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
                        
                        # 새로운 파일에 기록
                        record_trade_result(trade_result)
                        
                        print(MESSAGES['trade_record_saved_success'].format(symbol=symbol))
                        await bybit_bot.send_message(
                            chat_id=TELE_BYBIT_LOG_CHAT_ID,
                            text=MESSAGES['trade_closed_pnl_message'].format(symbol=symbol, pnl=trade_result['pnl'])
                        )
                    else:
                        print(MESSAGES['trade_record_fetch_fail'].format(symbol=symbol))
                        
                    return # 작업 완료 후 루프 종료
        except Exception as e:
            print(MESSAGES['position_monitor_error'].format(error_msg=e))
            
        await asyncio.sleep(5) # 5초 대기

def execute_bybit_order(order_info, message_id):
    """
    Bybit API를 사용하여 주문을 실행합니다.
    """
    global active_orders
    
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
            print(MESSAGES['usdt_balance_not_found'])
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

        # 1-1. 계좌 잔고 조회 및 주문 수량 계산 (로직 유지)
        wallet_balance = bybit_client.get_wallet_balance(accountType="UNIFIED")
        usdt_balance = next((item for item in wallet_balance['result']['list'][0]['coin'] if item['coin'] == 'USDT'), None)
        if not usdt_balance:
            print(MESSAGES['usdt_balance_not_found'])
            return

        total_usdt = float(usdt_balance['equity'])
        trade_amount = total_usdt * order_info['fund_percentage']

        if order_info['entry_price'] == 'NOW':
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
                    asyncio.run_coroutine_threadsafe(
                        send_bybit_failure_msg(original_symbol, reason="Failed to get instrument info for leverage adjustment."),
                        asyncio.get_event_loop()
                    )
                    return
            else:
                # 레버리지 관련 오류가 아닌 경우
                print(f"Bybit 레버리지 설정 중 알 수 없는 오류 발생: {e}")
                asyncio.run_coroutine_threadsafe(
                    send_bybit_failure_msg(original_symbol, reason=str(e)),
                    asyncio.get_event_loop()
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
                        
                        lot_size_filter = instrument_info['result']['list'][0]['lotSizeFilter']
                        qty_step = float(lot_size_filter['qtyStep'])
                        adjusted_qty = round(order_qty / qty_step) * qty_step
                        adjusted_qty_decimal = decimal.Decimal(adjusted_qty)
                        precision = len(str(qty_step).split('.')[1]) if '.' in str(qty_step) else 0
                        quantized_qty = adjusted_qty_decimal.quantize(decimal.Decimal('0.' + '0'*precision))
                        
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
                print(MESSAGES['all_scaling_failed'].format(original_symbol=original_symbol))
                asyncio.run_coroutine_threadsafe(
                    send_bybit_failure_msg(original_symbol, MESSAGES['no_valid_symbol_found']),
                    asyncio.get_event_loop()
                )
                return
            
        else: # 다른 종류의 오류일 경우
            print(MESSAGES['order_edit_system_error'].format(error_msg=e))
            asyncio.run_coroutine_threadsafe(
                send_bybit_failure_msg(original_symbol, reason=str(e)),
                asyncio.get_event_loop()
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
            position_data = positions_info['result']['list'][0]
            position_side = position_data['side']
            position_idx = position_data['positionIdx']
            
            # message_id를 사용하여 딕셔너리에 포지션 정보 및 orderId를 저장
            active_orders[message_id] = {
                'symbol': order_info['symbol'],
                'side': position_side,
                'entry_price': order_info['entry_price'],
                'targets': order_info['targets'],
                'positionIdx': position_idx,
                'orderId': bybit_order_id  # orderId 추가
            }
            
            # 텔레그램 요약 메시지 전송
            asyncio.run_coroutine_threadsafe(
                send_bybit_summary_msg(order_info, adjusted_qty, order_result),
                asyncio.get_event_loop()
            )

            # ✅ 포지션 청산 모니터링 시작
            asyncio.run_coroutine_threadsafe(
                record_trade_result_on_close(order_info['symbol']),
                asyncio.get_event_loop()
            )
            
        else:
            print(MESSAGES['position_info_error'])
            asyncio.run_coroutine_threadsafe(
                send_bybit_failure_msg(order_info['symbol'], MESSAGES['sl_tp_disabled_warning']),
                asyncio.get_event_loop()
            )
    else:
        # 이전에 처리되지 않은 다른 주문 실패
        print(MESSAGES['order_failed'], order_result)
        asyncio.run_coroutine_threadsafe(
            send_bybit_failure_msg(order_info['symbol'], reason=order_result['retMsg']),
            asyncio.get_event_loop()
        )

async def cancel_bybit_order(symbol_to_cancel):
    """
    지정된 종목의 미체결 주문을 모두 취소합니다.
    """
    global active_orders

    try:
        # Bybit API를 통해 해당 종목의 모든 미체결 주문을 취소합니다.
        cancel_all_result = bybit_client.cancel_all_orders(
            category="linear",
            symbol=symbol_to_cancel
        )

        if cancel_all_result['retCode'] == 0:
            # --- 수정된 부분: 취소된 주문이 있는지 확인 ---
            if cancel_all_result['result']['list']:
                print(MESSAGES['cancel_all_success'].format(symbol=symbol_to_cancel))
                await send_bybit_cancel_msg(symbol_to_cancel)

                # active_orders 딕셔너리에서 해당 종목 주문 삭제
                orders_to_remove = [msg_id for msg_id, order_info in active_orders.items() if order_info['symbol'] == symbol_to_cancel]
                for msg_id in orders_to_remove:
                    del active_orders[msg_id]
            else:
                # 취소할 주문이 없는 경우
                print(MESSAGES['no_open_order_to_cancel'])
                await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['no_open_order_to_cancel'])
        else:
            print(MESSAGES['cancel_fail'].format(symbol=symbol_to_cancel, error_msg=cancel_all_result['retMsg']))
            await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['cancel_fail'].format(symbol=symbol_to_cancel, error_msg=cancel_all_result['retMsg']))

    except Exception as e:
        print(MESSAGES['cancel_system_error'].format(error_msg=e))
        await send_bybit_failure_msg(symbol_to_cancel, MESSAGES['cancel_system_error'].format(error_msg=str(e)))


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
                await send_bybit_failure_msg(symbol, "현재 가격 정보를 가져오는 데 실패했습니다.")
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
            print(MESSAGES['sl_update_fail'].format(symbol=symbol, error_msg=amend_result['retMsg']))
            await send_bybit_failure_msg(symbol, MESSAGES['sl_update_fail_reason'].format(error_msg=amend_result['retMsg']))
            
    except Exception as e:
        print(MESSAGES['sl_update_system_error'].format(error_msg=e))
        await send_bybit_failure_msg(symbol, MESSAGES['sl_update_system_error'].format(error_msg=str(e)))

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
            print(MESSAGES['sl_update_fail'].format(symbol=symbol, error_msg=amend_result['retMsg']))
            await send_bybit_failure_msg(symbol, MESSAGES['sl_update_fail_reason'].format(error_msg=amend_result['retMsg']))
            
    except Exception as e:
        print(MESSAGES['sl_update_system_error'].format(error_msg=e))
        await send_bybit_failure_msg(symbol, MESSAGES['sl_update_system_error'].format(error_msg=str(e)))
        
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
            print(MESSAGES['sl_update_fail'].format(symbol=symbol, error_msg=amend_result['retMsg']))
            await send_bybit_failure_msg(symbol, MESSAGES['sl_update_fail_reason'].format(error_msg=amend_result['retMsg']))
            
    except Exception as e:
        print(MESSAGES['sl_update_system_error'].format(error_msg=e))
        await send_bybit_failure_msg(symbol, MESSAGES['sl_update_system_error'].format(error_msg=str(e)))