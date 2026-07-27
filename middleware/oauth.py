import os
import time
import urllib.parse
import httpx
from typing import Optional, Dict
from middleware.database import db_manager

# Redirect URI fallbacks/defaults
NOTION_CLIENT_ID = os.getenv("NOTION_CLIENT_ID")
NOTION_CLIENT_SECRET = os.getenv("NOTION_CLIENT_SECRET")
NOTION_REDIRECT_URI = os.getenv("NOTION_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/auth/notion/callback")

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/auth/github/callback")

ATLASSIAN_CLIENT_ID = os.getenv("ATLASSIAN_CLIENT_ID")
ATLASSIAN_CLIENT_SECRET = os.getenv("ATLASSIAN_CLIENT_SECRET")
ATLASSIAN_REDIRECT_URI = os.getenv("ATLASSIAN_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/auth/atlassian/callback")

def get_auth_url(provider: str, user_id: str, org_id: str) -> str:
    """
    Generates the external OAuth redirect URL for the given provider.
    The state parameter encodes '{user_id}:{org_id}' to associate the returning auth code.
    """
    state_str = f"{user_id}:{org_id}"
    state = urllib.parse.quote(state_str)
    
    if provider == "notion":
        if not NOTION_CLIENT_ID:
            raise ValueError("NOTION_CLIENT_ID is not configured in the server environment.")
        return (
            f"https://api.notion.com/v1/oauth/authorize?"
            f"client_id={NOTION_CLIENT_ID}&"
            f"response_type=code&"
            f"owner=user&"
            f"redirect_uri={urllib.parse.quote(NOTION_REDIRECT_URI)}&"
            f"state={state}"
        )
    elif provider == "github":
        if not GITHUB_CLIENT_ID:
            raise ValueError("GITHUB_CLIENT_ID is not configured in the server environment.")
        return (
            f"https://github.com/login/oauth/authorize?"
            f"client_id={GITHUB_CLIENT_ID}&"
            f"redirect_uri={urllib.parse.quote(GITHUB_REDIRECT_URI)}&"
            f"scope={urllib.parse.quote('repo read:user')}&"
            f"state={state}"
        )
    elif provider == "atlassian":
        if not ATLASSIAN_CLIENT_ID:
            raise ValueError("ATLASSIAN_CLIENT_ID is not configured in the server environment.")
        scopes = "read:jira-work write:jira-work read:confluence-content write:confluence-content offline_access read:me"
        return (
            f"https://auth.atlassian.com/authorize?"
            f"audience=api.atlassian.com&"
            f"client_id={ATLASSIAN_CLIENT_ID}&"
            f"scope={urllib.parse.quote(scopes)}&"
            f"redirect_uri={urllib.parse.quote(ATLASSIAN_REDIRECT_URI)}&"
            f"state={state}&"
            f"response_type=code&"
            f"prompt=consent"
        )
    else:
        raise ValueError(f"Invalid OAuth provider: {provider}")

async def exchange_auth_code(provider: str, code: str) -> Dict:
    """
    Exchanges the authorization code for access tokens from the provider.
    """
    async with httpx.AsyncClient() as client:
        if provider == "notion":
            # Notion requires client credentials in Basic auth header or JSON body
            auth_header = base64_auth_header(NOTION_CLIENT_ID or "", NOTION_CLIENT_SECRET or "")
            res = await client.post(
                "https://api.notion.com/v1/oauth/token",
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": NOTION_REDIRECT_URI
                },
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json"
                }
            )
            res.raise_for_status()
            data = res.json()
            return {
                "access_token": data.get("access_token"),
                "refresh_token": None,
                "expires_in": None,
                "tenant_id": data.get("workspace_id"),
                "scopes": [data.get("workspace_name") or "workspace"]
            }
            
        elif provider == "github":
            res = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": GITHUB_REDIRECT_URI
                },
                headers={"Accept": "application/json"}
            )
            res.raise_for_status()
            data = res.json()
            # Fetch user login as tenant_id
            access_token = data.get("access_token")
            user_res = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {access_token}"}
            )
            user_login = "github-user"
            if user_res.is_success:
                user_login = user_res.json().get("login") or "github-user"
            return {
                "access_token": access_token,
                "refresh_token": None,
                "expires_in": None,
                "tenant_id": user_login,
                "scopes": (data.get("scope") or "repo,user").split(",")
            }
            
        elif provider == "atlassian":
            res = await client.post(
                "https://auth.atlassian.com/oauth/token",
                json={
                    "grant_type": "authorization_code",
                    "client_id": ATLASSIAN_CLIENT_ID,
                    "client_secret": ATLASSIAN_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": ATLASSIAN_REDIRECT_URI
                },
                headers={"Content-Type": "application/json"}
            )
            res.raise_for_status()
            data = res.json()
            access_token = data.get("access_token")
            
            # Fetch Atlassian cloud_id (tenant_id)
            cloud_id = None
            res_resources = await client.get(
                "https://api.atlassian.com/oauth/token/accessible-resources",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json"
                }
            )
            if res_resources.is_success:
                resources = res_resources.json()
                if resources and len(resources) > 0:
                    cloud_id = resources[0].get("id")
            
            return {
                "access_token": access_token,
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in"),
                "tenant_id": cloud_id or "atlassian-cloud",
                "scopes": (data.get("scope") or "").split(" ")
            }
        else:
            raise ValueError(f"Invalid provider: {provider}")

def base64_auth_header(client_id: str, client_secret: str) -> str:
    import base64
    text = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(text.encode('utf-8')).decode('utf-8')
    return f"Basic {encoded}"

async def process_oauth_callback(provider: str, code: str, state: str) -> Dict:
    """
    Exchanges the code, extracts the user_id/org_id from state, and persists 
    the encrypted credentials securely in the database.
    """
    # Parse state "{user_id}:{org_id}"
    state_str = urllib.parse.unquote(state)
    if ":" not in state_str:
        raise ValueError("Invalid OAuth state parameter.")
        
    user_id, org_id = state_str.split(":", 1)
    
    # Exchange code for tokens
    token_data = await exchange_auth_code(provider, code)
    
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")
    tenant_id = token_data.get("tenant_id")
    scopes = token_data.get("scopes") or []
    
    expires_at_timestamp = None
    if expires_in:
        expires_at_timestamp = time.time() + float(expires_in)
        
    # Persist in DB (save_integration handles encryption internally)
    await db_manager.save_integration(
        user_id=user_id,
        provider=provider,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at_timestamp=expires_at_timestamp,
        scopes=scopes,
        tenant_id=tenant_id,
        org_id=org_id
    )
    
    return {
        "user_id": user_id,
        "org_id": org_id,
        "provider": provider,
        "tenant_id": tenant_id
    }
