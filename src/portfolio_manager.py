import json
import os
from datetime import datetime, timedelta
from utils import MESSAGES
from database_manager import record_trade_result_db, get_db_connection

def record_trade_result(conn, trade_data): # ✅ conn 인자 추가
    """
    거래 결과를 데이터베이스에 기록합니다.
    """
    try:
        record_trade_result_db(conn, trade_data) # ✅ conn 인자 전달

        # 콘솔에 이번 거래 로그 출력
        print("\n" + "="*30)
        print("✅ 이번 거래 로그가 데이터베이스에 저장되었습니다.")
        print(f"▪️ Symbol: {trade_data['symbol']}")
        print(f"▪️ P&L: {trade_data['pnl']:.2f}")
        print(f"▪️ Exit Price: {trade_data['exit_price']}")
        print("="*30 + "\n")
        
    except Exception as e:
        print(f"⚠️ 거래 기록을 데이터베이스에 저장하는 중 오류 발생: {e}")


def generate_report(conn, period='all'): # ✅ conn 인자 추가
    """
    거래 기록을 기반으로 통계 리포트를 생성합니다.
    period: 'all' (전체), 'daily', 'weekly' 등
    """
    cursor = conn.cursor()
    
    query = "SELECT * FROM trade_log"
    
    if period == 'day':
        # SQLite에서 현재 시점으로부터 1일 전까지의 데이터 조회
        query += " WHERE created_at >= strftime('%Y-%m-%d %H:%M:%S', 'now', '-1 day')"
    elif period == 'week':
        # SQLite에서 현재 시점으로부터 7일 전까지의 데이터 조회
        query += " WHERE created_at >= strftime('%Y-%m-%d %H:%M:%S', 'now', '-7 day')"

    cursor.execute(query)
    logs = cursor.fetchall()

    if not logs:
        return MESSAGES['no_trades_in_period']

    total_pnl = sum(log['pnl'] for log in logs)
    win_trades = sum(1 for log in logs if log['pnl'] > 0)
    total_trades = len(logs)
    win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
    print("running")
    
    report_message = (
        f"{MESSAGES['report_title'].format(period=period.capitalize())}\n\n"
        f"{MESSAGES['report_total_trades'].format(total_trades=total_trades)}\n"
        f"{MESSAGES['report_total_pnl'].format(total_pnl=total_pnl)}\n"
        f"{MESSAGES['report_win_rate'].format(win_rate=win_rate)}%\n"
    )
    
    # 콘솔에 리포트 내용 출력
    print("\n" + "="*30)
    print("📊 포트폴리오 리포트가 콘솔에 출력되었습니다.")
    print(report_message)
    print("="*30 + "\n")
    
    return report_message

# 이 함수는 외부에서 직접 호출되지 않으므로 __all__ 리스트에 포함하지 않습니다.
__all__ = ['record_trade_result', 'generate_report']