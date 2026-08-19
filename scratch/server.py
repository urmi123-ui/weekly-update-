import os
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from auth import get_credentials
from docs_tool import append_to_doc
from gmail_tool import create_email_draft

app = FastAPI(title="Google MCP Server")

class DocAppendRequest(BaseModel):
    doc_id: str
    content: str

class EmailDraftRequest(BaseModel):
    to: str
    subject: str
    body: str

async def request_approval(action_name: str, payload: dict) -> bool:
    """Prompt the user for approval in the terminal."""
    if os.environ.get("REQUIRE_APPROVAL", "true").lower() == "false" or \
       os.environ.get("ENVIRONMENT", "development").lower() == "production":
        return True
        
    print(f"\n--- ACTION REQUIRED ---")
    print(f"Action: {action_name}")
    print(f"Payload: {payload}")

    
    def _get_input():
        return input("Approve? (y/n): ").strip().lower()
        
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(None, _get_input)
    
    return response == 'y'

@app.post("/append_to_doc")
async def api_append_to_doc(req: DocAppendRequest):
    approved = await request_approval("append_to_doc", req.model_dump())
    if not approved:
        raise HTTPException(status_code=403, detail="Action rejected by user.")
    
    try:
        creds = get_credentials()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")
        
    result = append_to_doc(creds, req.doc_id, req.content)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))
        
    return result

@app.post("/create_email_draft")
async def api_create_email_draft(req: EmailDraftRequest):
    approved = await request_approval("create_email_draft", req.model_dump())
    if not approved:
        raise HTTPException(status_code=403, detail="Action rejected by user.")
        
    try:
        creds = get_credentials()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")
        
    result = create_email_draft(creds, req.to, req.subject, req.body)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))
        
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
