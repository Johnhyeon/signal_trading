📈 텔레그램 기반 자동 거래 봇
이 프로젝트는 텔레그램(Telegram)에서 특정 메시지 포맷을 자동으로 감지하고, 해당 정보를 기반으로 바이비트(Bybit) 거래소에서 암호화폐 선물 거래를 실행하는 자동화 봇입니다. 봇은 사용자 계정과 텔레그램 봇 API를 모두 활용하여 메시지를 수신하고, 거래 결과를 로그 채널에 전송하는 기능을 수행합니다.

✨ 주요 기능
텔레그램 메시지 실시간 감지: 지정된 텔레그램 채널의 메시지를 실시간으로 모니터링합니다.

유연한 메시지 파싱: 정규표현식을 통해 다양한 메시지 형식을 분석하여, 종목(Symbol), 진입가(Entry), 레버리지(Leverage), 손절가(Stop Loss), 익절가(Take Profit) 등의 핵심 거래 정보를 추출합니다.

자동 주문 실행: 파싱된 정보를 바탕으로 바이비트 API를 통해 시장가 또는 지정가 주문을 자동으로 실행합니다.

주문 수량 자동 계산: 계좌 잔고와 메시지에 명시된 투자 비중(Fund)에 따라 자동으로 주문 수량을 계산합니다.

주문 수정/취소: 기존 주문과 관련된 메시지가 수정되면 이전 주문을 취소하고 새로운 주문을 실행합니다. 또한, 'Cancel' 명령을 통해 미체결 주문을 즉시 취소할 수 있습니다.

실시간 알림: 주문 체결 및 실패 결과를 텔레그램 로그 채널로 전송하여 사용자에게 알립니다.

중복 주문 방지: 동일한 종목에 대한 중복 주문을 자동으로 필터링하여 불필요한 거래를 방지합니다.

🛠️ 기술 스택
언어: Python

텔레그램 API: telethon (메시지 수신), python-telegram-bot (봇 알림)

거래소 API: pybit (Bybit Unified Trading API)

환경 변수 관리: python-dotenv

📂 파일 설명
main.py: 텔레그램 메시지 이벤트를 처리하고, 파싱 및 거래 실행 함수들을 호출하는 메인 스크립트입니다.

message_parser.py: 텔레그램 메시지 텍스트를 파싱하여 거래 정보를 딕셔너리 형태로 추출하는 로직을 담고 있습니다.

trade_executor.py: Bybit API를 사용하여 실제 주문을 실행하고, 주문 수량을 계산하며, 결과를 텔레그램으로 전송하는 핵심 로직을 포함합니다.

api_clients.py: 환경 변수를 로드하고, Bybit 및 텔레그램 클라이언트 객체들을 초기화합니다.

.env: API 키와 같은 민감한 정보를 저장하는 파일입니다. (버전 관리 시 .gitignore에 반드시 포함시켜야 합니다.)

🛠️ 필수 환경 설정 (.env)
이 프로젝트를 실행하려면 API 키 및 기타 설정을 담은 .env 파일이 필요합니다. 프로젝트 루트 디렉터리에 .env 파일을 생성하고 아래 형식을 채워주세요.

Ini, TOML

'''
TELEGRAM_API_ID = 
TELEGRAM_API_HASH = ''
BYBIT_API_KEY = ''
BYBIT_SECRET_KEY = ''
TARGET_CHANNEL_ID = 
TELE_BYBIT_BOT_TOKEN = 
TELE_BYBIT_LOG_CHAT_ID = 
TEST_CHANNEL_ID = 
'''

.env 값 얻는 방법
텔레그램 API ID & HASH

My Telegram API 사이트에 접속하여 로그인합니다.

'API development tools' 메뉴에서 'Create a new application'을 클릭합니다.

양식을 작성하고 생성하면 App api_id와 App api_hash를 확인할 수 있습니다.

바이비트 API KEY & SECRET KEY

바이비트 계정에 로그인합니다.

계정 설정에서 API 관리 메뉴로 이동합니다.

새 API 키를 생성하고, '통합 거래' 권한을 부여합니다. 주문 및 잔고 조회에 필요한 권한을 체크해야 합니다. 생성 시 발급되는 API Key와 API Secret 값을 .env 파일에 입력합니다.

텔레그램 봇 토큰 (TELE_BYBIT_BOT_TOKEN)

텔레그램에서 @BotFather를 검색합니다.

start 명령을 입력하고, /newbot 명령으로 새로운 봇을 생성합니다.

봇 이름과 사용자 이름을 지정하면 HTTP API 토큰을 발급해 줍니다. 이 토큰을 .env 파일에 입력합니다.

텔레그램 채널 ID (TARGET_CHANNEL_ID, TEST_CHANNEL_ID, TELE_BYBIT_LOG_CHAT_ID)

텔레그램 웹 버전(web.telegram.org)에 접속합니다.

원하는 채널에 들어가 URL을 확인합니다. URL이 https://web.telegram.org/#/im?p=s12345678_1234567890 형식이라면, s를 제외한 숫자 12345678이 채널의 ID입니다.

공개 채널의 경우, 채널 ID는 보통 -100으로 시작하는 숫자로, 텔레그램 봇 @get_id_bot을 통해 쉽게 얻을 수 있습니다. 원하는 채널에 봇을 추가하고 /get_id 명령을 입력하면 채널 ID를 알려줍니다.