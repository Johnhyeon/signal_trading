import json
import os
from datetime import datetime, timedelta
from utils import MESSAGES

# 거래 기록을 저장할 파일 경로
LOG_DIR = os.path.join("..", "log")
TRADE_LOG_FILE = os.path.join(LOG_DIR, "trade_log.json")

def record_trade_result(trade_data):
    """
    거래 결과를 JSON 파일에 기록합니다.
    """
    # 로그 디렉터리가 없으면 생성
    os.makedirs(LOG_DIR, exist_ok=True)
    
    try:
        # 기존 로그 파일 읽기
        with open(TRADE_LOG_FILE, 'r', encoding='utf-8') as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # 파일이 없거나 형식이 잘못된 경우 빈 리스트로 시작
        logs = []

    # 새로운 거래 기록 추가
    logs.append(trade_data)

    # ✅ 추가: 콘솔에 이번 거래 로그 출력
    print("\n" + "="*30)
    print("✅ 이번 거래 로그가 콘솔에 저장되었습니다.")
    print(f"▪️ Symbol: {trade_data['symbol']}")
    print(f"▪️ P&L: {trade_data['pnl']:.2f}")
    print(f"▪️ Exit Price: {trade_data['exit_price']}")
    print("="*30 + "\n")
    
    # 업데이트된 로그 파일 저장
    with open(TRADE_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)
    
    print(MESSAGES['record_trade_success'].format(TRADE_LOG_FILE=TRADE_LOG_FILE))

def generate_report(period='all'):
    """
    거래 기록을 기반으로 통계 리포트를 생성합니다.
    period: 'all' (전체), 'daily', 'weekly' 등
    """
    # ✅ 수정: 로그 파일이 없으면 빈 파일로 초기화하는 로직 추가
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, 'w', encoding='utf-8') as f:
            f.write('[]')

    try:
        with open(TRADE_LOG_FILE, 'r', encoding='utf-8') as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return MESSAGES['no_trade_log']

    # 기간 필터링 로직
    if period == 'all':
        filtered_logs = logs
    else:
        now = datetime.now()
        filtered_logs = []
        for log in logs:
            # ✅ 수정: created_at 키가 없거나 형식이 잘못된 경우 건너뛰는 예외 처리 추가
            created_at = log.get('created_at')
            if not created_at:
                continue

            try:
                trade_date = datetime.fromisoformat(created_at)
                if period == 'day' and (now - trade_date) < timedelta(days=1):
                    filtered_logs.append(log)
                elif period == 'week' and (now - trade_date) < timedelta(weeks=1):
                    filtered_logs.append(log)
            except ValueError:
                # fromisoformat 변환 오류가 발생하면 로그 건너뛰기
                continue

    if not filtered_logs:
        return MESSAGES['no_trades_in_period']

    total_pnl = sum(log.get('pnl', 0) for log in filtered_logs)
    win_trades = sum(1 for log in filtered_logs if log.get('pnl', 0) > 0)
    total_trades = len(filtered_logs)
    win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
    
    report_message = (
        MESSAGES['report_title'].format(period=period.capitalize()) + "\n\n"
        f"{MESSAGES['report_total_trades'].format(total_trades=total_trades)}\n"
        f"{MESSAGES['report_total_pnl'].format(total_pnl=total_pnl)}\n"
        f"{MESSAGES['report_win_rate'].format(win_rate=win_rate)}\n"
    )

    # ✅ 추가: 콘솔에 리포트 내용 출력
    print("\n" + "="*30)
    print("📊 포트폴리오 리포트가 콘솔에 출력되었습니다.")
    print(report_message)
    print("="*30 + "\n")
    
    return report_message

# 이 함수는 외부에서 직접 호출되지 않으므로 __all__ 리스트에 포함하지 않습니다.
__all__ = ['record_trade_result', 'generate_report']