from common.protocol import Protocol
from .db import db_instance

def handle_register(payload):
    username = payload.get("username")
    password = payload.get("password")
    role = payload.get("role")

    if not username or not password or not role:
        return {"status": Protocol.STATUS_ERROR, "message": "Missing fields."}

    if db_instance.register_user(username, password, role):
        return {"status": Protocol.STATUS_OK, "message": f"Register {role} success."}
    else:
        return {"status": Protocol.STATUS_ERROR, "message": "Username already exists."}

def handle_login(payload):
    username = payload.get("username")
    password = payload.get("password")
    role = payload.get("role")

    if not username or not password:
        return {"status": Protocol.STATUS_ERROR, "message": "Missing fields."}

    user_id = db_instance.verify_user(username, password, role)
    if user_id:
        return {
            "status": Protocol.STATUS_OK, 
            "message": "Login success.",
            "user_id": user_id,
            "username": username
        }
    else:
        return {"status": Protocol.STATUS_ERROR, "message": "Invalid credentials."}