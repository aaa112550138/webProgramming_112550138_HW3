import sys
import os

# 將當前腳本所在目錄加入 sys.path，確保能 import 到同目錄下的模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from developer_client import DeveloperClient

if __name__ == "__main__":
    client = DeveloperClient()
    client.start()