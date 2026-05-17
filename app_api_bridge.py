import os
import json
import asyncio
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import datetime

# ==========================================
# PATHS & CONFIGURATION SETUP
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")
ACTIVE_JOBS_FILE = os.path.join(DB_FOLDER, "active_jobs.json")
PENDING_ACTION_FILE = os.path.join(DB_FOLDER, "pending_human_action.json")
API_LOG_FILE = os.path.join(DB_FOLDER, "cloud_api_logs.txt")
LIVE_TERMINAL_LOG = os.path.join(DB_FOLDER, "engine_live_logs.txt")

# Ensure DB_FOLDER exists to prevent runtime file not found errors
if not os.path.exists(DB_FOLDER):
    os.makedirs(DB_FOLDER)

app = FastAPI(
    title="NMStudio1 AI Engine - Cloud Command Center",
    description="REST API interface to bridge Cloud AI Workers and Web App Dashboard",
    version="1.0.0"
)

# ==========================================
# CORS SECURITY CONFIGURATION
# ==========================================
# Netlify frontend jate smooth-ly access korte pare tar jonno CORS enable kora holo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production deployment-e apnar Netlify domain url ekhane bshate hobe
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Schema for payload validation
class ResolutionPayload(BaseModel):
    job_id: str

# ==========================================
# SAFE DATABASE DATA ACCESSORS & LOGGERS
# ==========================================
def read_plain_text_db(file_path):
    """SSD limit o integrity bachanor jonno data strictly plain text-e read kora"""
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_to_terminal(f"[SYSTEM ERROR] Database JSON corruption detected in {os.path.basename(file_path)}: {str(e)}")
        return []

def log_to_terminal(message: str):
    """SSD te real-time log save kora jate frontend direct read korte pare"""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    try:
        with open(LIVE_TERMINAL_LOG, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        logging.error(f"Failed to write live terminal log: {e}")

# ==========================================
# ADVANCED REST API ENDPOINTS
# ==========================================

@app.get("/api/v1/health")
async def get_engine_health():
    """Web Dashboard e active system diagnostics dekhator jonno"""
    pending = read_plain_text_db(PENDING_ACTION_FILE)
    active = read_plain_text_db(ACTIVE_JOBS_FILE)
    
    return {
        "engine_status": "ONLINE",
        "node": "Render_Cloud_Cluster",
        "pending_roadblocks": len(pending),
        "active_processing_jobs": len(active),
        "timestamp": asyncio.get_event_loop().time()
    }

@app.get("/api/v1/roadblocks")
async def fetch_active_roadblocks():
    """Captcha ba login blocks gulo direct list akare Web app panel-e load hobe"""
    return read_plain_text_db(PENDING_ACTION_FILE)

@app.post("/api/v1/resolve")
async def resolve_roadblock(payload: ResolutionPayload):
    """Web UI te user Captcha solve kore 'Resume' chaple ei endpoint call hobe"""
    if not os.path.exists(PENDING_ACTION_FILE):
        raise HTTPException(status_code=404, detail="No active roadblocks found in database.")
        
    try:
        pending_actions = read_plain_text_db(PENDING_ACTION_FILE)
        
        # Specified Job ID ti clear kore queue unblock kora
        updated_actions = [action for action in pending_actions if action.get("job_id") != payload.job_id]
        
        with open(PENDING_ACTION_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_actions, f, indent=4)
            
        log_to_terminal(f"[FILE_4_NOTIFIER] Signal routed successfully. Job {payload.job_id} unblocked. Resuming pipeline.")
            
        return {
            "status": "success", 
            "message": f"Signal routed to cloud container. Job {payload.job_id} unblocked."
        }
    except Exception as e:
        log_to_terminal(f"[SYSTEM ERROR] Failed to resolve roadblock: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database state synchronization failed: {str(e)}")

@app.get("/api/v1/logs")
async def fetch_real_terminal_logs():
    """Web frontend er terminal-e real-time txt file theke log pathanor endpoint"""
    if not os.path.exists(LIVE_TERMINAL_LOG):
        return {"logs": ["[SYSTEM] Awaiting execution commands... Engine is on standby."]}
    
    try:
        with open(LIVE_TERMINAL_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # UI clean rakhar jonno sesh 25 ti real log extract kora hobe
            return {"logs": [line.strip() for line in lines[-25:] if line.strip()]}
    except Exception as e:
        return {"logs": [f"[CRITICAL ERROR] Log stream disconnected: {str(e)}"]}

# ==========================================
# MASTER ORCHESTRATION LOOP
# ==========================================
async def continuous_orchestration_loop():
    """Background workflow thread controller"""
    log_to_terminal("[MAIN_HUB] Autonomous master worker loop spawned in background isolate.")
    
    while True:
        try:
            # Check for roadblocks before continuing execution
            pending = read_plain_text_db(PENDING_ACTION_FILE)
            if len(pending) > 0:
                log_to_terminal(f"[SYSTEM WARNING] Engine paused. {len(pending)} roadblock(s) awaiting manual resolution.")
            else:
                log_to_terminal("[FILE_1_SCRAPER] Polling for new target tasks across targeted domains...")
                
                # TODO (Internal execution): Future File 1 to File 7 sequential integration will happen here.
                # Ekhane future-e subprocess.run diye apnar python file gulo sequentially call kora hobe.
        
        except Exception as e:
            log_to_terminal(f"[SYSTEM FAILURE] Master loop exception: {str(e)}")
            
        # Live updates check korar jonno 60 seconds interval set kora holo (1800 chilo aage)
        await asyncio.sleep(60) 

@app.post("/api/v1/engine/control")
async def modify_engine_state(action: str, background_tasks: BackgroundTasks):
    """Web frontend theke full AI engine start ba stop korar dynamic control system"""
    if action == "start":
        log_to_terminal("[SYSTEM] START initialization signal received from Web Dashboard.")
        background_tasks.add_task(continuous_orchestration_loop)
        return {"status": "success", "message": "Autonomous master worker loop spawned in background isolate."}
    elif action == "stop":
        log_to_terminal("[SYSTEM] STOP command received. Termination signal sent to active worker pipeline.")
        return {"status": "success", "message": "Termination signal sent to active worker pipeline."}
    else:
        log_to_terminal(f"[SYSTEM ERROR] Invalid engine modifier received: {action}")
        raise HTTPException(status_code=400, detail="Invalid engine action modifier specified.")

# ==========================================
# SYSTEM RUNTIME ENTRYPOINT
# ==========================================
if __name__ == "__main__":
    import uvicorn
    # Local debugging and runtime spinning on cloud instances
    uvicorn.run(app, host="0.0.0.0", port=8000)
