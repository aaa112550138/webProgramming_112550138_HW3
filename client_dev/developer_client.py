# developer_client.py

import socket
import sys
import os
import threading
import queue
import json
import shutil
import base64
import zipfile 

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) 
sys.path.append(project_root)

from common.utils import send_json, recv_json
from common.protocol import Protocol


# Host & Port -> connects to server
HOST = '140.113.17.11'
PORT = 30800

class DeveloperClient:
    def __init__(self):
        self.sock = None
        self.is_running = True
        self.user_token = None
        self.username = None
        self.msg_queue = queue.Queue()

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            threading.Thread(target=self.listen_to_server, daemon=True).start()
            return True
        except: return False

    def listen_to_server(self):
        while self.is_running:
            try:
                msg = recv_json(self.sock)
                if msg: self.msg_queue.put(msg)
                else: break
            except: break
        self.is_running = False

    def get_response(self, timeout=5):
        try: return self.msg_queue.get(timeout=timeout)
        except queue.Empty: return None

    def start(self):
        if not self.connect(): return
        try:
            while self.is_running:
                if self.user_token: self.main_menu()
                else: self.login_menu()
        except: pass
        finally: 
            if self.sock: self.sock.close()

    # Basic func
    def login_menu(self):
        print("\n=== Dev Auth ===")
        print("1. Login\n2. Register\n3. Exit")
        c = input("> ").strip()
        if c == '1': self.do_login()
        elif c == '2': self.do_register()
        elif c == '3': self.is_running = False

    def main_menu(self):
        print(f"\n=== Dev Dashboard ({self.username}) ===")
        print("1. Upload New Game\n2. List/Unpublish My Games\n3. Update Game\n4. Logout")
        c = input("> ").strip()
        if c == '1': self.do_upload_game()
        elif c == '2': self.do_list_and_manage_games()
        elif c == '3': self.do_update_game()
        elif c == '4': self.user_token = None

    def do_register(self):
        u, p = input("User: "), input("Pass: ")
        send_json(self.sock, {"cmd": Protocol.CMD_REGISTER, "username": u, "password": p, "role": "dev"})
        res = self.get_response()
        if res: print(res.get('message'))

    def do_login(self):
        u, p = input("User: "), input("Pass: ")
        send_json(self.sock, {"cmd": Protocol.CMD_LOGIN_DEV, "username": u, "password": p})
        res = self.get_response()
        if res and res.get("status") == "OK":
            self.user_token = res["user_id"]
            self.username = res["username"]
        else: print(f"Login Failed: {res.get('message') if res else 'Timeout'}")

    # D1: upload games
    def _package_and_send(self, cmd_type):
        """
        [核心邏輯] 處理檔案選取、過濾打包、並發送指定指令 (Upload 或 Update)
        修正版：排除垃圾檔案 + 增加 Timeout
        """
        # 設定原始碼存放目錄
        base_source_dir = os.path.join(current_dir, "my_games_source")
        
        if not os.path.exists(base_source_dir):
            os.makedirs(base_source_dir)
            print(f"[Info] Created directory: {base_source_dir}")
            print("Please put your game folders inside this directory.")
            return

        # 掃描目錄下的資料夾
        games = [d for d in os.listdir(base_source_dir) if os.path.isdir(os.path.join(base_source_dir, d))]
        
        if not games:
            print(f"No game folders found in {base_source_dir}.")
            return

        # 列出選項
        print("Available Game Folders:")
        for idx, g in enumerate(games):
            print(f"{idx+1}. {g}")
        
        try:
            sel_str = input("Select game folder (number, or 0 to cancel): ")
            sel = int(sel_str) - 1
            if sel == -1: return
            if sel < 0 or sel >= len(games):
                print("Invalid selection.")
                return 
            target_folder_name = games[sel]
            target_folder_path = os.path.join(base_source_dir, target_folder_name)
        except ValueError:
            print("Invalid input.")
            return

        # 檢查 config 是否存在
        config_path = os.path.join(target_folder_path, "game_config.json")
        if not os.path.exists(config_path):
            print(f"[Error] 'game_config.json' not found in {target_folder_name}!")
            return
        
        # 讀取 config
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"[Error] Failed to read config: {e}")
            return

        print(f"Selected: {config.get('game_name')} (v{config.get('version')})")
        
        if cmd_type == Protocol.CMD_UPDATE_GAME:
            print("⚠️  [Update Mode] Ensure you have incremented the version number in config!")

        confirm = input(f"Confirm {cmd_type}? (y/n): ")
        if confirm.lower() != 'y':
            return

        try:
            # 1. 壓縮 (手動過濾垃圾檔案，這是解決卡住的關鍵！)
            print("Zipping files (excluding .git, venv, __pycache__)...")
            zip_filename = os.path.join(current_dir, "temp_upload.zip")
            
            # 定義要排除的目錄名
            EXCLUDE_DIRS = {'.git', '__pycache__', 'venv', 'env', '.idea', '.vscode', 'node_modules', 'bin', 'obj'}
            # 定義要排除的副檔名或檔名
            EXCLUDE_FILES = {'.DS_Store', 'db.sqlite3', 'Thumbs.db'}
            
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(target_folder_path):
                    # 修改 dirs 列表以排除不需要的資料夾 (這樣 os.walk 就不會進去)
                    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                    
                    for file in files:
                        if file in EXCLUDE_FILES or file.endswith('.pyc'):
                            continue
                        
                        abs_path = os.path.join(root, file)
                        # 計算相對路徑，確保 zip 內部結構正確 (去除絕對路徑資訊)
                        rel_path = os.path.relpath(abs_path, target_folder_path)
                        zipf.write(abs_path, rel_path)
            
            # 檢查大小
            size_mb = os.path.getsize(zip_filename) / (1024 * 1024)
            print(f"Packed size: {size_mb:.2f} MB")
            
            # 如果還是太大，發出警告
            if size_mb > 50:
                print("⚠️  Warning: File is huge (>50MB). Upload might take a while.")

            # 2. 轉 Base64
            print("Encoding...")
            with open(zip_filename, "rb") as f:
                file_content = f.read()
                b64_str = base64.b64encode(file_content).decode('utf-8')
            
            os.remove(zip_filename)

            # 3. 發送
            req = {
                "cmd": cmd_type,
                "game_name": config.get('game_name'),
                "version": config.get('version'),
                "description": config.get('description', 'No description'),
                "file_data": b64_str
            }
            
            print("Sending to server (please wait)...")
            send_json(self.sock, req)
            
            # 4. 等待回應 (Timeout 加大到 60 秒)
            print("Waiting for server response...")
            res = self.get_response(timeout=10)
            
            if res:
                if res.get("status") == "OK":
                    print(f"✅ Success: {res.get('message')}")
                else:
                    print(f"❌ Failed: {res.get('message')}")
            else:
                print("❌ Error: Server timed out (check server logs or network).")
                
        except Exception as e:
            print(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()

    def do_upload_game(self): self._package_and_send(Protocol.CMD_UPLOAD_GAME)
    def do_update_game(self): self._package_and_send(Protocol.CMD_UPDATE_GAME)

    # D2: unpublish games
    def do_list_and_manage_games(self):
        send_json(self.sock, {"cmd": Protocol.CMD_LIST_MY_GAMES})
        res = self.get_response()
        if not res or res.get("status") != "OK": return
        
        games = res.get("games", [])
        if not games: 
            print("No games.")
            return
        
        print(f"{'ID':<5} {'Name':<15} {'Ver':<10} {'Status'}")
        for g in games: print(f"{g['id']:<5} {g['name']:<15} {g['version']:<10} {'Active' if g['is_active'] else 'Unpub'}")
        
        gid = input("Unpublish ID (0 cancel): ").strip()
        if gid and gid != '0':
            send_json(self.sock, {"cmd": Protocol.CMD_UNPUBLISH_GAME, "game_id": gid})
            res = self.get_response()
            if res: print(res.get('message'))

if __name__ == "__main__":
    DeveloperClient().start()