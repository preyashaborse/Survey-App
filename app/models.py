from pydantic import BaseModel
from typing import Optional


class LocationInfo(BaseModel):
    """Location/reference information about where the field was found"""
    page_number: Optional[int] = None  # For PDFs
    paragraph_number: Optional[int] = None  # For DOCX
    line_number: Optional[int] = None  # Line number in document
    context: Optional[str] = None  # Surrounding text or context
    section: Optional[str] = None  # Document section (e.g., "Header", "Body", "Footer")


class ExtractRequest(BaseModel):
    document_text: str
    field: str


class ExtractResponse(BaseModel):
    field: str
    value: str | None
    location: Optional[LocationInfo] = None


class FileExtractResponse(BaseModel):
    filename: str
    field: str
    value: str | None
    location: Optional[LocationInfo] = None


