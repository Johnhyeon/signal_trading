import time
from datetime import datetime

def aggregate_closed_positions(records):
    """
    Bybit closed order 기록을 입력받아 종목별로 합산된 closed position 리스트를 반환합니다.
    """
    aggregated_positions = {}
    for record in records:
        symbol = record['symbol']
        side = record['side']
        position_key = (symbol, side)

        if position_key not in aggregated_positions:
            aggregated_positions[position_key] = {
                'symbol': symbol,
                'side': side,
                'total_pnl': 0.0,
                'total_qty': 0.0,
                'total_fee': 0.0,
                'total_entry_value': 0.0,
                'total_exit_value': 0.0,
                'created_time': int(record['createdTime']),
            }
        
        pos = aggregated_positions[position_key]
        pos['total_pnl'] += float(record['closedPnl'])
        pos['total_qty'] += float(record['closedSize'])
        pos['total_fee'] += float(record.get('openFee', 0)) + float(record.get('closeFee', 0))
        pos['total_entry_value'] += float(record.get('cumEntryValue', 0))
        pos['total_exit_value'] += float(record.get('cumExitValue', 0))
        
        pos['created_time'] = max(pos['created_time'], int(record['createdTime']))
    
    final_positions = []
    for key, pos in aggregated_positions.items():
        if pos['total_qty'] > 0:
            pos['avg_entry_price'] = pos['total_entry_value'] / pos['total_qty']
            pos['avg_exit_price'] = pos['total_exit_value'] / pos['total_qty']
        else:
            pos['avg_entry_price'] = 0.0
            pos['avg_exit_price'] = 0.0
            
        final_positions.append(pos)
        
    final_positions.sort(key=lambda x: x['created_time'], reverse=True)
    
    return final_positions