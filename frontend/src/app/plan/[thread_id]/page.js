"use client";

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export default function PlanDetail() {
  const router = useRouter();
  const { thread_id } = useParams();
  
  const [loading, setLoading] = useState(true);
  const [planData, setPlanData] = useState(null);
  const [error, setError] = useState(null);
  const [comments, setComments] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState('tickets'); // 'tickets' or 'gaps'
  const [amendedPrd, setAmendedPrd] = useState('');
  const [activePersona, setActivePersona] = useState('PM');
  const [activeOrg, setActiveOrg] = useState('org-google');
  const [currentUser, setCurrentUser] = useState(null);
  const [changeRequests, setChangeRequests] = useState([]);
  const [devAiPrompt, setDevAiPrompt] = useState('');
  const [showDevModal, setShowDevModal] = useState(false);
  const [selectedTicketForChange, setSelectedTicketForChange] = useState(null);
  const [devFormName, setDevFormName] = useState('');
  const [devFormPoints, setDevFormPoints] = useState('');
  const [devFormDesc, setDevFormDesc] = useState('');
  
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

    const fetchChangeRequests = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/change-requests`, {
          headers: {
            'X-Org-Id': activeOrg
          }
        });
        if (res.ok) {
          const data = await res.json();
          setChangeRequests(data.change_requests || []);
        }
      } catch (err) {
        console.error("Failed to fetch change requests:", err);
      }
    };

    const fetchStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/status`, {
          headers: {
            'X-Org-Id': activeOrg
          }
        });
        if (!res.ok) {
          if (res.status === 404) {
            throw new Error("Session not found in this organization.");
          }
          throw new Error("Failed to load session details.");
        }
        
        const data = await res.json();
        if (!active) return;
        
        setPlanData(data);
        setLoading(false);
        
        // Also fetch change requests
        fetchChangeRequests();
        
        // Stop polling if completed or failed or awaiting interaction
        if (
          data.status === 'COMPLETED' || 
          data.status === 'COMPLETED_SYNCED' || 
          data.status === 'FAILED' ||
          data.status === 'AWAITING_EM_APPROVAL' ||
          data.status === 'AWAITING_APPROVAL' ||
          data.status === 'AWAITING_CRITIC_RESOLUTION'
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
  }, [thread_id, planData?.status, activeOrg]);

  // Authenticate user on mount
  useEffect(() => {
    const userStr = localStorage.getItem('currentUser');
    if (!userStr) {
      router.push('/login');
      return;
    }
    const user = JSON.parse(userStr);
    setCurrentUser(user);
    setActivePersona(user.role);
    setActiveOrg(user.orgId);
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem('currentUser');
    router.push('/login');
  };

  // Set initial amended PRD from backend once loaded
  useEffect(() => {
    if (planData?.raw_prd && !amendedPrd) {
      setAmendedPrd(planData.raw_prd);
    }
  }, [planData?.raw_prd]);

  const handleResolveChangeRequest = async (requestId, status) => {
    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/change-request/${requestId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': activePersona,
          'X-Org-Id': activeOrg
        },
        body: JSON.stringify({ status }),
      });

      if (!response.ok) {
        throw new Error("Failed to resolve change request.");
      }

      // Refresh list
      try {
        const resList = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/change-requests`, {
          headers: {
            'X-Org-Id': activeOrg
          }
        });
        if (resList.ok) {
          const dataList = await resList.json();
          setChangeRequests(dataList.change_requests || []);
        }
      } catch (e) {}
      
      // Refresh status to pull modified tickets list
      const resStatus = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/status`, {
        headers: {
          'X-Org-Id': activeOrg
        }
      });
      if (resStatus.ok) {
        const dataStatus = await resStatus.json();
        setPlanData(dataStatus);
      }
    } catch (err) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmitChangeRequest = async (e) => {
    e.preventDefault();
    if (!devFormName.trim() || !devFormPoints || !devFormDesc.trim()) {
      alert("Please fill out all fields.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/change-request`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': activePersona,
          'X-Org-Id': activeOrg
        },
        body: JSON.stringify({
          ticket_key: selectedTicketForChange.key,
          developer_name: devFormName,
          original_points: selectedTicketForChange.estimation,
          original_description: selectedTicketForChange.description,
          requested_points: parseInt(devFormPoints),
          requested_description: devFormDesc
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to submit change request.");
      }

      setShowDevModal(false);
      setSelectedTicketForChange(null);
      setDevFormName('');
      setDevFormPoints('');
      setDevFormDesc('');
      
      // Refresh list
      try {
        const resList = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/change-requests`, {
          headers: {
            'X-Org-Id': activeOrg
          }
        });
        if (resList.ok) {
          const dataList = await resList.json();
          setChangeRequests(dataList.change_requests || []);
        }
      } catch (e) {}
      alert("Ticket change request submitted successfully. Awaiting EM approval!");
    } catch (err) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCriticResolution = async (action, payloadValue) => {
    if (action === 'amend' && !payloadValue.trim()) {
      alert("Please provide the amended PRD content to continue.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/resume`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': activePersona,
          'X-Org-Id': activeOrg
        },
        body: JSON.stringify({
          action,
          amended_prd: action === 'amend' ? payloadValue : null,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to submit critic resolution.");
      }

      // Update state to trigger polling again
      setPlanData(prev => ({
        ...prev,
        status: 'PROCESSING',
        paused_waiting_input: false
      }));
      setLoading(true);
    } catch (err) {
      setError(err.message || "An error occurred while resuming the plan.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDecision = async (decision) => {
    if (decision === 'revise' && !comments.trim()) {
      alert("Please provide revision feedback comments for the AI Master to regenerate tickets.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/resume`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': activePersona,
          'X-Org-Id': activeOrg
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

  const handleRetryRun = async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/plan/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': activePersona,
          'X-Org-Id': activeOrg
        },
        body: JSON.stringify({
          raw_prd: planData?.raw_prd || amendedPrd || "",
          thread_id: thread_id
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to restart planning session.");
      }

      // Reset loading state and set status to processing to trigger spinner
      setPlanData(prev => ({
        ...prev,
        status: 'PROCESSING'
      }));
      setLoading(true);

      // Trigger hot reload after restart
      setTimeout(() => {
        router.refresh();
      }, 500);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDevAiProposeChanges = async () => {
    if (!devAiPrompt.trim()) {
      alert("Please enter a description of the changes you wish to propose.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/propose-ai-changes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': activePersona,
          'X-Org-Id': activeOrg
        },
        body: JSON.stringify({
          prompt: devAiPrompt
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to submit AI proposed changes.");
      }

      const data = await response.json();
      alert(data.message || "AI has successfully generated and submitted your change proposals!");
      setDevAiPrompt('');
      
      // Refresh change requests list
      try {
        const resList = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/change-requests`, {
          headers: {
            'X-Org-Id': activeOrg
          }
        });
        if (resList.ok) {
          const dataList = await resList.json();
          setChangeRequests(dataList.change_requests || []);
        }
      } catch (e) {}
    } catch (err) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSendToEm = async () => {
    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/send-to-em`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': activePersona,
          'X-Org-Id': activeOrg
        }
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to send to EM.");
      }

      const data = await response.json();
      alert(data.message || "Successfully sent plan to EM for review!");
      
      // Refresh status
      try {
        const res = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/status`, {
          headers: {
            'X-Org-Id': activeOrg,
            'X-User-Role': activePersona
          }
        });
        if (res.ok) {
          const statusData = await res.json();
          setPlanData(statusData);
        }
      } catch (e) {}
    } catch (err) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleShareWithDev = async () => {
    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/share-with-dev`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': activePersona,
          'X-Org-Id': activeOrg
        }
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to share with Dev.");
      }

      const data = await response.json();
      alert(data.message || "Successfully shared plan with developers!");
      
      // Refresh status
      try {
        const res = await fetch(`${API_BASE}/api/v1/plan/${thread_id}/status`, {
          headers: {
            'X-Org-Id': activeOrg,
            'X-User-Role': activePersona
          }
        });
        if (res.ok) {
          const statusData = await res.json();
          setPlanData(statusData);
        }
      } catch (e) {}
    } catch (err) {
      alert(err.message);
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

  const isAwaitingCritic = planData.status === 'AWAITING_CRITIC_RESOLUTION';
  const isAwaitingApproval = planData.status === 'AWAITING_EM_APPROVAL' || planData.status === 'AWAITING_APPROVAL';
  const isCompleted = planData.status === 'COMPLETED' || planData.status === 'COMPLETED_SYNCED';
  const isFailed = planData.status === 'FAILED';
  const historicalTicketsCount = planData.historical_context?.length || planData.interrupt_payload?.historical_context?.length || 0;

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
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          {currentUser && (
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '1rem',
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--glass-border)',
              padding: '6px 16px',
              borderRadius: '12px',
              fontSize: '0.85rem'
            }}>
              <span>🏢 <strong>{activeOrg === 'org-google' ? 'Google' : activeOrg === 'org-microsoft' ? 'Microsoft' : activeOrg === 'org-meta' ? 'Meta' : activeOrg}</strong></span>
              <span style={{ color: 'rgba(255,255,255,0.15)' }}>|</span>
              <span>👤 {currentUser.name} (<strong>{activePersona}</strong>)</span>
            </div>
          )}
          <button className="btn btn-secondary" onClick={() => router.push('/')}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: '6px' }}><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
            Dashboard
          </button>
          {activePersona === 'PM' && (
            planData.sent_to_em ? (
              <span style={{ color: '#34d399', fontSize: '0.85rem', fontWeight: 600, padding: '0 0.5rem', display: 'flex', alignItems: 'center' }}>✓ Sent to EM</span>
            ) : (
              <button 
                className="btn btn-primary"
                disabled={isSubmitting}
                onClick={handleSendToEm}
                style={{ background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)', borderColor: '#3b82f6' }}
              >
                {isSubmitting ? 'Sending...' : 'Send to EM for Review'}
              </button>
            )
          )}

          {activePersona === 'EM' && planData.sent_to_em && (
            planData.shared_with_dev ? (
              <span style={{ color: '#34d399', fontSize: '0.85rem', fontWeight: 600, padding: '0 0.5rem', display: 'flex', alignItems: 'center' }}>✓ Shared with Devs</span>
            ) : (
              <button 
                className="btn btn-primary"
                disabled={isSubmitting}
                onClick={handleShareWithDev}
                style={{ background: 'linear-gradient(135deg, #10b981 0%, #047857 100%)', borderColor: '#10b981' }}
              >
                {isSubmitting ? 'Sharing...' : 'Share with Developers'}
              </button>
            )
          )}

          {activePersona === 'DEV' && planData.shared_with_dev && (
            <span style={{ color: '#34d399', fontSize: '0.85rem', fontWeight: 600, padding: '0 0.5rem', display: 'flex', alignItems: 'center' }}>✓ Shared with Devs</span>
          )}

          {isAwaitingApproval && activePersona === 'EM' && (
            <button 
              className="btn btn-primary"
              disabled={isSubmitting}
              onClick={() => handleDecision('approve')}
            >
              {isSubmitting ? 'Syncing...' : 'Approve & Sync'}
            </button>
          )}
          <button className="btn btn-secondary" style={{ borderColor: 'rgba(239, 68, 68, 0.3)', color: '#f87171' }} onClick={handleLogout}>Log Out</button>
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
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', marginBottom: '0.75rem' }}>
                {planData.source_document || 'Direct Text Input'}
              </p>
              
              <h4 style={{ fontSize: '0.9rem', marginBottom: '0.5rem', fontWeight: 600, color: 'var(--text-primary)' }}>Planning Mode:</h4>
              <span style={{ 
                fontSize: '0.8rem', 
                fontWeight: 600, 
                padding: '4px 10px', 
                borderRadius: '6px', 
                display: 'inline-block',
                background: planData.project_mode === 'GREENFIELD' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(59, 130, 246, 0.1)',
                color: planData.project_mode === 'GREENFIELD' ? '#10b981' : '#3b82f6',
                border: planData.project_mode === 'GREENFIELD' ? '1px solid rgba(16, 185, 129, 0.2)' : '1px solid rgba(59, 130, 246, 0.2)'
              }}>
                {planData.project_mode === 'GREENFIELD' ? '🌱 Greenfield Mode' : '📁 Brownfield Mode'}
              </span>
            </div>

            {historicalTicketsCount > 0 && (
              <div style={{ marginTop: '1.25rem', padding: '0.75rem', borderRadius: '6px', background: 'rgba(52, 211, 153, 0.1)', border: '1px solid rgba(52, 211, 153, 0.2)' }}>
                <span style={{ fontSize: '0.8rem', color: '#34d399', fontWeight: 600, display: 'block' }}>
                  ✓ Calibrated against {historicalTicketsCount} similar past tickets
                </span>
              </div>
            )}
          </div>

          {/* Main Sandbox: Tickets / Gaps view */}
          <div className="glass-panel tickets-container">
            {planData.project_mode === 'GREENFIELD' && (
              <div style={{ 
                marginBottom: '1.25rem', 
                padding: '0.75rem 1.25rem', 
                borderRadius: '8px', 
                background: 'rgba(245, 158, 11, 0.1)', 
                border: '1px solid rgba(245, 158, 11, 0.2)',
                color: '#fbbf24',
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                fontWeight: 500
              }}>
                <span>⚠️</span>
                <span><strong>Greenfield Mode Active:</strong> Story points estimated using industry-standard baseline T-shirt sizing. Please note that zero-to-one implementation risk carries a higher variance.</span>
              </div>
            )}
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
              <button 
                className="btn" 
                style={{ 
                  background: activeTab === 'requests' ? 'var(--bg-tertiary)' : 'transparent',
                  borderColor: activeTab === 'requests' ? 'var(--accent-primary)' : 'transparent',
                  borderWidth: '1px',
                  borderStyle: 'solid',
                  padding: '0.5rem 1rem',
                  fontSize: '0.9rem'
                }}
                onClick={() => setActiveTab('requests')}
              >
                Change Requests ({changeRequests.length || 0})
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
                        
                        {activePersona === 'DEV' && (
                          <button 
                            type="button"
                            className="btn" 
                            style={{ 
                              marginTop: '0.75rem', 
                              padding: '5px 12px', 
                              fontSize: '0.8rem', 
                              borderColor: 'var(--accent-primary)',
                              color: '#fff',
                              background: 'var(--accent-primary-glow)',
                              fontWeight: 600,
                              borderRadius: '6px',
                              cursor: 'pointer'
                            }}
                            onClick={() => {
                              setSelectedTicketForChange(t);
                              setDevFormPoints(t.estimation);
                              setDevFormDesc(t.description);
                              setShowDevModal(true);
                            }}
                          >
                            📝 Propose Change
                          </button>
                        )}
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

            {activeTab === 'requests' && (
              <div style={{ animation: 'slideIn 0.3s ease-out', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#fff' }}>Developer Change Requests</h3>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                  Developers can request story point adjustments or description changes. Engineering Managers can approve or reject proposals.
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  {changeRequests.length === 0 ? (
                    <p style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '3rem 0' }}>No change requests submitted yet.</p>
                  ) : (
                    changeRequests.map((req, idx) => (
                      <div 
                        key={idx} 
                        style={{ 
                          padding: '1.25rem', 
                          borderRadius: '12px', 
                          background: 'rgba(255,255,255,0.01)', 
                          border: '1px solid var(--glass-border)',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '0.75rem'
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--accent-primary)' }}>{req.ticket_key}</span>
                          <span style={{ 
                            fontSize: '0.7rem', 
                            fontWeight: 700, 
                            padding: '3px 8px', 
                            borderRadius: '6px', 
                            background: req.status === 'APPROVED' ? 'var(--success-glow)' : req.status === 'REJECTED' ? 'var(--error-glow)' : 'rgba(255,255,255,0.08)',
                            color: req.status === 'APPROVED' ? 'var(--success)' : req.status === 'REJECTED' ? 'var(--error)' : 'var(--text-secondary)'
                          }}>
                            {req.status}
                          </span>
                        </div>

                        <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                          <strong>Requested By:</strong> {req.developer_name}
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', background: 'rgba(0,0,0,0.2)', padding: '0.75rem', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.02)' }}>
                          <div>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Story Points:</span>
                            <span style={{ fontSize: '0.85rem', color: '#fff' }}>{req.original_points} SP ➜ <strong style={{ color: 'var(--success)' }}>{req.requested_points} SP</strong></span>
                          </div>
                          <div>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Requested Description:</span>
                            <span 
                              style={{ fontSize: '0.85rem', color: '#fff', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
                              title={req.requested_description}
                            >
                              {req.requested_description}
                            </span>
                          </div>
                        </div>

                        {req.status === 'PENDING' && activePersona === 'EM' && (
                          <div style={{ display: 'flex', gap: '0.75rem', alignSelf: 'flex-end', marginTop: '0.25rem' }}>
                            <button 
                              type="button"
                              className="btn" 
                              style={{ padding: '6px 12px', fontSize: '0.8rem', background: 'var(--success)', border: 'none', color: '#fff', borderRadius: '6px', cursor: 'pointer' }}
                              disabled={isSubmitting}
                              onClick={() => handleResolveChangeRequest(req.id, 'APPROVED')}
                            >
                              ✓ Approve
                            </button>
                            <button 
                              type="button"
                              className="btn" 
                              style={{ padding: '6px 12px', fontSize: '0.8rem', borderColor: 'var(--error)', color: 'var(--error)', borderRadius: '6px', cursor: 'pointer', background: 'transparent' }}
                              disabled={isSubmitting}
                              onClick={() => handleResolveChangeRequest(req.id, 'REJECTED')}
                            >
                              ✕ Reject
                            </button>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Feedback & Revision Console */}
          {activePersona === 'DEV' ? (
            <div className="glass-panel feedback-panel">
              <h3 className="side-panel-title">AI Change Proposer</h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Describe Proposed Backlog Updates
                </label>
                <textarea 
                  className="feedback-textarea"
                  placeholder="e.g. Increase PROJ-101 story points to 5 because we need database migrations, and update description to include testing."
                  value={devAiPrompt}
                  onChange={(e) => setDevAiPrompt(e.target.value)}
                  disabled={isSubmitting}
                />
              </div>

              <button 
                className="btn btn-primary"
                style={{ width: '100%', marginTop: '1rem' }}
                disabled={isSubmitting}
                onClick={handleDevAiProposeChanges}
              >
                {isSubmitting ? 'Submitting Proposals...' : 'Propose Changes via AI'}
              </button>
              
              <div style={{ borderTop: '1px solid var(--glass-border)', paddingTop: '1rem', marginTop: '1rem' }}>
                <h4 style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                  Developer Guidelines:
                </h4>
                <ul className="bullet-list">
                  <li>Your suggestions will be analyzed by the AI Scrum Assistant.</li>
                  <li>Specific updates will be logged as PENDING change proposals.</li>
                  <li>The Engineering Manager (EM) will review and approve them before they merge.</li>
                </ul>
              </div>
            </div>
          ) : (
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
                  disabled={activePersona !== 'EM'}
                />
              </div>

              <button 
                className="btn btn-secondary"
                style={{ 
                  width: '100%', 
                  border: activePersona === 'EM' ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid rgba(255, 255, 255, 0.05)', 
                  color: activePersona === 'EM' ? '#f87171' : 'var(--text-muted)',
                  cursor: activePersona === 'EM' ? 'pointer' : 'not-allowed',
                  background: activePersona === 'EM' ? 'transparent' : 'rgba(255, 255, 255, 0.01)'
                }}
                disabled={isSubmitting || activePersona !== 'EM'}
                onClick={() => handleDecision('revise')}
              >
                {activePersona === 'EM' ? (isSubmitting ? 'Requesting...' : 'Request AI Revision') : '🔒 Revision Locked (EM Only)'}
              </button>
              
              <div style={{ borderTop: '1px solid var(--glass-border)', paddingTop: '1rem', marginTop: '1rem' }}>
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
          )}

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
            {planData.project_mode === 'GREENFIELD' && (
              <div style={{ 
                marginBottom: '1.25rem', 
                padding: '0.75rem 1.25rem', 
                borderRadius: '8px', 
                background: 'rgba(245, 158, 11, 0.1)', 
                border: '1px solid rgba(245, 158, 11, 0.2)',
                color: '#fbbf24',
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                fontWeight: 500,
                textAlign: 'left'
              }}>
                <span>⚠️</span>
                <span><strong>Greenfield Mode Variance:</strong> Story points estimated using industry-standard baseline T-shirt sizing. Please note that zero-to-one implementation risk carries a higher variance.</span>
              </div>
            )}
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
            <button className="btn btn-secondary" disabled={isSubmitting} onClick={handleRetryRun}>
              {isSubmitting ? 'Retrying...' : 'Retry Step'}
            </button>
            <button className="btn btn-primary" onClick={() => router.push('/')}>
              Back to Dashboard
            </button>
          </div>
        </div>
      )}

      {isAwaitingCritic && (
        <div className="sandbox-layout" style={{ gridTemplateColumns: '1.2fr 2fr', gap: '2rem', animation: 'slideIn 0.4s ease-out' }}>
          
          {/* Side Panel: Critique list */}
          <div className="glass-panel side-panel" style={{ maxHeight: 'calc(100vh - 200px)', overflowY: 'auto', padding: '1.5rem' }}>
            <h3 className="side-panel-title" style={{ color: 'var(--error)', display: 'flex', alignItems: 'center', marginBottom: '0.75rem', fontWeight: 600 }}>
              <span style={{ marginRight: '8px' }}>🔴</span> Gaps Identified
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1.5rem', lineHeight: '1.5' }}>
              The AI Critic has paused the workflow due to the following deficiencies in the PRD:
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {(planData.interrupt_payload?.critiques || []).map((critique, idx) => (
                <div 
                  key={idx} 
                  style={{ 
                    padding: '1.25rem', 
                    borderRadius: '12px', 
                    background: critique.category === 'CRITICAL' ? 'rgba(239, 68, 68, 0.05)' : 'rgba(245, 158, 11, 0.05)', 
                    border: `1px solid ${critique.category === 'CRITICAL' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.2)'}` 
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                    <span style={{ 
                      fontSize: '0.7rem', 
                      fontWeight: 700, 
                      padding: '3px 8px', 
                      borderRadius: '6px', 
                      background: critique.category === 'CRITICAL' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                      color: critique.category === 'CRITICAL' ? '#f87171' : '#fbbf24'
                    }}>
                      {critique.category}
                    </span>
                  </div>
                  <h4 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.5rem', color: '#fff', lineHeight: '1.4' }}>{critique.description}</h4>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
                    <strong style={{ color: 'var(--text-primary)' }}>Remediation:</strong> {critique.remediation}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Main Panel: PRD Editor & Actions */}
          <div className="glass-panel tickets-container" style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div>
              <h3 style={{ fontSize: '1.5rem', marginBottom: '0.5rem', fontWeight: 600, color: '#fff' }}>Resolve Gaps & Continue</h3>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
                Choose to either amend the PRD content with missing specifications or bypass the Critic's checks to proceed directly to ticket estimation.
              </p>
            </div>

            <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', flex: 1 }}>
              <label className="form-label" style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Product Requirement Document (PRD) Editor</label>
              <textarea 
                className="textarea-field"
                style={{ 
                  flex: 1, 
                  minHeight: '400px', 
                  fontFamily: 'monospace', 
                  fontSize: '0.9rem', 
                  lineHeight: '1.6', 
                  padding: '1.25rem',
                  borderRadius: '12px',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--glass-border)',
                  color: 'var(--text-primary)',
                  resize: 'vertical'
                }}
                value={amendedPrd}
                onChange={(e) => setAmendedPrd(e.target.value)}
              />
            </div>

            <div style={{ display: 'flex', gap: '1.25rem', marginTop: '0.5rem' }}>
              <button 
                className="btn btn-primary" 
                style={{ 
                  flex: 2, 
                  padding: '1rem', 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center', 
                  gap: '8px', 
                  fontWeight: 600,
                  boxShadow: '0 4px 12px rgba(99, 102, 241, 0.2)'
                }}
                disabled={isSubmitting}
                onClick={() => handleCriticResolution('amend', amendedPrd)}
              >
                {isSubmitting ? 'Regenerating...' : '✓ Submit Amended PRD & Re-run'}
              </button>
              
              <button 
                className="btn btn-secondary" 
                style={{ 
                  flex: 1, 
                  padding: '1rem', 
                  borderColor: 'rgba(255,255,255,0.12)', 
                  background: 'rgba(255,255,255,0.02)',
                  fontWeight: 600
                }}
                disabled={isSubmitting}
                onClick={() => handleCriticResolution('bypass', null)}
              >
                {isSubmitting ? 'Bypassing...' : 'Bypass Blocker'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showDevModal && selectedTicketForChange && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.75)',
          backdropFilter: 'blur(8px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          animation: 'fadeIn 0.25s ease-out'
        }}>
          <div className="glass-panel" style={{ width: '100%', maxWidth: '600px', padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)' }}>
            <div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#fff', marginBottom: '0.25rem' }}>Propose Change: {selectedTicketForChange.key}</h3>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Propose story point adjustments or description alterations to the EM.</p>
            </div>

            <form onSubmit={handleSubmitChangeRequest} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <label className="form-label" style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.85rem' }}>Developer Name</label>
                <input 
                  type="text" 
                  className="input-field" 
                  style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-tertiary)', border: '1px solid var(--glass-border)', color: '#fff' }}
                  placeholder="e.g. John Doe"
                  value={devFormName}
                  onChange={(e) => setDevFormName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <label className="form-label" style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.85rem' }}>Requested Story Points (Original: {selectedTicketForChange.estimation} SP)</label>
                <input 
                  type="number" 
                  className="input-field" 
                  style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-tertiary)', border: '1px solid var(--glass-border)', color: '#fff' }}
                  placeholder="e.g. 5"
                  value={devFormPoints}
                  onChange={(e) => setDevFormPoints(e.target.value)}
                  required
                />
              </div>

              <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <label className="form-label" style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.85rem' }}>Requested Description</label>
                <textarea 
                  className="textarea-field" 
                  style={{ width: '100%', minHeight: '120px', padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-tertiary)', border: '1px solid var(--glass-border)', color: '#fff', resize: 'vertical', lineHeight: '1.5' }}
                  value={devFormDesc}
                  onChange={(e) => setDevFormDesc(e.target.value)}
                  required
                />
              </div>

              <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem' }}>
                <button 
                  type="submit" 
                  className="btn btn-primary" 
                  style={{ flex: 2, padding: '0.75rem 1.5rem', fontWeight: 600 }}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? 'Submitting...' : 'Submit Request'}
                </button>
                <button 
                  type="button" 
                  className="btn btn-secondary" 
                  style={{ flex: 1, padding: '0.75rem 1.5rem', borderColor: 'rgba(255,255,255,0.12)', background: 'transparent' }}
                  onClick={() => {
                    setShowDevModal(false);
                    setSelectedTicketForChange(null);
                  }}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
