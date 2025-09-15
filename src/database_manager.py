import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

GDRIVE_PATH = os.getenv('GDRIVE_PATH')
DB_PATH = os.path.join(GDRIVE_PATH, 'trading_bot.db')

def get_db_connection():
    """SQLite 데이터베이스 연결을 반환합니다."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def setup_database():
    """데이터베이스 테이블을 생성합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # trade_log 테이블: 거래 기록
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL,
            exit_price REAL,
            qty REAL,
            pnl REAL,
            created_at TEXT NOT NULL
        )
    ''')
    
    # active_orders 테이블: 활성 주문 정보
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_orders (
            message_id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL,
            targets TEXT,
            positionIdx TEXT,
            orderId TEXT,
            fund_percentage REAL,
            leverage REAL,
            original_message TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def save_active_order(order_info):
    """활성 주문 정보를 데이터베이스에 저장합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO active_orders (
            message_id, symbol, side, entry_price, targets,
            positionIdx, orderId, fund_percentage, leverage, original_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        order_info['message_id'], order_info['symbol'], order_info['side'],
        order_info['entry_price'], str(order_info['targets']),
        order_info['positionIdx'], order_info['orderId'],
        order_info['fund_percentage'], order_info['leverage'], order_info['original_message']
    ))
    conn.commit()
    conn.close()

def delete_active_order(message_id):
    """활성 주문 정보를 데이터베이스에서 삭제합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM active_orders WHERE message_id = ?', (message_id,))
    conn.commit()
    conn.close()

def get_active_orders():
    """데이터베이스에서 모든 활성 주문 정보를 불러옵니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM active_orders')
    rows = cursor.fetchall()
    conn.close()
    
    # Dict 형태로 변환하여 반환
    orders = {}
    for row in rows:
        order_info = dict(row)
        order_info['targets'] = eval(order_info['targets']) # targets는 리스트로 변환
        orders[order_info['message_id']] = order_info
    return orders

def record_trade_result_db(trade_data):
    """거래 결과를 데이터베이스에 기록합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trade_log (symbol, side, entry_price, exit_price, qty, pnl, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        trade_data['symbol'], trade_data['side'], trade_data['entry_price'],
        trade_data['exit_price'], trade_data['qty'], trade_data['pnl'],
        trade_data['created_at']
    ))
    conn.commit()
    conn.close()