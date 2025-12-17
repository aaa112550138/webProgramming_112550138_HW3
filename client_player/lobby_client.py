import socket
import sys
import os
import threading
import queue
import json
import base64
import zipfile
import io
import subprocess
import shutil

# --- 路徑設定 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from common.utils import send_json, recv_json
from common.protocol import Protocol

HOST = '127.0.0.1'
PORT = 8888

class LobbyClient:
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
            print(f"[*] 已連線至大廳伺服器 {HOST}:{PORT}")
            
            recv_thread = threading.Thread(target=self.listen_to_server)
            recv_thread.daemon = True
            recv_thread.start()
            return True
        except Exception as e:
            print(f"[!] 連線失敗: {e}")
            return False

    def listen_to_server(self):
        while self.is_running:
            try:
                msg = recv_json(self.sock)
                if msg:
                    self.msg_queue.put(msg)
                else:
                    print("\n[!] 伺服器已斷開連線。")
                    self.is_running = False
                    break
            except:
                break

    def get_response(self, timeout=5):
        try:
            return self.msg_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # ================= UI / Menu Logic =================

    def start(self):
        if not self.connect(): return
        try:
            while self.is_running:
                if self.username:
                    self.lobby_menu()
                else:
                    self.login_menu()
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            if self.sock: self.sock.close()

    def login_menu(self):
        print("\n=== 玩家登入 ===")
        print("1. 登入")
        print("2. 註冊")
        print("3. 離開")
        choice = input("請選擇 (1-3): ").strip()

        if choice == '1': self.do_login()
        elif choice == '2': self.do_register()
        elif choice == '3': self.is_running = False

    def lobby_menu(self):
        print(f"\n=== 遊戲大廳 ({self.username}) ===")
        print("1. 瀏覽商城 (Browse)")
        print("2. 下載遊戲 (Download)")
        print("3. 建立/加入房間 (Play)")
        print("4. 評分與評論 (Rate & Review)")
        print("5. 查看遊戲詳情 (View Details)")
        print("6. 登出 (Logout)")
        choice = input("請選擇 (1-6): ").strip()

        if choice == '1': self.do_list_games()
        elif choice == '2': self.do_download_game_optimized()
        elif choice == '3': self.room_menu()
        elif choice == '4': self.do_review_game()
        elif choice == '5': self.do_view_details()
        elif choice == '6': 
            self.username = None
            print("已登出。")

    def room_menu(self):
        print("\n=== 房間選單 ===")
        print("1. 建立房間 (Create Room)")
        print("2. 列表並加入 (List & Join)")
        print("3. 返回 (Back)")
        choice = input("請選擇 (1-3): ").strip()

        if choice == '1':
            self.do_create_room()
        elif choice == '2':
            self.do_join_room()
        elif choice == '3':
            return

    # ================= Core Game Launch & Update Logic =================

    def launch_game(self, game_name, ip, port):
        """核心功能：啟動本地遊戲程式 (Blocking Mode)"""
        game_dir = os.path.join(current_dir, "downloads", self.username, game_name)
        config_path = os.path.join(game_dir, "game_config.json")
        
        if not os.path.exists(config_path):
            print(f"❌ 在 {game_dir} 找不到遊戲檔案，請先下載。")
            return

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            cmd_template = config.get("exe_cmd", "")
            cmd = cmd_template.replace("{ip}", ip).replace("{port}", str(port))
            
            print(f"🚀 啟動遊戲中: {cmd}")
            
            # 1. 啟動 Process
            process = subprocess.Popen(cmd, shell=True, cwd=game_dir)
            
            # 2. 暫停 Lobby，等待遊戲結束
            print("\n" + "="*50)
            print(f"   🎮 正在遊玩 {game_name}...")
            print("   (大廳已暫停，關閉遊戲視窗後返回。)")
            print("="*50 + "\n")
            
            process.wait() # <--- 程式會卡在這裡，直到遊戲視窗關閉
            
            print("\n✅ 遊戲結束，返回大廳...\n")
            
        except Exception as e:
            print(f"❌ 啟動失敗: {e}")

    def check_and_update_game(self, game_id, game_name, server_version):
        """自動檢查版本並決定是否下載"""
        self.download_game_silently(game_id, game_name, server_version)

    def download_game_silently(self, game_id, game_name, server_version=None):
        """
        背景下載遊戲 (包含版本檢查與移除舊檔)
        """
        base_download_path = os.path.join(current_dir, "downloads", self.username, game_name)
        config_path = os.path.join(base_download_path, "game_config.json")

        # 防止重複下載
        if server_version and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    local_config = json.load(f)
                local_ver = local_config.get("version", "0.0")
                
                if local_ver == server_version:
                    print(f"✅ 遊戲 '{game_name}' 已是最新版 (v{local_ver})，跳過下載。")
                    return
                else:
                    print(f"⬇ 偵測到新版本 (Server: {server_version}, Local: {local_ver})，開始更新...")
            except:
                print("⚠️ 設定檔損毀，重新下載...")
        else:
            print(f"⬇ 正在下載 {game_name}...")

        # 開始下載流程
        req = {"cmd": Protocol.CMD_DOWNLOAD_GAME, "game_id": str(game_id)}
        send_json(self.sock, req)
        
        res = self.get_response(timeout=15)
        if res and res.get("status") == "OK":
            try:
                b64_data = res.get("file_data")
                # 優先使用 Server 回傳的正確名稱
                final_game_name = res.get("game_name", game_name) 
                final_path = os.path.join(current_dir, "downloads", self.username, final_game_name)

                # 清理舊版本
                if os.path.exists(final_path):
                    try:
                        shutil.rmtree(final_path)
                    except:
                        pass 
                
                # 建立新資料夾
                os.makedirs(final_path, exist_ok=True)
                
                with zipfile.ZipFile(io.BytesIO(base64.b64decode(b64_data))) as zf:
                    zf.extractall(final_path)
                print(f"✅ 下載完成！安裝於: {final_game_name}")
            except Exception as e:
                print(f"❌ 安裝失敗: {e}")
        else:
             msg = res.get("message") if res else "Timeout"
             print(f"❌ 下載失敗: {msg}")

    def _fetch_game_list(self):
        """內部呼叫：取得遊戲列表資料"""
        send_json(self.sock, {"cmd": Protocol.CMD_LIST_GAMES})
        res = self.get_response()
        if res and res.get("status") == "OK":
            return res.get("games", [])
        return None

    # ================= Actions =================

    def do_register(self):
        u = input("帳號: ")
        p = input("密碼: ")
        req = {"cmd": Protocol.CMD_REGISTER, "username": u, "password": p, "role": "player"}
        send_json(self.sock, req)
        res = self.get_response()
        if res: print(f"Server: {res.get('message')}")

    def do_login(self):
        u = input("帳號: ")
        p = input("密碼: ")
        req = {"cmd": Protocol.CMD_LOGIN_PLAYER, "username": u, "password": p}
        send_json(self.sock, req)
        res = self.get_response()
        if res and res.get("status") == "OK":
            self.username = res.get("username")
            print("登入成功！")
        else:
            print(f"登入失敗: {res.get('message') if res else 'Timeout'}")

    def do_list_games(self):
        print("\n--- 遊戲列表 ---")
        games = self._fetch_game_list()
        if games:
            print(f"{'ID':<5} {'Name':<15} {'Version':<10} {'Author':<10} {'Description'}")
            print("-" * 60)
            for g in games:
                print(f"{g['id']:<5} {g['name']:<15} {g['version']:<10} {g['author']:<10} {g['description']}")
        else:
            print("目前沒有遊戲上架。")

    def do_download_game_optimized(self):
        print("\n--- 下載遊戲 ---")
        games = self._fetch_game_list()
        
        if not games:
            print("無法取得遊戲列表。")
            return

        print(f"{'ID':<5} {'Name':<15} {'Version':<10}")
        print("-" * 40)
        for g in games:
            print(f"{g['id']:<5} {g['name']:<15} {g['version']:<10}")

        gid_str = input("輸入遊戲 ID 下載 (輸入 0 取消): ").strip()
        if gid_str == '0': return

        target_game = next((g for g in games if str(g['id']) == gid_str), None)
        
        if not target_game:
            print("❌ 錯誤: 無效的遊戲 ID。")
            return

        self.download_game_silently(gid_str, target_game['name'], target_game['version'])

    def do_review_game(self):
        print("\n--- 評分與評論 ---")
        self.do_list_games()
        gid = input("輸入遊戲 ID 評論: ").strip()
        if not gid: return
        try:
            rating = int(input("評分 (1-5): ").strip())
        except: return
        comment = input("留言 (選填): ").strip()
        req = {"cmd": Protocol.CMD_REVIEW_GAME, "game_id": gid, "rating": rating, "comment": comment}
        send_json(self.sock, req)
        res = self.get_response()
        if res: print(f"Server: {res.get('message')}")

    def do_view_details(self):
        print("\n--- 遊戲詳情 ---")
        self.do_list_games()
        gid = input("輸入遊戲 ID 查看: ").strip()
        if not gid: return
        send_json(self.sock, {"cmd": Protocol.CMD_GET_REVIEWS, "game_id": gid})
        res = self.get_response()
        if res and res.get("status") == "OK":
            reviews = res.get("reviews", [])
            print(f"\n平均評分: {res.get('average_rating')}")
            for r in reviews:
                print(f"[{r['date']}] {r['player']}: {r['rating']}★ {r['comment']}")
        else:
            print("讀取失敗。")

    def do_create_room(self):
        print("\n--- 建立房間 ---")
        games = self._fetch_game_list()
        if not games:
            print("無法取得列表。")
            return
            
        for g in games:
            print(f"{g['id']}. {g['name']}")
            
        gid_str = input("輸入遊戲 ID: ").strip()
        if gid_str == '0': return

        target_game = next((g for g in games if str(g['id']) == gid_str), None)
        if not target_game:
            print("❌ 無效 ID。")
            return

        req = {"cmd": Protocol.CMD_CREATE_ROOM, "game_id": gid_str}
        send_json(self.sock, req)
        
        print("正在請求 Server 建立房間...")
        res = self.get_response(timeout=10)
        
        if res and res.get("status") == "OK":
            print(f"✅ 房間已建立! ID: {res['room_id']}, Port: {res['port']}")
            
            server_ver = res.get("game_version", "1.0")
            self.check_and_update_game(gid_str, res['game_name'], server_ver)
            
            self.launch_game(res['game_name'], HOST, res['port'])
        else:
            msg = res.get("message") if res else "Timeout"
            print(f"❌ 建立失敗: {msg}")

    def do_join_room(self):
        print("\n--- 加入房間 ---")
        send_json(self.sock, {"cmd": Protocol.CMD_LIST_ROOMS})
        res = self.get_response()
        
        rooms = res.get("rooms", [])
        if not rooms:
            print("目前沒有房間。")
            return
            
        print(f"\n{'RoomID':<8} {'Game':<15} {'Host':<10} {'Players'}")
        print("-" * 50)
        for r in rooms:
            print(f"{r['id']:<8} {r['game_name']:<15} {r['host']:<10} {r['players']}/2")
            
        rid = input("輸入房間 ID: ").strip()
        if rid == '0': return
        
        req = {"cmd": Protocol.CMD_JOIN_ROOM, "room_id": rid}
        send_json(self.sock, req)
        
        res = self.get_response()
        if res and res.get("status") == "OK":
            print("✅ 加入成功!")
            
            server_ver = res.get("game_version", "1.0")
            self.check_and_update_game(res['game_id'], res['game_name'], server_ver)
            
            self.launch_game(res['game_name'], HOST, res['port'])
        else:
             print(f"❌ 加入失敗: {res.get('message') if res else 'Timeout'}")

if __name__ == "__main__":
    client = LobbyClient()
    client.start()