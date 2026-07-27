"use client";

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export default function Dashboard() {
  const router = useRouter();
  const [rawPrd, setRawPrd] = useState(
    `# Project: Google OAuth login integration\n\n` +
    `We need to add Google OAuth login to our web app. Users should see a ` +
    `'Sign in with Google' button, which redirects to Google's authentication page, ` +
    `and handles the redirect callback securely to log them in.\n`
  );
  const [sourceDocument, setSourceDocument] = useState('');
  const [projects, setProjects] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [activePersona, setActivePersona] = useState('PM');
  const [activeOrg, setActiveOrg] = useState('org-google');
  const [currentUser, setCurrentUser] = useState(null);
  const [isParsingFile, setIsParsingFile] = useState(false);
  const [isParsingUrl, setIsParsingUrl] = useState(false);
  const [uploadSuccessMsg, setUploadSuccessMsg] = useState('');
  const [projectMode, setProjectMode] = useState('BROWNFIELD');
  const [githubRepo, setGithubRepo] = useState('');
  const [jiraProjectKey, setJiraProjectKey] = useState('');
  const [sprintConstraints, setSprintConstraints] = useState('');

  const [integrations, setIntegrations] = useState([
    { provider: 'github', connected: false },
    { provider: 'notion', connected: false },
    { provider: 'atlassian', connected: false }
  ]);
  const [isFetchingIntegrations, setIsFetchingIntegrations] = useState(false);

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

  const handleFetchUrl = async () => {
    if (!sourceDocument.trim()) return;
    
    setIsParsingUrl(true);
    setError(null);
    setUploadSuccessMsg('');

    try {
      const userStr = localStorage.getItem('currentUser');
      if (!userStr) {
        throw new Error("You must be logged in to fetch integration resources.");
      }
      const user = JSON.parse(userStr);

      const response = await fetch(`${API_BASE}/api/v1/parse-url`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': activePersona,
          'X-Org-Id': activeOrg,
          'user-id': user.email
        },
        body: JSON.stringify({
          url: sourceDocument.trim()
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to fetch document from URL.");
      }

      const data = await response.json();
      setRawPrd(data.markdown);
      setUploadSuccessMsg(`Successfully fetched and parsed document! Content loaded below.`);
    } catch (err) {
      setError(err.message || "An error occurred during URL parsing.");
    } finally {
      setIsParsingUrl(false);
    }
  };

  const processUploadedFile = async (file) => {
    const MAX_SIZE = 10 * 1024 * 1024; // 10MB
    if (file.size > MAX_SIZE) {
      setError("File size exceeds the maximum limit of 10MB.");
      setUploadSuccessMsg('');
      return;
    }

    setIsParsingFile(true);
    setError(null);
    setUploadSuccessMsg('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE}/api/v1/parse-document`, {
        method: 'POST',
        headers: {
          'X-User-Role': activePersona,
          'X-Org-Id': activeOrg
        },
        body: formData
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to parse document.");
      }

      const data = await response.json();
      setRawPrd(data.markdown);
      setUploadSuccessMsg(`Successfully parsed ${file.name}! Content loaded below.`);
    } catch (err) {
      setError(err.message || "An error occurred during document parsing.");
    } finally {
      setIsParsingFile(false);
    }
  };

  const handleFileChange = async (e) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      await processUploadedFile(files[0]);
    }
  };

  const handleFileDrop = async (e) => {
    e.preventDefault();
    e.currentTarget.style.borderColor = 'var(--glass-border)';
    e.currentTarget.style.background = 'rgba(255, 255, 255, 0.01)';
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      await processUploadedFile(files[0]);
    }
  };

  const fetchIntegrations = async () => {
    const userStr = localStorage.getItem('currentUser');
    if (!userStr) return;
    const user = JSON.parse(userStr);
    
    setIsFetchingIntegrations(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/integrations`, {
        headers: {
          'user-id': user.email,
          'X-User-Role': user.role,
          'X-Org-Id': user.orgId
        }
      });
      if (res.ok) {
        const data = await res.json();
        setIntegrations(data.integrations || []);
      }
    } catch (err) {
      console.error("Failed to fetch integrations:", err);
    } finally {
      setIsFetchingIntegrations(false);
    }
  };

  useEffect(() => {
    if (currentUser) {
      fetchIntegrations();
    }
  }, [currentUser, activeOrg]);

  // Handle redirect callback message from OAuth redirects
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const urlParams = new URLSearchParams(window.location.search);
    const integration = urlParams.get('integration');
    const provider = urlParams.get('provider');
    const message = urlParams.get('message');

    if (integration === 'success') {
      setUploadSuccessMsg(`Successfully connected your ${provider} account!`);
      // Clear query params to make URL clean
      window.history.replaceState({}, document.title, window.location.pathname);
      fetchIntegrations();
    } else if (integration === 'error') {
      setError(`Failed to connect ${provider}: ${message || 'Unknown error'}`);
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, [currentUser]);

  const handleConnect = async (provider) => {
    if (!currentUser) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/${provider}/connect?user_id=${currentUser.email}&org_id=${activeOrg}`);
      if (res.ok) {
        const data = await res.json();
        window.location.href = data.url;
      } else {
        const errorData = await res.json();
        throw new Error(errorData.detail || `Failed to fetch connection URL for ${provider}.`);
      }
    } catch (err) {
      setError(`Failed to connect ${provider}: ${err.message}`);
    }
  };

  const handleDisconnect = async (provider) => {
    if (!currentUser) return;
    if (!confirm(`Are you sure you want to disconnect your ${provider} integration?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/${provider}`, {
        method: 'DELETE',
        headers: {
          'user-id': currentUser.email,
          'X-User-Role': activePersona,
          'X-Org-Id': activeOrg
        }
      });
      if (res.ok) {
        setUploadSuccessMsg(`Successfully disconnected ${provider}.`);
        fetchIntegrations();
      } else {
        const errorData = await res.json();
        throw new Error(errorData.detail || `Failed to disconnect ${provider}.`);
      }
    } catch (err) {
      setError(`Failed to disconnect: ${err.message}`);
    }
  };

  // Fetch recent projects
  useEffect(() => {
    async function fetchProjects() {
      try {
        const res = await fetch(`${API_BASE}/api/v1/projects`, {
          headers: {
            'X-Org-Id': activeOrg,
            'X-User-Role': activePersona
          }
        });
        if (res.ok) {
          const data = await res.json();
          setProjects(data.projects || []);
        }
      } catch (err) {
        console.error("Failed to fetch projects:", err);
      }
    }
    fetchProjects();
    const interval = setInterval(fetchProjects, 10000); // refresh every 10s
    return () => clearInterval(interval);
  }, [activeOrg, activePersona]);

  const handleStartPlanning = async (e) => {
    e.preventDefault();
    if (!rawPrd.trim() && !sourceDocument.trim()) {
      setError("Please enter your Product Requirement Document (PRD) content or provide a valid source document URL.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const headers = {
        'Content-Type': 'application/json',
        'X-User-Role': activePersona,
        'X-Org-Id': activeOrg
      };
      if (currentUser && currentUser.email) {
        headers['user-id'] = currentUser.email;
      }

      const response = await fetch(`${API_BASE}/api/v1/plan/start`, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          raw_prd: rawPrd || null,
          source_document: sourceDocument || null,
          project_mode: projectMode,
          github_repo: githubRepo || null,
          jira_project_key: jiraProjectKey || null,
          sprint_constraints: sprintConstraints || null
        }),
      });


      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to start planning session.");
      }

      const data = await response.json();
      router.push(`/plan/${data.thread_id}`);
    } catch (err) {
      setError(err.message || "An error occurred. Make sure your FastAPI backend is running.");
      setIsSubmitting(false);
    }
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'PROCESSING': return 'badge-processing';
      case 'AWAITING_EM_APPROVAL': return 'badge-paused';
      case 'COMPLETED_SYNCED': return 'badge-synced';
      case 'COMPLETED': return 'badge-completed';
      case 'FAILED': return 'badge-failed';
      default: return 'badge-completed';
    }
  };

  return (
    <div className="container">
      <header className="header">
        <div className="logo-group">
          <div className="logo-icon">PM</div>
          <div>
            <h1 className="title-gradient">PM-Wizard Control Room</h1>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>AI-Driven Sprint Planner & Engineering Middleware</p>
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
          <button className="btn btn-secondary" style={{ borderColor: 'rgba(239, 68, 68, 0.3)', color: '#f87171' }} onClick={handleLogout}>Log Out</button>
        </div>
      </header>

      {activePersona === 'PM' ? (
        <div className="dashboard-grid">
          {/* Main Planning input card */}
          <div className="glass-panel planning-card">
            <h2 style={{ marginBottom: '1.5rem', fontWeight: 600 }}>Create New Sprint Plan</h2>
            
            {error && (
              <div style={{ 
                padding: '1rem', 
                borderRadius: '8px', 
                background: 'var(--error-glow)', 
                color: 'var(--error)', 
                border: '1px solid rgba(239, 68, 68, 0.3)',
                marginBottom: '1.5rem'
              }}>
                {error}
              </div>
            )}

            <form onSubmit={handleStartPlanning}>
              <div className="form-group">
                <label className="form-label">Upstream Source URL (Optional)</label>
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <input 
                    type="text" 
                    className="input-field" 
                    style={{ flex: 1 }}
                    placeholder="e.g. https://notion.so/my-workspace/prd-document"
                    value={sourceDocument}
                    onChange={(e) => setSourceDocument(e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={handleFetchUrl}
                    disabled={isParsingUrl || !sourceDocument.trim()}
                    className="btn btn-secondary"
                    style={{ whiteSpace: 'nowrap', minWidth: '120px' }}
                  >
                    {isParsingUrl ? 'Fetching...' : 'Fetch Link'}
                  </button>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Upload Upstream Document (Optional)</label>
                <div 
                  style={{
                    border: '2px dashed var(--glass-border)',
                    borderRadius: '12px',
                    padding: '1.5rem',
                    textAlign: 'center',
                    background: 'rgba(255, 255, 255, 0.01)',
                    cursor: 'pointer',
                    transition: 'var(--transition-smooth)',
                    position: 'relative'
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.currentTarget.style.borderColor = 'var(--accent-primary)';
                    e.currentTarget.style.background = 'rgba(99, 102, 241, 0.05)';
                  }}
                  onDragLeave={(e) => {
                    e.preventDefault();
                    e.currentTarget.style.borderColor = 'var(--glass-border)';
                    e.currentTarget.style.background = 'rgba(255, 255, 255, 0.01)';
                  }}
                  onDrop={handleFileDrop}
                  onClick={() => document.getElementById('file-upload-input').click()}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = 'var(--accent-primary)';
                    e.currentTarget.style.background = 'rgba(255, 255, 255, 0.02)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'var(--glass-border)';
                    e.currentTarget.style.background = 'rgba(255, 255, 255, 0.01)';
                  }}
                >
                  <input 
                    type="file" 
                    id="file-upload-input" 
                    style={{ display: 'none' }} 
                    accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp"
                    onChange={handleFileChange}
                  />
                  
                  {isParsingFile ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem' }}>
                      <div className="spinner" style={{ width: '32px', height: '32px', borderWidth: '3px', borderLeftColor: '#fff', borderTopColor: '#fff', animation: 'spin 1s linear infinite' }}></div>
                      <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                        Parsing document structure, tables, and visual assets...
                      </span>
                    </div>
                  ) : (
                    <div>
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: 'var(--accent-primary)', marginBottom: '0.5rem' }}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                      <p style={{ fontSize: '0.95rem', fontWeight: 600, color: '#fff', margin: '0 0 0.25rem 0' }}>
                        Drag & Drop PRD Document or Click to Browse
                      </p>
                      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
                        Supports PDF, DOCX, TXT, MD, and Images (Max 10MB)
                      </p>
                    </div>
                  )}
                </div>
                {uploadSuccessMsg && (
                  <div style={{ 
                    marginTop: '0.75rem', 
                    fontSize: '0.85rem', 
                    color: 'var(--success)', 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '0.25rem',
                    fontWeight: 500
                  }}>
                    ✅ {uploadSuccessMsg}
                  </div>
                )}
              </div>

              {/* Project Planning Mode Selector */}
              <div className="form-group">
                <label className="form-label">Planning Mode</label>
                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
                  <button
                    type="button"
                    onClick={() => setProjectMode('BROWNFIELD')}
                    className={`btn ${projectMode === 'BROWNFIELD' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ flex: 1, padding: '0.75rem', fontWeight: 600 }}
                  >
                    📁 Brownfield (Exist. Codebase)
                  </button>
                  <button
                    type="button"
                    onClick={() => setProjectMode('GREENFIELD')}
                    className={`btn ${projectMode === 'GREENFIELD' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ flex: 1, padding: '0.75rem', fontWeight: 600 }}
                  >
                    🌱 Greenfield (New Project)
                  </button>
                </div>
              </div>

              {projectMode === 'BROWNFIELD' && (
                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.25rem' }}>
                  <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
                    <label className="form-label">GitHub Repository (Optional)</label>
                    <input 
                      type="text" 
                      className="input-field" 
                      placeholder="owner/repo (e.g. facebook/react)"
                      value={githubRepo}
                      onChange={(e) => setGithubRepo(e.target.value)}
                    />
                  </div>
                  <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
                    <label className="form-label">Jira Project Key (Optional)</label>
                    <input 
                      type="text" 
                      className="input-field" 
                      placeholder="e.g. PROJ"
                      value={jiraProjectKey}
                      onChange={(e) => setJiraProjectKey(e.target.value)}
                    />
                  </div>
                </div>
              )}

              <div className="form-group">
                <label className="form-label">Sprint Constraints (Optional)</label>
                <input 
                  type="text" 
                  className="input-field" 
                  placeholder="e.g. Limit scope to 3 sprints, focus on performance, standard tech stack"
                  value={sprintConstraints}
                  onChange={(e) => setSprintConstraints(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">PRD Markdown Content</label>
                <textarea 
                  className="textarea-field"
                  value={rawPrd}
                  onChange={(e) => setRawPrd(e.target.value)}
                  placeholder="# Project Name..."
                />
              </div>


              <button 
                type="submit" 
                className="btn btn-primary" 
                style={{ width: '100%', padding: '1rem' }}
                disabled={isSubmitting}
              >
                {isSubmitting ? (
                  <>
                    <div className="spinner" style={{ width: '20px', height: '20px', borderWidth: '2px', borderLeftColor: '#fff', borderTopColor: '#fff', animation: 'spin 1s linear infinite' }}></div>
                    Initializing AI Workflow...
                  </>
                ) : (
                  <>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: '8px' }}><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                    Generate AI Sprint Plan
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Right Sidebar containing both Integrations and Recent Sessions */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            {/* Integrations Card */}
            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <h2 className="history-title" style={{ marginBottom: '1.25rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.75rem' }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: '8px', color: 'var(--accent-primary)' }}><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                Connected Systems
              </h2>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {integrations.map((integration) => {
                  const p = integration.provider;
                  const isConnected = integration.connected;
                  const tenantId = integration.tenant_id;
                  
                  // Visual details per provider
                  let title = "System";
                  let icon = "🔗";
                  if (p === 'github') { title = "GitHub"; icon = "🐱"; }
                  else if (p === 'notion') { title = "Notion"; icon = "📓"; }
                  else if (p === 'atlassian') { title = "Atlassian (Jira/Confluence)"; icon = "➿"; }

                  return (
                    <div 
                      key={p}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '0.75rem 1rem',
                        borderRadius: '10px',
                        background: isConnected ? 'rgba(16, 185, 129, 0.02)' : 'rgba(255, 255, 255, 0.01)',
                        border: isConnected ? '1px solid rgba(16, 185, 129, 0.15)' : '1px solid var(--glass-border)',
                        transition: 'var(--transition-smooth)'
                      }}
                    >
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem', maxWidth: '70%' }}>
                        <span style={{ fontSize: '0.9rem', fontWeight: 600, color: '#fff', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span>{icon}</span> {title}
                        </span>
                        <span style={{ fontSize: '0.75rem', color: isConnected ? 'var(--success)' : 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {isConnected ? `Connected: ${tenantId || 'Active'}` : 'Disconnected'}
                        </span>
                      </div>

                      <div>
                        {isConnected ? (
                          <button
                            type="button"
                            className="btn btn-secondary"
                            style={{ 
                              padding: '4px 10px', 
                              fontSize: '0.75rem', 
                              borderColor: 'rgba(239, 68, 68, 0.2)', 
                              color: '#f87171',
                              background: 'transparent'
                            }}
                            onClick={() => handleDisconnect(p)}
                          >
                            Disconnect
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn btn-primary"
                            style={{ padding: '4px 12px', fontSize: '0.75rem', fontWeight: 500 }}
                            onClick={() => handleConnect(p)}
                          >
                            Link
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Sidebar History list */}
            <div className="glass-panel history-card" style={{ maxHeight: '420px' }}>
              <h2 className="history-title">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '8px' }}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                Recent Sessions
              </h2>
              
              <div className="history-list">
                {projects.length === 0 ? (
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', marginTop: '2rem' }}>
                    No active or historical planning runs found in the database.
                  </p>
                ) : (
                  projects.map((proj) => (
                    <div 
                      key={proj.thread_id} 
                      className="history-item"
                      onClick={() => router.push(`/plan/${proj.thread_id}`)}
                    >
                      <div className="history-item-header">
                        <span className="history-item-title">{proj.title || "Untitled Session"}</span>
                        <span className={`badge ${getStatusBadgeClass(proj.status)}`}>
                          {proj.status.replace('_', ' ')}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span className="history-item-date">
                          {new Date(proj.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </span>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                          {proj.total_story_points ? `${proj.total_story_points} pts` : ''}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

      ) : (
        <div className="glass-panel" style={{ padding: '2.5rem', animation: 'slideIn 0.5s ease-out' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0, color: '#fff' }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ color: 'var(--accent-primary)', marginRight: '8px' }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              Review Plans
            </h2>
            <span style={{ 
              background: 'rgba(255,255,255,0.03)', 
              border: '1px solid var(--glass-border)',
              padding: '6px 16px', 
              borderRadius: '20px', 
              fontSize: '0.85rem', 
              color: 'var(--text-secondary)',
              fontWeight: 500
            }}>
              {projects.length} {projects.length === 1 ? 'Plan' : 'Plans'} Available
            </span>
          </div>

          {projects.length === 0 ? (
            <div style={{ 
              display: 'flex', 
              flexDirection: 'column', 
              alignItems: 'center', 
              justifyContent: 'center', 
              padding: '5rem 2rem',
              color: 'var(--text-muted)',
              border: '1px dashed rgba(255, 255, 255, 0.05)',
              borderRadius: '12px',
              background: 'rgba(255,255,255,0.01)'
            }}>
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ marginBottom: '1.5rem', color: 'var(--text-muted)', opacity: 0.6 }}><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="9" x2="15" y2="9"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="11" y2="17"/></svg>
              <p style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>No sprint plans ready for review</p>
              <p style={{ fontSize: '0.85rem', textAlign: 'center', maxWidth: '380px', margin: 0, color: 'var(--text-muted)' }}>
                {activePersona === 'EM' 
                  ? 'Once a Product Manager submits a plan and sends it to you, it will appear here for backlog approval.'
                  : 'Once an Engineering Manager reviews and shares a sprint plan, it will appear here for implementation.'
                }
              </p>
            </div>
          ) : (
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', 
              gap: '1.5rem' 
            }}>
              {projects.map((proj) => (
                <div 
                  key={proj.thread_id}
                  onClick={() => router.push(`/plan/${proj.thread_id}`)}
                  style={{
                    background: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid var(--glass-border)',
                    borderRadius: '16px',
                    padding: '1.5rem',
                    cursor: 'pointer',
                    transition: 'var(--transition-smooth)',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    minHeight: '220px',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.1)'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-4px)';
                    e.currentTarget.style.borderColor = 'var(--accent-primary)';
                    e.currentTarget.style.background = 'rgba(255, 255, 255, 0.04)';
                    e.currentTarget.style.boxShadow = '0 12px 28px rgba(0,0,0,0.25)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'none';
                    e.currentTarget.style.borderColor = 'var(--glass-border)';
                    e.currentTarget.style.background = 'rgba(255, 255, 255, 0.02)';
                    e.currentTarget.style.boxShadow = '0 4px 20px rgba(0,0,0,0.1)';
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem', gap: '0.5rem' }}>
                      <h3 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0, color: '#fff', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', width: '70%' }}>
                        {proj.title || "Untitled Session"}
                      </h3>
                      <span className={`badge ${getStatusBadgeClass(proj.status)}`} style={{ flexShrink: 0 }}>
                        {proj.status.replace('_', ' ')}
                      </span>
                    </div>

                    <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem' }}>
                      <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '8px', padding: '6px 8px', textAlign: 'center', flex: 1 }}>
                        <div style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--accent-secondary)' }}>{proj.total_epics || 0}</div>
                        <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Epics</div>
                      </div>
                      <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '8px', padding: '6px 8px', textAlign: 'center', flex: 1 }}>
                        <div style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--accent-primary)' }}>{proj.total_stories || 0}</div>
                        <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Stories</div>
                      </div>
                      <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '8px', padding: '6px 8px', textAlign: 'center', flex: 1 }}>
                        <div style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--success)' }}>{proj.total_story_points || 0}</div>
                        <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Points</div>
                      </div>
                    </div>

                    {proj.ai_summary && (
                      <p style={{ 
                        fontSize: '0.85rem', 
                        color: 'var(--text-secondary)', 
                        lineHeight: '1.5',
                        margin: '0 0 1.25rem 0',
                        display: '-webkit-box',
                        WebkitLineClamp: 3,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                      }}>
                        {proj.ai_summary}
                      </p>
                    )}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '1rem', marginTop: 'auto' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      🕒 {new Date(proj.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <span style={{ fontSize: '0.85rem', color: 'var(--accent-primary)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      {activePersona === 'EM' ? 'Review Backlog' : 'View Backlog'}
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
