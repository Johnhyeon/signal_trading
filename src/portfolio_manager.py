import json
import os
from datetime import datetime

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
    
    # 업데이트된 로그 파일 저장
    with open(TRADE_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)
    
    print(f"✅ 거래 기록이 {TRADE_LOG_FILE}에 추가되었습니다.")

def generate_report(period='all'):
    """
    거래 기록을 기반으로 통계 리포트를 생성합니다.
    period: 'all' (전체), 'daily', 'weekly' 등
    """
    try:
        with open(TRADE_LOG_FILE, 'r', encoding='utf-8') as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return "⚠️ 아직 거래 기록이 없습니다."

    # 기간 필터링 (현재는 전체 기간만 지원)
    if period == 'all':
        filtered_logs = logs
    else:
        # 향후 기능 확장을 위한 로직
        filtered_logs = logs

    if not filtered_logs:
        return "⚠️ 해당 기간 동안의 거래 기록이 없습니다."

    total_pnl = sum(log.get('pnl', 0) for log in filtered_logs)
    win_trades = sum(1 for log in filtered_logs if log.get('pnl', 0) > 0)
    total_trades = len(filtered_logs)
    win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
    
    report_message = (
        f"📊 **포트폴리오 통계 리포트** ({period.capitalize()})\n\n"
        f"🔄 **총 거래 횟수**: {total_trades}\n"
        f"💰 **총 손익 (P&L)**: {total_pnl:.2f} USDT\n"
        f"🎯 **승률**: {win_rate:.2f}%\n"
    )
    
    return report_message

# 이 함수는 외부에서 직접 호출되지 않으므로 __all__ 리스트에 포함하지 않습니다.
__all__ = ['record_trade_result', 'generate_report']