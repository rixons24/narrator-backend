from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.parsing_schemas import ParsedScript
from app.services.parsing_pipeline import parse_script

router = APIRouter(prefix="/api/parse", tags=["parsing"])


class ParseRequest(BaseModel):
    raw_text: str
    title: str | None = None


@router.post("/structure", response_model=ParsedScript)
async def structure_script(req: ParseRequest):
    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty.")

    try:
        result = await parse_script(req.raw_text, title=req.title)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Parsing failed: {e}")

    if not result.scenes:
        raise HTTPException(status_code=422, detail="No scenes could be parsed.")

    return result
