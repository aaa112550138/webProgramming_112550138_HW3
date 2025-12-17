import os
import shutil

# for cleaning
PATHS_TO_CLEAN = [
    "server/db.sqlite3",              # 資料庫檔案
    "server/storage/games",           # 上傳的 ZIP 檔
    "server/running_games",           # Server 端解壓縮後的執行檔
    "client_player/downloads",        # Player 端下載的遊戲
]

def clean_path(path):
    if not os.path.exists(path):
        print(f"[略過] {path} 不存在")
        return

    try:
        if os.path.isfile(path):
            os.remove(path)
            print(f"[已刪除檔案] {path}")
        elif os.path.isdir(path):
            # 刪除資料夾內所有內容
            shutil.rmtree(path)
            # 重新建立空資料夾 (除了 db 檔案)
            if "db.sqlite3" not in path:
                os.makedirs(path)
            print(f"[已清空目錄] {path}")
    except Exception as e:
        print(f"[錯誤] 無法處理 {path}: {e}")

def main():
    print("="*40)
    print("      ⚠️  警告：環境重設工具  ⚠️")
    print("="*40)
    print("這將會刪除所有：")
    print("1. 使用者帳號與密碼")
    print("2. 上架的遊戲檔案與紀錄")
    print("3. 評論與遊玩歷史")
    print("4. 客戶端下載的暫存檔")
    print("-" * 40)
    
    confirm = input("確定要重設嗎？(輸入 'y' 確認): ").strip().lower()
    
    if confirm == 'y':
        print("\n開始清理...")
        for p in PATHS_TO_CLEAN:
            # 轉換為絕對路徑以避免路徑錯誤
            abs_path = os.path.abspath(p)
            clean_path(abs_path)
        print("\n✅ 重設完成！請重新啟動 server/main.py 以初始化資料庫。")
    else:
        print("已取消。")

if __name__ == "__main__":
    main()