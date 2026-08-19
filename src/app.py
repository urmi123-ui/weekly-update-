import os
import sys
import json
import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Ensure python path has src directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import pipeline tasks
try:
    from src.scraper import fetch_recent_reviews
    from src.processing import process_reviews
    from src.reasoning import run_reasoning_engine
    from src.orchestrator import format_doc_report, format_email_teaser
except ImportError:
    from scraper import fetch_recent_reviews
    from processing import process_reviews
    from reasoning import run_reasoning_engine
    from orchestrator import format_doc_report, format_email_teaser

load_dotenv()

app = FastAPI(title="Weekly Review Pulse Local Backend")

# Enable CORS for React Frontend (on port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDIT_LOG_FILE = "audit_log.json"
INSIGHTS_FILE = "insights.json"
REVIEWS_FILE = "reviews.json"

# State tracking for background run
PIPELINE_STATUS = {
    "status": "idle",  # idle, running, failed
    "step": "",        # scraping, clustering, done
    "message": "Ready to analyze.",
    "error": None
}

class RunRequest(BaseModel):
    product: str = "groww"
    weeks_window: int = 8

class DeliverRequest(BaseModel):
    doc_id: Optional[str] = None
    to_emails: Optional[str] = None
    email_subject: str
    email_body: Optional[str] = None
    doc_body: Optional[str] = None
    run_id: str
    deliver_to_doc: bool = True
    deliver_to_email: bool = True

def load_json_file(filepath: str, default_val):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return default_val

def save_json_file(filepath: str, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[Backend] Error writing to {filepath}: {e}")

def post_json_helper(url: str, payload: dict, api_key: str = None) -> dict:
    import urllib.request
    import urllib.error
    req_data = json.dumps(payload).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['X-API-Key'] = api_key
        headers['Authorization'] = f"Bearer {api_key}"
        
    req = urllib.request.Request(
        url,
        data=req_data,
        headers=headers,
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        try:
            err_json = json.loads(err_body)
            detail = err_json.get("detail", str(e))
        except Exception:
            detail = err_body or str(e)
        raise Exception(f"HTTP {e.code}: {detail}")
    except Exception as e:
        raise Exception(f"Connection failed: {str(e)}")

async def run_pipeline_task(product: str, weeks_window: int):
    global PIPELINE_STATUS
    try:
        PIPELINE_STATUS["status"] = "running"
        PIPELINE_STATUS["step"] = "scraping"
        PIPELINE_STATUS["message"] = f"Scraping reviews for {product} over lookback window of {weeks_window} weeks..."
        PIPELINE_STATUS["error"] = None
        
        # Determine package name
        app_package = os.getenv("TARGET_APP_PACKAGE", "com.nextbillion.groww") if product == "groww" else "com.nextbillion.groww"
        
        loop = asyncio.get_running_loop()
        
        # 1. Scrape Play Store
        raw_reviews = await loop.run_in_executor(None, fetch_recent_reviews, app_package, weeks_window)
        
        PIPELINE_STATUS["message"] = "Cleaning and scrubbing reviews of private PII info..."
        normalized = await loop.run_in_executor(None, process_reviews, raw_reviews)
        
        save_json_file("raw_reviews.json", raw_reviews)
        save_json_file(REVIEWS_FILE, normalized)
        
        # 2. Run Embeddings & Clustering Summarization
        PIPELINE_STATUS["step"] = "clustering"
        PIPELINE_STATUS["message"] = "Generating local embeddings and clustering review themes..."
        await loop.run_in_executor(None, run_reasoning_engine)
        
        PIPELINE_STATUS["status"] = "idle"
        PIPELINE_STATUS["step"] = "done"
        PIPELINE_STATUS["message"] = "Analysis pipeline completed successfully! View results below."
    except Exception as e:
        PIPELINE_STATUS["status"] = "failed"
        PIPELINE_STATUS["step"] = ""
        PIPELINE_STATUS["error"] = str(e)
        PIPELINE_STATUS["message"] = f"Execution failed: {str(e)}"

@app.get("/api/status")
def get_status():
    return PIPELINE_STATUS

@app.get("/api/config")
def get_config():
    return {
        "google_doc_id": os.getenv("GOOGLE_DOC_ID", ""),
        "pulse_email_to": os.getenv("PULSE_EMAIL_TO", ""),
        "target_app_package": os.getenv("TARGET_APP_PACKAGE", "com.nextbillion.groww"),
        "review_window_weeks": int(os.getenv("REVIEW_WINDOW_WEEKS", 8))
    }

@app.post("/api/run")
def trigger_pipeline(req: RunRequest, background_tasks: BackgroundTasks):
    global PIPELINE_STATUS
    if PIPELINE_STATUS["status"] == "running":
        return {"status": "error", "message": "Pipeline is already running."}
        
    background_tasks.add_task(run_pipeline_task, req.product, req.weeks_window)
    return {"status": "started", "message": "Pipeline run started in the background."}

@app.get("/api/insights")
def get_insights():
    insights = load_json_file(INSIGHTS_FILE, [])
    reviews = load_json_file(REVIEWS_FILE, [])
    
    default_doc_body = ""
    default_email_body = ""
    default_email_subject = ""
    
    if insights:
        import datetime
        iso_year, iso_week, _ = datetime.datetime.now().isocalendar()
        run_id = f"Groww-{iso_year}-W{iso_week:02d}"
        
        doc_id = os.getenv("GOOGLE_DOC_ID")
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit" if doc_id else ""
        weeks_window = int(os.getenv("REVIEW_WINDOW_WEEKS", 8))
        period_str = f"Rolling {weeks_window}-Week Window"
        
        try:
            default_doc_body = format_doc_report(insights, len(reviews), period_str, run_id)
            default_email_body = format_email_teaser(insights, doc_url, run_id)
            default_email_subject = f"Groww Review Pulse teaser — {iso_year} W{iso_week:02d}"
        except Exception as e:
            print(f"[Backend API] Error formatting previews: {e}")
            
    return {
        "insights": insights,
        "total_reviews": len(reviews),
        "default_doc_body": default_doc_body,
        "default_email_body": default_email_body,
        "default_email_subject": default_email_subject
    }

@app.get("/api/history")
def get_history():
    return load_json_file(AUDIT_LOG_FILE, [])

# Scheduler Configuration & Helpers
SCHEDULER_CONFIG_FILE = "scheduler_config.json"

class SchedulerConfigRequest(BaseModel):
    enabled: bool
    day_of_week: int
    hour: int
    minute: int
    deliver_to_doc: bool
    deliver_to_email: bool
    weeks_window: int
    product: str

def load_scheduler_config() -> dict:
    default_config = {
        "enabled": True,
        "day_of_week": 0,  # Monday
        "hour": 9,
        "minute": 0,
        "deliver_to_doc": True,
        "deliver_to_email": True,
        "weeks_window": int(os.getenv("REVIEW_WINDOW_WEEKS", 8)),
        "product": "groww"
    }
    if os.path.exists(SCHEDULER_CONFIG_FILE):
        try:
            with open(SCHEDULER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                # Merge with default to handle missing keys
                for k, v in default_config.items():
                    if k not in loaded:
                        loaded[k] = v
                return loaded
        except Exception as e:
            print(f"[Scheduler] Error loading config, using defaults: {e}")
    return default_config

def save_scheduler_config(config: dict):
    try:
        with open(SCHEDULER_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"[Scheduler] Error saving config: {e}")

def calculate_next_run(config: dict) -> str:
    if not config.get("enabled", True):
        return "Disabled"
        
    import datetime
    now = datetime.datetime.now()
    target_day = config.get("day_of_week", 0) # 0 = Monday, 6 = Sunday
    target_hour = config.get("hour", 9)
    target_minute = config.get("minute", 0)
    
    current_day = now.weekday()
    days_ahead = target_day - current_day
    
    if days_ahead < 0:
        days_ahead += 7
    elif days_ahead == 0:
        target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        if now >= target_time:
            days_ahead = 7
            
    next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0) + datetime.timedelta(days=days_ahead)
    return next_run.isoformat()

def execute_delivery_pipeline(
    run_id: str,
    doc_body: Optional[str],
    email_body: Optional[str],
    email_subject: str,
    deliver_to_doc: bool,
    deliver_to_email: bool,
    doc_id: Optional[str] = None,
    to_emails: Optional[str] = None
) -> dict:
    # Resolve parameters
    doc_id = doc_id or os.getenv("GOOGLE_DOC_ID")
    to_emails = to_emails or os.getenv("PULSE_EMAIL_TO")
    hosted_mcp_url = os.getenv("HOSTED_MCP_URL", "https://mcp-server-r01m.onrender.com").rstrip('/')
    api_key = os.getenv("MCP_API_SECRET_KEY")
    
    doc_url = None
    draft_id = None
    
    if not deliver_to_doc and not deliver_to_email:
        raise Exception("At least one delivery channel (Docs or Email) must be enabled.")

    # 1. Append to Doc
    if deliver_to_doc:
        if not doc_id:
            raise Exception("Google Doc ID not configured.")
        
        doc_body_content = doc_body or email_body or ""
        if not doc_body_content:
            raise Exception("Document content (doc_body) cannot be empty.")
            
        doc_title = f"Groww Weekly Review Pulse — {run_id}"
        # Prepend title with line markers if not already present
        if doc_title not in doc_body_content:
            doc_content = f"\n\n{doc_title}\n" + "=" * len(doc_title) + f"\n{doc_body_content}\n"
        else:
            doc_content = f"\n\n{doc_body_content}\n"
            
        print(f"[Delivery Pipeline] Appending to Google Doc: {doc_id}...")
        doc_result = post_json_helper(f"{hosted_mcp_url}/append_to_doc", {
            "doc_id": doc_id,
            "content": doc_content
        }, api_key=api_key)
            
        if doc_result.get("status") == "error":
            raise Exception(doc_result.get("error", "Unknown doc append error"))
            
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    
    # 2. Create Gmail Draft
    if deliver_to_email:
        if not to_emails:
            raise Exception("Recipients not configured.")
        if not email_body:
            raise Exception("Email body (email_body) cannot be empty.")
            
        print(f"[Delivery Pipeline] Creating Gmail draft...")
        email_result = post_json_helper(f"{hosted_mcp_url}/create_email_draft", {
            "to": to_emails,
            "subject": email_subject,
            "body": email_body
        }, api_key=api_key)
            
        if email_result.get("status") == "error":
            raise Exception(email_result.get("error", "Unknown email draft error"))
            
        draft_id = email_result.get("draft_id", "")
        
    # 3. Log to history
    import datetime
    audit_logs = load_json_file(AUDIT_LOG_FILE, [])
    
    status_str = "completed"
    if deliver_to_doc and not deliver_to_email:
        status_str = "docs_only"
    elif deliver_to_email and not deliver_to_doc:
        status_str = "email_only"
        
    audit_entry = {
        "run_id": run_id,
        "timestamp": datetime.datetime.now().isoformat(),
        "status": status_str,
        "doc_id": doc_id if deliver_to_doc else None,
        "doc_url": doc_url,
        "email_message_id": draft_id,
        "recipients": to_emails if deliver_to_email else None
    }
    audit_logs.append(audit_entry)
    save_json_file(AUDIT_LOG_FILE, audit_logs)
    
    return {
        "doc_url": doc_url,
        "draft_id": draft_id
    }

async def run_automated_scheduled_task(product: str, weeks_window: int, run_id: str, deliver_to_doc: bool, deliver_to_email: bool):
    global PIPELINE_STATUS
    print(f"[Scheduler Task] Starting automated scheduled pipeline and delivery for run_id={run_id}...")
    try:
        PIPELINE_STATUS["status"] = "running"
        PIPELINE_STATUS["step"] = "scraping"
        PIPELINE_STATUS["message"] = f"[Scheduled] Scraping reviews for {product} over lookback window of {weeks_window} weeks..."
        PIPELINE_STATUS["error"] = None
        
        # Determine package name
        app_package = os.getenv("TARGET_APP_PACKAGE", "com.nextbillion.groww") if product == "groww" else "com.nextbillion.groww"
        
        loop = asyncio.get_running_loop()
        
        # 1. Scrape Play Store
        raw_reviews = await loop.run_in_executor(None, fetch_recent_reviews, app_package, weeks_window)
        
        PIPELINE_STATUS["message"] = "[Scheduled] Cleaning and scrubbing reviews of private PII info..."
        normalized = await loop.run_in_executor(None, process_reviews, raw_reviews)
        
        save_json_file("raw_reviews.json", raw_reviews)
        save_json_file(REVIEWS_FILE, normalized)
        
        # 2. Run Embeddings & Clustering Summarization
        PIPELINE_STATUS["step"] = "clustering"
        PIPELINE_STATUS["message"] = "[Scheduled] Generating local embeddings and clustering review themes..."
        await loop.run_in_executor(None, run_reasoning_engine)
        
        # 3. Deliver automatically
        PIPELINE_STATUS["step"] = "delivering"
        PIPELINE_STATUS["message"] = "[Scheduled] Preparing and delivering report to Google Workspace..."
        
        insights = load_json_file(INSIGHTS_FILE, [])
        if not insights:
            print("[Scheduler Task] Warning: No insights generated, skipping delivery.")
            PIPELINE_STATUS["status"] = "idle"
            PIPELINE_STATUS["step"] = "done"
            PIPELINE_STATUS["message"] = "Analysis finished but no themes/insights were found."
            return
            
        doc_id = os.getenv("GOOGLE_DOC_ID")
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit" if doc_id else ""
        period_str = f"Rolling {weeks_window}-Week Window"
        
        doc_body = format_doc_report(insights, len(normalized), period_str, run_id)
        email_body = format_email_teaser(insights, doc_url, run_id)
        email_subject = f"Groww Review Pulse teaser — {run_id.replace('Groww-', '')}"
        
        delivery_res = await loop.run_in_executor(
            None,
            lambda: execute_delivery_pipeline(
                run_id=run_id,
                doc_body=doc_body,
                email_body=email_body,
                email_subject=email_subject,
                deliver_to_doc=deliver_to_doc,
                deliver_to_email=deliver_to_email
            )
        )
        
        PIPELINE_STATUS["status"] = "idle"
        PIPELINE_STATUS["step"] = "done"
        PIPELINE_STATUS["message"] = f"Scheduled run {run_id} completed and delivered successfully!"
        print(f"[Scheduler Task] Completed successfully. Details: {delivery_res}")
        
    except Exception as e:
        PIPELINE_STATUS["status"] = "failed"
        PIPELINE_STATUS["step"] = ""
        PIPELINE_STATUS["error"] = str(e)
        PIPELINE_STATUS["message"] = f"Scheduled execution failed: {str(e)}"
        print(f"[Scheduler Task] Failed: {e}")
        
        # Record failure in audit log
        import datetime
        try:
            audit_logs = load_json_file(AUDIT_LOG_FILE, [])
            audit_logs.append({
                "run_id": run_id,
                "timestamp": datetime.datetime.now().isoformat(),
                "status": "failed",
                "error": str(e)
            })
            save_json_file(AUDIT_LOG_FILE, audit_logs)
        except Exception as le:
            print(f"[Scheduler Task] Error logging failure: {le}")

@app.post("/api/deliver")
def deliver_insights(req: DeliverRequest):
    try:
        res = execute_delivery_pipeline(
            run_id=req.run_id,
            doc_body=req.doc_body,
            email_body=req.email_body,
            email_subject=req.email_subject,
            deliver_to_doc=req.deliver_to_doc,
            deliver_to_email=req.deliver_to_email,
            doc_id=req.doc_id,
            to_emails=req.to_emails
        )
        return {
            "status": "success",
            "doc_url": res["doc_url"],
            "draft_id": res["draft_id"],
            "channels_delivered": {
                "docs": req.deliver_to_doc,
                "email": req.deliver_to_email
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/scheduler")
def get_scheduler():
    config = load_scheduler_config()
    next_run = calculate_next_run(config)
    
    # Get last scheduled run status from audit logs
    audit_logs = load_json_file(AUDIT_LOG_FILE, [])
    # Filter logs that are scheduled runs (run_id contains W[0-9]+ and not DRAFT)
    scheduled_runs = [
        entry for entry in audit_logs 
        if entry.get("run_id") and "-DRAFT" not in entry.get("run_id")
    ]
    
    last_run = None
    if scheduled_runs:
        last_run = scheduled_runs[-1]
        
    return {
        "config": config,
        "next_run": next_run,
        "last_run": last_run
    }

@app.post("/api/scheduler")
def update_scheduler(req: SchedulerConfigRequest):
    config = {
        "enabled": req.enabled,
        "day_of_week": req.day_of_week,
        "hour": req.hour,
        "minute": req.minute,
        "deliver_to_doc": req.deliver_to_doc,
        "deliver_to_email": req.deliver_to_email,
        "weeks_window": req.weeks_window,
        "product": req.product
    }
    save_scheduler_config(config)
    
    next_run = calculate_next_run(config)
    print(f"[Backend API] Scheduler configuration updated. Next run: {next_run}")
    
    return {
        "status": "success",
        "message": "Scheduler configuration updated.",
        "config": config,
        "next_run": next_run
    }

async def scheduler_loop():
    print("[Scheduler] Built-in Weekly Review Pulse scheduler started.")
    await asyncio.sleep(5)
    
    while True:
        try:
            config = load_scheduler_config()
            if not config.get("enabled", True):
                await asyncio.sleep(30)
                continue
                
            import datetime
            now = datetime.datetime.now()
            
            target_day = config.get("day_of_week", 0)
            target_hour = config.get("hour", 9)
            target_minute = config.get("minute", 0)
            
            if now.weekday() == target_day and now.hour == target_hour and now.minute == target_minute:
                # Resolve run_id
                iso_year, iso_week, _ = now.isocalendar()
                run_id = f"Groww-{iso_year}-W{iso_week:02d}"
                
                # Check audit log history
                audit_logs = load_json_file(AUDIT_LOG_FILE, [])
                has_run_this_week = any(
                    entry.get("run_id") == run_id and entry.get("status") in ["completed", "docs_only", "email_only"]
                    for entry in audit_logs
                )
                
                if not has_run_this_week:
                    global PIPELINE_STATUS
                    if PIPELINE_STATUS["status"] != "running":
                        print(f"[Scheduler] Triggering scheduled execution for run_id={run_id}")
                        weeks_window = config.get("weeks_window", 8)
                        product = config.get("product", "groww")
                        deliver_to_doc = config.get("deliver_to_doc", True)
                        deliver_to_email = config.get("deliver_to_email", True)
                        
                        asyncio.create_task(
                            run_automated_scheduled_task(
                                product=product,
                                weeks_window=weeks_window,
                                run_id=run_id,
                                deliver_to_doc=deliver_to_doc,
                                deliver_to_email=deliver_to_email
                            )
                        )
                        
                        # Sleep 65 seconds to prevent re-triggering within the same minute
                        await asyncio.sleep(65)
                        continue
        except Exception as e:
            print(f"[Scheduler] Error in scheduler loop: {e}")
            
        await asyncio.sleep(30)

@app.on_event("startup")
def on_startup():
    asyncio.create_task(scheduler_loop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)
