from pydantic import BaseModel
from typing import Optional, List

class LocationInfo(BaseModel):
    page_number: Optional[int] = None
    paragraph_number: Optional[int] = None
    line_number: Optional[int] = None
    context: Optional[str] = None
    section: Optional[str] = None
    docName: Optional[str] = None  # Document name for multi-document scenarios

class BulkExtractRequest(BaseModel):
    document_text: str
    fields: list[str]

class BulkExtractFieldResult(BaseModel):
    field: str
    value: str | None
    location: Optional[LocationInfo] = None

class BulkExtractResponse(BaseModel):
    results: List[BulkExtractFieldResult]
