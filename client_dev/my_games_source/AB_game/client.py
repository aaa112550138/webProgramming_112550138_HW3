import socket
import threading
import sys
import argparse

class BullsAndCowsClient:
    def __init__(self, host, port):
        self.server_addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.running = True

    def receive_messages(self):
        """背景接收 Server 訊息"""
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    print("\n[!] 遊戲結束或伺服器斷線。按 Enter 離開...")
                    self.running = False
                    break
                
                msg = data.decode('utf-8')
                print(msg, end='', flush=True) 
            except:
                break

    def start(self):
        try:
            self.sock.connect(self.server_addr)
            # print("=== 已連線 ===") # 讓 Server 的歡迎訊息來顯示就好
            
            recv_thread = threading.Thread(target=self.receive_messages)
            recv_thread.daemon = True
            recv_thread.start()

            while self.running:
                try:
                    # 這裡會阻塞等待使用者輸入
                    # 因為是回合制，Server 會在輪到你時印出 "> " 提示
                    user_input = input() 
                    
                    if not self.running: break
                    if user_input.lower() in ['exit', 'quit']: break
                        
                    self.sock.sendall(user_input.encode('utf-8'))
                except:
                    break
                    
        except Exception as e:
            print(f"[!] 連線失敗: {e}")
        finally:
            self.running = False
            self.sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-ip", "--ip", type=str, default="127.0.0.1")
    parser.add_argument("-p", "--port", type=int, default=9000)
    args = parser.parse_args()

    client = BullsAndCowsClient(args.ip, args.port)
    client.start()