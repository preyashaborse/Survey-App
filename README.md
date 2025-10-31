# AI Autofill App

FastAPI backend service for AI-assisted survey field autofill using GPT-4 with location tracking.

## Features

- **GPT-4o Extraction**: Uses OpenAI's GPT-4o model to intelligently extract field values from documents
- **Location Tracking**: Returns detailed location information including:
  - Page number (for PDFs)
  - Paragraph number (for DOCX)
  - Line number
  - Document section (e.g., "Header", "Body", "Contact Information")
  - Surrounding context
- **Multiple Format Support**: Supports PDF and DOCX files
- **JSON Output**: Returns structured JSON with field values and location references

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

   Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys)

3. Run the application:
```bash
uvicorn app.main:app --reload
```

## API Endpoints

### POST `/extract`
Extract field value from text input using GPT-4o.

**Request:**
```json
{
  "document_text": "Name: John Doe\nEmail: john@example.com",
  "field": "Email"
}
```

**Response:**
```json
{
  "field": "Email",
  "value": "john@example.com",
  "location": {
    "line_number": 2,
    "context": "Name: John Doe\nEmail: john@example.com",
    "section": "Body"
  }
}
```

### POST `/extract_file`
Extract field value from uploaded PDF or DOCX file using GPT-4o.

**Request:** Form data with `file` and `field` parameters

**Response:**
```json
{
  "filename": "document.pdf",
  "field": "Email",
  "value": "john@example.com",
  "location": {
    "page_number": 1,
    "line_number": 5,
    "paragraph_number": null,
    "context": "Contact Information\nEmail: john@example.com\nPhone: 123-456-7890",
    "section": "Contact Information"
  }
}
```

## Usage

1. Open `http://localhost:8000` in your browser
2. Upload a PDF or DOCX file
3. Enter the field name you want to extract
4. Click "Extract" to get the value and location information
