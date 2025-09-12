import json
import os
from dotenv import load_dotenv
import asyncio
from api_clients import bybit_bot, TELE_BYBIT_LOG_CHAT_ID

load_dotenv()

# 환경 변수에서 언어 코드 가져오기 (기본값: 'ko')
LANG_CODE = os.getenv('LANG_CODE')

def load_messages(lang_code: str = LANG_CODE) -> dict:
    """
    지정된 언어 코드에 맞는 메시지 파일을 로드합니다.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, '..', 'lang', f'messages_{lang_code}.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError(f"Language file 'messages_{lang_code}.json' not found in {base_dir}/../lang/")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in 'messages_{lang_code}.json'")
    except Exception as e:
        raise RuntimeError(f"Error loading language file: {e}")

# 메시지를 로드 (다른 모듈에서 import 가능)
MESSAGES = load_messages()

# ✅ 추가: 활성 주문 정보를 파일로 저장하는 함수
def save_active_orders(orders, file_path='log/active_orders.json'):
    """활성 주문 정보를 JSON 파일에 저장합니다."""
    # 추가: 디렉토리가 없으면 생성
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(orders, f, indent=4)

# ✅ 추가: 활성 주문 정보를 파일에서 불러오는 함수
def load_active_orders(file_path='log/active_orders.json'):
    """JSON 파일에서 활성 주문 정보를 불러옵니다."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # 파일이 없거나 내용이 비어있으면 빈 딕셔너리 반환
        return {}

def log_error_and_send_message(msg: str, exc: Exception = None, chat_id: int = TELE_BYBIT_LOG_CHAT_ID) -> None:
    """
    에러 메시지를 콘솔에 출력하고, 텔레그램 봇으로 메시지를 전송합니다.
    """
    error_msg = f"ERROR: {msg}"
    if exc:
        error_msg += f"\nDetails: {exc}"
    
    print(error_msg)
    
    # 텔레그램 메시지 전송 (비동기 처리)
    async def send_tele_msg():
        try:
            await bybit_bot.send_message(
                chat_id=chat_id,
                text=error_msg,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"⚠️ 텔레그램 메시지 전송 실패: {e}")

    # 이벤트 루프가 이미 실행 중인 경우
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(send_tele_msg(), loop)
    else:
        # 이벤트 루프가 없는 경우 (동기 컨텍스트)
        asyncio.run(send_tele_msg())

__all__ = ['load_messages', 'save_active_orders', 'load_active_orders', 'MESSAGES', 'log_error_and_send_message']