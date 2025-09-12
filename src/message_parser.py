import re
import random
import decimal
from utils import MESSAGES # 추가

def parse_telegram_message(message_text):
    """
    텔레그램 메시지 텍스트를 파싱하여 주문 정보를 추출합니다.
    """
    try:
        # 1. TP와 SL을 먼저 파싱하여 포지션 방향을 결정
        all_tp_matches = re.findall(r'TP(?:\d+)?:\s*([\d\.-]+)', message_text, re.IGNORECASE)
        sl_match_final = re.search(r'Stop\s*Loss?:\s*([\d\.]+)', message_text, re.IGNORECASE)

        if not sl_match_final or not all_tp_matches:
            print(MESSAGES['parsing_failed_tp_sl'])
            return None
        
        # 하이픈으로 연결된 TP 값 분리
        targets = []
        for tp_string in all_tp_matches:
            # 하이픈으로 연결된 문자열을 분리하여 리스트에 추가
            parts = tp_string.split('-')
            for part in parts:
                targets.append(float(part))
                
        stop_loss = float(sl_match_final.group(1))
        
        # 첫 번째 TP와 SL을 비교하여 포지션 방향 결정
        first_tp = targets[0]
        side = "Buy" if first_tp > stop_loss else "Sell"

        # 2. 'Long'/'Short' 구문이 없는 메시지 형식을 처리 (이모티콘 스티커 케이스)
        symbol_match_emoji = re.search(r'([A-Z0-9]+)/([A-Z]+)', message_text)
        entry_now_match = re.search(r'Entry NOW', message_text)

        if symbol_match_emoji and entry_now_match:
            symbol = symbol_match_emoji.group(1) + symbol_match_emoji.group(2)
            entry_price = "NOW"
            leverage = None  # trade_executor.py에서 결정하도록 None으로 설정
            fund_percentage = 0.05
            
            return {
                'symbol': symbol,
                'side': side,
                'leverage': leverage,
                'fund_percentage': fund_percentage,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'targets': targets,
                'original_message': message_text # 원본 메시지 텍스트 추가
            }
            
        # 3. 기존 메시지 형식 처리 (기존 로직 유지)
        symbol_match = re.search(r'\$([A-Z0-9]+)', message_text, re.IGNORECASE)
        leverage_match = re.search(r'Leverage:\s*x(\d+)', message_text, re.IGNORECASE)
        fund_match = re.search(r'Fund:\s*(\d+)%', message_text)
        entry_match = re.search(r'Entry:\s*(NOW|(\d+(?:\.\d{1,3})?)(?:[xX]{1,2}|\.[xX]{1,2})?)', message_text)
        tp_matches = re.findall(r'TP\d+:\s*([\d\.]+)', message_text)
        
        if not all([symbol_match, leverage_match, fund_match, entry_match, sl_match_final, tp_matches]):
            print(MESSAGES['parsing_failed_old_format'])
            return None

        symbol = symbol_match.group(1).upper() + "USDT"
        leverage = int(leverage_match.group(1))
        fund_percentage = float(fund_match.group(1)) / 100
        
        entry_price_str = entry_match.group(1)
        
        if 'xx' in entry_price_str:
            base_price_str = entry_price_str.replace('xx', '')
            base_price = int(base_price_str)
            random_digits = random.randint(0, 99)
            entry_price = float(base_price * 100 + random_digits)
        elif entry_price_str.endswith('x'):
            if '.' in entry_price_str:
                base_price_str = entry_price_str.replace('x', '')
                base_price = float(base_price_str)
                random_digit = random.randint(0, 9)
                decimal_places = len(base_price_str.split('.')[1])
                entry_price = round(base_price + random_digit * (10 ** -(decimal_places + 1)), decimal_places + 1)
            else:
                base_price_str = entry_price_str.replace('x', '')
                base_price = int(base_price_str)
                random_digit = random.randint(0, 9)
                entry_price = float(str(base_price) + str(random_digit))
        elif entry_price_str == "NOW":
            entry_price = "NOW"
        else:
            entry_price = float(entry_price_str)
            
        return {
            'symbol': symbol,
            'side': side,
            'leverage': leverage,
            'fund_percentage': fund_percentage,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'targets': targets,
            'original_message': message_text # 원본 메시지 텍스트 추가
        }
        
    except Exception as e:
        print(MESSAGES['parsing_error'], e)
        return None
    
def parse_cancel_message(message_text):
    """
    'Cancel' 메시지를 파싱하여 종목명을 추출합니다.
    예: "Cancel APT" -> "APT"
    """
    # 'Cancel' 뒤에 오는 종목명을 찾습니다. 대소문자 무시
    cancel_match = re.search(r'Cancel\s+\$?([A-Z0-9]+)', message_text, re.IGNORECASE)
    
    if cancel_match:
        return cancel_match.group(1).upper() + "USDT"
    
    return None

def parse_dca_message(message_text):
    """
    DCA 메시지 텍스트를 파싱하여 DCA 지정가와 새로운 SL 값을 추출합니다.
    예: "DCA Limit 213, Move SL = 216"
    """
    try:
        # 'DCA Limit'과 'Move SL'에 대한 값들을 정규표현식으로 찾습니다.
        dca_match = re.search(r'DCA\s+Limit\s*[:=]?\s*([\d\.]+)', message_text, re.IGNORECASE)
        sl_match = re.search(r'Move\s*SL\s*[:=]?\s*([\d\.]+)', message_text, re.IGNORECASE)

        if not dca_match or not sl_match:
            print(MESSAGES['dca_parsing_failed'])
            return None, None
        
        dca_price = float(dca_match.group(1))
        new_sl = float(sl_match.group(1))

        return dca_price, new_sl

    except Exception as e:
        print(MESSAGES['parsing_error'], e)
        return None, None