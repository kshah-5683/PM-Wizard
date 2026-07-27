import re
import urllib.parse
from typing import Optional
import httpx
from middleware.oauth import get_valid_token
from middleware.document_parser import clean_and_format_markdown

def extract_notion_page_id(url: str) -> Optional[str]:
    """
    Extracts the page ID from a Notion URL.
    Handles standard formats:
    - https://www.notion.so/workspace/Page-Name-a1b2c3d4e5f67890a1b2c3d4e5f67890
    - https://notion.so/a1b2c3d4e5f67890a1b2c3d4e5f67890
    - https://www.notion.so/a1b2c3d4e5f67890a1b2c3d4e5f67890?v=...
    """
    clean_url = url.split('?')[0]
    segments = clean_url.rstrip('/').split('/')
    if not segments:
        return None
    last_segment = segments[-1]
    
    # Try to find a 32-char hex string (UUID without hyphens) or 36-char (UUID with hyphens) at the end
    match_hex = re.search(r'([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$', last_segment, re.IGNORECASE)
    if match_hex:
        return match_hex.group(1).replace('-', '')
        
    match_any = re.search(r'([a-f0-9]{32})', last_segment, re.IGNORECASE)
    if match_any:
        return match_any.group(1)
        
    return None

def extract_confluence_page_id(url: str) -> Optional[str]:
    """
    Extracts the page ID from a Confluence URL.
    Handles:
    - https://workspace.atlassian.net/wiki/spaces/SPACE/pages/123456/Page+Title
    - https://workspace.atlassian.net/wiki/pages/viewpage.action?pageId=123456
    """
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if 'pageId' in query:
        return query['pageId'][0]
        
    match = re.search(r'/pages/(\d+)', parsed.path)
    if match:
        return match.group(1)
        
    return None

def extract_rich_text(rich_text_list: list) -> str:
    text = ""
    for rt in rich_text_list:
        content = rt.get("text", {}).get("content", "")
        annotations = rt.get("annotations", {})
        if annotations.get("code"):
            content = f"`{content}`"
        if annotations.get("bold"):
            content = f"**{content}**"
        if annotations.get("italic"):
            content = f"*{content}*"
        if annotations.get("strikethrough"):
            content = f"~~{content}~~"
        text += content
    return text

async def fetch_notion_blocks(block_id: str, access_token: str, client: httpx.AsyncClient) -> list:
    blocks = []
    url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    params = {}
    while True:
        res = await client.get(url, headers=headers, params=params)
        if res.status_code == 404:
            print(f"[Notion] Block/Page {block_id} not found.")
            break
        res.raise_for_status()
        data = res.json()
        blocks.extend(data.get("results", []))
        if data.get("has_more") and data.get("next_cursor"):
            params["start_cursor"] = data["next_cursor"]
        else:
            break
            
    return blocks

async def notion_blocks_to_markdown(block_id: str, access_token: str, client: httpx.AsyncClient, depth: int = 0) -> str:
    if depth > 5:
        return ""
    
    blocks = await fetch_notion_blocks(block_id, access_token, client)
    md_content = []
    
    for block in blocks:
        block_type = block.get("type")
        sub_block_id = block.get("id")
        has_children = block.get("has_children", False)
        
        block_md = ""
        
        if block_type == "paragraph":
            text = extract_rich_text(block["paragraph"]["rich_text"])
            block_md = text
        elif block_type == "heading_1":
            text = extract_rich_text(block["heading_1"]["rich_text"])
            block_md = f"# {text}"
        elif block_type == "heading_2":
            text = extract_rich_text(block["heading_2"]["rich_text"])
            block_md = f"## {text}"
        elif block_type == "heading_3":
            text = extract_rich_text(block["heading_3"]["rich_text"])
            block_md = f"### {text}"
        elif block_type == "bulleted_list_item":
            text = extract_rich_text(block["bulleted_list_item"]["rich_text"])
            block_md = f"* {text}"
        elif block_type == "numbered_list_item":
            text = extract_rich_text(block["numbered_list_item"]["rich_text"])
            block_md = f"1. {text}"
        elif block_type == "to_do":
            checked = block["to_do"].get("checked", False)
            box = "[x]" if checked else "[ ]"
            text = extract_rich_text(block["to_do"]["rich_text"])
            block_md = f"- {box} {text}"
        elif block_type == "code":
            lang = block["code"].get("language", "plain text")
            text = extract_rich_text(block["code"]["rich_text"])
            block_md = f"```{lang}\n{text}\n```"
        elif block_type == "image":
            img_info = block["image"]
            img_type = img_info.get("type")
            url = ""
            if img_type == "external":
                url = img_info.get("external", {}).get("url", "")
            elif img_type == "file":
                url = img_info.get("file", {}).get("url", "")
            if url:
                block_md = f"![image]({url})"
        elif block_type == "table":
            table_rows = await fetch_notion_blocks(sub_block_id, access_token, client)
            md_rows = []
            for idx, row in enumerate(table_rows):
                if row.get("type") == "table_row":
                    cells = row["table_row"].get("cells", [])
                    row_cells = [extract_rich_text(cell) for cell in cells]
                    md_rows.append("| " + " | ".join(row_cells) + " |")
                    if idx == 0:
                        md_rows.append("| " + " | ".join(["---"] * len(row_cells)) + " |")
            if md_rows:
                block_md = "\n" + "\n".join(md_rows) + "\n"
        elif block_type == "quote":
            text = extract_rich_text(block["quote"]["rich_text"])
            block_md = f"> {text}"
        elif block_type == "callout":
            text = extract_rich_text(block["callout"]["rich_text"])
            icon_info = block["callout"].get("icon")
            icon_str = ""
            if icon_info:
                if icon_info.get("type") == "emoji":
                    icon_str = icon_info.get("emoji", "") + " "
            block_md = f"> [!NOTE]\n> {icon_str}{text}"
        elif block_type == "divider":
            block_md = "---"
        elif block_type == "child_page":
            title = block["child_page"].get("title", "")
            block_md = f"*[Link to Child Page: {title}]*"
        
        if has_children and block_type not in ("table", "child_page"):
            children_md = await notion_blocks_to_markdown(sub_block_id, access_token, client, depth + 1)
            if children_md:
                indented = "\n".join("  " + line for line in children_md.split("\n"))
                block_md = f"{block_md}\n{indented}"
                
        if block_md:
            md_content.append(block_md)
            
    return "\n\n".join(md_content)

async def fetch_notion_document(page_id: str, access_token: str) -> str:
    """
    Fetches the blocks of a Notion page and converts them into clean markdown.
    """
    async with httpx.AsyncClient() as client:
        # Fetch page title first
        url = f"https://api.notion.com/v1/pages/{page_id}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": "2022-06-28"
        }
        title = "Notion PRD Document"
        try:
            res = await client.get(url, headers=headers)
            if res.is_success:
                page_data = res.json()
                properties = page_data.get("properties", {})
                # Try finding standard Title property (sometimes named 'title', 'Name', etc.)
                for k, prop in properties.items():
                    if prop.get("type") == "title":
                        title_list = prop.get("title", [])
                        if title_list:
                            title = title_list[0].get("text", {}).get("content", "Notion PRD Document")
                        break
        except Exception as e:
            print(f"[Notion] Failed to fetch page title details: {e}")
            
        # Fetch blocks
        raw_markdown = await notion_blocks_to_markdown(page_id, access_token, client)
        full_text = f"# {title}\n\n{raw_markdown}"
        
        # Format markdown via the lightweight LLM cleaner to ensure premium document aesthetics
        cleaned_md = await clean_and_format_markdown(full_text)
        return cleaned_md

async def fetch_confluence_document(page_id: str, cloud_id: str, access_token: str) -> str:
    """
    Fetches the XHTML body of a Confluence page and converts it to markdown via our formatting LLM.
    """
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/wiki/rest/api/content/{page_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    params = {
        "expand": "body.storage"
    }
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()
        
        title = data.get("title", "Confluence Document")
        body_html = data.get("body", {}).get("storage", {}).get("value", "")
        
        raw_content = f"# {title}\n\n{body_html}"
        
        cleaned_md = await clean_and_format_markdown(raw_content)
        return cleaned_md

async def fetch_external_document(url: str, user_id: str, org_id: str) -> str:
    """
    Dispatches document fetching to Notion or Confluence based on the URL type.
    """
    # 1. Check Notion
    notion_id = extract_notion_page_id(url)
    if notion_id:
        print(f"[Resolver] Resolving Notion URL: {url} (ID: {notion_id})")
        token = await get_valid_token(user_id, "notion", org_id)
        if not token:
            raise ValueError("Notion integration is not connected. Please connect it in settings.")
        return await fetch_notion_document(notion_id, token)
        
    # 2. Check Confluence
    confluence_id = extract_confluence_page_id(url)
    if confluence_id:
        print(f"[Resolver] Resolving Confluence URL: {url} (ID: {confluence_id})")
        # For Atlassian, we need both token and cloud_id (tenant_id)
        from middleware.database import db_manager
        integration = await db_manager.get_integration(user_id, "atlassian", org_id)
        if not integration:
            raise ValueError("Atlassian integration is not connected. Please connect it in settings.")
        cloud_id = integration.get("tenant_id")
        if not cloud_id:
            raise ValueError("Atlassian Cloud ID is not resolved. Please reconnect the integration.")
            
        token = await get_valid_token(user_id, "atlassian", org_id)
        if not token:
            raise ValueError("Atlassian token could not be fetched/refreshed. Please reconnect the integration.")
            
        return await fetch_confluence_document(confluence_id, cloud_id, token)
        
    raise ValueError("Unsupported or invalid source document URL. Only Notion and Confluence URLs are supported.")
