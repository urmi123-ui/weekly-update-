import { useState, useEffect } from 'react';
import './App.css';

interface Insight {
  theme: string;
  quotes: string[];
  actionable_idea: string;
  cluster_id: number;
  review_count: number;
}

interface HistoryEntry {
  run_id: string;
  timestamp: string;
  status: string;
  doc_id: string;
  doc_url: string;
  email_message_id: string;
  recipients: string;
  idempotency_key?: string;
}

interface PipelineStatus {
  status: 'idle' | 'running' | 'failed';
  step: string;
  message: string;
  error: string | null;
}

const BACKEND_URL = 'http://127.0.0.1:5000';

function App() {
  const [product, setProduct] = useState('groww');
  const [weeksWindow, setWeeksWindow] = useState(8);
  const [docId, setDocId] = useState('');
  const [toEmails, setToEmails] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');

  const [insights, setInsights] = useState<Insight[]>([]);
  const [totalReviews, setTotalReviews] = useState(0);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [status, setStatus] = useState<PipelineStatus>({
    status: 'idle',
    step: '',
    message: 'Ready.',
    error: null,
  });

  const [delivering, setDelivering] = useState(false);
  const [deliveryResult, setDeliveryResult] = useState<{ doc_url?: string; draft_id?: string } | null>(null);
  const [deliveryError, setDeliveryError] = useState<string | null>(null);

  const [deliverToDoc, setDeliverToDoc] = useState(true);
  const [deliverToEmail, setDeliverToEmail] = useState(true);
  const [docBody, setDocBody] = useState('');
  const [activeTab, setActiveTab] = useState<'doc' | 'email'>('doc');

  // Load baseline files and config
  useEffect(() => {
    fetchConfig();
    fetchInsights();
    fetchHistory();
    checkStatus();
  }, []);

  const fetchConfig = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/config`);
      const data = await res.json();
      if (data.google_doc_id) setDocId(data.google_doc_id);
      if (data.pulse_email_to) setToEmails(data.pulse_email_to);
      if (data.review_window_weeks) setWeeksWindow(data.review_window_weeks);
    } catch (err) {
      console.error('Error fetching config:', err);
    }
  };

  // Poll status when running
  useEffect(() => {
    let intervalId: any;
    if (status.status === 'running') {
      intervalId = setInterval(() => {
        checkStatus();
      }, 2000);
    }
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [status.status]);

  const checkStatus = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/status`);
      const data = await res.json();
      setStatus(data);
      if (data.status === 'idle' && data.step === 'done') {
        fetchInsights();
        fetchHistory();
      }
    } catch (err) {
      console.error('Error fetching pipeline status:', err);
    }
  };

  const fetchInsights = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/insights`);
      const data = await res.json();
      setInsights(data.insights || []);
      setTotalReviews(data.total_reviews || 0);

      // Generate default subject and body
      if (data.default_email_subject) {
        setSubject(data.default_email_subject);
      } else {
        const isoYear = new Date().getFullYear();
        const isoWeek = getWeekNumber(new Date());
        setSubject(`Groww Review Pulse teaser — ${isoYear} W${String(isoWeek).padStart(2, '0')}`);
      }

      if (data.default_doc_body) {
        setDocBody(data.default_doc_body);
      } else {
        setDocBody('');
      }
      
      if (data.default_email_body) {
        setBody(data.default_email_body);
      } else {
        if (data.insights && data.insights.length > 0) {
          let draftBody = `Hi Team,\n\nHere is the Weekly Product Review Pulse teaser report for Groww.\n\nTop Customer Themes & Actions:\n`;
          data.insights.slice(0, 4).forEach((ins: Insight) => {
            draftBody += `- ${ins.theme} (${ins.review_count} reviews)\n  Suggested Action: ${ins.actionable_idea}\n`;
          });
          draftBody += `\nBest regards,\nProduct Pulse Bot`;
          setBody(draftBody);
        } else {
          setBody(
            `Hi Team,\n\nHere is the Weekly Product Review Pulse teaser report for Groww.\n\nTop Customer Themes & Actions:\n- [Theme 1] (X reviews)\n  Suggested Action: [Action 1]\n- [Theme 2] (Y reviews)\n  Suggested Action: [Action 2]\n\nBest regards,\nProduct Pulse Bot`
          );
        }
      }
    } catch (err) {
      console.error('Error fetching insights:', err);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/history`);
      const data = await res.json();
      setHistory(data.reverse()); // Show newest first
    } catch (err) {
      console.error('Error fetching history:', err);
    }
  };

  const runPipeline = async () => {
    try {
      setDeliveryResult(null);
      setDeliveryError(null);
      const res = await fetch(`${BACKEND_URL}/api/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product, weeks_window: weeksWindow }),
      });
      const data = await res.json();
      if (data.status === 'started') {
        setStatus({
          status: 'running',
          step: 'scraping',
          message: 'Pipeline run initiated. Scraping reviews...',
          error: null,
        });
      }
    } catch (err) {
      console.error('Error starting pipeline:', err);
    }
  };

  const deliverReport = async () => {
    if (!deliverToDoc && !deliverToEmail) {
      setDeliveryError('At least one delivery channel (Google Docs or Gmail) must be enabled.');
      return;
    }

    setDelivering(true);
    setDeliveryResult(null);
    setDeliveryError(null);
    
    const isoYear = new Date().getFullYear();
    const isoWeek = getWeekNumber(new Date());
    const runId = `Groww-${isoYear}-W${String(isoWeek).padStart(2, '0')}`;

    try {
      const res = await fetch(`${BACKEND_URL}/api/deliver`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_id: deliverToDoc ? (docId || undefined) : undefined,
          to_emails: deliverToEmail ? (toEmails || undefined) : undefined,
          email_subject: subject,
          email_body: body,
          doc_body: docBody,
          run_id: runId,
          deliver_to_doc: deliverToDoc,
          deliver_to_email: deliverToEmail
        }),
      });
      
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to deliver report.');
      }
      
      setDeliveryResult(data);
      fetchHistory();
    } catch (err: any) {
      setDeliveryError(err.message || 'Delivery error.');
    } finally {
      setDelivering(false);
    }
  };

  const getWeekNumber = (d: Date) => {
    d = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
    var yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    var weekNo = Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
    return weekNo;
  };

  return (
    <div className="dashboard-container">
      <header className="header">
        <div>
          <h1>Weekly Review Pulse</h1>
          <p>Scrape, analyze, cluster and deliver Play Store feedback automatically.</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>Status:</span>
          <span className={`status-badge status-${status.status}`}>
            {status.status}
          </span>
        </div>
      </header>

      <div className="grid-layout">
        {/* Left column: controls and history */}
        <aside className="sidebar">
          {/* Controls Panel */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h2 className="panel-title">Pipeline Control</h2>
            
            <div className="form-group">
              <label>Target Product</label>
              <select 
                className="form-input" 
                value={product} 
                onChange={(e) => setProduct(e.target.value)}
                disabled={status.status === 'running'}
              >
                <option value="groww">Groww (Play Store)</option>
              </select>
            </div>

            <div className="form-group">
              <label>Lookback Window (Weeks)</label>
              <input 
                type="number" 
                className="form-input"
                min="1"
                max="24"
                value={weeksWindow}
                onChange={(e) => setWeeksWindow(parseInt(e.target.value) || 8)}
                disabled={status.status === 'running'}
              />
            </div>

            <button 
              className="btn-primary" 
              onClick={runPipeline}
              disabled={status.status === 'running'}
            >
              {status.status === 'running' ? (
                <>
                  <div className="spinner"></div>
                  Processing...
                </>
              ) : 'Analyze App Reviews'}
            </button>

            {status.message && (
              <div style={{ marginTop: '1.25rem', fontSize: '0.85rem', color: status.status === 'failed' ? '#ef4444' : '#a78bfa' }}>
                <p style={{ margin: 0 }}><strong>Step:</strong> {status.step || 'Idle'}</p>
                <p style={{ margin: '0.25rem 0 0 0', color: '#cbd5e1' }}>{status.message}</p>
              </div>
            )}
          </div>

          {/* Delivery Configuration */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h2 className="panel-title">Delivery Parameters</h2>
            
            <div className="form-group-checkbox">
              <label className="checkbox-container">
                <input 
                  type="checkbox" 
                  checked={deliverToDoc}
                  onChange={(e) => setDeliverToDoc(e.target.checked)}
                />
                <span>Deliver to Google Docs</span>
              </label>
            </div>

            <div className="form-group" style={{ opacity: deliverToDoc ? 1 : 0.5, transition: 'opacity 0.2s', marginBottom: '1.5rem' }}>
              <label>Google Doc ID (Overrides .env)</label>
              <input 
                type="text" 
                placeholder="e.g. 1SChyLfsIS3..."
                className="form-input" 
                value={docId}
                onChange={(e) => setDocId(e.target.value)}
                disabled={!deliverToDoc}
              />
            </div>

            <div className="form-group-checkbox">
              <label className="checkbox-container">
                <input 
                  type="checkbox" 
                  checked={deliverToEmail}
                  onChange={(e) => setDeliverToEmail(e.target.checked)}
                />
                <span>Deliver Gmail Draft</span>
              </label>
            </div>

            <div className="form-group" style={{ opacity: deliverToEmail ? 1 : 0.5, transition: 'opacity 0.2s' }}>
              <label>Teaser Email Recipients (Overrides .env)</label>
              <input 
                type="text" 
                placeholder="e.g. manager@groww.in"
                className="form-input" 
                value={toEmails}
                onChange={(e) => setToEmails(e.target.value)}
                disabled={!deliverToEmail}
              />
            </div>
          </div>

          {/* Run History */}
          <div className="glass-panel" style={{ padding: '1.5rem', maxHeight: '400px', overflowY: 'auto' }}>
            <h2 className="panel-title">Run Log History</h2>
            {history.length === 0 ? (
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', margin: 0 }}>No runs logged yet.</p>
            ) : (
              history.map((h, i) => (
                <div key={i} className="history-item">
                  <div className="history-meta">
                    <span>{h.run_id || h.idempotency_key || 'Unknown Run'}</span>
                    <span>{h.timestamp ? new Date(h.timestamp).toLocaleDateString() : 'Legacy'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
                    {h.doc_url ? (
                      <a href={h.doc_url} target="_blank" rel="noreferrer" className="history-link">
                        Open Google Doc ↗
                      </a>
                    ) : (
                      <span style={{ color: '#64748b', fontSize: '0.8rem' }}>No Doc Link</span>
                    )}
                    <span 
                      className="status-badge" 
                      style={{ 
                        fontSize: '0.7rem', 
                        padding: '0.1rem 0.4rem', 
                        background: h.status === 'completed' ? 'rgba(16, 185, 129, 0.15)' : 
                                    h.status === 'docs_only' ? 'rgba(59, 130, 246, 0.15)' :
                                    h.status === 'email_only' ? 'rgba(139, 92, 246, 0.15)' :
                                    'rgba(239, 68, 68, 0.15)', 
                        color: h.status === 'completed' ? '#10b981' : 
                               h.status === 'docs_only' ? '#3b82f6' :
                               h.status === 'email_only' ? '#8b5cf6' :
                               '#ef4444' 
                      }}
                    >
                      {h.status === 'docs_only' ? 'docs only' : 
                       h.status === 'email_only' ? 'email draft' : 
                       h.status}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* Right column: main workspace */}
        <main style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>


          {/* Insights Section */}
          {insights.length === 0 ? (
            <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center' }}>
              <h3 style={{ margin: 0, color: '#f8fafc' }}>No review analysis loaded</h3>
              <p style={{ color: '#94a3b8', margin: '0.5rem 0 1.5rem 0' }}>Trigger an App Review scrape and clustering reasoning to generate the weekly pulse report.</p>
            </div>
          ) : (
            <div>
              <h2 style={{ fontSize: '1.25rem', color: '#f8fafc', marginBottom: '1rem', marginTop: 0 }}>
                Clustered Review Themes ({insights.length} clusters, {totalReviews} reviews analyzed)
              </h2>
              <div className="cards-container">
                {insights.map((ins, index) => (
                  <div key={index} className="glass-panel insight-card">
                    <div className="insight-header">
                      <h3 className="insight-theme">{ins.theme}</h3>
                      <span className="count-badge">{ins.review_count} reviews</span>
                    </div>
                    
                    <div className="actionable-block">
                      <div className="actionable-label">Actionable Idea</div>
                      <p className="actionable-text">{ins.actionable_idea}</p>
                    </div>

                    <div>
                      <div className="quotes-title">Verbatim Quotes</div>
                      {ins.quotes.map((q, idx) => (
                        <div key={idx} className="quote-item">
                          "{q}"
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Delivery Section */}
          <div className="glass-panel" style={{ padding: '2rem' }}>
            <h2 className="panel-title">Workspace Delivery Configuration & Previews</h2>
            <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginTop: '-0.5rem', marginBottom: '1.5rem' }}>
              Preview and customize report content for Google Docs and Gmail draft separately before publishing.
            </p>
            
            {/* Tabs for Previews */}
            <div className="tabs-container">
              <button 
                className={`tab-btn ${activeTab === 'doc' ? 'active' : ''}`}
                onClick={() => setActiveTab('doc')}
                type="button"
              >
                Google Doc Report
                {!deliverToDoc && <span className="tab-disabled-dot" title="Disabled"></span>}
              </button>
              <button 
                className={`tab-btn ${activeTab === 'email' ? 'active' : ''}`}
                onClick={() => setActiveTab('email')}
                type="button"
              >
                Gmail Teaser Email
                {!deliverToEmail && <span className="tab-disabled-dot" title="Disabled"></span>}
              </button>
            </div>

            <div className="tab-content" style={{ marginTop: '1.5rem' }}>
              {activeTab === 'doc' && (
                <div>
                  {!deliverToDoc && (
                    <div className="tab-warning">
                      ⚠️ Google Docs delivery is currently disabled. Toggle it in "Delivery Parameters" to enable.
                    </div>
                  )}
                  <div className="form-group" style={{ opacity: deliverToDoc ? 1 : 0.6 }}>
                    <label>Google Doc Plain-Text Body Preview</label>
                    <textarea 
                      className="form-input" 
                      rows={14}
                      value={docBody}
                      onChange={(e) => setDocBody(e.target.value)}
                      disabled={!deliverToDoc}
                      style={{ fontFamily: 'monospace', fontSize: '0.85rem', resize: 'vertical' }}
                    />
                  </div>
                </div>
              )}

              {activeTab === 'email' && (
                <div>
                  {!deliverToEmail && (
                    <div className="tab-warning">
                      ⚠️ Gmail Teaser delivery is currently disabled. Toggle it in "Delivery Parameters" to enable.
                    </div>
                  )}
                  <div style={{ opacity: deliverToEmail ? 1 : 0.6 }}>
                    <div className="form-group">
                      <label>Teaser Subject Line</label>
                      <input 
                        type="text" 
                        className="form-input" 
                        value={subject}
                        onChange={(e) => setSubject(e.target.value)}
                        disabled={!deliverToEmail}
                      />
                    </div>

                    <div className="form-group">
                      <label>Teaser Email Plain-Text Body Preview</label>
                      <textarea 
                        className="form-input" 
                        rows={10}
                        value={body}
                        onChange={(e) => setBody(e.target.value)}
                        disabled={!deliverToEmail}
                        style={{ fontFamily: 'monospace', fontSize: '0.85rem', resize: 'vertical' }}
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>

            <button 
              className="btn-primary" 
              onClick={deliverReport} 
              disabled={delivering || (!deliverToDoc && !deliverToEmail)}
              style={{ width: 'auto', padding: '0.85rem 2rem', marginTop: '1rem' }}
            >
              {delivering ? (
                <>
                  <div className="spinner"></div>
                  Delivering to Workspace...
                </>
              ) : (
                !deliverToDoc && !deliverToEmail ? 'Workspace Delivery Disabled' :
                deliverToDoc && deliverToEmail ? 'Publish to Google Doc & Create Gmail Draft' :
                deliverToDoc ? 'Publish to Google Doc' : 'Create Gmail Draft'
              )}
            </button>

            {deliveryResult && (
              <div style={{ marginTop: '1.5rem', padding: '1rem', background: 'rgba(16, 185, 129, 0.15)', border: '1px solid #10b981', borderRadius: '8px' }}>
                <p style={{ margin: 0, color: '#10b981', fontWeight: 600 }}>✓ Delivery Successful!</p>
                {deliveryResult.doc_url && (
                  <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem' }}>
                    Google Doc updated! Open here: <a href={deliveryResult.doc_url} target="_blank" rel="noreferrer" style={{ color: '#3b82f6', textDecoration: 'underline' }}>{deliveryResult.doc_url}</a>
                  </p>
                )}
                {deliveryResult.draft_id && (
                  <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem' }}>
                    Teaser email draft created successfully. Gmail Draft ID: {deliveryResult.draft_id}
                  </p>
                )}
              </div>
            )}

            {deliveryError && (
              <div style={{ marginTop: '1.5rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid #ef4444', borderRadius: '8px' }}>
                <p style={{ margin: 0, color: '#ef4444', fontWeight: 600 }}>✗ Delivery Failed</p>
                <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#cbd5e1' }}>{deliveryError}</p>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
