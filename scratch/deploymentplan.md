# Railway Deployment Plan

To deploy this MCP server on Railway, we need to handle a few differences between a local environment and a cloud environment. 

## 1. Environment Variables for Secrets
Railway uses environment variables to store secrets. You should **never** commit `credentials.json` or `token.json` to GitHub.

Instead, we will load these from environment variables.
- Convert your `credentials.json` and `token.json` into Base64 strings.
- Add them to your Railway project settings as `GOOGLE_CREDENTIALS_B64` and `GOOGLE_TOKEN_B64`.
- The `auth.py` script will be modified to decode these and use them in memory instead of reading from disk.

## 2. Disable Terminal Prompts
Railway is a headless environment, meaning it has no interactive terminal.
- The `Approve? (y/n)` prompt in `server.py` will cause the server to hang forever waiting for input.
- We will add an environment variable check (e.g., `REQUIRE_APPROVAL=false` or `ENVIRONMENT=production`). 
- When deployed, the server will skip the manual approval step and execute requests immediately.

## 3. Specify the Start Command
We need to tell Railway how to start the FastAPI server.
- Create a `Procfile` in the project root with the following content:
  ```
  web: uvicorn server:app --host 0.0.0.0 --port $PORT
  ```
- Railway will automatically detect this and start the server correctly, binding it to the dynamic `$PORT` it assigns.

## 4. Next Steps
If you want to proceed with this deployment plan, let me know, and I will:
1. Update `auth.py` to support loading credentials from environment variables.
2. Update `server.py` to conditionally skip the approval prompt.
3. Add the `Procfile` to the project root.
4. Provide you with a quick script or command to convert your JSON files into Base64 strings so you can paste them into the Railway dashboard.
