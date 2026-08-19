import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from dotenv import load_dotenv

# Load env variables
load_dotenv()

AUDIT_LOG_FILE = "audit_log.json"

def load_audit_log() -> list:
    if os.path.exists(AUDIT_LOG_FILE):
        try:
            with open(AUDIT_LOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_audit_log(log_data: list):
    try:
        with open(AUDIT_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=4)
    except Exception as e:
        print(f"[Pulse] Warning: Failed to write audit log: {e}")

def post_json(url: str, payload: dict, api_key: str = None) -> dict:
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

def handle_deliver_email(args):
    # 1. Load and parse the teaser file
    if not os.path.exists(args.email_teaser_file):
        print(f"[Pulse] Error: Teaser file not found at: {args.email_teaser_file}")
        sys.exit(1)
        
    try:
        with open(args.email_teaser_file, 'r', encoding='utf-8') as f:
            teaser_data = json.load(f)
    except Exception as e:
        print(f"[Pulse] Error: Failed to parse teaser JSON: {e}")
        sys.exit(1)
        
    subject = teaser_data.get("subject", "Weekly Product Review Pulse Teaser")
    text_body = teaser_data.get("text_body", "")
    
    if not text_body:
        # Fallback if field name differs
        text_body = teaser_data.get("body", "")
        
    # 2. Resolve parameters
    to_emails = args.to or os.getenv("PULSE_EMAIL_TO")
    doc_id = args.doc_id or os.getenv("GOOGLE_DOC_ID")
    email_mode = args.email_mode or os.getenv("PULSE_EMAIL_MODE", "draft")
    hosted_mcp_url = os.getenv("HOSTED_MCP_URL", "https://mcp-server-r01m.onrender.com").rstrip('/')
    api_key = os.getenv("MCP_API_SECRET_KEY")
    
    if not to_emails:
        print("[Pulse] Error: Recipients not specified. Configure PULSE_EMAIL_TO in .env or use --to option.")
        sys.exit(1)
    if not doc_id:
        print("[Pulse] Error: Google Doc ID not specified. Configure GOOGLE_DOC_ID in .env or use --doc-id option.")
        sys.exit(1)
        
    doc_url = args.doc_url or f"https://docs.google.com/document/d/{doc_id}/edit"
    
    # 3. Construct idempotency key (e.g. groww-2026-W23-email)
    parent_dir = os.path.basename(os.path.dirname(args.email_teaser_file)) or "run"
    idempotency_key = f"{parent_dir}-email"
    
    # 4. Check idempotency
    audit_logs = load_audit_log()
    for entry in audit_logs:
        if entry.get("idempotency_key") == idempotency_key and entry.get("status") == "completed":
            print(f"[Pulse] Skipped: Delivery for {idempotency_key} has already completed successfully.")
            sys.exit(0)
            
    # 5. Inject document URL into the email body
    full_body = f"{text_body}\n\nYou can read the full report directly in Google Docs:\n{doc_url}"
    
    # 6. Execute Dry-Run or Live
    if args.dry_run:
        print("\n# Dry-run")
        print(f"Would deliver email teaser to: {to_emails}")
        print(f"Delivery Mode: {email_mode}")
        print(f"Subject: {subject}")
        print("Body Content:")
        print("-" * 40)
        print(full_body)
        print("-" * 40)
        print("[Pulse] Dry-run completed successfully.")
        return
        
    # Check if send mode is requested but not supported
    if email_mode == "send":
        print("[Pulse] Warning: direct 'send' is not supported on the hosted server. Falling back to 'draft' mode.")
        email_mode = "draft"
        
    print(f"[Pulse] Connecting to hosted server: {hosted_mcp_url}...")
    try:
        result = post_json(f"{hosted_mcp_url}/create_email_draft", {
            "to": to_emails,
            "subject": subject,
            "body": full_body
        }, api_key=api_key)
        
        print(f"[Pulse] Gmail Draft Result: {result.get('status')}")
        if result.get("status") == "success":
            draft_id = result.get("draft_id", "")
            print(f"[Pulse] Success! Created Gmail Draft ID: {draft_id}")
            
            # Log success
            audit_logs.append({
                "idempotency_key": idempotency_key,
                "status": "completed",
                "draft_id": draft_id,
                "recipients": to_emails
            })
            save_audit_log(audit_logs)
        else:
            raise Exception(result.get("error", "Unknown server error"))
            
    except Exception as e:
        print(f"[Pulse] Error: Delivery pipeline failed: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Pulse Google Workspace CLI utility")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Subcommand: deliver-email
    deliver_parser = subparsers.add_parser("deliver-email", help="Deliver teaser report email")
    deliver_parser.add_argument("--email-teaser-file", type=str, required=True, help="Path to email teaser JSON file")
    deliver_parser.add_argument("--to", type=str, help="Recipient emails (comma separated)")
    deliver_parser.add_argument("--doc-id", type=str, help="Google Doc ID")
    deliver_parser.add_argument("--doc-url", type=str, help="Google Doc URL")
    deliver_parser.add_argument("--email-mode", type=str, choices=["draft", "send"], help="Email delivery mode")
    deliver_parser.add_argument("--dry-run", action="store_true", help="Perform dry-run without contacting the server")
    deliver_parser.add_argument("--report-file", type=str, help="Path to report file")
    deliver_parser.add_argument("--json", action="store_true", help="Output logs in JSON")
    
    args = parser.parse_args()
    
    if args.command == "deliver-email":
        handle_deliver_email(args)

if __name__ == "__main__":
    main()
