# Weekly Product Review Pulse — Implementation Plan

This document breaks down the development of the Weekly Product Review Pulse system for Groww into logical phases.

## Phase 1: Setup & Data Ingestion
**Goal:** Successfully fetch and prepare raw review data from the Google Play Store.

1. **Project Scaffolding:** Set up the repository, environment variables, and dependencies (scraper, data processing, embeddings, etc.).
2. **Play Store Scraper:**
   - Implement scraping logic targeted at the Groww app on the Google Play Store.
   - Implement date filtering to support the rolling 8-12 week window.
3. **Data Processing & Safety:**
   - Sanitize raw text to remove formatting anomalies.
   - Implement Quality Gating: strictly filter out reviews with fewer than 8 words, containing emojis, or written in non-English languages to ensure dense, high-quality data for clustering.
   - Implement PII (Personally Identifiable Information) scrubbing using heuristics or NLP to ensure privacy before the data is sent to the LLM.

## Phase 2: Reasoning Engine (Clustering & LLM)
**Goal:** Convert raw, scrubbed text into clustered themes and actionable insights.

1. **Embeddings Generation (Local):**
   - Use the `BAAI/bge-small-en-v1.5` model (via the `sentence-transformers` library) to generate vector embeddings entirely locally, rather than relying on OpenAI's embedding API.
2. **Clustering (UMAP + HDBSCAN):**
   - Implement dimensionality reduction and density-based clustering to group semantically similar reviews into overarching topics.
3. **LLM Summarization & Extraction (Groq):**
   - Use the Groq API with the `llama-3.3-70b-versatile` model.
   - **Rate Limiting & Constraints:** The model has the following Groq limits:
     * Request per minute (RPM): 30
     * Requests per day (RPD): 1K
     * Tokens per minute (TPM): 12K
     * Tokens per day (TPD): 100K
     * We must implement token-aware chunking and throttling/delays between API calls to avoid hitting the 12K tokens-per-minute limit.
   - Write prompts to extract themes, verbatim quotes, and actionable ideas from each cluster.
   - Instruct the LLM to handle multi-topic reviews by extracting only the specific sentence/fragment that applies to the cluster theme, rather than assuming the entire review is about one theme.
   - Implement strict validation logic to ensure extracted quotes exist word-for-word in the original reviews.

## Phase 3: Custom Workspace MCP Server Integration
**Goal:** Integrate the already created and hosted Google Workspace MCP server.

1. **MCP Server Connection Setup:** Instead of running a local server process, update the client inside the orchestrator to connect to the hosted MCP server at `https://mcp-server-r01m.onrender.com` using SSE (Server-Sent Events) client transport.
2. **Authentication Configuration:** Ensure the hosted server is configured with the correct Google Service Account or OAuth credentials.
3. **Google Docs Integration Verification:**
   - Verify the `append_google_doc_section` tool successfully appends reports to Google Docs as plain text.
   - Verify logic to manage stable section anchors to ensure idempotency (preventing duplicate appends) works with the hosted API.
4. **Gmail Integration Verification:**
   - Verify the `send_gmail_teaser` tool successfully drafts and sends emails containing a teaser and a deep link to the Google Doc section.
   - Verify run-scoped identifiers guarantee idempotency on email sends.

## Phase 4: Output Rendering & Orchestration
**Goal:** Format the insights and connect the entire pipeline from end to end.

1. **Report Renderers:**
   - Create a Document Renderer to format LLM outputs into a structured plain-text layout (using plain-text headers and dividers, since rich formatting is not supported by the MCP server).
   - Create an Email Renderer to construct the short teaser and doc hyperlink.
2. **Agent / Orchestrator:**
   - Build the main execution flow: Scrape -> Scrub -> Cluster -> LLM -> Render -> MCP Server Calls.
3. **Auditing & Logging:**
   - Implement detailed logging of the execution run (timestamps, ISO week, token usage, Doc heading IDs, Gmail message IDs).

## Phase 5: Deployment, CLI & Scheduling
**Goal:** Automate the pipeline and provide tools for manual operations.

1. **CLI Interface:** Develop a command-line tool to allow operators to trigger runs for a specific product (Groww) and specific historical ISO weeks (backfilling).
2. **Weekly Scheduling (Built-in Background Scheduler):**
   - Implement an automated async background task loop inside the FastAPI backend application.
   - The scheduler runs as a daemon task, checking the time and current ISO week.
   - Every Monday morning (e.g., at 9:00 AM), it automatically triggers the scrape, processing, clustering, and delivery pipeline for the current ISO week without requiring manual operator intervention.
   - Uses the run-scoped audit log for idempotency to ensure it only runs once per week.
3. **Staging / Testing:** Run the system in "draft-only" mode where emails are drafted but not sent, allowing for stakeholder review before moving to fully automated sends.
