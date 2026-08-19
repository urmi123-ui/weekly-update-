# Weekly Product Review Pulse — Edge Cases and Corner Cases

This document outlines potential edge cases, failure modes, and corner cases for the Weekly Product Review Pulse system. Addressing these will ensure the pipeline remains robust, idempotent, and useful.

## 1. Data Ingestion & Scraping Edge Cases
* **Zero Reviews in the Window:** No new reviews were posted in the last 8-12 weeks (unlikely for Groww, but possible for strict date filters). The system should gracefully handle empty datasets without crashing, optionally skipping the Google Doc append or appending a "No significant reviews found for this period" message.
* **Scraper Rate Limiting & Blocking:** Google Play Store may throttle or block the scraper IP if volume is too high.
* **Unexpected HTML Changes:** The Play Store DOM structure changes, breaking the scraper. The system needs robust error handling and alerts when scraping yields zero data while expecting thousands.
* **Review Bombing (Massive Volume):** A sudden influx of thousands of reviews (e.g., due to an app outage). This could blow up token limits and memory usage during embedding/clustering.
* **Non-English and "Hinglish" Text:** Indian users frequently write reviews in Hinglish or regional languages using English scripts. The clustering and LLM models must be robust enough to handle or accurately translate these.

## 2. Data Processing & PII Scrubbing
* **Missed PII:** Users might include sensitive data in non-standard formats (e.g., "my UPI is name at bank", non-standard phone number spacing).
* **Aggressive PII Scrubbing (False Positives):** The scrubber might mistakenly remove crucial context (e.g., removing the number "500" thinking it's part of a phone number when the user is saying "I lost 500 rupees").
* **Extremely Long Reviews:** A user pastes an essay in a single review that exceeds the LLM context window or embedding token limit. The system needs truncation strategies.

## 3. Reasoning Engine (Clustering & LLM)
* **Clustering Failures (Too Dense / Too Sparse):** 
  * *Too Dense:* All reviews are clustered into a single massive group (e.g., everything is just labeled "App issues").
  * *Too Sparse:* HDBSCAN marks 90% of reviews as "noise" (outliers), resulting in no meaningful themes being generated.
* **LLM Hallucinations on Quotes:** The LLM hallucinates a quote that sounds realistic but does not exist in the source text. (Requires strict programmatic string-matching validation after LLM generation).
* **LLM Output Formatting:** The LLM fails to return the requested structured format (e.g., broken JSON or incorrect markdown), causing the rendering step to crash. 

## 4. Custom MCP Server & Google Workspace Integration
* **Partial Failures:** The system successfully appends the report to the Google Doc, but the Gmail API fails (e.g., network timeout). On a retry, the system must recognize the Doc was already updated (via idempotency anchors) and *only* attempt to send the email.
* **Missing or Deleted Google Doc:** The target "system of record" Google Doc is accidentally deleted by a stakeholder, or the Service Account loses edit access.
* **Google Doc Size Limits:** Over a long period, appending weekly reports might hit Google Docs size or character limits.
* **Credential Expiry:** The OAuth tokens or Service Account keys used by the custom MCP server expire or are rotated, causing sudden authentication errors.

## 5. Orchestration & Scheduling
* **Timezone & ISO Week Boundary Issues:** Discrepancies between the server's timezone (e.g., UTC) and the expected schedule (IST). A job running at Sunday 11:30 PM UTC vs Monday 5:00 AM IST might calculate different ISO week numbers.
* **Concurrent Executions:** A manual CLI backfill is triggered at the exact same time the weekly cron job starts, potentially causing race conditions when appending to the Google Doc.
* **Cost Overruns:** A bug causes the pipeline to loop infinitely or process historical data repeatedly, incurring massive LLM API costs. (Requires hard limits/budgets per run).
