import asyncio
import decimal
from api_clients import bybit_client, bybit_bot, TELE_BYBIT_LOG_CHAT_ID
from message_parser import parse_telegram_message, parse_cancel_message

# 메시지 ID와 주문 정보를 매핑할 전역 딕셔너리
active_orders = {}

async def send_bybit_summary_msg(order_info, adjusted_qty, order_result):
    """Bybit 주문 결과를 텔레그램 봇으로 전송"""
    message_summary = (
        "📈 **자동 주문 접수 완료**\n\n"
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
        "📈 **주문 취소 완료**\n"
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
        f"⚠️ **{symbol} 주문 실패**\n"
        f"▪️ **사유:** {reason}"
    )

    await bybit_bot.send_message(
        chat_id=TELE_BYBIT_LOG_CHAT_ID,
        text=message_summary,
        parse_mode='Markdown'
    )
    
def execute_bybit_order(order_info, message_id):
    """
    Bybit API를 사용하여 주문을 실행합니다.
    """
    global active_orders
    print(f"Bybit 주문 실행 중: {order_info['symbol']}")
    try:
        # 'NOW' 진입가일 경우 시장가 주문
        if order_info['entry_price'] == 'NOW':
            order_type = "Market"
            order_price = None  # 시장가 주문에서는 가격을 지정하지 않음
            print("Entry NOW. Placing a Market order.")

            # 시장가 주문일 경우 종목에 따라 레버리지 자동 설정
            symbol = order_info['symbol']
            if symbol == 'BTCUSDT' or symbol == 'ETHUSDT':
                order_info['leverage'] = 3
                print(f"{symbol}이므로 레버리지를 3x로 설정합니다.")
            elif symbol == 'SOLUSDT':
                order_info['leverage'] = 2
                print(f"{symbol}이므로 레버리지를 2x로 설정합니다.")
            else:
                order_info['leverage'] = 1
                print(f"기타 알트코인이므로 레버리지를 1x로 설정합니다.")

        else:
            order_type = "Limit"
            order_price = str(order_info['entry_price'])
            print("Placing a Limit order.")

        # 1. 계좌 잔고 조회 및 주문 수량 계산
        wallet_balance = bybit_client.get_wallet_balance(accountType="UNIFIED")
        usdt_balance = next((item for item in wallet_balance['result']['list'][0]['coin'] if item['coin'] == 'USDT'), None)
        
        if usdt_balance:
            total_usdt = float(usdt_balance['equity'])
            trade_amount = total_usdt * order_info['fund_percentage']
            print("총 USDT 잔고:", round(total_usdt))
            print("거래에 사용할 USDT 금액:", round(trade_amount))
        else:
            print("USDT 잔고를 찾을 수 없습니다.")
            return

        # 'NOW' 주문일 경우, 주문 수량 계산을 위해 현재 가격을 조회
        if order_info['entry_price'] == 'NOW':
            ticker_info = bybit_client.get_tickers(category="linear", symbol=order_info['symbol'])
            current_price = float(ticker_info['result']['list'][0]['lastPrice'])
            order_qty = (trade_amount * order_info['leverage']) / current_price
        else:
            order_qty = (trade_amount * order_info['leverage']) / float(order_info['entry_price'])
        
        print("총 거래 금액:", round(trade_amount * order_info['leverage']))
        print("계산된 주문 수량(코인):", round(order_qty, 3))

        # 2. 종목 정보 조회 및 주문 수량 정밀도 조정
        instrument_info = bybit_client.get_instruments_info(
            category="linear",
            symbol=order_info['symbol']
        )

        if instrument_info['retCode'] == 0 and instrument_info['result']['list']:
            lot_size_filter = instrument_info['result']['list'][0]['lotSizeFilter']
            qty_step = float(lot_size_filter['qtyStep'])
        else:
            print(f"오류: {order_info['symbol']} 종목 정보를 찾을 수 없습니다. 주문을 취소합니다.")
            return # 함수를 여기서 종료
        
        lot_size_filter = instrument_info['result']['list'][0]['lotSizeFilter']
        qty_step = float(lot_size_filter['qtyStep'])
        adjusted_qty = round(order_qty / qty_step) * qty_step
        # adjusted_qty를 decimal로 변환
        adjusted_qty_decimal = decimal.Decimal(adjusted_qty)
        # qty_step의 소수점 자릿수를 파악
        precision = len(str(qty_step).split('.')[1]) if '.' in str(qty_step) else 0
        # 정밀도에 맞게 수량 조정
        quantized_qty = adjusted_qty_decimal.quantize(decimal.Decimal('0.' + '0'*precision))

        # 3. 레버리지 설정 (이전 로직 유지)
        position_info = bybit_client.get_positions(
            category="linear",
            symbol=order_info['symbol']
        )
        
        if position_info['retCode'] == 0 and position_info['result']['list']:
            current_leverage = int(position_info['result']['list'][0]['leverage'])
        else:
            current_leverage = 0 # 열린 포지션이 없으면 레버리지 0으로 간주

        # 'NOW' 주문 로직을 위해 레버리지 설정 부분이 order_info['leverage'] 값을 사용하도록 수정
        if current_leverage != order_info['leverage']:
            bybit_client.set_leverage(
                category="linear",
                symbol=order_info['symbol'],
                buyLeverage=str(order_info['leverage']),
                sellLeverage=str(order_info['leverage'])
            )
            print(f"레버리지를 {order_info['leverage']}x로 설정했습니다.")

        # 4. 주문 실행 (수정된 주문 타입과 가격 사용)
        order_result = bybit_client.place_order(
            category="linear",
            symbol=order_info['symbol'],
            side=order_info['side'],
            orderType=order_type,
            qty=str(quantized_qty),
            price=order_price,
            takeProfit=str(order_info['targets'][0]),
            stopLoss=str(order_info['stop_loss'])
        )

        # 5. 주문 결과 메시지 전송
        if order_result and order_result['retCode'] == 0:
            print("주문이 성공적으로 접수되었습니다.")
            bybit_order_id = order_result['result']['orderId']
            # message_id를 사용하여 딕셔너리에 저장
            active_orders[message_id] = {'orderId': bybit_order_id, 'symbol': order_info['symbol']}
            
            # 텔레그램 요약 메시지 전송
            asyncio.run_coroutine_threadsafe(
                send_bybit_summary_msg(order_info, adjusted_qty, order_result),
                asyncio.get_event_loop()
            )
        else:
            print("주문 접수 실패:", order_result)
            asyncio.run_coroutine_threadsafe(
                send_bybit_failure_msg(order_info['symbol'], reason=order_result['retMsg']),
                asyncio.get_event_loop()
            )

    except Exception as e:
        print(f"Bybit 주문 중 오류 발생: {e}")
        asyncio.run_coroutine_threadsafe(
            send_bybit_failure_msg(order_info['symbol'], reason=str(e)),
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
                print(f"{symbol_to_cancel} 종목의 모든 주문이 성공적으로 취소되었습니다.")
                await send_bybit_cancel_msg(symbol_to_cancel)
                
                # active_orders 딕셔너리에서 해당 종목 주문 삭제
                orders_to_remove = [msg_id for msg_id, order_info in active_orders.items() if order_info['symbol'] == symbol_to_cancel]
                for msg_id in orders_to_remove:
                    del active_orders[msg_id]
            else:
                # 취소할 주문이 없는 경우
                print(f"오류: {symbol_to_cancel} 종목의 오픈 주문이 없습니다.")
                await send_bybit_failure_msg(symbol_to_cancel, "오픈 주문이 없어 취소할 수 없습니다.")
        else:
            print(f"{symbol_to_cancel} 종목 주문 취소 실패: {cancel_all_result['retMsg']}")
            await send_bybit_failure_msg(symbol_to_cancel, cancel_all_result['retMsg'])

    except Exception as e:
        print(f"주문 취소 중 오류 발생: {e}")
        await send_bybit_failure_msg(symbol_to_cancel, f"시스템 오류: {str(e)}")