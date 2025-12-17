import socket
import json
import struct

def send_json(sock, data):
    try:
        json_str = json.dumps(data)
        json_bytes = json_str.encode('utf-8')
        header = struct.pack('!I', len(json_bytes))
        sock.sendall(header + json_bytes)
        return True
    except Exception as e:
        print(f"[Error] send_json failed: {e}")
        return False

def recv_json(sock):
    try:
        header = recv_all(sock, 4)
        if not header: return None
        data_len = struct.unpack('!I', header)[0]
        data_bytes = recv_all(sock, data_len)
        if not data_bytes: return None
        return json.loads(data_bytes.decode('utf-8'))
    except Exception as e:
        print(f"[Error] recv_json failed: {e}")
        return None

def recv_all(sock, n):
    data = b''
    while len(data) < n:
        try:
            packet = sock.recv(n - len(data))
            if not packet: return None
            data += packet
        except: return None
    return data