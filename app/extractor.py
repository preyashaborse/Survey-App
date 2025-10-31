import os
import json
from typing import Optional, Dict, Tuple
from io import BytesIO

from docx import Document  # python-docx
from pypdf import PdfReader
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def read_pdf_text(file_bytes: bytes) -> Tuple[str, Dict[int, int]]:
    """
    Extract text from PDF and return text with page-to-line mapping.
    Returns: (full_text, line_to_page_map) where line_to_page_map maps line number to page number.
    """
    reader = PdfReader(BytesIO(file_bytes))
    parts: list[str] = []
    line_to_page: Dict[int, int] = {}
    current_line = 0
    
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text:
            lines = text.splitlines()
            for line in lines:
                if line.strip():  # Only count non-empty lines
                    line_to_page[current_line] = page_num
                    current_line += 1
            parts.append(text)
    
    return "\n".join(parts), line_to_page


def read_docx_text(file_bytes: bytes) -> Tuple[str, Dict[int, int]]:
    """
    Extract text from DOCX and return text with paragraph-to-line mapping.
    Returns: (full_text, line_to_paragraph_map) where line_to_paragraph_map maps line number to paragraph number.
    """
    doc = Document(BytesIO(file_bytes))
    parts: list[str] = []
    line_to_paragraph: Dict[int, int] = {}
    current_line = 0
    
    for para_num, para in enumerate(doc.paragraphs, start=1):
        if para.text:
            lines = para.text.splitlines()
            for line in lines:
                if line.strip():
                    line_to_paragraph[current_line] = para_num
                    current_line += 1
            parts.append(para.text)
    
    return "\n".join(parts), line_to_paragraph


def extract_text_from_file_with_location(filename: str, file_bytes: bytes) -> Tuple[str, Dict[int, int], str]:
    """
    Extract text with location metadata.
    Returns: (full_text, line_to_location_map, file_type)
    """
    name = filename.lower()
    if name.endswith(".pdf"):
        text, line_map = read_pdf_text(file_bytes)
        return text, line_map, "pdf"
    if name.endswith(".docx"):
        text, line_map = read_docx_text(file_bytes)
        return text, line_map, "docx"
    raise ValueError("Unsupported file type. Please upload a .pdf or .docx file.")


def extract_field_value_with_gpt(
    document_text: str,
    field: str,
    line_to_location_map: Optional[Dict[int, int]] = None,
    file_type: Optional[str] = None
) -> Tuple[Optional[str], Optional[Dict]]:
    """
    Extract field value using GPT-4 with location information.
    
    Args:
        document_text: The document text to search
        field: The field name to extract
        line_to_location_map: Optional mapping of line numbers to page/paragraph numbers
        file_type: Optional file type ("pdf" or "docx")
    
    Returns:
        Tuple of (value, location_info_dict) where location_info_dict contains:
        - page_number or paragraph_number
        - line_number
        - context (surrounding text)
        - section (if identifiable)
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it in your .env file.")
    
    client = OpenAI(api_key=api_key)
    
    # Prepare the prompt with location hints
    location_hint = ""
    if file_type == "pdf":
        location_hint = " If found, provide the page number and approximate line number."
    elif file_type == "docx":
        location_hint = " If found, provide the paragraph number and approximate line number."
    
    prompt = f"""You are a document analysis assistant. Extract the value for the field "{field}" from the following document text.

Document Text:
{document_text}

Instructions:
1. Find the value associated with the field "{field}" in the document.
2. The field might appear in various formats like:
   - "{field}: value"
   - "{field} = value"
   - "{field} - value"
   - Or as a labeled field in a form
3. Extract the complete value accurately.
4. Provide location information: approximate line number where found, surrounding context (2-3 lines before and after), and any identifiable section (e.g., "Header", "Body", "Contact Information", etc.).{location_hint}

Return your response as a valid JSON object with this exact structure:
{{
    "value": "the extracted value or null if not found",
    "location": {{
        "line_number": <approximate line number or null>,
        "context": "surrounding text context (2-3 lines before and after)",
        "section": "document section name or null"
    }}
}}

If the field is not found, return: {{"value": null, "location": {{"line_number": null, "context": null, "section": null}}}}

Return ONLY valid JSON, no additional text or explanation."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # Using GPT-4o (you can change to "gpt-4-turbo" or "gpt-4" if needed)
            messages=[
                {"role": "system", "content": "You are a precise document extraction assistant. Always return valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Low temperature for consistent extraction
            response_format={"type": "json_object"}  # Force JSON response
        )
        
        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        
        value = result.get("value")
        location_data = result.get("location", {})
        
        # Enhance location data with actual page/paragraph numbers if mapping is available
        if line_to_location_map and location_data.get("line_number") is not None:
            line_num = location_data["line_number"]
            if isinstance(line_num, int) and line_num in line_to_location_map:
                if file_type == "pdf":
                    location_data["page_number"] = line_to_location_map.get(line_num)
                elif file_type == "docx":
                    location_data["paragraph_number"] = line_to_location_map.get(line_num)
        
        return value if value else None, location_data if location_data else None
        
    except json.JSONDecodeError as e:
        # Fallback: try to extract value from response text
        print(f"JSON decode error: {e}, response: {result_text}")
        return None, None
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        raise Exception(f"Failed to extract field using GPT-4: {str(e)}")

