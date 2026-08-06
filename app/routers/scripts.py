import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import ScriptUploadResponse
from app.services.extraction import UnsupportedFormatError, extract_text

router = APIRouter(prefix="/api/scripts", tags=["scripts"])
ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".fountain"}


@router.post("/upload", response_model=ScriptUploadResponse)
async def upload_script(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{suffix}'.")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        raw_text = extract_text(tmp_path, file.filename)
    except UnsupportedFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="No extractable text found.")

    return ScriptUploadResponse(
        filename=file.filename,
        format=suffix.lstrip(".").lower(),
        char_count=len(raw_text),
        line_count=raw_text.count("\n") + 1,
        raw_text=raw_text,
    )
