import os
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="Discord Bot 總控中心")

# 記憶體內存儲伺服器節點狀態
# 格式: { "server_id": { "last_seen": float, "status": str, "is_active": bool } }
servers_db = {}

# 當前被授權上線的伺服器 ID
current_active_id = None
# 手動指定鎖定 Active 的伺服器 ID (None 代表由系統自動判斷)
manually_locked_id = None

# 容災超時時間（秒），超過此時間未收到心跳視為掛掉
TIMEOUT_LIMIT = 25

class HeartbeatPayload(BaseModel):
    server_id: str
    status: str  # "idle" (備用中), "active" (運行中), "restarting" (重啟中)

class ControlPayload(BaseModel):
    action: str  # "force_active", "release_lock", "restart"
    target_id: str

# 設定網頁範本目錄
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """總控中心首頁"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/heartbeat")
async def receive_heartbeat(payload: HeartbeatPayload):
    """接收來自節點的心跳"""
    global current_active_id, manually_locked_id
    server_id = payload.server_id
    now = time.time()
    
    # 註冊或更新節點資訊
    servers_db[server_id] = {
        "last_seen": now,
        "status": payload.status,
        "is_active": False
    }

    # 進行主備狀態調度
    # 1. 清理與確認目前在線的伺服器 (心跳未超時)
    active_servers = [
        sid for sid, info in servers_db.items() 
        if now - info["last_seen"] < TIMEOUT_LIMIT
    ]

    # 2. 確定誰應該是 Active
    if manually_locked_id and manually_locked_id in active_servers:
        # 若有手動鎖定且該主機在線，則以手動鎖定優先
        current_active_id = manually_locked_id
    else:
        # 清除失效的手動鎖定
        if manually_locked_id and manually_locked_id not in active_servers:
            manually_locked_id = None
            
        # 自動調度邏輯：選擇在線的伺服器中，優先權最高者 (以字母順序排序，例如 1 號優先於 2 號)
        if current_active_id not in active_servers:
            if active_servers:
                # 排序後選擇第一個在線的
                active_servers.sort()
                current_active_id = active_servers[0]
            else:
                current_active_id = None

    # 更新狀態庫中的 is_active 標記
    for sid in servers_db:
        servers_db[sid]["is_active"] = (sid == current_active_id)

    return {
        "active_server_id": current_active_id,
        "status": "ok"
    }

@app.get("/api/status")
async def get_status():
    """取得所有伺服器狀態與當前 Active 資訊"""
    now = time.time()
    nodes = []
    
    for sid, info in servers_db.items():
        is_online = (now - info["last_seen"] < TIMEOUT_LIMIT)
        nodes.append({
            "server_id": sid,
            "is_online": is_online,
            "last_seen_seconds_ago": round(now - info["last_seen"], 1),
            "status": info["status"] if is_online else "offline",
            "is_active": info["is_active"] if is_online else False
        })
        
    return {
        "nodes": nodes,
        "current_active_id": current_active_id,
        "manually_locked_id": manually_locked_id
    }

@app.post("/api/control")
async def control_node(payload: ControlPayload):
    """手動總控操作"""
    global manually_locked_id, current_active_id
    action = payload.action
    target_id = payload.target_id

    if action == "force_active":
        if target_id not in servers_db:
            raise HTTPException(status_code=400, detail="無效的伺服器 ID")
        manually_locked_id = target_id
        current_active_id = target_id
        for sid in servers_db:
            servers_db[sid]["is_active"] = (sid == target_id)
        return {"status": "ok", "message": f"已手動指定 {target_id} 為 Active"}

    elif action == "release_lock":
        manually_locked_id = None
        return {"status": "ok", "message": "已解除手動鎖定，回復自動切換模式"}

    elif action == "restart":
        # 標記該伺服器需要重啟，這會由機器人下一次心跳取得並執行
        if target_id in servers_db:
            servers_db[target_id]["status"] = "restarting_pending"
            return {"status": "ok", "message": f"已發送重啟請求給 {target_id}"}
        raise HTTPException(status_code=400, detail="無效的伺服器 ID")

    raise HTTPException(status_code=400, detail="不支援的操作")
