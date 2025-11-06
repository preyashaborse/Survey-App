from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import Depends
from app.auth.deps import get_current_user
from app.auth.schemas import User
from app.routers import auth
import traceback
from app.models import ExtractRequest, ExtractResponse, FileExtractResponse, LocationInfo
from app.extractor import (
    extract_field_value_with_gpt,
    extract_text_from_file_with_location
)


app = FastAPI(title="AI Autofill Service")

app.include_router(auth.router)


@app.post("/extract", response_model=ExtractResponse)
async def extract_endpoint(payload: ExtractRequest, current_user: User = Depends(get_current_user)) -> ExtractResponse:
    """Extract field value from text using GPT-4o"""
    try:
        value, location_data = extract_field_value_with_gpt(
            payload.document_text,
            payload.field,
            line_to_location_map=None,
            file_type=None
        )
        location = None
        if location_data:
            # Filter out None values and ensure all required fields exist
            clean_location = {k: v for k, v in location_data.items() if v is not None}
            if clean_location:
                location = LocationInfo(**clean_location)
        return ExtractResponse(field=payload.field, value=value, location=location)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract field using GPT-4o: {str(e)}")


@app.get("/", response_class=HTMLResponse)
def upload_form() -> HTMLResponse:
    # Minimal HTML UI with upload button and input field
    html = """
    <!doctype html>
    <html>
      <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>AI Autofill - Upload</title>
        <style>
          body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }
          .card { max-width: 640px; padding: 1.5rem; border: 1px solid #e5e7eb; border-radius: 12px; }
          .row { margin-bottom: 1rem; }
          label { display: block; font-weight: 600; margin-bottom: 0.25rem; }
          input[type=text] { width: 100%; padding: 0.5rem; border: 1px solid #d1d5db; border-radius: 8px; }
          button { padding: 0.6rem 1rem; background: #111827; color: white; border: none; border-radius: 8px; cursor: pointer; }
          .muted { color: #6b7280; }
          .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
        </style>
      </head>
      <body>
        <div class=\"card\">
          <h2>Upload a PDF or DOCX</h2>
          <div class=\"row\">
            <label for=\"file\">Document</label>
            <input id=\"file\" name=\"file\" type=\"file\" accept=\".pdf,.docx\" />
            <div id=\"filename\" class=\"muted mono\"></div>
          </div>
          <div class=\"row\">
            <label for=\"field\">Field to extract</label>
            <input id=\"field\" name=\"field\" type=\"text\" placeholder=\"e.g., Email\" />
          </div>
          <div class=\"row\">
            <button id=\"submit\">Extract</button>
          </div>
          <div id=\"result\"></div>
        </div>

        <script>
          const fileInput = document.getElementById('file');
          const filenameEl = document.getElementById('filename');
          fileInput.addEventListener('change', () => {
            const f = fileInput.files?.[0];
            filenameEl.textContent = f ? `Uploaded: ${f.name}` : '';
          });

          document.getElementById('submit').addEventListener('click', async () => {
            const f = fileInput.files?.[0];
            const field = document.getElementById('field').value;
            const resultEl = document.getElementById('result');
            resultEl.textContent = '';
            if (!f) { resultEl.textContent = 'Please choose a file.'; return; }
            if (!field) { resultEl.textContent = 'Please enter a field.'; return; }
            const form = new FormData();
            form.append('file', f);
            form.append('field', field);
            try {
              const res = await fetch('/extract_file', { method: 'POST', body: form });
              const data = await res.json();
              if (!res.ok) throw new Error(data.detail || 'Request failed');
              let locationHtml = '';
              if (data.location) {
                const loc = data.location;
                locationHtml = `<div style="margin-top: 1rem; padding: 1rem; background: #f3f4f6; border-radius: 8px;">
                  <strong>Location Information:</strong><br/>
                  ${loc.page_number ? `<div>Page: ${loc.page_number}</div>` : ''}
                  ${loc.paragraph_number ? `<div>Paragraph: ${loc.paragraph_number}</div>` : ''}
                  ${loc.line_number ? `<div>Line: ${loc.line_number}</div>` : ''}
                  ${loc.section ? `<div>Section: ${loc.section}</div>` : ''}
                  ${loc.context ? `<div style="margin-top: 0.5rem; font-style: italic; color: #6b7280;">Context: ${loc.context}</div>` : ''}
                </div>`;
              }
              resultEl.innerHTML = `<div><strong>Filename:</strong> ${data.filename}</div>` +
                                   `<div><strong>Field:</strong> ${data.field}</div>` +
                                   `<div><strong>Value:</strong> ${data.value ?? 'Not found'}</div>` +
                                   locationHtml;
            } catch (err) {
              resultEl.textContent = err.message;
            }
          });
        </script>
      </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.post("/extract_file", response_model=FileExtractResponse)
async def extract_from_file(file: UploadFile = File(...), field: str = Form(...), current_user: User = Depends(get_current_user)) -> FileExtractResponse:
    """Extract field value from uploaded file using GPT-4o with location tracking"""
    try:
        file_bytes = await file.read()
        # Extract text with location metadata
        text, line_map, file_type = extract_text_from_file_with_location(file.filename, file_bytes)
    except ValueError as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to read the uploaded file: {str(e)}")

    try:
        # Use GPT-4o for extraction with location tracking
        value, location_data = extract_field_value_with_gpt(
            text,
            field,
            line_to_location_map=line_map,
            file_type=file_type
        )
        location = None
        if location_data:
            # Filter out None values and ensure all required fields exist
            clean_location = {k: v for k, v in location_data.items() if v is not None}
            if clean_location:
                location = LocationInfo(**clean_location)
        return FileExtractResponse(
            filename=file.filename,
            field=field,
            value=value,
            location=location
        )
    except ValueError as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to extract field using GPT-4o: {str(e)}")


