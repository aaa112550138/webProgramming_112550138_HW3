# Db.py

import sqlite3
import hashlib
import os
import datetime

# 設定資料庫路徑
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db.sqlite3')

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        
        # 1. Users
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                UNIQUE(username, role)
            )
        ''')
        
        # 2. Games
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                developer_id INTEGER,
                description TEXT,
                file_path TEXT,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY(developer_id) REFERENCES users(id)
            )
        ''')

        # 3. Play History (遊玩紀錄 - 用於驗證資格)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS play_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                game_id INTEGER,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(player_id) REFERENCES users(id),
                FOREIGN KEY(game_id) REFERENCES games(id)
            )
        ''')

        # 4. Reviews (評論與評分)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER,
                player_id INTEGER,
                rating INTEGER CHECK(rating >= 1 AND rating <= 5),
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(game_id) REFERENCES games(id),
                FOREIGN KEY(player_id) REFERENCES users(id)
            )
        ''')
        
        self.conn.commit()

    # ================= Auth =================
    def register_user(self, username, password, role):
        try:
            pwd_hash = hashlib.sha256(password.encode()).hexdigest()
            self.conn.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)', 
                              (username, pwd_hash, role))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def verify_user(self, username, password, role):
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor = self.conn.execute('SELECT id FROM users WHERE username=? AND password_hash=? AND role=?', 
                                   (username, pwd_hash, role))
        row = cursor.fetchone()
        return row[0] if row else None

    # ================= Game Management =================
    def add_game(self, name, version, dev_id, description, file_path):
        try:
            self.conn.execute('''
                INSERT INTO games (name, version, developer_id, description, file_path, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (name, version, dev_id, description, file_path))
            self.conn.commit()
            return True
        except: return False

    def update_game_version(self, game_id, new_version, new_desc, new_file_path):
        try:
            self.conn.execute('UPDATE games SET version=?, description=?, file_path=? WHERE id=?', 
                              (new_version, new_desc, new_file_path, game_id))
            self.conn.commit()
            return True
        except: return False

    def get_all_games(self):
        cursor = self.conn.execute('''
            SELECT g.id, g.name, g.version, g.description, u.username 
            FROM games g JOIN users u ON g.developer_id = u.id
            WHERE g.is_active = 1
        ''')
        return [{"id": r[0], "name": r[1], "version": r[2], "description": r[3], "author": r[4]} for r in cursor.fetchall()]

    def get_game_file_info(self, game_id):
        cursor = self.conn.execute("SELECT file_path, name FROM games WHERE id=?", (game_id,))
        return cursor.fetchone()

    def get_game_info_by_name(self, name, dev_id):
        cursor = self.conn.execute("SELECT id, version FROM games WHERE name=? AND developer_id=?", (name, dev_id))
        return cursor.fetchone()

    def get_game_owner_by_name(self, name):
        cursor = self.conn.execute("SELECT developer_id FROM games WHERE name=?", (name,))
        row = cursor.fetchone()
        return row[0] if row else None
    
    def get_game_details_by_name(self, name):
        cursor = self.conn.execute("SELECT id, developer_id, is_active FROM games WHERE name=?", (name,))
        row = cursor.fetchone()
        return (row[0], row[1], bool(row[2])) if row else None

    # ================= Developer =================
    def get_games_by_dev(self, dev_id):
        cursor = self.conn.execute('SELECT id, name, version, description, is_active FROM games WHERE developer_id = ?', (dev_id,))
        return [{"id": r[0], "name": r[1], "version": r[2], "description": r[3], "is_active": bool(r[4])} for r in cursor.fetchall()]

    def set_game_active(self, game_id, is_active):
        try:
            self.conn.execute("UPDATE games SET is_active=? WHERE id=?", (1 if is_active else 0, game_id))
            self.conn.commit()
            return True
        except: return False

    def is_game_owner(self, game_id, dev_id):
        cursor = self.conn.execute("SELECT id FROM games WHERE id=? AND developer_id=?", (game_id, dev_id))
        return cursor.fetchone() is not None
    
    def get_game_status(self, game_id):
        cursor = self.conn.execute("SELECT is_active FROM games WHERE id=?", (game_id,))
        row = cursor.fetchone()
        return bool(row[0]) if row else False

    # ================= Social / Reviews (New) =================
    
    def add_play_history(self, player_id, game_id):
        """記錄玩家玩過某款遊戲"""
        try:
            # 避免短時間重複插入過多紀錄 (可選)
            self.conn.execute('INSERT INTO play_history (player_id, game_id) VALUES (?, ?)', (player_id, game_id))
            self.conn.commit()
        except Exception as e:
            print(f"History Error: {e}")

    def has_played(self, player_id, game_id):
        """檢查玩家是否玩過該遊戲"""
        cursor = self.conn.execute('SELECT id FROM play_history WHERE player_id=? AND game_id=? LIMIT 1', (player_id, game_id))
        return cursor.fetchone() is not None

    def add_review(self, player_id, game_id, rating, comment):
        """新增評論"""
        try:
            self.conn.execute('INSERT INTO reviews (player_id, game_id, rating, comment) VALUES (?, ?, ?, ?)', 
                              (player_id, game_id, rating, comment))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Review Error: {e}")
            return False

    def get_game_reviews(self, game_id):
        """取得某款遊戲的所有評論"""
        cursor = self.conn.execute('''
            SELECT r.rating, r.comment, u.username, r.created_at 
            FROM reviews r
            JOIN users u ON r.player_id = u.id
            WHERE r.game_id = ?
            ORDER BY r.created_at DESC
        ''', (game_id,))
        
        reviews = []
        for r in cursor.fetchall():
            reviews.append({
                "rating": r[0],
                "comment": r[1],
                "player": r[2],
                "date": r[3]
            })
        return reviews

db_instance = Database()