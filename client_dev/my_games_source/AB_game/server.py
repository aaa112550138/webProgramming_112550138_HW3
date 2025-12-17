import socket
import threading
import time
import argparse

class PvPGameServer:
    def __init__(self, host='0.0.0.0', port=9000):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(2)
        
        self.clients = []      # [conn1, conn2]
        self.secrets = {}      # {conn: "1234"}
        self.player_ids = {}   # {conn: 1}
        self.lock = threading.Lock()
        self.game_started = False
        self.turn_index = 0    # 0 or 1
        
        print(f"PvP 1A2B Server started on {port}")

    def broadcast(self, msg, exclude=None):
        """廣播訊息給所有人 (可排除某人)"""
        for conn in self.clients:
            if conn != exclude:
                try:
                    conn.sendall(msg.encode('utf-8'))
                except: pass

    def send_to(self, conn, msg):
        """傳送訊息給特定人"""
        try:
            conn.sendall(msg.encode('utf-8'))
        except: pass

    def calculate_ab(self, guess, secret):
        if not guess.isdigit() or len(guess) != 4 or len(set(guess)) != 4:
            return None # 格式錯誤
        a = 0
        b = 0
        for i in range(4):
            if guess[i] == secret[i]: a += 1
            elif guess[i] in secret: b += 1
        return f"{a}A{b}B"

    def handle_setup_phase(self):
        """出題階段：等待兩位玩家設定謎底"""
        self.broadcast("\n=== 階段一：出題階段 ===\n")
        self.broadcast("請輸入 4 個不重複數字作為你的【防守謎底】(對手要猜這個)：\n")
        self.broadcast("設定中... > ")

        setup_done = [False, False] # [P1_done, P2_done]

        def get_secret(index):
            conn = self.clients[index]
            while True:
                try:
                    data = conn.recv(1024).strip()
                    if not data: break # 斷線
                    
                    secret = data.decode('utf-8').strip()
                    if self.calculate_ab(secret, "1234") is None: # 借用檢查格式
                        self.send_to(conn, "❌ 格式錯誤！請輸入 4 個不重複數字 > ")
                        continue
                    
                    self.secrets[conn] = secret
                    self.send_to(conn, f"✅ 謎底已設定為 [{secret}]。等待對手...\n")
                    setup_done[index] = True
                    break
                except:
                    break

        # 啟動兩個執行緒同時等待輸入
        t1 = threading.Thread(target=get_secret, args=(0,))
        t2 = threading.Thread(target=get_secret, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        if all(setup_done):
            self.game_loop()
        else:
            self.broadcast("\n有人斷線，遊戲結束。\n")

    def game_loop(self):
        """對戰階段：回合制互猜"""
        self.broadcast("\n=== 階段二：對戰開始！ ===\n")
        self.broadcast(f"雙方都已設定謎底。由 Player {self.turn_index + 1} 先攻！\n")
        
        while True:
            current_conn = self.clients[self.turn_index]
            opponent_conn = self.clients[1 - self.turn_index]
            opponent_secret = self.secrets[opponent_conn]
            pid = self.player_ids[current_conn]

            # 提示目前狀態
            self.send_to(current_conn, f"\n🟢 [你的回合] 請猜測 Player {self.player_ids[opponent_conn]} 的謎底 > ")
            self.send_to(opponent_conn, f"\n🔴 [對手回合] 等待 Player {pid} 猜測...\n")

            try:
                # 等待當前玩家輸入
                data = current_conn.recv(1024).strip()
                if not data: break
                
                guess = data.decode('utf-8').strip()
                
                # 檢查格式 (為了簡化，若格式錯就不換回合，讓他重輸)
                result = self.calculate_ab(guess, opponent_secret)
                if result is None:
                    self.send_to(current_conn, "❌ 格式錯誤，請重試。\n")
                    continue

                # 廣播結果
                msg = f"\n📢 Player {pid} 猜了 [{guess}] 結果是 -> {result}\n"
                self.broadcast(msg)

                # 判斷勝負
                if result == "4A0B":
                    self.broadcast(f"\n🏆 恭喜 Player {pid} 猜對了！獲得勝利！\n")
                    self.broadcast("遊戲結束。伺服器將在 5 秒後關閉。\n")
                    time.sleep(5)
                    break # 結束迴圈，Server 關閉

                # 交換回合
                self.turn_index = 1 - self.turn_index

            except Exception as e:
                print(e)
                break

    def start(self):
        print("等待玩家加入 (需 2 人)...")
        while len(self.clients) < 2:
            conn, addr = self.server.accept()
            pid = len(self.clients) + 1
            self.clients.append(conn)
            self.player_ids[conn] = pid
            print(f"Player {pid} ({addr}) joined.")
            self.send_to(conn, f"歡迎！你是 Player {pid}。等待另一位玩家...\n")

        self.handle_setup_phase()
        
        # 遊戲結束，清理連線
        for c in self.clients: c.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=9000)
    args = parser.parse_args()
    
    PvPGameServer(port=args.port).start()