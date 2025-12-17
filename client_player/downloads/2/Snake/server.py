import socket
import threading
import json
import time
import random
import argparse

# 遊戲設定
WIDTH, HEIGHT = 600, 400
GRID_SIZE = 20
FPS = 10

# 顏色庫
COLORS = [
    (0, 255, 0), (0, 0, 255), (255, 0, 0), (255, 255, 0),
    (0, 255, 255), (255, 0, 255), (255, 165, 0), (128, 0, 128)
]

class GameServer:
    def __init__(self, host='0.0.0.0', port=9000):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen()
        print(f"[GAME SERVER] Listening on {host}:{port}")

        self.clients = {} 
        self.snakes = {} 
        self.food = [random.randint(0, (WIDTH//GRID_SIZE)-1), random.randint(0, (HEIGHT//GRID_SIZE)-1)]
        
        # ★★★ 修正關鍵：改用 RLock (可重入鎖) 避免 Deadlock ★★★
        self.lock = threading.RLock() 
        self.running = True

    def respawn_snake(self, player_id):
        """重生"""
        start_x = random.randint(2, (WIDTH//GRID_SIZE)-3)
        start_y = random.randint(2, (HEIGHT//GRID_SIZE)-3)
        color = COLORS[player_id % len(COLORS)]
        
        # 因為用了 RLock，就算外部已經上鎖，這裡再鎖一次也不會卡死
        with self.lock:
            self.snakes[player_id] = {
                'id': player_id,
                'body': [[start_x, start_y]],
                'dir': [0, 0], 
                'color': color,
                'score': 0
            }

    def handle_client(self, conn, addr, player_id):
        print(f"[NEW PLAYER] {addr} connected as Player {player_id}")
        
        # 1. Handshake
        try:
            init_msg = json.dumps({"type": "init", "player_id": player_id, "width": WIDTH, "height": HEIGHT})
            conn.sendall(init_msg.encode() + b'\n')
        except:
            return

        # 這裡上鎖了
        with self.lock:
            self.clients[player_id] = conn
            # 呼叫 respawn_snake，它裡面也會上鎖 -> RLock 允許這樣做
            self.respawn_snake(player_id)

        try:
            while self.running:
                data = conn.recv(1024)
                if not data: break
                
                try:
                    decoded = data.decode().strip()
                    for line in decoded.split('\n'):
                        if not line: continue
                        msg = json.loads(line)
                        
                        # 處理移動
                        if 'dir' in msg:
                            new_dir = msg.get('dir')
                            with self.lock:
                                if player_id in self.snakes:
                                    # 防回頭
                                    curr = self.snakes[player_id]['dir']
                                    if len(self.snakes[player_id]['body']) > 1:
                                        if (new_dir[0]+curr[0]==0) and (new_dir[1]+curr[1]==0):
                                            continue
                                    self.snakes[player_id]['dir'] = new_dir
                        
                        # 處理重新開始
                        elif msg.get('action') == 'restart':
                            self.respawn_snake(player_id)

                except: pass
        except: pass
        finally:
            print(f"Player {player_id} disconnected")
            conn.close()
            with self.lock:
                if player_id in self.clients: del self.clients[player_id]
                if player_id in self.snakes: del self.snakes[player_id]

    def game_loop(self):
        while self.running:
            time.sleep(1/FPS)
            
            with self.lock:
                state_update = {'type': 'update', 'snakes': [], 'food': self.food}
                
                # 收集所有身體座標用於碰撞
                all_bodies = []
                for s in self.snakes.values():
                    all_bodies.extend(s['body'])

                dead_players = []

                for pid, snake in self.snakes.items():
                    if snake['dir'] == [0, 0]:
                        state_update['snakes'].append(snake)
                        continue

                    head = snake['body'][0]
                    new_head = [head[0] + snake['dir'][0], head[1] + snake['dir'][1]]
                    new_head[0] %= (WIDTH // GRID_SIZE)
                    new_head[1] %= (HEIGHT // GRID_SIZE)

                    # 碰撞判定
                    if new_head in all_bodies:
                        dead_players.append(pid)
                        continue

                    # 吃食物
                    if new_head == self.food:
                        snake['score'] += 10
                        snake['body'].insert(0, new_head)
                        while True:
                            nf = [random.randint(0, (WIDTH//GRID_SIZE)-1), random.randint(0, (HEIGHT//GRID_SIZE)-1)]
                            if nf not in all_bodies and nf != new_head:
                                self.food = nf
                                break
                    else:
                        snake['body'].insert(0, new_head)
                        snake['body'].pop()
                    
                    state_update['snakes'].append(snake)

                # 處理死亡
                for pid in dead_players:
                    if pid in self.snakes:
                        final_score = self.snakes[pid]['score']
                        del self.snakes[pid] # 從地圖移除
                        
                        # 通知該玩家 Game Over
                        if pid in self.clients:
                            try:
                                msg = json.dumps({"type": "game_over", "score": final_score})
                                self.clients[pid].sendall(msg.encode() + b'\n')
                            except: pass

                # 廣播更新
                msg = json.dumps(state_update).encode() + b'\n'
                for client in self.clients.values():
                    try: client.sendall(msg)
                    except: pass

    def start(self):
        threading.Thread(target=self.game_loop, daemon=True).start()
        pid = 0
        while True:
            conn, addr = self.server.accept()
            threading.Thread(target=self.handle_client, args=(conn, addr, pid), daemon=True).start()
            pid += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=9000)
    args = parser.parse_args()
    server = GameServer(port=args.port)
    server.start()