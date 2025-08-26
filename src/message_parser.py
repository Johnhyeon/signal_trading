import re
import random
import decimal

def parse_telegram_message(message_text):
    """
    텔레그램 메시지 텍스트를 파싱하여 주문 정보를 추출합니다.
    """
    try:
        symbol_match = re.search(r'\$([A-Z0-9]+)', message_text)
        leverage_match = re.search(r'Leverage:\s*x(\d+)', message_text)
        fund_match = re.search(r'Fund:\s*(\d+)%', message_text)
        entry_match = re.search(r'Entry:\s*(NOW|[\d]+xx|[\d]+x|\d+(?:\.\d+)?x|\d+(?:\.\d+)?)', message_text)
        sl_match = re.search(r'Stop\s*Loss?:\s*([\d\.]+)', message_text)
        tp_matches = re.findall(r'TP\d+:\s*([\d\.]+)', message_text)
       # 'Long' 또는 'Short' 문구가 있는지 먼저 확인
        position_type = "Buy" if "Long" in message_text else "Sell" if "Short" in message_text else None
        
        if not all([symbol_match, leverage_match, fund_match, entry_match, sl_match, tp_matches, position_type]):
            print("메시지 형식이 올바르지 않아 파싱에 실패했습니다.")
            return None

        symbol = symbol_match.group(1) + "USDT"
        leverage = int(leverage_match.group(1))
        fund_percentage = 0.05
        stop_loss = float(sl_match.group(1))
        targets = [float(tp) for tp in tp_matches]

        entry_price_str = entry_match.group(1)
        entry_price = None
        print("Entry price str:", entry_price_str)
        # entry_price = float(entry_price_str.replace('x', ''))
        # print("Initial entry price:", entry_price)

        if 'xx' in entry_price_str:
            base_price_str = entry_price_str.replace('xx', '')
            base_price = int(base_price_str)
            random_digits = random.randint(0, 99)
            
            # 정수형 가격에 100을 곱한 뒤 난수 추가
            entry_price = float(base_price * 100 + random_digits)
        elif entry_price_str.endswith('x'):
            if '.' in entry_price_str:
                # 소수점 케이스: 0.84x -> 0.84 + 난수(0~9)
                base_price_str = entry_price_str.replace('x', '')
                base_price = float(base_price_str)
                random_digit = random.randint(0, 9)
                
                # 소수점 아래 자릿수를 계산하여 정확한 위치에 난수 추가
                decimal_places = len(base_price_str.split('.')[1])
                entry_price = round(base_price + random_digit * (10 ** -(decimal_places + 1)), decimal_places + 1)
            else:
                # 정수 케이스: 451x -> 451 + 난수(0~9)
                base_price_str = entry_price_str.replace('x', '')
                base_price = int(base_price_str)
                random_digit = random.randint(0, 9)
                entry_price = float(str(base_price) + str(random_digit))
        else:
            entry_price = float(entry_price_str)

        print("Final entry price:", entry_price)
        return {
            'symbol': symbol,
            'side': position_type,
            'leverage': leverage,
            'fund_percentage': fund_percentage,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'targets': targets
        }
    except Exception as e:
        print(f"메시지 파싱 중 오류 발생: {e}")
        return None