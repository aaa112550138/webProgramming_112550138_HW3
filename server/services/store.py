import os
import base64
from common.protocol import Protocol
from .db import db_instance
from server.services import lobby

# 設定存放路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(current_dir)
STORAGE_DIR = os.path.join(server_dir, 'storage', 'games')

if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

def handle_upload_game(payload, dev_user_id):
    name = payload.get("game_name")
    version = payload.get("version")
    desc = payload.get("description")
    b64_data = payload.get("file_data")

    if not all([name, version, b64_data]):
        return {"status": Protocol.STATUS_ERROR, "message": "Missing game data"}

    # 檢查遊戲狀態 (是否已存在、是否屬於該開發者、是否已下架)
    game_details = db_instance.get_game_details_by_name(name)
    
    is_resurrection = False
    game_id_to_resurrect = None

    if game_details:
        game_id, owner_id, is_active = game_details
        
        # 1. 檢查擁有權
        if owner_id != dev_user_id:
            return {"status": Protocol.STATUS_ERROR, "message": f"Game Name '{name}' is taken by another developer."}
        
        # 2. 如果正在架上，提示使用 Update
        if is_active:
            return {"status": Protocol.STATUS_ERROR, "message": f"Game '{name}' already active. Please use 'Update Game'."}
        
        # 3. 標記為復活模式
        is_resurrection = True
        game_id_to_resurrect = game_id

    try:
        # 處理檔案儲存
        filename = f"{name}_{version}.zip"
        safe_filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in "._-"])
        save_path = os.path.join(STORAGE_DIR, safe_filename)
        
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(b64_data))
            
        if is_resurrection:
            # 執行復活：更新資料 + 設定為 Active
            db_instance.update_game_version(game_id_to_resurrect, version, desc, safe_filename)
            db_instance.set_game_active(game_id_to_resurrect, True)
            return {"status": Protocol.STATUS_OK, "message": f"Game '{name}' has been re-published (resurrected)!"}
        else:
            # 執行新增
            if db_instance.add_game(name, version, dev_user_id, desc, safe_filename):
                return {"status": Protocol.STATUS_OK, "message": "Game uploaded successfully."}
            else:
                return {"status": Protocol.STATUS_ERROR, "message": "DB Error."}

    except Exception as e:
        return {"status": Protocol.STATUS_ERROR, "message": str(e)}

def handle_update_game(payload, dev_user_id):
    name = payload.get("game_name")
    new_version = payload.get("version")
    b64_data = payload.get("file_data")
    desc = payload.get("description")

    # 1. 檢查遊戲是否存在且屬於該開發者
    existing_game = db_instance.get_game_info_by_name(name, dev_user_id)
    if not existing_game:
        return {
            "status": Protocol.STATUS_ERROR, 
            "message": f"Game '{name}' not found or you don't own it. Please use 'Upload New Game' first."
        }
    
    game_id, current_version = existing_game

    # 防呆：版本檢查
    if new_version == current_version:
        return {
            "status": Protocol.STATUS_ERROR, 
            "message": f"Version {new_version} already exists. Please update 'version' in game_config.json."
        }

    try:
        filename = f"{name}_{new_version}.zip"
        safe_filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in "._-"])
        save_path = os.path.join(STORAGE_DIR, safe_filename)

        with open(save_path, "wb") as f:
            f.write(base64.b64decode(b64_data))

        if db_instance.update_game_version(game_id, new_version, desc, safe_filename):
            return {
                "status": Protocol.STATUS_OK, 
                "message": f"Game updated to version {new_version}."
            }
        else:
            return {"status": Protocol.STATUS_ERROR, "message": "DB Error during update."}

    except Exception as e:
        return {"status": Protocol.STATUS_ERROR, "message": str(e)}

def handle_list_games():
    """列出所有上架中的遊戲 (給玩家看)"""
    try:
        games = db_instance.get_all_games()
        return {"status": Protocol.STATUS_OK, "games": games}
    except Exception as e:
        return {"status": Protocol.STATUS_ERROR, "message": str(e)}

def handle_download_game(payload):
    game_id = payload.get("game_id")
    
    # 1. 查 DB
    game_info = db_instance.get_game_file_info(game_id)
    if not game_info:
        return {"status": Protocol.STATUS_ERROR, "message": "Game not found."}
    
    file_rel_path, game_name = game_info
    full_path = os.path.join(STORAGE_DIR, file_rel_path)
    
    if not os.path.exists(full_path):
        return {"status": Protocol.STATUS_ERROR, "message": "Game file missing on server."}

    try:
        with open(full_path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode('utf-8')
            
        return {
            "status": Protocol.STATUS_OK,
            "message": "Download started.",
            "file_data": file_data,
            "game_name": game_name,
            "file_name": file_rel_path
        }
    except Exception as e:
        return {"status": Protocol.STATUS_ERROR, "message": str(e)}

def handle_list_my_games(dev_user_id):
    """列出該開發者的所有遊戲 (包含已下架)"""
    try:
        games = db_instance.get_games_by_dev(dev_user_id)
        return {"status": Protocol.STATUS_OK, "games": games}
    except Exception as e:
        return {"status": Protocol.STATUS_ERROR, "message": str(e)}

def handle_unpublish_game(payload, dev_user_id):
    game_id = payload.get("game_id")
    
    # 1. 檢查權限
    if not db_instance.is_game_owner(game_id, dev_user_id):
        return {"status": Protocol.STATUS_ERROR, "message": "Permission denied: You do not own this game."}

    # 2. 檢查房間狀態 (呼叫 lobby 模組)
    if lobby.is_game_running(game_id):
        return {
            "status": Protocol.STATUS_ERROR, 
            "message": "Cannot unpublish: There are active rooms playing this game. Please wait or close them first."
        }

    # 3. 執行下架
    if db_instance.set_game_active(game_id, False):
        return {"status": Protocol.STATUS_OK, "message": "Game unpublished successfully."}
    else:
        return {"status": Protocol.STATUS_ERROR, "message": "DB Error."}

def handle_review_game(payload, user_id):
    """處理玩家評論"""
    game_id = payload.get("game_id")
    rating = payload.get("rating")
    comment = payload.get("comment")

    if not game_id or not rating:
        return {"status": Protocol.STATUS_ERROR, "message": "Missing fields."}

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            return {"status": Protocol.STATUS_ERROR, "message": "Rating must be 1-5."}
    except:
        return {"status": Protocol.STATUS_ERROR, "message": "Invalid rating."}

    # 檢查是否有玩過 (未玩先評禁止)
    if not db_instance.has_played(user_id, game_id):
        return {"status": Protocol.STATUS_ERROR, "message": "You must play the game before reviewing."}

    if db_instance.add_review(user_id, game_id, rating, comment):
        return {"status": Protocol.STATUS_OK, "message": "Review added successfully."}
    else:
        return {"status": Protocol.STATUS_ERROR, "message": "Failed to save review."}

def handle_get_reviews(payload):
    """取得遊戲評論列表與平均分"""
    game_id = payload.get("game_id")
    try:
        reviews = db_instance.get_game_reviews(game_id)
        avg_rating = 0
        if reviews:
            avg_rating = sum(r['rating'] for r in reviews) / len(reviews)
            
        return {
            "status": Protocol.STATUS_OK, 
            "reviews": reviews, 
            "average_rating": round(avg_rating, 1)
        }
    except Exception as e:
        return {"status": Protocol.STATUS_ERROR, "message": str(e)}