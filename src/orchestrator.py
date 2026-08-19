import os
import sys
import json
import argparse
import subprocess
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

AUDIT_LOG_FILE = "audit_log.json"

def load_audit_log() -> list:
    if os.path.exists(AUDIT_LOG_FILE):
        try:
            with open(AUDIT_LOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Orchestrator] Failed to read audit log, starting fresh: {e}")
    return []

def save_audit_log(log_data: list):
    try:
        with open(AUDIT_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=4)
    except Exception as e:
        print(f"[Orchestrator] Failed to write audit log: {e}")

def get_run_status(run_id: str, logs: list) -> dict:
    for entry in logs:
        if entry.get("run_id") == run_id:
            return entry
    return None

def format_doc_report(insights: list, total_reviews: int, period_str: str, run_id: str) -> str:
    """Formats the insights list into structured plain-text for Google Docs."""
    lines = []
    lines.append(f"Period: {period_str}")
    lines.append(f"Run ID: {run_id}")
    lines.append(f"Total Reviews Analyzed: {total_reviews}")
    lines.append("-" * 40)
    
    # 1. Top Themes
    lines.append("\nTOP THEMES")
    lines.append("=" * 10)
    for ins in insights:
        lines.append(f"- {ins['theme']} ({ins['review_count']} reviews)")
        lines.append(f"  Idea: {ins['actionable_idea']}")
        
    # 2. Verbatim Quotes
    lines.append("\nREAL USER QUOTES")
    lines.append("=" * 16)
    for ins in insights:
        quotes = ins.get('quotes', [])
        if quotes:
            lines.append(f"\n[Theme: {ins['theme']}]")
            for q in quotes:
                lines.append(f"- \"{q}\"")
                
    # 3. Action Ideas
    lines.append("\nACTIONABLE IDEAS FOR TEAMS")
    lines.append("=" * 26)
    for ins in insights:
        lines.append(f"* {ins['theme']}: {ins['actionable_idea']}")
        
    # 4. Audience Segment
    lines.append("\nWHO THIS HELPS")
    lines.append("=" * 14)
    lines.append("- Product Managers: Prioritize core features and track regressions.")
    lines.append("- Customer Support: Identify repeating support SLAs and ticket sources.")
    lines.append("- Engineering: Address app crashes and performance bottlenecks.")
    
    return "\n".join(lines)

def format_email_teaser(insights: list, doc_url: str, run_id: str) -> str:
    """Formats the teaser email content with a deep link to the doc section."""
    lines = []
    lines.append("Hi Team,\n")
    lines.append(f"Here is the Weekly Product Review Pulse teaser report for Groww ({run_id}).\n")
    lines.append("Top Customer Themes & Actions:")
    
    for ins in insights[:4]:  # Show top 4 themes
        lines.append(f"- {ins['theme']} ({ins['review_count']} reviews)")
        lines.append(f"  Suggested Action: {ins['actionable_idea']}")
        
    lines.append("\nYou can read the full report including real user quotes and details directly in Google Docs:")
    lines.append(doc_url)
    lines.append("\nBest regards,")
    lines.append("Product Pulse Bot")
    
    return "\n".join(lines)

def post_json(url: str, payload: dict) -> dict:
    import urllib.request
    import urllib.error
    import json
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
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

async def run_mcp_delivery(run_id: str, doc_id: str, stakeholder_emails: str, doc_title: str, doc_body: str, email_subject: str, insights: list, draft_only: bool = False):
    """
    Sends the reports to the hosted MCP HTTP server.
    Appends report to Google Doc and creates a draft teaser in Gmail.
    """
    import asyncio
    mcp_url = os.getenv("HOSTED_MCP_URL", "https://mcp-server-r01m.onrender.com").rstrip('/')
    
    # Prepend the section title with text dividers as plain-text heading formatting
    doc_content = f"\n\n{doc_title}\n" + "=" * len(doc_title) + f"\n{doc_body}\n"
    
    def call_append():
        return post_json(f"{mcp_url}/append_to_doc", {
            "doc_id": doc_id,
            "content": doc_content
        })
        
    print(f"[Orchestrator] Appending section to Google Doc via hosted server: {mcp_url}...")
    loop = asyncio.get_running_loop()
    doc_status = await loop.run_in_executor(None, call_append)
    print(f"[Orchestrator] Doc Append Result: {doc_status.get('status')}")
    
    if doc_status.get("status") == "error":
        raise Exception(doc_status.get("error"))
        
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"[Orchestrator] Document Link: {doc_url}")
    
    # 2. Format email teaser
    email_body = format_email_teaser(insights, doc_url, run_id)
    
    # 3. Call create_email_draft
    def call_draft():
        return post_json(f"{mcp_url}/create_email_draft", {
            "to": stakeholder_emails,
            "subject": email_subject,
            "body": email_body
        })
        
    print(f"[Orchestrator] Creating teaser email draft in Gmail via hosted server...")
    email_status = await loop.run_in_executor(None, call_draft)
    print(f"[Orchestrator] Gmail Draft Result: {email_status.get('status')}")
    
    if email_status.get("status") == "error":
        raise Exception(email_status.get("error"))
        
    return {
        "doc_status": doc_status.get("status"),
        "doc_heading_id": "",
        "email_status": email_status.get("status"),
        "email_message_id": email_status.get("draft_id", ""),
        "doc_url": doc_url
    }

async def main():
    parser = argparse.ArgumentParser(description="Weekly Product Review Pulse Orchestrator")
    parser.add_argument("--week", type=int, help="ISO week override (e.g. 33)")
    parser.add_argument("--year", type=int, help="ISO year override (e.g. 2026)")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip Play Store scraper and use local cache")
    parser.add_argument("--skip-reasoning", action="store_true", help="Skip reasoning engine and use local insights.json cache")
    parser.add_argument("--product", type=str, default="groww", help="Target product (default: groww)")
    parser.add_argument("--draft", action="store_true", help="Enable staging mode: create a Gmail draft instead of sending")
    args = parser.parse_args()
    
    # Validate product
    product_lower = args.product.lower()
    if product_lower != "groww":
        print(f"[Orchestrator] Error: Product '{args.product}' is not supported. Supported products: groww")
        sys.exit(1)
        
    # Map product to app package name
    app_package = "com.nextbillion.groww"
    
    # 1. Resolve ISO week and year
    if args.week and args.year:
        iso_week = args.week
        iso_year = args.year
    else:
        iso_year, iso_week, _ = datetime.now().isocalendar()
        
    run_id = f"Groww-{iso_year}-W{iso_week:02d}"
    if args.draft:
        run_id += "-DRAFT"
        
    print(f"[Orchestrator] Initiating Run ID: {run_id} (Staging Mode = {args.draft})")
    
    # 2. Idempotency Check
    audit_logs = load_audit_log()
    existing_status = get_run_status(run_id, audit_logs)
    if existing_status and existing_status.get("status") == "completed":
        print(f"[Orchestrator] Skipped: Run {run_id} has already completed successfully.")
        print(f"Details: Doc Heading ID={existing_status.get('doc_heading_id')}, Message ID={existing_status.get('email_message_id')}")
        sys.exit(0)
        
    # 3. Load config values
    doc_id = os.getenv("GOOGLE_DOC_ID")
    stakeholder_emails = os.getenv("PULSE_EMAIL_TO")
    app_package = os.getenv("TARGET_APP_PACKAGE", "com.nextbillion.groww")
    weeks_window = int(os.getenv("REVIEW_WINDOW_WEEKS", 8))
    
    if not doc_id or doc_id == "your_google_doc_id_here":
        print("[Orchestrator] Error: GOOGLE_DOC_ID is not configured in .env file.")
        sys.exit(1)
    if not stakeholder_emails or stakeholder_emails == "stakeholder1@example.com,stakeholder2@example.com":
        print("[Orchestrator] Error: PULSE_EMAIL_TO is not configured in .env file.")
        sys.exit(1)
        
    # 4. Scrape & Normalize (Phase 1)
    if not args.skip_scrape:
        print(f"[Orchestrator] Scraping {weeks_window} weeks of reviews for {app_package}...")
        # Import local modules inline
        sys.path.append(os.path.abspath('src'))
        from scraper import fetch_recent_reviews
        from processing import process_reviews
        
        raw_reviews = fetch_recent_reviews(app_package, weeks=weeks_window)
        print(f"[Orchestrator] Scraped {len(raw_reviews)} raw reviews.")
        
        # Save raw to raw_reviews.json
        with open("raw_reviews.json", 'w', encoding='utf-8') as f:
            json.dump(raw_reviews, f, indent=4, default=str)
            
        # Normalize reviews
        normalized = process_reviews(raw_reviews)
        print(f"[Orchestrator] Normalized down to {len(normalized)} reviews.")
        with open("reviews.json", 'w', encoding='utf-8') as f:
            json.dump(normalized, f, indent=4, default=str)
    else:
        print("[Orchestrator] Skipping scraper. Using local cache reviews.json.")
        if not os.path.exists("reviews.json"):
            print("[Orchestrator] Error: reviews.json cache not found. Remove --skip-scrape.")
            sys.exit(1)
            
    # Load normalized reviews to get total count
    with open("reviews.json", 'r', encoding='utf-8') as f:
        reviews_data = json.load(f)
    total_reviews = len(reviews_data)
    
    # 5. Reasoning Engine (Phase 2)
    # We trigger run_reasoning_engine from reasoning.py
    if not args.skip_reasoning:
        print("[Orchestrator] Running Reasoning Engine (Embedding, Clustering, Groq Summarization)...")
        from reasoning import run_reasoning_engine
        run_reasoning_engine()
    else:
        print("[Orchestrator] Skipping reasoning engine. Using local cache insights.json.")
    
    # Load reasoning output
    if not os.path.exists("insights.json"):
        print("[Orchestrator] Error: insights.json could not be generated.")
        sys.exit(1)
    with open("insights.json", 'r', encoding='utf-8') as f:
        insights = json.load(f)
        
    if not insights:
        print("[Orchestrator] No insights generated (empty dataset or zero clusters).")
        sys.exit(0)
        
    # 6. Format Report
    period_str = f"Rolling {weeks_window}-Week Window"
    section_title = f"Groww Weekly Review Pulse — {iso_year} Week {iso_week:02d}"
    doc_body = format_doc_report(insights, total_reviews, period_str, run_id)
    email_subject = f"Groww Review Pulse teaser — {iso_year} W{iso_week:02d}"
    
    # 7. Delivery via MCP Server
    delivery_info = None
    try:
        delivery_info = await run_mcp_delivery(
            run_id=run_id,
            doc_id=doc_id,
            stakeholder_emails=stakeholder_emails,
            doc_title=section_title,
            doc_body=doc_body,
            email_subject=email_subject,
            insights=insights
        )
    except Exception as e:
        print(f"[Orchestrator] Delivery pipeline failed: {e}")
        # Log failure to audit log
        audit_logs.append({
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "status": "failed",
            "error": str(e),
            "total_reviews": total_reviews
        })
        save_audit_log(audit_logs)
        sys.exit(1)
        
    # 8. Log Success
    audit_entry = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "status": "completed",
        "doc_id": doc_id,
        "doc_heading_id": delivery_info["doc_heading_id"],
        "doc_url": delivery_info["doc_url"],
        "email_message_id": delivery_info["email_message_id"],
        "total_reviews": total_reviews
    }
    audit_logs.append(audit_entry)
    save_audit_log(audit_logs)
    print(f"[Orchestrator] Success! Run {run_id} has been fully completed and logged.")

if __name__ == "__main__":
    # Change directory to script's parent if needed or ensure PYTHONPATH includes src
    sys.path.append(os.path.abspath('src'))
    asyncio.run(main())
