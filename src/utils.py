import json
import os
from dotenv import load_dotenv

load_dotenv()

# 환경 변수에서 언어 코드 가져오기
LANG_CODE = os.getenv('LANG_CODE')

def load_messages(lang_code):
    """
    지정된 언어 코드에 맞는 메시지 파일을 로드합니다.
    """
    try:
        file_path = os.path.join(os.path.dirname(__file__), '..', 'lang', f'messages_{lang_code}.json')
        with open(file_path, 'r', encoding='utf-8') as f:
            messages = json.load(f)
        return messages
    except FileNotFoundError:
        print(f"Error: Language file 'messages_{lang_code}.json' not found.")
        return {}
    except Exception as e:
        print(f"Error loading language file: {e}")
        return {}

# 메시지를 로드하고, 다른 모듈에서 사용하기 위해 변수를 노출시킵니다.
MESSAGES = load_messages(LANG_CODE)