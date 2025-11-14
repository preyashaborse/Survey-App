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
    # Minimal HTML UI with login form and upload/extract interface
    html = """
    <!doctype html>
    <html>
      <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>AI Autofill - Upload</title>
        <style>
          body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }
          .card { max-width: 640px; padding: 1.5rem; border: 1px solid #e5e7eb; border-radius: 12px; margin-bottom: 2rem; }
          .row { margin-bottom: 1rem; }
          label { display: block; font-weight: 600; margin-bottom: 0.25rem; }
          input[type=text], input[type=password], input[type=file] { width: 100%; padding: 0.5rem; border: 1px solid #d1d5db; border-radius: 8px; box-sizing: border-box; }
          button { padding: 0.6rem 1rem; background: #111827; color: white; border: none; border-radius: 8px; cursor: pointer; }
          button:hover { background: #1f2937; }
          .muted { color: #6b7280; }
          .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
          .success { color: #059669; background: #ecfdf5; padding: 0.5rem; border-radius: 8px; margin-bottom: 1rem; }
          .error { color: #dc2626; background: #fef2f2; padding: 0.5rem; border-radius: 8px; margin-bottom: 1rem; }
          #authSection { display: none; }
          #extractSection { display: none; }
          .logout-btn { background: #6b7280; padding: 0.4rem 0.8rem; font-size: 0.9rem; }
          .logout-btn:hover { background: #4b5563; }
        </style>
      </head>
      <body>
        <!-- Login Section -->
        <div id=\"authSection\" class=\"card\">
          <h2>Login</h2>
          <div id=\"authMessage\"></div>
          <div class=\"row\">
            <label for=\"username\">Username</label>
            <input id=\"username\" type=\"text\" placeholder=\"e.g., preyasha\" />
          </div>
          <div class=\"row\">
            <label for=\"password\">Password</label>
            <input id=\"password\" type=\"password\" placeholder=\"Enter your password\" />
          </div>
          <div class=\"row\">
            <button id=\"loginBtn\">Login</button>
          </div>
        </div>

        <!-- Extract Section (shown after login) -->
        <div id=\"extractSection\">
          <div class=\"card\">
            <div style=\"display: flex; justify-content: space-between; align-items: center;\">
              <h2>Upload a PDF or DOCX</h2>
              <button class=\"logout-btn\" id=\"logoutBtn\">Logout</button>
            </div>
            <div class=\"row\">
              <label for=\"file\">Document</label>
              <input id=\"file\" name=\"file\" type=\"file\" accept=\".pdf,.docx\" />
              <div id=\"filename\" class=\"muted mono\"></div>
            </div>
            <div class=\"row\">
            <!-- Survey Questions UI -->
            <div id="surveyQuestions"></div>
            <div id="result"></div>
          </div>
        </div>

        <script>
          let token = null;

          // Survey questions definition
          const surveyQuestions = [
            { id: 1, text: 'Do you currently have a SOC 2 Type II Report?', type: 'yesno' },
            { id: 2, text: 'If yes, mention the audit firm name and reporting period.', type: 'text' },
            { id: 3, text: 'Do you plan to pursue SOC 2 certification within the next 12 months?', type: 'yesno' },
            { id: 4, text: 'Provide a brief overview of your information security governance structure (e.g., CISO, InfoSec committee).', type: 'text' },
            { id: 5, text: 'Is there a documented and approved Information Security Policy?', type: 'yesno' },
            { id: 6, text: 'Are employees required to complete security awareness training annually?', type: 'yesno' },
            { id: 7, text: 'How frequently are user access rights reviewed?', type: 'dropdown', options: ['Monthly', 'Quarterly', 'Annually', 'Other'] },
            { id: 8, text: 'Describe your incident response process, including escalation and communication flow.', type: 'text' },
            { id: 9, text: 'Is multi-factor authentication (MFA) enabled for administrative and critical systems?', type: 'yesno' },
            { id: 10, text: 'How often are vulnerability scans performed on your production environment?', type: 'dropdown', options: ['Monthly', 'Quarterly', 'Annually', 'Other'] },
            { id: 11, text: 'Do you have a documented Business Continuity and Disaster Recovery (BCP/DR) plan?', type: 'yesno' },
            { id: 12, text: 'When was your last BCP/DR test conducted?', type: 'dropdown', options: ['Last 3 months', 'Last 6 months', 'Last year', 'Other'] },
            { id: 13, text: 'What is your average system uptime (%) over the last 12 months?', type: 'text' },
            { id: 14, text: 'Are change management procedures documented and approved before deployment?', type: 'yesno' },
            { id: 15, text: 'Are data inputs and outputs validated for accuracy and completeness?', type: 'yesno' },
            { id: 16, text: 'Do you classify and label data based on sensitivity/confidentiality?', type: 'yesno' },
            { id: 17, text: 'Describe the encryption methods used to protect data at rest and in transit.', type: 'text' },
            { id: 18, text: 'Do you collect or process personally identifiable information (PII) or personal data?', type: 'yesno' },
            { id: 19, text: 'Which privacy regulation primarily applies to your organization?', type: 'dropdown', options: ['GDPR', 'CCPA', 'HIPAA', 'Other'] },
            { id: 20, text: 'Provide details of any ongoing initiatives or planned improvements toward SOC 2 compliance.', type: 'text' }
          ];

          // Function to render survey questions
          function renderSurveyQuestions() {
            const container = document.getElementById('surveyQuestions');
            container.innerHTML = '';
            surveyQuestions.forEach(q => {
              const row = document.createElement('div');
              row.className = 'row';
              const label = document.createElement('label');
              label.textContent = q.text;
              label.setAttribute('for', `q${q.id}`);
              row.appendChild(label);
              let input;
              if (q.type === 'yesno') {
                input = document.createElement('select');
                input.id = `q${q.id}`;
                input.innerHTML = '<option value="">Select</option><option value="Yes">Yes</option><option value="No">No</option>';
              } else if (q.type === 'dropdown') {
                input = document.createElement('select');
                input.id = `q${q.id}`;
                input.innerHTML = '<option value="">Select</option>' + (q.options || []).map(opt => `<option value="${opt}">${opt}</option>`).join('');
              } else if (q.type === 'text') {
                input = document.createElement('textarea');
                input.id = `q${q.id}`;
                input.rows = 2;
                input.style.width = '100%';
              }
              row.appendChild(input);
              // Add Get Answer button
              const btn = document.createElement('button');
              btn.textContent = 'Get Answer';
              btn.type = 'button';
              btn.style.marginLeft = '1rem';
              btn.onclick = () => getAnswerForQuestion(q);
              row.appendChild(btn);
              // Reference/result display
              const answerDiv = document.createElement('div');
              answerDiv.id = `answer${q.id}`;
              answerDiv.className = 'muted';
              row.appendChild(answerDiv);
              container.appendChild(row);
            });
          }

          // Function to get answer for a question
          async function getAnswerForQuestion(q) {
            const fileInput = document.getElementById('file');
            const f = fileInput.files?.[0];
            const resultEl = document.getElementById(`answer${q.id}`);
            resultEl.textContent = '';
            if (!f) { resultEl.textContent = 'Please choose a file.'; return; }
            if (!token) { resultEl.textContent = 'Not authenticated. Please login first.'; return; }
            // Call /extract_file for this question
            const form = new FormData();
            form.append('file', f);
            form.append('field', q.text);
            try {
              const res = await fetch('/extract_file', {
                method: 'POST',
                body: form,
                headers: {
                  'Authorization': `Bearer ${token}`
                }
              });
              if (res.status === 401) { handleExpiredToken(); return; }
              const data = await res.json();
              if (!res.ok) throw new Error(data.detail || 'Request failed');
              // Populate the answer field (input/textarea/select) with the extracted value
              const inputEl = document.getElementById(`q${q.id}`);
              if (inputEl) {
                if (inputEl.tagName === 'SELECT') {
                  // Try to match value to option, else add as custom option
                  let found = false;
                  for (let i = 0; i < inputEl.options.length; i++) {
                    if (inputEl.options[i].value === data.value) {
                      inputEl.selectedIndex = i;
                      found = true;
                      break;
                    }
                  }
                  if (!found && data.value) {
                    // Add custom option and select it
                    const opt = document.createElement('option');
                    opt.value = data.value;
                    opt.text = data.value;
                    inputEl.appendChild(opt);
                    inputEl.value = data.value;
                  }
                } else if (inputEl.tagName === 'TEXTAREA' || inputEl.type === 'text') {
                  inputEl.value = data.value ?? '';
                }
              }
              // Show reference info below
              let locationHtml = '';
              if (data.location) {
                const loc = data.location;
                locationHtml = `<div style=\"margin-top: 0.5rem; font-size: 0.95em;\">` +
                  `${loc.page_number ? `<div>Page: ${loc.page_number}</div>` : ''}` +
                  `${loc.paragraph_number ? `<div>Paragraph: ${loc.paragraph_number}</div>` : ''}` +
                  `${loc.line_number ? `<div>Line: ${loc.line_number}</div>` : ''}` +
                  `${loc.section ? `<div>Section: ${loc.section}</div>` : ''}` +
                  `${loc.context ? `<div style='margin-top: 0.3rem; font-style: italic;'>Context: ${loc.context}</div>` : ''}` +
                  `</div>`;
              }
              resultEl.innerHTML = locationHtml;
            } catch (err) {
              resultEl.textContent = err.message;
            }
          }

          // Function to validate token by making a test request
          async function validateToken(testToken) {
            try {
              const res = await fetch('/extract', {
                method: 'POST',
                headers: {
                  'Authorization': `Bearer ${testToken}`,
                  'Content-Type': 'application/json'
                },
                body: JSON.stringify({ document_text: '', field: '' })
              });
              if (res.status === 401) { return false; }
              return true;
            } catch (err) { return true; }
          }

          // Function to handle expired/invalid token
          function handleExpiredToken() {
            localStorage.removeItem('authToken');
            token = null;
            document.getElementById('authSection').style.display = 'block';
            document.getElementById('extractSection').style.display = 'none';
            document.getElementById('authMessage').innerHTML = '<div class="error">Session expired. Please log in again.</div>';
            document.getElementById('username').value = '';
            document.getElementById('password').value = '';
            document.getElementById('result').textContent = '';
            document.getElementById('file').value = '';
            document.getElementById('filename').textContent = '';
            renderSurveyQuestions();
          }
          
          window.onload = async function() {
            token = localStorage.getItem('authToken');

            // On page load, check if token exists
            if (token) {
              // Validate token is still valid
              const isValid = await validateToken(token);
              if (isValid) {
                document.getElementById('authSection').style.display = 'none';
                document.getElementById('extractSection').style.display = 'block';
                renderSurveyQuestions();
              } else {
                // Token expired, fall back to login
                handleExpiredToken();
              }
            } else {
              document.getElementById('authSection').style.display = 'block';
              document.getElementById('extractSection').style.display = 'none';
            }

            // Login button click handler
            document.getElementById('loginBtn').addEventListener('click', async () => {
              const username = document.getElementById('username').value;
              const password = document.getElementById('password').value;
              const messageEl = document.getElementById('authMessage');
              messageEl.textContent = '';

              if (!username || !password) {
                messageEl.innerHTML = '<div class="error">Please enter username and password.</div>';
                return;
              }

              try {
                const formData = new FormData();
                formData.append('username', username);
                formData.append('password', password);
                const res = await fetch('/auth/token', { method: 'POST', body: formData });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Login failed');

                // Store token and switch to extract view
                token = data.access_token;
                localStorage.setItem('authToken', token);
                messageEl.innerHTML = '<div class="success">Login successful!</div>';

                // Show extract section, hide auth section
                document.getElementById('authSection').style.display = 'none';
                document.getElementById('extractSection').style.display = 'block';
                renderSurveyQuestions();

                // Clear input fields
                document.getElementById('username').value = '';
                document.getElementById('password').value = '';
              } catch (err) {
                messageEl.innerHTML = `<div class=\"error\">Login failed: ${err.message}</div>`;
              }
            });

            // Logout button click handler
            document.getElementById('logoutBtn').addEventListener('click', () => {
              localStorage.removeItem('authToken');
              token = null;
              document.getElementById('authSection').style.display = 'block';
              document.getElementById('extractSection').style.display = 'none';
              document.getElementById('username').value = '';
              document.getElementById('password').value = '';
              document.getElementById('authMessage').textContent = '';
              document.getElementById('result').textContent = '';
              document.getElementById('file').value = '';
              renderSurveyQuestions();
            });

            // File upload tracking
            const fileInput = document.getElementById('file');
            const filenameEl = document.getElementById('filename');
            fileInput.addEventListener('change', () => {
              const f = fileInput.files?.[0];
              filenameEl.textContent = f ? `Uploaded: ${f.name}` : '';
            });
          };
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


