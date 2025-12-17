import socket
import threading
import sys
import os

# --- 路徑設定 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from common.utils import send_json, recv_json
from common.protocol import Protocol

# 引入服務模組
from server.services import auth
from server.services import store
from server.services import lobby
from server.services.db import db_instance

HOST = '0.0.0.0'
PORT = 30800

# 線上使用者追蹤 { "username:role": ("ip", port) }
online_users = {}
online_lock = threading.Lock()

def handle_client(conn, addr):
    print(f"[NEW CONNECTION] {addr} connected.")
    
    current_user = None 
    user_key = None
    current_room_id = None # 記錄目前所在的房間 ID
    
    try:
        while True:
            # 接收請求
            request = recv_json(conn)
            
            # 如果這裡是 None，代表上面 utils.py 回傳 None (斷線或錯誤)
            if request is None:
                print(f"[{addr}] Connection closed or invalid packet.")
                break
            
            cmd = request.get("cmd")
            # Debug Log: 印出收到的指令
            print(f"[{addr}] Received CMD: {cmd}") 

            response = {}

            # ==================== Auth (驗證) ====================
            if cmd == Protocol.CMD_REGISTER:
                response = auth.handle_register(request)
            
            elif cmd == Protocol.CMD_LOGIN_DEV or cmd == Protocol.CMD_LOGIN_PLAYER:
                role = "dev" if cmd == Protocol.CMD_LOGIN_DEV else "player"
                request["role"] = role
                
                auth_resp = auth.handle_login(request)
                
                if auth_resp["status"] == Protocol.STATUS_OK:
                    username = auth_resp["username"]
                    temp_key = f"{username}:{role}"
                    
                    # 檢查重複登入
                    is_duplicate = False
                    with online_lock:
                        if temp_key in online_users:
                            existing_addr = online_users[temp_key]
                            if existing_addr != addr:
                                is_duplicate = True
                        
                        if not is_duplicate:
                            online_users[temp_key] = addr
                    
                    if is_duplicate:
                        response = {"status": Protocol.STATUS_ERROR, "message": "帳號已在其他地方登入。"}
                    else:
                        response = auth_resp
                        current_user = {
                            "id": response["user_id"],
                            "username": response["username"],
                            "role": role
                        }
                        user_key = temp_key
                        print(f"[{addr}] {role} logged in: {username}")
                else:
                    response = auth_resp

            # ==================== Store (商城 - 開發者端) ====================
            elif cmd == Protocol.CMD_UPLOAD_GAME:
                if not current_user or current_user["role"] != "dev":
                    response = {"status": Protocol.STATUS_ERROR, "message": "Permission denied."}
                else:
                    print(f"[{addr}] Processing Upload...")
                    response = store.handle_upload_game(request, current_user["id"])
                    print(f"[{addr}] Upload result: {response.get('status')}")

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
                # 允許未登入瀏覽，或是您可以強制要求登入
                if not current_user:
                     response = {"status": Protocol.STATUS_ERROR, "message": "Please login first."}
                else:
                    response = store.handle_list_games()

            elif cmd == Protocol.CMD_DOWNLOAD_GAME:
                if not current_user:
                    response = {"status": Protocol.STATUS_ERROR, "message": "Please login first."}
                else:
                    print(f"[{addr}] Processing Download...")
                    response = store.handle_download_game(request)

            # ==================== Lobby (大廳 / 房間) ====================
            elif cmd == Protocol.CMD_CREATE_ROOM:
                if not current_user:
                    response = {"status": Protocol.STATUS_ERROR, "message": "Login first."}
                else:
                    gid = request.get("game_id")
                    response = lobby.handle_create_room(current_user["id"], current_user["username"], gid)
                    if response["status"] == Protocol.STATUS_OK:
                        current_room_id = response["room_id"]

            elif cmd == Protocol.CMD_LIST_ROOMS:
                response = lobby.handle_list_rooms()

            elif cmd == Protocol.CMD_JOIN_ROOM:
                if not current_user:
                    response = {"status": Protocol.STATUS_ERROR, "message": "Login first."}
                else:
                    rid = request.get("room_id")
                    response = lobby.handle_join_room(rid, current_user["id"], current_user["username"])
                    if response["status"] == Protocol.STATUS_OK:
                        current_room_id = rid

            elif cmd == Protocol.CMD_LEAVE_ROOM:
                if not current_user:
                    response = {"status": Protocol.STATUS_ERROR, "message": "Login first."}
                else:
                    rid = request.get("room_id")
                    response = lobby.handle_leave_room(rid, current_user["username"])
                    if response["status"] == Protocol.STATUS_OK:
                        current_room_id = None

            # ==================== Social / Reviews ====================
            elif cmd == Protocol.CMD_REVIEW_GAME:
                if not current_user or current_user["role"] != "player":
                    response = {"status": Protocol.STATUS_ERROR, "message": "Permission denied."}
                else:
                    response = store.handle_review_game(request, current_user["id"])

            elif cmd == Protocol.CMD_GET_REVIEWS:
                response = store.handle_get_reviews(request)
            
            # ==================== Default ====================
            else:
                response = {
                    "status": Protocol.STATUS_ERROR, 
                    "message": f"Unknown command: {cmd}"
                }

            send_json(conn, response)

    except Exception as e:
        print(f"[ERROR] Exception handling client {addr}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清除線上狀態
        if user_key:
            with online_lock:
                if user_key in online_users and online_users[user_key] == addr:
                    del online_users[user_key]
        
        # 斷線時觸發離開房間
        if current_room_id and current_user:
            print(f"[{addr}] User {current_user['username']} disconnected. Leaving room {current_room_id}...")
            lobby.handle_leave_room(current_room_id, current_user["username"])

        conn.close()
        print(f"[DISCONNECT] {addr} disconnected.")

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((HOST, PORT))
        server.listen()
        print(f"[STARTING] Server is listening on {HOST}:{PORT}")
        print(f"[INFO] Database checked/initialized.")
        
        storage_path = os.path.join(project_root, 'server', 'storage', 'games')
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)
        print(f"[INFO] Storage directory: {storage_path}")

        while True:
            conn, addr = server.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.daemon = True 
            thread.start()
            
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server is shutting down...")
    finally:
        server.close()

if __name__ == "__main__":
    start_server()