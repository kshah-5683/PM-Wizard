import io
import os
import base64
import litellm
import re

# Optional third-party imports with fallbacks
try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

VISION_MODEL = os.getenv("VISION_MODEL", "groq/llama-3.2-11b-vision-preview")

async def describe_image(img_bytes: bytes, extension: str) -> str:
    """
    Submits image bytes to the vision model via LiteLLM to get a text transcription/description.
    """
    try:
        base64_image = base64.b64encode(img_bytes).decode('utf-8')
        mime_type = f"image/{extension}" if extension in ('png', 'jpeg', 'jpg', 'webp', 'gif') else "image/png"
        
        response = await litellm.acompletion(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analyze this wireframe, diagram, screenshot, or document page image. Transcribe all readable text, outline the core UI components, business logic rules, and structural tables represented. Provide a structured explanation suited for software engineering and sprint backlog planning."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=600
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Vision] Failed to analyze image: {e}")
        return f"[Image content transcription failed: {str(e)}]"

async def clean_and_format_markdown(raw_text: str) -> str:
    """
    Cleans up raw extracted texts, table lists, and image annotations into a well-structured markdown PRD.
    """
    prompt = (
        "You are a Senior Product Manager and Technical Writer.\n"
        "Your task is to take the following raw extracted content from an uploaded document (which includes raw text, structural tables, and image/diagram descriptions) "
        "and organize it into a beautiful, coherent Product Requirement Document (PRD) in Markdown format.\n"
        "Rules:\n"
        "1. Retain all original requirements, constraints, details, tables, and tech stacks.\n"
        "2. Structure it cleanly with clear headers (H1, H2, H3), lists, and formatted tables.\n"
        "3. Incorporate any image/diagram descriptions as clear contextual references (e.g. '> [!NOTE] Wireframe/Image context...').\n"
        "4. Do NOT output any intro/outro conversation (e.g. 'Here is your markdown...'). Output ONLY the final structured markdown document."
    )
    
    try:
        from middleware.llm import aresilient_completion
        from middleware.config import LIGHTWEIGHT_MODEL
        
        response = await aresilient_completion(
            model=LIGHTWEIGHT_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": raw_text}
            ],
            max_tokens=4000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Parser] Formatting LLM failed: {e}. Returning raw content.")
        return raw_text

async def process_pdf(file_bytes: bytes) -> str:
    """
    Extracts text, images, and basic layout info from a PDF.
    """
    if not PYPDF_AVAILABLE:
        return (
            "# Uploaded PDF Document\n\n"
            "⚠️ **Warning:** The `pypdf` package is not installed on this server workspace. "
            "Please check that dependencies in `requirements.txt` are installed. "
            "Raw contents could not be parsed."
        )
        
    pdf_file = io.BytesIO(file_bytes)
    reader = pypdf.PdfReader(pdf_file)
    text_blocks = []
    
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        text_blocks.append(f"## --- PDF Page {i+1} ---\n\n{page_text}")
        
        # Parse inline images
        try:
            for img_idx, img in enumerate(page.images):
                img_bytes = img.data
                img_ext = img.name.split('.')[-1].lower() if '.' in img.name else 'png'
                # Analyze image using vision API
                description = await describe_image(img_bytes, img_ext)
                text_blocks.append(f"\n> [!NOTE]\n> **Extracted UI Wireframe/Diagram (Page {i+1}, Image {img_idx+1})**:\n> {description}\n")
        except Exception as img_err:
            print(f"[Parser] Failed to extract inline image on page {i+1}: {img_err}")
            
    return "\n\n".join(text_blocks)

async def process_docx(file_bytes: bytes) -> str:
    """
    Extracts text paragraphs, reconstructs tables, and decodes image attachments from a DOCX file.
    """
    if not DOCX_AVAILABLE:
        return (
            "# Uploaded DOCX Document\n\n"
            "⚠️ **Warning:** The `python-docx` package is not installed on this server workspace. "
            "Please check that dependencies in `requirements.txt` are installed. "
            "Raw contents could not be parsed."
        )

    docx_file = io.BytesIO(file_bytes)
    doc = docx.Document(docx_file)
    content = []
    
    # Iterate through child elements to keep tables and paragraphs in correct order
    for block in doc.element.body:
        if block.tag.endswith('p'):  # Paragraph
            p = docx.text.paragraph.Paragraph(block, doc)
            if p.text.strip():
                content.append(p.text)
        elif block.tag.endswith('tbl'):  # Table
            table = docx.table.Table(block, doc)
            md_table = []
            for row_idx, row in enumerate(table.rows):
                row_data = [cell.text.replace('\n', ' ').strip() for cell in row.cells]
                # Filter duplicate cells resulting from merged rows
                unique_row_data = []
                for cell in row_data:
                    if not unique_row_data or unique_row_data[-1] != cell:
                        unique_row_data.append(cell)
                md_table.append("| " + " | ".join(unique_row_data) + " |")
                if row_idx == 0:
                    md_table.append("| " + " | ".join(["---"] * len(unique_row_data)) + " |")
            if md_table:
                content.append("\n" + "\n".join(md_table) + "\n")

    # Extract image parts
    try:
        image_idx = 1
        for inline_shape in doc.inline_shapes:
            if inline_shape.has_picture:
                img_part = inline_shape._inline.graphic.graphicData.pic.blipFill.blip.embed
                img_data = doc.part.related_parts[img_part].image.blob
                img_filename = doc.part.related_parts[img_part].image.filename or f"image_{image_idx}.png"
                img_ext = img_filename.split('.')[-1].lower() or 'png'
                
                description = await describe_image(img_data, img_ext)
                content.append(f"\n> [!NOTE]\n> **Embedded Image {image_idx} ({img_filename})**:\n> {description}\n")
                image_idx += 1
    except Exception as img_err:
        print(f"[Parser] Failed to extract DOCX pictures: {img_err}")
        
    return "\n\n".join(content)

async def process_uploaded_document(file_bytes: bytes, extension: str) -> str:
    """
    Dispatcher function to parse uploaded documents by file type.
    """
    raw_content = ""
    if extension in ('txt', 'md'):
        raw_content = file_bytes.decode('utf-8', errors='ignore')
    elif extension == 'pdf':
        raw_content = await process_pdf(file_bytes)
    elif extension == 'docx':
        raw_content = await process_docx(file_bytes)
    elif extension in ('png', 'jpg', 'jpeg', 'webp'):
        description = await describe_image(file_bytes, extension)
        raw_content = f"# Extracted Wireframe/Image Context\n\n## Description\n{description}"
    else:
        raise ValueError(f"Unsupported file format: {extension}")
        
    # Clean up and structure the markdown document
    cleaned_markdown = await clean_and_format_markdown(raw_content)
    return cleaned_markdown
