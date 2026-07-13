"use client";

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

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

  // Fetch recent projects
  useEffect(() => {
    async function fetchProjects() {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/v1/projects');
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
  }, []);

  const handleStartPlanning = async (e) => {
    e.preventDefault();
    if (!rawPrd.trim()) {
      setError("Please enter your Product Requirement Document (PRD) content.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await fetch('http://127.0.0.1:8000/api/v1/plan/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          raw_prd: rawPrd,
          source_document: sourceDocument || null,
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
        <div>
          <button className="btn btn-secondary" onClick={() => router.refresh()}>Refresh Panel</button>
        </div>
      </header>

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
              <input 
                type="text" 
                className="input-field" 
                placeholder="e.g. https://notion.so/my-workspace/prd-document"
                value={sourceDocument}
                onChange={(e) => setSourceDocument(e.target.value)}
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

        {/* Sidebar History list */}
        <div className="glass-panel history-card">
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
  );
}
