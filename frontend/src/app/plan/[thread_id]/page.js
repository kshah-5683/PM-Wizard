"use client";

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';

export default function PlanDetail() {
  const router = useRouter();
  const { thread_id } = useParams();
  
  const [loading, setLoading] = useState(true);
  const [planData, setPlanData] = useState(null);
  const [error, setError] = useState(null);
  const [comments, setComments] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState('tickets'); // 'tickets' or 'gaps'
  
  // Custom loading message rotation
  const [loadingMessage, setLoadingMessage] = useState('Initializing agent loops...');
  
  useEffect(() => {
    const messages = [
      'Initializing agent loops...',
      'Ingesting PRD and parsing structure...',
      'Vision Model analyzing wireframes and visual contexts...',
      'AI Critic searching for edge cases & business logic gaps...',
      'Analyzing repository file structure and tech debt hotspots...',
      'Scrum Master agent forecasting team velocity...',
      'Generating user stories, epics, and subtasks...',
      'Calculating story points using Fibonacci sequence...'
    ];
    let idx = 0;
    const interval = setInterval(() => {
      idx = (idx + 1) % messages.length;
      setLoadingMessage(messages[idx]);
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  // Poll status endpoint
  useEffect(() => {
    let active = true;
    let pollInterval = null;

    const fetchStatus = async () => {
      try {
        const res = await fetch(`http://127.0.0.1:8000/api/v1/plan/${thread_id}/status`);
        if (!res.ok) {
          if (res.status === 404) {
            throw new Error("Session not found in system.");
          }
          throw new Error("Failed to load session details.");
        }
        
        const data = await res.json();
        if (!active) return;
        
        setPlanData(data);
        setLoading(false);
        
        // Stop polling if completed or failed
        if (
          data.status === 'COMPLETED' || 
          data.status === 'COMPLETED_SYNCED' || 
          data.status === 'FAILED' ||
          data.status === 'AWAITING_EM_APPROVAL'
        ) {
          if (pollInterval) {
            clearInterval(pollInterval);
          }
        }
      } catch (err) {
        if (active) {
          setError(err.message);
          setLoading(false);
          if (pollInterval) {
            clearInterval(pollInterval);
          }
        }
      }
    };

    fetchStatus();
    
    // Poll every 3 seconds for active processes
    pollInterval = setInterval(() => {
      if (planData && (
        planData.status === 'PROCESSING' || 
        planData.status === 'PENDING'
      )) {
        fetchStatus();
      } else if (!planData) {
        fetchStatus();
      }
    }, 3000);

    return () => {
      active = false;
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [thread_id, planData?.status]);

  const handleDecision = async (decision) => {
    if (decision === 'revise' && !comments.trim()) {
      alert("Please provide revision feedback comments for the AI Master to regenerate tickets.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`http://127.0.0.1:8000/api/v1/plan/${thread_id}/resume`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          decision,
          comments: decision === 'revise' ? comments : (comments || "Approved"),
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to process decision.");
      }

      // Update state to trigger polling again
      setPlanData(prev => ({
        ...prev,
        status: 'PROCESSING',
        paused_waiting_input: false
      }));
      setComments('');
      setLoading(true);
    } catch (err) {
      setError(err.message || "An error occurred while resuming the plan.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading && (!planData || planData.status === 'PROCESSING' || planData.status === 'PENDING')) {
    return (
      <div className="container">
        <div className="loading-view">
          <div className="spinner"></div>
          <h2 style={{ fontWeight: 600 }}>Building Sprint Backlog</h2>
          <p style={{ color: 'var(--text-secondary)' }}>{loadingMessage}</p>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Thread ID: {thread_id}</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container">
        <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center', maxWidth: '600px', margin: '4rem auto' }}>
          <div style={{ color: 'var(--error)', fontSize: '3rem', marginBottom: '1rem' }}>⚠️</div>
          <h2 style={{ marginBottom: '1rem', fontWeight: 600 }}>Session Error</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem' }}>{error}</p>
          <button className="btn btn-primary" onClick={() => router.push('/')}>
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (!planData) return null;

  const isAwaitingApproval = planData.status === 'AWAITING_EM_APPROVAL';
  const isCompleted = planData.status === 'COMPLETED' || planData.status === 'COMPLETED_SYNCED';
  const isFailed = planData.status === 'FAILED';

  return (
    <div className="container">
      {/* Header */}
      <header className="header">
        <div className="logo-group">
          <div className="logo-icon" style={{ cursor: 'pointer' }} onClick={() => router.push('/')}>PM</div>
          <div>
            <h1 className="title-gradient" style={{ cursor: 'pointer' }} onClick={() => router.push('/')}>PM-Wizard Control Room</h1>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Session: <strong style={{ fontFamily: 'monospace', color: 'var(--accent-primary)' }}>{thread_id.substring(0, 8)}...</strong>
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button className="btn btn-secondary" onClick={() => router.push('/')}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: '6px' }}><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
            Dashboard
          </button>
          {isAwaitingApproval && (
            <button 
              className="btn btn-primary"
              disabled={isSubmitting}
              onClick={() => handleDecision('approve')}
            >
              {isSubmitting ? 'Syncing...' : 'Approve & Sync'}
            </button>
          )}
        </div>
      </header>

      {/* Main Content Area based on Status */}
      {isAwaitingApproval && (
        <div className="sandbox-layout">
          
          {/* Side Panel: Metrics */}
          <div className="glass-panel side-panel">
            <h3 className="side-panel-title">Planning Metrics</h3>
            <div className="metric-grid">
              <div className="metric-card">
                <span className="metric-val">{planData.metrics?.total_epics || 0}</span>
                <span className="metric-lbl">Total Epics</span>
              </div>
              <div className="metric-card">
                <span className="metric-val">{planData.metrics?.total_stories || 0}</span>
                <span className="metric-lbl">User Stories</span>
              </div>
              <div className="metric-card">
                <span className="metric-val">{planData.metrics?.total_story_points || 0}</span>
                <span className="metric-lbl">Total Points</span>
              </div>
              <div className="metric-card">
                <span className="metric-val">{planData.attempt_count || 0}</span>
                <span className="metric-lbl">AI Revisions</span>
              </div>
            </div>
            
            <div style={{ marginTop: '1rem' }}>
              <h4 style={{ fontSize: '0.9rem', marginBottom: '0.5rem', fontWeight: 600, color: 'var(--text-primary)' }}>Source Document:</h4>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {planData.source_document || 'Direct Text Input'}
              </p>
            </div>
          </div>

          {/* Main Sandbox: Tickets / Gaps view */}
          <div className="glass-panel tickets-container">
            <div style={{ display: 'flex', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem', marginBottom: '1.5rem', gap: '1rem' }}>
              <button 
                className="btn" 
                style={{ 
                  background: activeTab === 'tickets' ? 'var(--bg-tertiary)' : 'transparent',
                  borderColor: activeTab === 'tickets' ? 'var(--accent-primary)' : 'transparent',
                  borderWidth: '1px',
                  borderStyle: 'solid',
                  padding: '0.5rem 1rem',
                  fontSize: '0.9rem'
                }}
                onClick={() => setActiveTab('tickets')}
              >
                Draft Backlog ({planData.draft_tickets?.length || 0})
              </button>
              <button 
                className="btn" 
                style={{ 
                  background: activeTab === 'gaps' ? 'var(--bg-tertiary)' : 'transparent',
                  borderColor: activeTab === 'gaps' ? 'var(--accent-primary)' : 'transparent',
                  borderWidth: '1px',
                  borderStyle: 'solid',
                  padding: '0.5rem 1rem',
                  fontSize: '0.9rem'
                }}
                onClick={() => setActiveTab('gaps')}
              >
                AI Gaps Analysis
              </button>
            </div>

            {activeTab === 'tickets' && (
              <div>
                <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '1.2rem' }}>
                  The Scrum Master agent suggested the following work packages. Review, adjust, or request revisions.
                </p>
                
                <div className="ticket-list">
                  {!planData.draft_tickets || planData.draft_tickets.length === 0 ? (
                    <p style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '3rem 0' }}>No tickets generated.</p>
                  ) : (
                    planData.draft_tickets.map((t, idx) => (
                      <div key={idx} className="ticket-card">
                        <div className="ticket-header">
                          <span className="ticket-id">{t.key || `TICKET-${idx+1}`}</span>
                          <div className="ticket-meta">
                            <span className={`ticket-type-badge type-${t.type || 'Story'}`}>{t.type || 'Story'}</span>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Priority: <strong>{t.priority || 'Medium'}</strong></span>
                            <span className="ticket-est">{t.estimation || 0} SP</span>
                          </div>
                        </div>
                        <h4 className="ticket-title">{t.title}</h4>
                        <p className="ticket-desc">{t.description}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {activeTab === 'gaps' && (
              <div style={{ animation: 'slideIn 0.3s ease-out' }}>
                <h3 style={{ fontSize: '1.2rem', marginBottom: '1rem', fontWeight: 600, color: '#fff' }}>Missing Edge Cases & Feedback</h3>
                <div style={{ 
                  padding: '1.25rem', 
                  borderRadius: '10px', 
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(255,255,255,0.05)',
                  whiteSpace: 'pre-line',
                  fontSize: '0.95rem',
                  lineHeight: '1.7',
                  color: 'var(--text-primary)'
                }}>
                  {planData.missing_edge_cases || 'No gaps or edge cases identified by the AI Critic.'}
                </div>
              </div>
            )}
          </div>

          {/* Feedback & Revision Console */}
          <div className="glass-panel feedback-panel">
            <h3 className="side-panel-title">Revision Console</h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                Regeneration Prompts / Adjustments
              </label>
              <textarea 
                className="feedback-textarea"
                placeholder="e.g. Split ticket-2 into two smaller stories, or combine the authentication tickets into a single Epic."
                value={comments}
                onChange={(e) => setComments(e.target.value)}
              />
            </div>

            <button 
              className="btn btn-secondary"
              style={{ width: '100%', border: '1px solid rgba(239, 68, 68, 0.4)', color: '#f87171' }}
              disabled={isSubmitting}
              onClick={() => handleDecision('revise')}
            >
              {isSubmitting ? 'Requesting...' : 'Request AI Revision'}
            </button>
            
            <div style={{ borderTop: '1px solid var(--glass-border)', paddingTop: '1rem' }}>
              <h4 style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                Revision Guidelines:
              </h4>
              <ul className="bullet-list">
                <li>Provide specific feedback on estimates (e.g. "make estimation for OAuth 5 points").</li>
                <li>Add missing acceptance criteria for tickets.</li>
                <li>Request splitting complex user stories into subtasks.</li>
              </ul>
            </div>
          </div>

        </div>
      )}

      {isCompleted && (
        <div className="glass-panel sync-status" style={{ maxWidth: '800px', margin: '4rem auto', padding: '3rem' }}>
          <div className="circle-success">✓</div>
          <h2 style={{ fontWeight: 600, fontSize: '1.8rem', marginTop: '1rem' }}>Backlog Synchronized Successfully!</h2>
          <p style={{ color: 'var(--text-secondary)', textAlign: 'center', maxWidth: '600px', fontSize: '0.95rem' }}>
            The plan has been fully reviewed and pushed downstream. All tickets have been synchronized with your Jira/Linear project boards.
          </p>
          
          <div style={{ width: '100%', marginTop: '2rem', borderTop: '1px solid var(--glass-border)', paddingTop: '2rem' }}>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '1.25rem', fontWeight: 600, textAlign: 'center' }}>
              Synchronized Backlog ({planData.draft_tickets?.length || 0} Tickets)
            </h3>
            
            <div className="ticket-list" style={{ maxHeight: '400px', overflowY: 'auto', paddingRight: '0.5rem' }}>
              {planData.draft_tickets?.map((t, idx) => (
                <div key={idx} className="ticket-card" style={{ cursor: 'default' }}>
                  <div className="ticket-header">
                    <span className="ticket-id" style={{ color: 'var(--success)', background: 'var(--success-glow)' }}>{t.key}</span>
                    <div className="ticket-meta">
                      <span className={`ticket-type-badge type-${t.type}`}>{t.type}</span>
                      <span className="ticket-est">{t.estimation} SP</span>
                    </div>
                  </div>
                  <h4 className="ticket-title">{t.title}</h4>
                </div>
              ))}
            </div>
          </div>

          <button className="btn btn-primary" style={{ marginTop: '2.5rem', width: '200px' }} onClick={() => router.push('/')}>
            Back to Dashboard
          </button>
        </div>
      )}

      {isFailed && (
        <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center', maxWidth: '600px', margin: '4rem auto' }}>
          <div style={{ color: 'var(--error)', fontSize: '4rem', marginBottom: '1rem' }}>✕</div>
          <h2 style={{ marginBottom: '1rem', fontWeight: 600, fontSize: '1.75rem' }}>Planning Run Failed</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem', lineHeight: '1.6' }}>
            The LangGraph state machine encountered a critical error during execution. This could be due to rate limit issues on the free-tier API endpoints.
          </p>
          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
            <button className="btn btn-secondary" onClick={() => handleDecision('revise')}>
              Retry Step
            </button>
            <button className="btn btn-primary" onClick={() => router.push('/')}>
              Back to Dashboard
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
