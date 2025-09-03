import json
import os
from dotenv import load_dotenv

load_dotenv()

# 환경 변수에서 언어 코드 가져오기 (기본값: 'ko')
LANG_CODE = os.getenv('LANG_CODE')

def load_messages(lang_code: str = LANG_CODE) -> dict:
    """
    지정된 언어 코드에 맞는 메시지 파일을 로드합니다.
    """
    # 파일 경로 생성 (상대 경로 사용)
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

def log_error(msg: str, exc: Exception = None) -> None:
    """
    에러 메시지를 출력합니다. 나중에 logging 모듈로 확장 가능.
    """
    print(f"ERROR: {msg}")
    if exc:
        print(f"Details: {exc}")