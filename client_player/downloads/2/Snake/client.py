import pygame
import socket
import json
import threading
import sys
import argparse

# 顏色
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
GRID_SIZE = 20

class GameClient:
    def __init__(self, host='127.0.0.1', port=9000):
        self.server_addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.game_state = {'snakes': [], 'food': [0,0]}
        self.my_id = -1
        self.running = True
        self.width = 600
        self.height = 400
        
        # 狀態旗標
        self.is_dead = False
        self.final_score = 0
        self.retry_btn = None

    def connect(self):
        try:
            self.sock.connect(self.server_addr)
            print("Connected!")
            
            # Handshake
            data = self.sock.recv(1024).decode()
            init = json.loads(data)
            if init.get('type') == 'init':
                self.my_id = init['player_id']
                return True
            return False
        except Exception as e:
            print(f"Conn Error: {e}")
            return False

    def listen(self):
        buf = ""
        while self.running:
            try:
                data = self.sock.recv(4096).decode()
                if not data: break
                buf += data
                while '\n' in buf:
                    msg_str, buf = buf.split('\n', 1)
                    if not msg_str: continue
                    msg = json.loads(msg_str)
                    
                    if msg.get('type') == 'game_over':
                        self.is_dead = True
                        self.final_score = msg.get('score', 0)
                    elif msg.get('type') == 'update' and not self.is_dead:
                        self.game_state = msg
            except: break

    def send_dir(self, dx, dy):
        try:
            self.sock.sendall(json.dumps({"dir": [dx, dy]}).encode() + b'\n')
        except: pass

    def send_restart(self):
        try:
            self.sock.sendall(json.dumps({"action": "restart"}).encode() + b'\n')
            self.is_dead = False
        except: pass

    def draw_game_over(self, screen):
        # 半透明遮罩
        s = pygame.Surface((self.width, self.height))
        s.set_alpha(200)
        s.fill(BLACK)
        screen.blit(s, (0,0))

        font_l = pygame.font.SysFont("Arial", 48, bold=True)
        font_s = pygame.font.SysFont("Arial", 24)

        t_lost = font_l.render("GAME OVER", True, RED)
        screen.blit(t_lost, t_lost.get_rect(center=(self.width//2, self.height//2 - 50)))

        t_score = font_s.render(f"Score: {self.final_score}", True, WHITE)
        screen.blit(t_score, t_score.get_rect(center=(self.width//2, self.height//2)))

        # 按鈕
        self.retry_btn = pygame.Rect(self.width//2 - 70, self.height//2 + 40, 140, 40)
        pygame.draw.rect(screen, GREEN, self.retry_btn, border_radius=10)
        t_retry = font_s.render("Try Again", True, BLACK)
        screen.blit(t_retry, t_retry.get_rect(center=self.retry_btn.center))

    def run(self):
        if not self.connect(): return
        pygame.init()
        screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption(f"Snake P{self.my_id}")
        clock = pygame.time.Clock()
        threading.Thread(target=self.listen, daemon=True).start()
        font = pygame.font.SysFont("Arial", 16)

        while self.running:
            screen.fill(BLACK)
            for event in pygame.event.get():
                if event.type == pygame.QUIT: self.running = False
                
                if self.is_dead:
                    if event.type == pygame.MOUSEBUTTONDOWN and self.retry_btn:
                        if self.retry_btn.collidepoint(event.pos):
                            self.send_restart()
                else:
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_UP: self.send_dir(0, -1)
                        elif event.key == pygame.K_DOWN: self.send_dir(0, 1)
                        elif event.key == pygame.K_LEFT: self.send_dir(-1, 0)
                        elif event.key == pygame.K_RIGHT: self.send_dir(1, 0)

            # 畫食物
            fx, fy = self.game_state.get('food', [0,0])
            pygame.draw.rect(screen, RED, (fx*GRID_SIZE, fy*GRID_SIZE, GRID_SIZE, GRID_SIZE))

            # 畫蛇
            for snake in self.game_state.get('snakes', []):
                color = tuple(snake.get('color', WHITE))
                is_me = (snake.get('id') == self.my_id)
                
                for seg in snake.get('body', []):
                    r = (seg[0]*GRID_SIZE, seg[1]*GRID_SIZE, GRID_SIZE, GRID_SIZE)
                    pygame.draw.rect(screen, color, r)
                    if is_me: pygame.draw.rect(screen, WHITE, r, 2)
                
                if snake.get('body'):
                    h = snake['body'][0]
                    lbl = f"ME({snake.get('score',0)})" if is_me else f"P{snake.get('id')}"
                    txt = font.render(lbl, True, WHITE)
                    screen.blit(txt, (h[0]*GRID_SIZE, h[1]*GRID_SIZE-20))

            if self.is_dead: self.draw_game_over(screen)

            pygame.display.flip()
            clock.tick(60)
        pygame.quit()
        self.sock.close()
        sys.exit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-ip", "--ip", type=str, default="127.0.0.1")
    parser.add_argument("-p", "--port", type=int, default=9000)
    args = parser.parse_args()
    GameClient(host=args.ip, port=args.port).run()