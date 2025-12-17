import subprocess
import socket
import threading
import os
import time
import json 
import zipfile
from common.protocol import Protocol
from server.services.db import db_instance

# 用來存放所有房間的狀態
# 結構範例: { "1": { "game_id": 1, "port": 9000, "host": "p1", "players": ["p1"], "process": PopenObj, "version": "1.0" } }
rooms = {}
room_id_counter = 1
lock = threading.Lock()

# 設定遊戲 Server 的 Port 範圍
PORT_RANGE_START = 9000
PORT_RANGE_END = 9100

def find_free_port():
    """尋找一個沒被佔用的 Port"""
    for port in range(PORT_RANGE_START, PORT_RANGE_END):
        is_used = False
        with lock:
            for r in rooms.values():
                if r['port'] == port:
                    is_used = True
                    break
        if is_used: continue

        # 雙重檢查：確認系統層面該 Port 真的沒被佔用
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
    return None

def is_game_running(game_id):
    """檢查是否有任何房間正在運行此遊戲 (用於下架檢查)"""
    target_gid = str(game_id)
    with lock:
        for room in rooms.values():
            if str(room.get('game_id')) == target_gid:
                return True
    return False

def handle_create_room(user_id, username, game_id):
    global room_id_counter
    
    # 0. 檢查遊戲是否被下架
    try:
        # 假設 db.py 有實作 get_game_status
        if hasattr(db_instance, 'get_game_status'):
            is_active = db_instance.get_game_status(game_id)
            if not is_active:
                return {"status": Protocol.STATUS_ERROR, "message": "Game is unpublished/inactive."}
    except:
        pass

    # 1. 從 DB 取得真實的檔案路徑 (例如: Snake_1.1.zip)
    game_info = db_instance.get_game_file_info(game_id)
    if not game_info:
        return {"status": Protocol.STATUS_ERROR, "message": "Game not found in DB."}
    
    file_rel_path, game_name = game_info 
    
    # 2. 準備路徑
    # project_root/server/
    server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # ZIP 檔位置: project_root/server/storage/games/Snake_1.1.zip
    zip_path = os.path.join(server_dir, "storage", "games", file_rel_path)
    
    # 執行區位置: project_root/server/running_games/Snake_1.1/
    # 我們用檔名(去掉.zip)當作資料夾名稱，這樣不同版本會分開
    folder_name = file_rel_path.replace(".zip", "")
    run_dir = os.path.join(server_dir, "running_games", folder_name)

    # 3. 檢查並解壓縮 (確保 Server 跑的是上傳的 ZIP)
    if not os.path.exists(run_dir):
        print(f"[Lobby] Extracting new version to {run_dir}...")
        try:
            os.makedirs(run_dir, exist_ok=True)
            if not os.path.exists(zip_path):
                 return {"status": Protocol.STATUS_ERROR, "message": f"Game ZIP missing: {file_rel_path}"}
            
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(run_dir)
        except Exception as e:
            return {"status": Protocol.STATUS_ERROR, "message": f"Unzip failed: {e}"}

    # 4. 讀取 Config
    config_path = os.path.join(run_dir, "game_config.json")
    if not os.path.exists(config_path):
         return {"status": Protocol.STATUS_ERROR, "message": "game_config.json missing in ZIP."}
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except:
        return {"status": Protocol.STATUS_ERROR, "message": "Config format error."}
    
    # 取得版本號
    current_server_version = config.get("version", "1.0") 
    
    # 準備 Port
    port = find_free_port()
    if not port:
        return {"status": Protocol.STATUS_ERROR, "message": "No free ports available."}

    # 準備啟動指令
    server_cmd_template = config.get("server_cmd", "")
    cmd = server_cmd_template.replace("{port}", str(port))
    
    print(f"[Lobby] Starting Game Server (v{current_server_version}): {cmd}")

    try:
        # 5. 啟動 Game Server Process
        # ★★★ 關鍵：cwd 設定為 run_dir，這樣 Server 就在解壓後的目錄跑
        process = subprocess.Popen(cmd, shell=True, cwd=run_dir)
        
        # 6. 記錄房間
        with lock:
            rid = str(room_id_counter)
            room_id_counter += 1
            rooms[rid] = {
                "game_id": game_id,
                "game_name": game_name,
                "port": port,
                "host": username,
                "players": [username],
                "process": process,
                "version": current_server_version 
            }
        
        # ★★★ 關鍵：記錄遊玩歷史 (為了讓評論功能生效) ★★★
        try:
            db_instance.add_play_history(user_id, game_id)
        except Exception as e:
            print(f"[Lobby Warning] Failed to add play history: {e}")

        return {
            "status": Protocol.STATUS_OK,
            "message": "Room created.",
            "room_id": rid,
            "port": port,
            "game_name": game_name,
            "game_version": current_server_version 
        }

    except Exception as e:
        print(f"[Lobby Error] {e}")
        return {"status": Protocol.STATUS_ERROR, "message": f"Failed to start server: {e}"}

def handle_list_rooms():
    with lock:
        room_list = []
        for rid, r in rooms.items():
            room_list.append({
                "id": rid,
                "game_name": r['game_name'],
                "host": r['host'],
                "players": len(r['players']),
                "port": r['port'],
                "version": r.get('version', '1.0') 
            })
        return {"status": Protocol.STATUS_OK, "rooms": room_list}

def handle_join_room(room_id, user_id, username):
    with lock:
        if room_id not in rooms:
            return {"status": Protocol.STATUS_ERROR, "message": "Room not found."}
        
        room = rooms[room_id]
        room["players"].append(username)
        
        # ★★★ 關鍵：記錄遊玩歷史 ★★★
        try:
            db_instance.add_play_history(user_id, room["game_id"])
        except Exception as e:
            print(f"[Lobby Warning] Failed to add play history: {e}")

        return {
            "status": Protocol.STATUS_OK,
            "message": "Joined room.",
            "port": room["port"],
            "game_name": room["game_name"],
            "game_id": room["game_id"],
            "game_version": room.get("version", "1.0") 
        }