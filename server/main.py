# server/main.py
import socket
import threading
import sys
import os

# --- 路徑設定 ---
# 取得目前檔案所在目錄 (server/)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 取得專案根目錄 (Final_Project/)
project_root = os.path.dirname(current_dir)
# 將專案根目錄加入 sys.path，這樣才能 import common
sys.path.append(project_root)

from common.utils import send_json, recv_json
from common.protocol import Protocol

# 引入服務模組
from server.services import auth
from server.services import store
from server.services import lobby
from server.services.db import db_instance

HOST = '0.0.0.0'
PORT = 8888

# ★★★ 線上使用者追蹤 ★★★
# 結構: { "username:role": ("ip", port) }
# 用於防止重複登入
online_users = {}
online_lock = threading.Lock()

def handle_client(conn, addr):
    """
    處理單一 Client 的連線邏輯 (執行緒函式)
    """
    print(f"[NEW CONNECTION] {addr} connected.")
    
    # 用來儲存當前連線的使用者狀態 (Session)
    current_user = None 
    user_key = None # 用來在斷線時快速找到並移除紀錄
    
    try:
        while True:
            # 1. 接收請求
            request = recv_json(conn)
            
            # 若 recv_json 回傳 None，代表連線中斷
            if request is None:
                break
            
            cmd = request.get("cmd")
            response = {}

            # ==================== Auth (驗證) ====================
            if cmd == Protocol.CMD_REGISTER:
                response = auth.handle_register(request)
            
            elif cmd == Protocol.CMD_LOGIN_DEV or cmd == Protocol.CMD_LOGIN_PLAYER:
                # 判斷身分
                role = "dev" if cmd == Protocol.CMD_LOGIN_DEV else "player"
                request["role"] = role
                
                # 先驗證帳密
                auth_resp = auth.handle_login(request)
                
                if auth_resp["status"] == Protocol.STATUS_OK:
                    username = auth_resp["username"]
                    temp_key = f"{username}:{role}"
                    
                    # ★★★ 檢查重複登入 ★★★
                    is_duplicate = False
                    with online_lock:
                        if temp_key in online_users:
                            # 如果已經有人登入，檢查是不是「我自己」(同個 socket addr)
                            existing_addr = online_users[temp_key]
                            if existing_addr != addr:
                                is_duplicate = True
                        
                        if not is_duplicate:
                            # 登記為線上
                            online_users[temp_key] = addr
                    
                    if is_duplicate:
                        response = {
                            "status": Protocol.STATUS_ERROR, 
                            "message": f"Account '{username}' is already logged in on another device."
                        }
                    else:
                        # 登入成功，更新 Session
                        response = auth_resp
                        current_user = {
                            "id": response["user_id"],
                            "username": response["username"],
                            "role": role
                        }
                        user_key = temp_key
                        print(f"[{addr}] {role.capitalize()} logged in: {username}")
                else:
                    response = auth_resp

            # ==================== Store (商城 - 開發者端) ====================
            elif cmd == Protocol.CMD_UPLOAD_GAME:
                if not current_user or current_user["role"] != "dev":
                    response = {"status": Protocol.STATUS_ERROR, "message": "Permission denied."}
                else:
                    response = store.handle_upload_game(request, current_user["id"])

            elif cmd == Protocol.CMD_UPDATE_GAME:
                if not current_user or current_user["role"] != "dev":
                    response = {"status": Protocol.STATUS_ERROR, "message": "Permission denied."}
                else:
                    response = store.handle_update_game(request, current_user["id"])

            elif cmd == Protocol.CMD_LIST_MY_GAMES:
                if not current_user or current_user["role"] != "dev":
                    response = {"status": Protocol.STATUS_ERROR, "message": "Permission denied."}
                else:
                    response = store.handle_list_my_games(current_user["id"])

            elif cmd == Protocol.CMD_UNPUBLISH_GAME:
                if not current_user or current_user["role"] != "dev":
                    response = {"status": Protocol.STATUS_ERROR, "message": "Permission denied."}
                else:
                    response = store.handle_unpublish_game(request, current_user["id"])

            # ==================== Store (商城 - 玩家端) ====================
            elif cmd == Protocol.CMD_LIST_GAMES:
                if not current_user:
                     response = {"status": Protocol.STATUS_ERROR, "message": "Please login first."}
                else:
                    response = store.handle_list_games()

            elif cmd == Protocol.CMD_DOWNLOAD_GAME:
                if not current_user:
                    response = {"status": Protocol.STATUS_ERROR, "message": "Please login first."}
                else:
                    response = store.handle_download_game(request)

            # ==================== Lobby (大廳 / 房間) ====================
            elif cmd == Protocol.CMD_CREATE_ROOM:
                if not current_user:
                    response = {"status": Protocol.STATUS_ERROR, "message": "Login first."}
                else:
                    gid = request.get("game_id")
                    response = lobby.handle_create_room(current_user["id"], current_user["username"], gid)

            elif cmd == Protocol.CMD_LIST_ROOMS:
                response = lobby.handle_list_rooms()

            elif cmd == Protocol.CMD_JOIN_ROOM:
                if not current_user:
                    response = {"status": Protocol.STATUS_ERROR, "message": "Login first."}
                else:
                    rid = request.get("room_id")
                    # ★★★ 這裡傳入了 user_id，修復了之前崩潰的問題 ★★★
                    response = lobby.handle_join_room(rid, current_user["id"], current_user["username"])

            # ==================== Social / Reviews ====================
            elif cmd == Protocol.CMD_REVIEW_GAME:
                if not current_user or current_user["role"] != "player":
                    response = {"status": Protocol.STATUS_ERROR, "message": "Permission denied."}
                else:
                    response = store.handle_review_game(request, current_user["id"])

            elif cmd == Protocol.CMD_GET_REVIEWS:
                # 讀取評論不需要登入，或是看你設計
                response = store.handle_get_reviews(request)
            
            # ==================== Default ====================
            else:
                response = {
                    "status": Protocol.STATUS_ERROR, 
                    "message": f"Unknown command: {cmd}"
                }

            # 3. 回傳結果
            send_json(conn, response)

    except Exception as e:
        print(f"[ERROR] Exception handling client {addr}: {e}")
        import traceback
        traceback.print_exc() # 印出詳細錯誤，方便除錯
    finally:
        # ★★★ 斷線清理：移除線上狀態 ★★★
        if user_key:
            with online_lock:
                # 再次檢查是否真的是我 (避免誤刪了剛登入的別人 - 雖然機率極低)
                if user_key in online_users and online_users[user_key] == addr:
                    del online_users[user_key]
                    print(f"[{addr}] User {user_key} logged out (session cleared).")
        
        conn.close()
        print(f"[DISCONNECT] {addr} disconnected.")

def start_server():
    """
    啟動 TCP Server
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # 允許 Port 重複使用 (避免重啟 Server 時顯示 Address already in use)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((HOST, PORT))
        server.listen()
        print(f"[STARTING] Server is listening on {HOST}:{PORT}")
        print(f"[INFO] Database checked/initialized.")
        
        # 確保 storage 目錄存在
        storage_path = os.path.join(project_root, 'server', 'storage', 'games')
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)
        print(f"[INFO] Storage directory: {storage_path}")

        while True:
            conn, addr = server.accept()
            # 為每個連線建立一個獨立的 Thread
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.daemon = True 
            thread.start()
            
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server is shutting down...")
    finally:
        server.close()

if __name__ == "__main__":
    start_server()