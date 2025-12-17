import sys
import os

# 將當前腳本所在目錄加入 sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from lobby_client import LobbyClient

if __name__ == "__main__":
    client = LobbyClient()
    client.start()