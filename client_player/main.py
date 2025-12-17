# client_player/main.py

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from lobby_client import LobbyClient

if __name__ == "__main__":
    client = LobbyClient()
    client.start()