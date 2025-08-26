@echo off
rem C:\Users\DRIMAES\Desktop\myproject\signal_trading 경로로 이동
cd "C:\Users\DRIMAES\Desktop\myproject\signal_trading"

rem 'trading' 가상환경 활성화 (Python 가상환경의 Scripts 폴더 경로)
call "C:\Users\DRIMAES\Desktop\myproject\signal_trading\trading\Scripts\activate"

rem src 디렉토리로 이동
cd src

rem main.py 실행
python main.py

rem 가상환경 비활성화 (스크립트 종료 후에도 가상환경이 유지되지 않도록)
call deactivate

rem 스크립트 실행 후 창이 닫히지 않도록 잠시 대기
pause