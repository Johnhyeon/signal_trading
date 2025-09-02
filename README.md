### [README_KO](https://github.com/Johnhyeon/signal_trading/blob/master/README.md)
### [README_EN](https://github.com/Johnhyeon/signal_trading/blob/master/README_en.md)
---

# 📈 텔레그램 기반 자동 거래 봇
텔레그램 채널 신호를 자동으로 감지하여 Bybit 선물 거래를 실행하는 자동 매매 봇
이 봇은 지정된 텔레그램 메시지를 파싱하고, Bybit API를 통해 실시간으로 주문을 실행/관리하며, 모든 결과를 로그 채널로 전송합니다.
---
## ✨ 주요 기능

### 🔔 텔레그램 메시지 실시간 감지
지정된 채널의 거래 신호 메시지를 모니터링합니다.

### 🧩 유연한 메시지 파싱
정규표현식을 통해 다양한 신호 포맷에서 종목(Symbol), 진입가(Entry), 레버리지(Leverage), 손절가(Stop Loss), 익절가(Take Profit) 등을 추출합니다.

### ⚡ 자동 주문 실행
추출된 정보를 기반으로 시장가 / 지정가 주문을 자동 실행합니다.

### 📊 주문 수량 자동 계산
계좌 잔고와 신호에 포함된 투자 비중(Fund)에 따라 주문 수량을 자동 산출합니다.

### 🔄 주문 수정 & 취소
신호 메시지 수정 시 기존 주문 취소 → 신규 주문 실행
"Cancel" 명령어로 미체결 주문 즉시 취소 가능
"Move SL = entry" 명령어로 SL entry 이동 가능
"Move SL = TP1" 명령어로 SL TP1 이동 가능
"Move SL = TP2" 명령어로 SL TP2 이동 가능

### 📡 실시간 알림
체결/실패 결과를 텔레그램 로그 채널로 전송합니다.

### 🛑 중복 주문 방지
동일 심볼에 대한 중복 거래를 자동 필터링합니다.

### 💹 포트폴리오 관리 (신규 기능)
모든 거래 기록을 `log/trade_log.json` 파일에 저장하고, 이를 바탕으로 총 손익(P&L), 승률 등 통계 리포트를 생성합니다.

---
## 🛠️ 환경 설정
이 프로젝트 실행을 위해 .env 파일이 필요합니다.
프로젝트 루트에 .env 파일을 생성 후 아래 값을 입력하세요:

```
TELEGRAM_API_ID=
TELEGRAM_API_HASH=''
BYBIT_API_KEY=''
BYBIT_SECRET_KEY=''
TARGET_CHANNEL_ID=
TELE_BYBIT_BOT_TOKEN=
TELE_BYBIT_LOG_CHAT_ID=
TEST_CHANNEL_ID=
LANG_CODE='ko'  # 'ko' 또는 'en'으로 설정하여 언어 선택
```

### 🔑 .env 값 얻는 방법
1️⃣ 텔레그램 API ID & HASH
1. My Telegram API 접속 후 로그인 [https://my.telegram.org/]
2. API development tools → Create a new application
<img width="457" height="180" alt="image" src="https://github.com/user-attachments/assets/a9d2e683-d45c-4420-9875-9a82af8e62bb" />
3. 생성 완료 후 api_id와 api_hash 확인
<img width="852" height="1137" alt="image" src="https://github.com/user-attachments/assets/81ec453b-45e7-4252-bc15-2b7b6758d81b" />
4. 발급한 TELEGRAM_API_ID, TELEGRAM_API_HASH .env에 입력

### 2️⃣ Bybit API KEY & SECRET KEY
1. Bybit 계정 로그인
2. 계정 설정 → API 관리
<img width="372" height="665" alt="image" src="https://github.com/user-attachments/assets/6d55f5a1-32bc-4725-8579-d382f38e2cd3" />
<img width="1679" height="553" alt="image" src="https://github.com/user-attachments/assets/d7a9580f-1cdf-4f7d-b744-9098d9b1cf0c" />
3. 새 API 키 생성 → 거래/잔고 조회 권한 부여
<img width="1159" height="816" alt="image" src="https://github.com/user-attachments/assets/48f6b137-8734-404b-8ca5-1ec477811c70" />
4. 발급한 BYBIT_API_KEY, BYBIT_SECRET_KEY .env에 입력

### 3️⃣ 텔레그램 봇 토큰 (TELE_BYBIT_BOT_TOKEN)
[ko: https://blog.naver.com/lifelectronics/223198582215]
[en: https://youtu.be/aupKH_J1xc0]
1. 텔레그램에서 @BotFather 검색
2. /newbot 명령 입력 후 봇 생성
3. 발급된 HTTP API 토큰(TELE_BYBIT_BOT_TOKEN)을 .env에 입력

### 4️⃣ 텔레그램 채널 ID (TARGET_CHANNEL_ID, TEST_CHANNEL_ID, TELE_BYBIT_LOG_CHAT_ID)
1. 웹 텔레그램 접속 후 URL에서 확인 가능 [https://web.telegram.org/] 로그인 필요
2. 가져오고 싶은 채널의 ID 확인 (주소창에서 확인 가능) [ex) https://web.telegram.org/k/#-2340000000]
3. 확인한 채널 ID를 .env의 TARGET_CHANNEL_ID -100[채널ID] 입력 [ex) -1002340123456]
### 텔레그램 TEST 채널 생성
1. 텔레그램 앱에서 채널 생성 (채널명은 아무거나)
2. 해당 채널 역시 위처럼 채널 ID를 확인 후 .env의 TEST_CHANNEL_ID -100[채널ID] 입력 [ex) -1002340123456]

## 🚀 실행 방법

### venv 설치 (가상환경)

### 필요 패키지 설치
pip install -r requirements.txt

### 실행
python main.py

### or .bat 실행
파일 내 프로젝트/가상환경 경로 설정 후 실행
```
@echo off
rem D:\.. to your project root full path
cd "D:\..\signal_trading

rem 'trading' virtual env Activation (Python venv Scripts path)
call "D:\..\signal_trading\venv\Scripts\activate"

rem move src
cd src

rem run main.py
python main.py

rem venv deactivate
call deactivate

pause
```

# ⚠️ 주의사항
본 프로젝트는 교육 및 연구 목적으로 제작되었습니다.
실제 거래에 사용할 경우, 반드시 테스트넷 환경에서 충분히 검증 후 사용하세요.
암호화폐 거래는 높은 리스크가 있으므로, 모든 책임은 사용자 본인에게 있습니다.


