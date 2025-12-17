# client_dev/main.py
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from developer_client import DeveloperClient

if __name__ == "__main__":
    client = DeveloperClient()
    client.start()