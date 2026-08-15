from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.parsing_schemas import ParsedScript
from app.services.parsing_pipeline import parse_script

router = APIRouter(prefix="/api/parse", tags=["parsing"])


class ParseRequest(BaseModel):
    raw_text: str
    title: str | None = None
    # Opt-in — when False (default), parsing is identical to before this
    # feature existed: same prompt, same cost, same latency. Only set to
    # True when the frontend's sound-effects toggle is on.
    detect_sound_effects: bool = False


@router.post("/structure", response_model=ParsedScript)
async def structure_script(req: ParseRequest):
    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty.")

    try:
        result = await parse_script(
            req.raw_text, title=req.title, detect_sound_effects=req.detect_sound_effects,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Parsing failed: {e}")

    if not result.scenes:
        raise HTTPException(status_code=422, detail="No scenes could be parsed.")

    return result
