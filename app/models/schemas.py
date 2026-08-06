from typing import Literal
from pydantic import BaseModel

ScriptFormat = Literal["pdf", "docx", "txt", "fountain"]


class ScriptUploadResponse(BaseModel):
    filename: str
    format: ScriptFormat
    char_count: int
    line_count: int
    raw_text: str
