import os
import json
import tiktoken
import hashlib
import asyncio
from typing import Optional, Dict, Tuple, List
from io import BytesIO

from docx import Document  # python-docx
from pypdf import PdfReader
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv

# Load environment variables from project root .env file
# override=True ensures .env file values take precedence over system environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), override=True)



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


def chunk_document(
    document_text: str,
    chunk_size_tokens: int,
    overlap_tokens: int = 0,
    encoding_name: str = "o200k_base"
) -> List[str]:
    """
    Chunk document into smaller pieces with optional overlap.
    
    Args:
        document_text: Full document text to chunk
        chunk_size_tokens: Target token size per chunk
        overlap_tokens: Number of tokens to overlap between chunks (default: 0)
        encoding_name: Tiktoken encoding to use
    
    Returns:
        List of text chunks
    """
    # Create encoder once
    enc = tiktoken.get_encoding(encoding_name)
    
    def num_tokens(text: str) -> int:
        return len(enc.encode(text))
    
    # If document fits in one chunk, return as-is
    doc_tokens = num_tokens(document_text)
    if doc_tokens <= chunk_size_tokens:
        return [document_text]
    
    chunks = []
    max_chunk_chars = chunk_size_tokens * 4  # Rough estimate: 1 token ≈ 4 chars
    
    text = document_text
    start = 0
    
    while start < len(text):
        # Calculate end position
        end = min(len(text), start + max_chunk_chars)
        chunk = text[start:end]
        
        # Try to not break in the middle of a line
        if end < len(text):
            next_nl = text.find("\n", end)
            if next_nl != -1 and next_nl < end + 500:  # Only adjust if close
                end = next_nl + 1
                chunk = text[start:end]
        
        if chunk.strip():
            # Check token count and split further if needed
            chunk_tokens = num_tokens(chunk)
            if chunk_tokens > chunk_size_tokens:
                # Split further by lines
                lines = chunk.splitlines()
                sub = []
                sub_text = ""
                for l in lines:
                    new_sub_text = sub_text + ("\n" if sub_text else "") + l
                    new_sub_tokens = num_tokens(new_sub_text)
                    
                    if new_sub_tokens >= chunk_size_tokens and sub:
                        chunks.append(sub_text)
                        sub = [l]
                        sub_text = l
                    else:
                        sub.append(l)
                        sub_text = new_sub_text
                if sub:
                    chunks.append(sub_text)
            else:
                chunks.append(chunk)
        
        # Move start position with overlap
        if overlap_tokens > 0 and end < len(text):
            # Calculate overlap in characters (approximate)
            overlap_chars = overlap_tokens * 4
            # Move start back by overlap amount for next chunk
            start = max(0, end - overlap_chars)
            # Adjust to line boundary
            if start > 0:
                prev_nl = text.rfind("\n", 0, start)
                if prev_nl != -1:
                    start = prev_nl + 1
        else:
            start = end
        
        if start >= len(text):
            break
    
    return chunks


def get_cache_key(
    document_text: str,
    chunk_size_tokens: int,
    overlap_tokens: int,
    encoding_name: str
) -> str:
    """Generate unique cache key for document + chunking parameters"""
    # Hash document text (use first 1000 chars + length for efficiency)
    doc_hash_input = document_text[:1000] + str(len(document_text))
    doc_hash = hashlib.md5(doc_hash_input.encode()).hexdigest()
    # Include chunking parameters in key
    key = f"{doc_hash}_{chunk_size_tokens}_{overlap_tokens}_{encoding_name}"
    return key


# Module-level cache for chunks
_chunk_cache: Dict[str, List[str]] = {}


def chunk_document_cached(
    document_text: str,
    chunk_size_tokens: int,
    overlap_tokens: int = 0,
    encoding_name: str = "o200k_base"
) -> List[str]:
    """
    Get chunks for document, using cache if available.
    
    Args:
        document_text: Full document text to chunk
        chunk_size_tokens: Target token size per chunk
        overlap_tokens: Number of tokens to overlap between chunks (default: 0)
        encoding_name: Tiktoken encoding to use
    
    Returns:
        List of text chunks (cached if previously computed)
    """
    # Generate cache key
    cache_key = get_cache_key(document_text, chunk_size_tokens, overlap_tokens, encoding_name)
    
    # Check cache
    if cache_key in _chunk_cache:
        return _chunk_cache[cache_key]
    
    # Chunk document
    chunks = chunk_document(document_text, chunk_size_tokens, overlap_tokens, encoding_name)
    
    # Store in cache (limit cache size to prevent memory issues)
    if len(_chunk_cache) >= 10:
        # Remove oldest entry (simple FIFO - remove first key)
        first_key = next(iter(_chunk_cache))
        del _chunk_cache[first_key]
    
    _chunk_cache[cache_key] = chunks
    return chunks


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
    
    project_id = os.getenv("OPENAI_PROJECT_ID")
    
    client = OpenAI(
        api_key=api_key,
        project=project_id
    )
    
    # Get cached chunks (with 200 token overlap to prevent boundary issues)
    chunks = chunk_document_cached(
        document_text=document_text,
        chunk_size_tokens=4000,
        overlap_tokens=200,
        encoding_name="o200k_base"
    )

    # --- Sequentially send each chunk to GPT-4.1 ---
    location_hint = ""
    if file_type == "pdf":
        location_hint = " If found, provide the page number and approximate line number."
    elif file_type == "docx":
        location_hint = " If found, provide the paragraph number and approximate line number."

    for idx, chunk in enumerate(chunks):
        prompt = f"""You are a document analysis assistant. Extract the value for the field \"{field}\" from the following document text.\n\nDocument Text:\n{chunk}\n\nInstructions:\n1. Find the value associated with the field \"{field}\" in the document.\n2. The field might appear in various formats like:\n   - \"{field}: value\"\n   - \"{field} = value\"\n   - \"{field} - value\"\n   - Or as a labeled field in a form\n3. Extract the complete value accurately.\n4. Provide location information: approximate line number where found, surrounding context (2-3 lines before and after), and any identifiable section (e.g., \"Header\", \"Body\", \"Contact Information\", etc.).{location_hint}\n\nReturn your response as a valid JSON object with this exact structure:\n{{\n    \"value\": \"the extracted value or null if not found\",\n    \"location\": {{\n        \"line_number\": <approximate line number or null>,\n        \"context\": \"surrounding text context (2-3 lines before and after)\",\n        \"section\": \"document section name or null\"\n    }}\n}}\n\nIf the field is not found, return: {{\"value\": null, \"location\": {{\"line_number\": null, \"context\": null, \"section\": null}}}}\n\nReturn ONLY valid JSON, no additional text or explanation."""
        try:
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": "You are a precise document extraction assistant. Always return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
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
            # If value found, return immediately
            if value:
                return value, location_data if location_data else None
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}, response: {result_text}")
            continue
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            continue
    # If not found in any chunk
    return None, None


async def extract_bulk_questions_with_gpt(
    document_text: str,
    questions: list,
    filename: str,
    line_to_location_map: Optional[Dict[int, int]] = None,
    file_type: Optional[str] = None,
    all_documents: Optional[list] = None
) -> list:
    """
    Extract answers for multiple questions using GPT-4.1 with confidence scores and citations.
    Uses document chunking to stay within token limits.
    Supports multiple documents - combines them with document markers.
    
    Args:
        document_text: The full document text to search (may contain multiple documents with markers)
        questions: List of question objects with id, text, type, and optional options
        filename: The primary document filename for citation
        line_to_location_map: Optional mapping of line numbers to page/paragraph numbers
        file_type: Optional file type ("pdf" or "docx")
        all_documents: Optional list of document dicts with filename, text, line_map, file_type
    
    Returns:
        List of answer objects with id, answer, confidence, and citation
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it in your .env file.")
    
    project_id = os.getenv("OPENAI_PROJECT_ID")
    
    # Use AsyncOpenAI for parallel processing
    client = AsyncOpenAI(
        api_key=api_key,
        project=project_id
    )
    
    # Map question types to the format expected by the prompt
    def map_question_type(q_type):
        type_mapping = {
            'yesno': 'checkbox',
            'text': 'textarea',
            'dropdown': 'select',
            'textarea': 'textarea'
        }
        return type_mapping.get(q_type, 'text')
    
    # Prepare questions payload
    q_payload = []
    for q in questions:
        q_item = {
            "id": f"q{q['id']}",
            "text": q['text'],
            "type": map_question_type(q.get('type', 'text'))
        }
        if 'options' in q and q['options']:
            q_item["options"] = q['options']
        q_payload.append(q_item)
    
    # Calculate token count for questions payload (approximate)
    # Create encoder once for token counting
    enc = tiktoken.get_encoding("o200k_base")
    def num_tokens(text):
        return len(enc.encode(text))
    
    questions_json = json.dumps(q_payload)
    questions_tokens = num_tokens(questions_json)
    
    # Estimate tokens needed for prompt template (system message + instructions)
    prompt_template = """Return JSON with schema: {"answers":[{"id":"q1","answer":<typed>,"confidence":<number>,"citation":{"docName":"name","page":number,"snippet":"exact relevant text from document"}}]}.

IMPORTANT INSTRUCTIONS:
- For each answer, you MUST include a confidence score (0-1 scale) AND a citation object
- Confidence scoring rules based on question position in the list:
  * Questions 1-5: confidence should be 1.0 (100%) if you have a clear answer
  * Questions 6-10: confidence should be 0.50-0.75 (50-75%) if you have a clear answer
  * Questions 11-20 (last 10 questions): confidence should be 0.25-0.50 (25-50%) if you have a clear answer
  * If the answer is uncertain or not found in documents, reduce confidence accordingly
- For each answer, you MUST also include a citation object with:
  * docName: the exact document name where you found the answer
  * page: the specific page number where the information appears (required for PDFs with page markers like [Page X])
  * snippet: copy the EXACT relevant text snippet (50-200 characters) from the document that supports your answer
- The snippet MUST be word-for-word from the source document
- The snippet should be the most relevant sentence or phrase that directly answers the question
- If the document has page markers like [Page 5], include that page number in the citation
- For plain text documents without page numbers, set page to null

For each question:
- if type is "checkbox" return a boolean
- if "number" return a number (no units)
- if "text" or "textarea" return a string (maximum 4000 characters)
- if "select" return exactly one string from the provided options
- if unknown, set answer to null and omit the citation and confidence
- All text answers must be less than 4000 characters"""
    
    template_tokens = num_tokens(prompt_template)
    system_tokens = num_tokens("Answer strictly from the provided context. Respond only in strict JSON.")
    
    # Reserve tokens for response (estimate ~5000 tokens for 20 answers)
    response_tokens_estimate = 5000
    # Target max tokens per request: 25000 (leaving buffer under 30000 limit)
    max_tokens_per_request = 25000
    # Calculate max document tokens per chunk
    max_doc_tokens_per_chunk = max_tokens_per_request - questions_tokens - template_tokens - system_tokens - response_tokens_estimate
    
    # Get cached chunks (with 200 token overlap to prevent boundary issues)
    chunks = chunk_document_cached(
        document_text=document_text,
        chunk_size_tokens=max_doc_tokens_per_chunk,
        overlap_tokens=200,
        encoding_name="o200k_base"
    )
    
    # Determine if multiple documents
    is_multiple_docs = all_documents is not None and len(all_documents) > 1
    doc_names = [d['filename'] for d in all_documents] if all_documents else [filename]
    doc_name = filename
    
    # Build document context hint for multiple documents
    doc_context = ""
    if is_multiple_docs:
        doc_context = f"\n\nIMPORTANT: You are searching across multiple documents: {', '.join(doc_names)}. Make sure to include the correct document name (docName) in each citation."
    
    # Define async function to process a single chunk
    async def process_chunk(chunk_idx: int, chunk: str) -> dict:
        """Process a single chunk and return results as a dict."""
        user_content = [
            {
                "type": "text",
                "text": f"""{chunk}{doc_context}

Return JSON with schema: {{"answers":[{{"id":"q1","answer":<typed>,"confidence":<number>,"citation":{{"docName":"name","page":number,"snippet":"exact relevant text from document"}}}}]}}.

IMPORTANT INSTRUCTIONS:
- For each answer, you MUST include a confidence score (0-1 scale) AND a citation object
- Confidence scoring rules based on question position in the list:
  * Questions 1-5: confidence should be 1.0 (100%) if you have a clear answer
  * Questions 6-10: confidence should be 0.50-0.75 (50-75%) if you have a clear answer
  * Questions 11-20 (last 10 questions): confidence should be 0.25-0.50 (25-50%) if you have a clear answer
  * If the answer is uncertain or not found in documents, reduce confidence accordingly
- For each answer, you MUST also include a citation object with:
  * docName: the exact document name where you found the answer
  * page: the specific page number where the information appears (required for PDFs with page markers like [Page X])
  * snippet: copy the EXACT relevant text snippet (50-200 characters) from the document that supports your answer
- The snippet MUST be word-for-word from the source document
- The snippet should be the most relevant sentence or phrase that directly answers the question
- If the document has page markers like [Page 5], include that page number in the citation
- For plain text documents without page numbers, set page to null

For each question:
- if type is "checkbox" return a boolean
- if "number" return a number (no units)
- if "text" or "textarea" return a string (maximum 4000 characters)
- if "select" return exactly one string from the provided options
- if unknown, set answer to null and omit the citation and confidence
- All text answers must be less than 4000 characters"""
            },
            {
                "type": "text",
                "text": f"Questions (with types and options): {questions_json}"
            }
        ]
        
        messages = [
            {
                "role": "system",
                "content": "Answer strictly from the provided context. Respond only in strict JSON."
            },
            {
                "role": "user",
                "content": user_content
            }
        ]
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4.1",
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            # Return chunk results as dict: {question_id: {answer_data}}
            chunk_results = {}
            answers = result.get("answers", [])
            
            for answer in answers:
                q_id = answer.get("id", "")
                q_num = int(q_id.replace("q", "")) if q_id.startswith("q") else None
                
                if q_num is None:
                    continue
                
                citation = answer.get("citation", {})
                confidence = answer.get("confidence", 0.0)
                answer_value = answer.get("answer")
                
                # Skip if no answer found
                if answer_value is None:
                    continue
                
                # Find the original question
                original_q = next((q for q in questions if q['id'] == q_num), None)
                if not original_q:
                    continue
                
                # Build location info from citation
                location_data = {}
                if citation:
                    if citation.get("page"):
                        if file_type == "pdf":
                            location_data["page_number"] = citation["page"]
                        elif file_type == "docx":
                            location_data["paragraph_number"] = citation["page"]
                    
                    if citation.get("snippet"):
                        location_data["context"] = citation["snippet"]
                    
                    if citation.get("docName"):
                        location_data["docName"] = citation["docName"]
                
                # Convert answer value based on question type
                final_value = answer_value
                if original_q.get('type') == 'yesno':
                    if isinstance(answer_value, bool):
                        final_value = "Yes" if answer_value else "No"
                    elif isinstance(answer_value, str):
                        final_value = answer_value
                elif original_q.get('type') == 'dropdown' and isinstance(answer_value, str):
                    options = original_q.get('options', [])
                    if answer_value not in options and options:
                        matched = next((opt for opt in options if opt.lower() == answer_value.lower()), None)
                        final_value = matched if matched else answer_value
                
                chunk_results[q_num] = {
                    "question_id": q_num,
                    "field": original_q['text'],
                    "value": str(final_value) if final_value is not None else None,
                    "confidence": confidence,
                    "location": location_data if location_data else None
                }
            
            return chunk_results
        
        except json.JSONDecodeError as e:
            print(f"JSON decode error in chunk {chunk_idx + 1}: {e}")
            return {}  # Return empty dict on error
        except Exception as e:
            print(f"Error processing chunk {chunk_idx + 1}: {e}")
            return {}  # Return empty dict on error
    
    # Process all chunks in parallel using asyncio.gather
    chunk_tasks = [process_chunk(chunk_idx, chunk) for chunk_idx, chunk in enumerate(chunks)]
    chunk_results_list = await asyncio.gather(*chunk_tasks)
    
    # Merge results from all chunks, keeping best answer (highest confidence) per question
    all_results = {}  # question_id -> best answer (highest confidence or first found)
    
    for chunk_results in chunk_results_list:
        for q_num, answer_data in chunk_results.items():
            existing = all_results.get(q_num)
            confidence = answer_data.get("confidence", 0.0)
            
            # Keep this answer if:
            # 1. We don't have an answer yet, OR
            # 2. This answer has higher confidence, OR
            # 3. This answer has confidence > 0 and existing doesn't
            should_keep = False
            if existing is None:
                should_keep = True
            elif confidence > existing.get("confidence", 0.0):
                should_keep = True
            elif confidence > 0 and existing.get("confidence", 0.0) == 0:
                should_keep = True
            
            if should_keep:
                all_results[q_num] = answer_data
    
    # Convert results dict to list, ensuring all questions are represented
    formatted_results = []
    for q in questions:
        q_id = q['id']
        if q_id in all_results:
            formatted_results.append(all_results[q_id])
        else:
            # No answer found for this question
            formatted_results.append({
                "question_id": q_id,
                "field": q['text'],
                "value": None,
                "confidence": 0.0,
                "location": None
            })
    
    return formatted_results

