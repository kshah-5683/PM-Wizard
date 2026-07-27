'use strict';

'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { supabase } from '../supabase';

export default function LoginPage() {
  const router = useRouter();
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState('PM');
  const [orgId, setOrgId] = useState('org-google');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // If user is already logged in, redirect to dashboard
    const user = localStorage.getItem('currentUser');
    if (user) {
      router.push('/');
    }
  }, [router]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    // Simulate network latency for premium feel
    await new Promise((resolve) => setTimeout(resolve, 800));

    const isSupabaseConfigured = process.env.NEXT_PUBLIC_SUPABASE_URL && 
                                 process.env.NEXT_PUBLIC_SUPABASE_URL !== 'https://mock-project.supabase.co';

    try {
      if (isSupabaseConfigured) {
        console.log("[Auth] Attempting real Supabase authentication...");
        if (isSignUp) {
          if (!email || !password || !name) {
            throw new Error("All fields are required for sign up.");
          }
          const { data, error: signUpError } = await supabase.auth.signUp({
            email,
            password,
            options: {
              data: {
                name,
                role,
                org_id: orgId
              }
            }
          });
          if (signUpError) throw signUpError;
          
          const user = data?.user;
          if (!user) throw new Error("Sign up completed but no user details returned.");

          const currentUserData = {
            email: user.email,
            name: user.user_metadata?.name || name,
            role: user.user_metadata?.role || role,
            orgId: user.user_metadata?.org_id || orgId,
            id: user.id
          };

          localStorage.setItem('currentUser', JSON.stringify(currentUserData));
          localStorage.setItem('activePersona', currentUserData.role);
          localStorage.setItem('activeOrg', currentUserData.orgId);
          if (data.session?.access_token) {
            localStorage.setItem('supabaseToken', data.session.access_token);
          }
          router.push('/');
        } else {
          if (!email || !password) {
            throw new Error("Please fill out all fields.");
          }
          const { data, error: signInError } = await supabase.auth.signInWithPassword({
            email,
            password
          });
          if (signInError) throw signInError;

          const user = data?.user;
          if (!user) throw new Error("Sign in succeeded but no user data returned.");

          const currentUserData = {
            email: user.email,
            name: user.user_metadata?.name || user.email.split('@')[0],
            role: user.user_metadata?.role || "PM",
            orgId: user.user_metadata?.org_id || "default-org",
            id: user.id
          };

          localStorage.setItem('currentUser', JSON.stringify(currentUserData));
          localStorage.setItem('activePersona', currentUserData.role);
          localStorage.setItem('activeOrg', currentUserData.orgId);
          if (data.session?.access_token) {
            localStorage.setItem('supabaseToken', data.session.access_token);
          }
          router.push('/');
        }
      } else {
        // Fallback to simulated offline localStorage auth for sandbox testing
        console.log("[Auth] Supabase URL is mock. Falling back to local simulated authentication...");
        if (isSignUp) {
          if (!email || !password || !name) {
            throw new Error("All fields are required for sign up.");
          }
          
          const users = JSON.parse(localStorage.getItem('registeredUsers') || '[]');
          if (users.find(u => u.email.toLowerCase() === email.toLowerCase())) {
            throw new Error("User with this email already exists.");
          }

          const newUser = {
            email: email.toLowerCase(),
            password,
            name,
            role,
            orgId
          };
          users.push(newUser);
          localStorage.setItem('registeredUsers', JSON.stringify(users));

          localStorage.setItem('currentUser', JSON.stringify(newUser));
          localStorage.setItem('activePersona', role);
          localStorage.setItem('activeOrg', orgId);
          router.push('/');
        } else {
          if (!email || !password) {
            throw new Error("Please fill out all fields.");
          }

          const users = JSON.parse(localStorage.getItem('registeredUsers') || '[]');
          const defaultUsers = [
            { email: 'pm@wizard.com', password: 'password', name: 'Product Manager User', role: 'PM', orgId: 'org-google' },
            { email: 'em@wizard.com', password: 'password', name: 'Engineering Manager User', role: 'EM', orgId: 'org-google' },
            { email: 'dev@wizard.com', password: 'password', name: 'Developer User', role: 'DEV', orgId: 'org-google' }
          ];

          const allUsers = [...defaultUsers, ...users];
          const match = allUsers.find(
            u => u.email.toLowerCase() === email.toLowerCase() && u.password === password
          );

          if (!match) {
            throw new Error("Invalid email or password.");
          }

          localStorage.setItem('currentUser', JSON.stringify(match));
          localStorage.setItem('activePersona', match.role);
          localStorage.setItem('activeOrg', match.orgId);
          router.push('/');
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'radial-gradient(circle at center, #1e1b4b 0%, #09090b 100%)',
      padding: '2rem',
      fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      color: '#fff',
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Decorative Orbs */}
      <div style={{
        position: 'absolute',
        top: '20%',
        left: '25%',
        width: '350px',
        height: '350px',
        background: 'rgba(99, 102, 241, 0.15)',
        filter: 'blur(100px)',
        borderRadius: '50%',
        zIndex: 0
      }}></div>
      <div style={{
        position: 'absolute',
        bottom: '15%',
        right: '20%',
        width: '400px',
        height: '400px',
        background: 'rgba(168, 85, 247, 0.15)',
        filter: 'blur(120px)',
        borderRadius: '50%',
        zIndex: 0
      }}></div>

      <div style={{
        width: '100%',
        maxWidth: '450px',
        zIndex: 1,
        animation: 'fadeIn 0.5s ease-out'
      }}>
        {/* Logo/Identity */}
        <div style={{
          textAlign: 'center',
          marginBottom: '2rem',
        }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '56px',
            height: '56px',
            borderRadius: '16px',
            background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
            fontSize: '1.5rem',
            fontWeight: 800,
            color: '#fff',
            boxShadow: '0 8px 30px rgba(99, 102, 241, 0.3)',
            marginBottom: '1rem'
          }}>PM</div>
          <h1 style={{
            fontSize: '1.8rem',
            fontWeight: 700,
            background: 'linear-gradient(to right, #fff, #94a3b8)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            margin: 0
          }}>PM-Wizard Control Room</h1>
          <p style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: '0.5rem' }}>
            Collaborative Agile & Sprint Planning Middleware
          </p>
        </div>

        {/* Auth Glass Card */}
        <div style={{
          background: 'rgba(15, 23, 42, 0.45)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '20px',
          padding: '2.5rem',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.5)'
        }}>
          <h2 style={{
            fontSize: '1.25rem',
            fontWeight: 600,
            marginBottom: '1.5rem',
            textAlign: 'center'
          }}>{isSignUp ? 'Create your account' : 'Sign in to dashboard'}</h2>

          {error && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              color: '#f87171',
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              fontSize: '0.85rem',
              marginBottom: '1.5rem',
              textAlign: 'center'
            }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {isSignUp && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <label style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600 }}>Full Name</label>
                <input
                  type="text"
                  placeholder="John Doe"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={{
                    padding: '0.75rem 1rem',
                    background: 'rgba(255,255,255,0.03)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: '8px',
                    color: '#fff',
                    outline: 'none',
                    fontSize: '0.9rem',
                    transition: 'border 0.2s'
                  }}
                  required
                />
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600 }}>Email Address</label>
              <input
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={{
                  padding: '0.75rem 1rem',
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  borderRadius: '8px',
                  color: '#fff',
                  outline: 'none',
                  fontSize: '0.9rem'
                }}
                required
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600 }}>Password</label>
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{
                  padding: '0.75rem 1rem',
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  borderRadius: '8px',
                  color: '#fff',
                  outline: 'none',
                  fontSize: '0.9rem'
                }}
                required
              />
            </div>

            {isSignUp && (
              <>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <label style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600 }}>User Persona Role</label>
                  <select
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    style={{
                      padding: '0.75rem 1rem',
                      background: '#1e1b4b',
                      border: '1px solid rgba(255,255,255,0.08)',
                      borderRadius: '8px',
                      color: '#fff',
                      outline: 'none',
                      fontSize: '0.9rem',
                      cursor: 'pointer'
                    }}
                  >
                    <option value="PM">👤 Product Manager (PM)</option>
                    <option value="EM">🔑 Engineering Manager (EM)</option>
                    <option value="DEV">💻 Developer (DEV)</option>
                  </select>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <label style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600 }}>Tenant Organization</label>
                  <select
                    value={orgId}
                    onChange={(e) => setOrgId(e.target.value)}
                    style={{
                      padding: '0.75rem 1rem',
                      background: '#1e1b4b',
                      border: '1px solid rgba(255,255,255,0.08)',
                      borderRadius: '8px',
                      color: '#fff',
                      outline: 'none',
                      fontSize: '0.9rem',
                      cursor: 'pointer'
                    }}
                  >
                    <option value="org-google">🏢 Google</option>
                    <option value="org-microsoft">🏢 Microsoft</option>
                    <option value="org-meta">🏢 Meta</option>
                  </select>
                </div>
              </>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                marginTop: '0.5rem',
                padding: '0.75rem',
                border: 'none',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
                color: '#fff',
                fontSize: '0.95rem',
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'opacity 0.2s, transform 0.1s',
                boxShadow: '0 4px 15px rgba(99, 102, 241, 0.3)'
              }}
            >
              {loading ? 'Processing...' : (isSignUp ? 'Register & Enter' : 'Sign In')}
            </button>
          </form>

          {/* Seed User Help box */}
          {!isSignUp && (
            <div style={{
              marginTop: '1.5rem',
              padding: '0.75rem 1rem',
              background: 'rgba(255,255,255,0.02)',
              border: '1px solid rgba(255,255,255,0.04)',
              borderRadius: '8px',
              fontSize: '0.75rem',
              color: '#94a3b8',
              lineHeight: '1.4'
            }}>
              💡 <strong>Seed testing accounts (Password: <code>password</code>)</strong>:
              <div style={{ marginTop: '0.25rem' }}>• PM: <code>pm@wizard.com</code></div>
              <div>• EM: <code>em@wizard.com</code></div>
              <div>• Developer: <code>dev@wizard.com</code></div>
            </div>
          )}

          <div style={{
            marginTop: '1.5rem',
            textAlign: 'center',
            fontSize: '0.85rem'
          }}>
            <span style={{ color: '#94a3b8' }}>
              {isSignUp ? 'Already have an account? ' : "Don't have an account? "}
            </span>
            <button
              type="button"
              onClick={() => {
                setIsSignUp(!isSignUp);
                setError(null);
              }}
              style={{
                background: 'none',
                border: 'none',
                color: '#818cf8',
                cursor: 'pointer',
                fontWeight: 600,
                padding: 0
              }}
            >
              {isSignUp ? 'Sign In' : 'Sign Up'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
