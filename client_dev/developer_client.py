# developer_client.py

import socket
import sys
import os
import threading
import queue
import json
import shutil
import base64

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) 
sys.path.append(project_root)

from common.utils import send_json, recv_json
from common.protocol import Protocol

HOST = '127.0.0.1'
PORT = 8888

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

    def _package_and_send(self, cmd_type):
        base = os.path.join(current_dir, "my_games_source")
        if not os.path.exists(base): os.makedirs(base)
        games = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
        if not games: 
            print("No games found.")
            return

        for i, g in enumerate(games): print(f"{i+1}. {g}")
        try:
            sel = int(input("Select: ")) - 1
            if sel < 0 or sel >= len(games): return
            target = os.path.join(base, games[sel])
        except: return

        if not os.path.exists(os.path.join(target, "game_config.json")):
            print("Missing game_config.json")
            return
        
        with open(os.path.join(target, "game_config.json")) as f: config = json.load(f)
        
        zip_path = shutil.make_archive(os.path.join(current_dir, "temp"), 'zip', target)
        with open(zip_path, "rb") as f: b64 = base64.b64encode(f.read()).decode()
        os.remove(zip_path)

        send_json(self.sock, {
            "cmd": cmd_type,
            "game_name": config.get('game_name'),
            "version": config.get('version'),
            "description": config.get('description'),
            "file_data": b64
        })
        res = self.get_response(15)
        if res: print(res.get('message'))

    def do_upload_game(self): self._package_and_send(Protocol.CMD_UPLOAD_GAME)
    def do_update_game(self): self._package_and_send(Protocol.CMD_UPDATE_GAME)

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