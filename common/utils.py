import socket
import json
import struct

def send_json(sock, data):
    try:
        json_str = json.dumps(data)
        json_bytes = json_str.encode('utf-8')
        # Big Endian, Unsigned Int (4 bytes)
        header = struct.pack('!I', len(json_bytes))
        sock.sendall(header + json_bytes)
        return True
    except Exception as e:
        print(f"[Utils Error] send_json failed: {e}")
        return False

def recv_json(sock):
    try:
        # 1. 讀取標頭 (4 bytes)
        header = recv_all(sock, 4)
        if not header:
            # 這裡不印錯誤，因為 Client 正常斷線也會走到這
            return None
        
        # 解析長度
        data_len = struct.unpack('!I', header)[0]
        
        # 2. 根據長度讀取內容
        # print(f"[Debug] Expecting {data_len} bytes...") # Debug用
        data_bytes = recv_all(sock, data_len)
        if not data_bytes:
            print(f"[Utils Error] recv_json: Incomplete data. Expected {data_len} bytes.")
            return None
            
        # 3. 解碼 JSON
        json_str = data_bytes.decode('utf-8')
        return json.loads(json_str)

    except UnicodeDecodeError as e:
        print(f"[Utils Error] JSON Decode Error: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"[Utils Error] JSON Parse Error: {e}")
        return None
    except Exception as e:
        print(f"[Utils Error] recv_json unknown error: {e}")
        return None

def recv_all(sock, n):
    data = b''
    while len(data) < n:
        try:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None # 對方關閉連線
            data += chunk
        except Exception as e:
            print(f"[Utils Error] recv_all socket error: {e}")
            return None
    return data