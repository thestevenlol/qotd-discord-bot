# question_bot/db_manager.py
import sqlite3
import os
from typing import List, Tuple, Optional, Dict

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'questions.db') # Correct path

def get_db_connection():
    # Ensure the 'data' directory exists
    os.makedirs(os.path.join(os.path.dirname(__file__), 'data'), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row # Access columns by name
    return conn

def initialize_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Guild configurations for sending messages
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guild_configs (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            send_time TEXT, -- HH:MM format (UTC)
            frequency TEXT, -- 'daily', 'weekly', 'disabled'
            ping_role_id INTEGER,
            current_pack_name TEXT
        )
    ''')

    # Question packs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS question_packs (
            pack_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL, -- Packs are guild-specific
            pack_name TEXT NOT NULL,
            UNIQUE(guild_id, pack_name)
        )
    ''')

    # Questions within packs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            question_id INTEGER PRIMARY KEY AUTOINCREMENT,
            pack_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            FOREIGN KEY (pack_id) REFERENCES question_packs (pack_id) ON DELETE CASCADE
        )
    ''')

    # Track sent questions for each guild and pack to avoid repeats
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sent_questions (
            guild_id INTEGER NOT NULL,
            pack_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (guild_id, pack_id, question_id),
            FOREIGN KEY (pack_id) REFERENCES question_packs (pack_id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions (question_id) ON DELETE CASCADE
        )
    ''')
    
    # Suggested questions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suggested_questions (
            suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            status TEXT DEFAULT 'pending' -- 'pending', 'approved', 'denied'
        )
    ''')

    conn.commit()
    conn.close()

# --- Guild Config Functions ---
def update_guild_config(guild_id: int, channel_id: Optional[int] = None, send_time: Optional[str] = None,
                        frequency: Optional[str] = None, ping_role_id: Optional[int] = None,
                        current_pack_name: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO guild_configs (guild_id) VALUES (?)", (guild_id,))
    
    updates = []
    params = []
    if channel_id is not None:
        updates.append("channel_id = ?")
        params.append(channel_id)
    if send_time is not None:
        updates.append("send_time = ?")
        params.append(send_time)
    if frequency is not None:
        updates.append("frequency = ?")
        params.append(frequency)
    if ping_role_id is not None:
        updates.append("ping_role_id = ?")
        params.append(ping_role_id)
    if current_pack_name is not None: # Can be set to NULL
        updates.append("current_pack_name = ?")
        params.append(current_pack_name)
    
    if updates:
        params.append(guild_id)
        cursor.execute(f"UPDATE guild_configs SET {', '.join(updates)} WHERE guild_id = ?", tuple(params))
    conn.commit()
    conn.close()

def get_guild_config(guild_id: int) -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM guild_configs WHERE guild_id = ?", (guild_id,))
    config = cursor.fetchone()
    conn.close()
    return config

def get_all_guild_configs() -> List[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM guild_configs WHERE channel_id IS NOT NULL AND send_time IS NOT NULL AND frequency != 'disabled'")
    configs = cursor.fetchall()
    conn.close()
    return configs

# --- Question Pack Functions ---
def create_pack(guild_id: int, pack_name: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO question_packs (guild_id, pack_name) VALUES (?, ?)", (guild_id, pack_name))
        conn.commit()
        return True
    except sqlite3.IntegrityError: # Pack name already exists for this guild
        return False
    finally:
        conn.close()

def get_pack(guild_id: int, pack_name: str) -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM question_packs WHERE guild_id = ? AND pack_name = ?", (guild_id, pack_name))
    pack = cursor.fetchone()
    conn.close()
    return pack
    
def get_pack_by_id(pack_id: int) -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM question_packs WHERE pack_id = ?", (pack_id,))
    pack = cursor.fetchone()
    conn.close()
    return pack

def delete_pack(guild_id: int, pack_name: str) -> bool:
    pack = get_pack(guild_id, pack_name)
    if not pack:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    # Cascading delete should handle questions and sent_questions related to this pack
    cursor.execute("DELETE FROM question_packs WHERE pack_id = ?", (pack['pack_id'],))
    conn.commit()
    deleted_rows = cursor.rowcount > 0
    conn.close()
    return deleted_rows

def get_guild_packs(guild_id: int) -> List[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM question_packs WHERE guild_id = ? ORDER BY pack_name", (guild_id,))
    packs = cursor.fetchall()
    conn.close()
    return packs

# --- Question Functions ---
def add_question_to_pack(pack_id: int, question_text: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO questions (pack_id, question_text) VALUES (?, ?)", (pack_id, question_text))
    conn.commit()
    question_id = cursor.lastrowid
    conn.close()
    return question_id

def get_questions_for_pack(pack_id: int) -> List[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM questions WHERE pack_id = ? ORDER BY question_id", (pack_id,))
    questions = cursor.fetchall()
    conn.close()
    return questions

def get_sent_question_ids(guild_id: int, pack_id: int) -> List[int]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT question_id FROM sent_questions WHERE guild_id = ? AND pack_id = ?", (guild_id, pack_id))
    sent_ids = [row['question_id'] for row in cursor.fetchall()]
    conn.close()
    return sent_ids

def mark_question_as_sent(guild_id: int, pack_id: int, question_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sent_questions (guild_id, pack_id, question_id) VALUES (?, ?, ?)",
                   (guild_id, pack_id, question_id))
    conn.commit()
    conn.close()

def reset_sent_questions_for_pack(guild_id: int, pack_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sent_questions WHERE guild_id = ? AND pack_id = ?", (guild_id, pack_id))
    conn.commit()
    conn.close()
    
def get_unsent_question(guild_id: int, pack_id: int) -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    # Get one random unsent question
    cursor.execute("""
        SELECT q.*
        FROM questions q
        LEFT JOIN sent_questions sq ON q.question_id = sq.question_id AND sq.guild_id = ? AND sq.pack_id = ?
        WHERE q.pack_id = ? AND sq.question_id IS NULL
        ORDER BY RANDOM()
        LIMIT 1
    """, (guild_id, pack_id, pack_id))
    question = cursor.fetchone()
    conn.close()
    return question

# --- Suggestion Functions ---
def add_suggestion(guild_id: int, user_id: int, question_text: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO suggested_questions (guild_id, user_id, question_text) VALUES (?, ?, ?)",
                   (guild_id, user_id, question_text))
    conn.commit()
    suggestion_id = cursor.lastrowid
    conn.close()
    return suggestion_id

def get_pending_suggestions(guild_id: int) -> List[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suggested_questions WHERE guild_id = ? AND status = 'pending' ORDER BY suggestion_id", (guild_id,))
    suggestions = cursor.fetchall()
    conn.close()
    return suggestions

def get_suggestion(suggestion_id: int) -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suggested_questions WHERE suggestion_id = ?", (suggestion_id,))
    suggestion = cursor.fetchone()
    conn.close()
    return suggestion

def update_suggestion_status(suggestion_id: int, status: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE suggested_questions SET status = ? WHERE suggestion_id = ?", (status, suggestion_id))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    # This part is just for testing the DB setup directly
    # Run this file once (`python db_manager.py`) to create the initial DB structure.
    print("Initializing database...")
    initialize_db()
    print("Database initialized at:", DATABASE_PATH)
    # Example usage (optional test)
    # create_pack(123, "Test Pack")
    # pack = get_pack(123, "Test Pack")
    # if pack:
    #     add_question_to_pack(pack['pack_id'], "What is your favorite color?")
    #     questions = get_questions_for_pack(pack['pack_id'])
    #     print(f"Questions in 'Test Pack': {questions}")