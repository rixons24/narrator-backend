"""Step 2: per-scene LLM structuring — provider-agnostic (Groq or Ollama)."""
import asyncio

from app.models.parsing_schemas import DialogueElement, ParsedScene
from app.services.llm_client import LLMError, LLMTimeoutError, generate_json
from app.services.scene_splitter import Scene

SYSTEM_PROMPT = """You are a screenplay structuring engine. You read one scene of a \
professionally formatted screenplay (already cleaned of page numbers and title-page \
credits) and output ONLY a single JSON object describing its structure. No prose, no \
explanation, no markdown code fences — JSON only.

CRITICAL DISAMBIGUATION RULE — read this first:
Screenwriters frequently write short, ALL-CAPS sentences for dramatic emphasis that are \
NOT character cues, e.g. "THE ROOM ERUPTS IN GUNFIRE." A real character cue is followed \
by spoken dialogue in normal sentence case on the next non-blank line. An emphasis \
sentence is followed by more action description, or another all-caps sentence, or a \
scene heading. When in doubt: does the next line read like something a person would SAY \
out loud? If yes, the all-caps line above it was a cue. If not, classify it as "action".

CUE NAME MODIFIERS:
Strip parenthetical modifiers like (V.O.), (O.S.), (CONT'D) to get the canonical speaker \
name — "MIKE (V.O.)" and "MIKE" are the SAME character, "MIKE".

PARENTHETICALS:
A line in (parentheses) between a cue and dialogue, or mid-dialogue, is a parenthetical \
direction — attribute it to the same speaker, type "parenthetical".

OUTPUT SCHEMA:
{
  "location": string or null,
  "time_of_day": string or null,
  "characters_present": [string],
  "elements": [
    {"type": "action", "text": string},
    {"type": "dialogue", "speaker": string, "text": string},
    {"type": "parenthetical", "speaker": string, "text": string}
  ]
}

Preserve element order. Merge consecutive raw lines belonging to the same action \
paragraph or dialogue speech into one element."""

USER_PROMPT_TEMPLATE = """Scene heading: {heading}

Scene text:
{body}

Output the JSON object for this scene now."""

COLD_START_RETRY_DELAY = 5


async def parse_scene(scene: Scene) -> ParsedScene:
    prompt = USER_PROMPT_TEMPLATE.format(heading=scene.heading or "(none)", body=scene.body)

    async def _call() -> dict:
        return await generate_json(prompt, system=SYSTEM_PROMPT)

    try:
        data = await _call()
    except LLMTimeoutError:
        await asyncio.sleep(COLD_START_RETRY_DELAY)
        data = await _call()

    elements = [
        DialogueElement(type=el.get("type", "action"), speaker=el.get("speaker"), text=el.get("text", ""))
        for el in data.get("elements", [])
    ]

    return ParsedScene(
        scene_index=scene.index,
        heading=scene.heading,
        location=data.get("location"),
        time_of_day=data.get("time_of_day"),
        characters_present=data.get("characters_present", []),
        elements=elements,
    )


async def parse_script_scenes(
    scenes: list[Scene], max_concurrent: int = 4,
) -> tuple[list[ParsedScene], list[str]]:
    """max_concurrent=4 default — cloud API providers (Groq) handle much
    higher concurrency than a single local GPU could, so this is bumped up
    from the local-Ollama default of 2."""
    semaphore = asyncio.Semaphore(max_concurrent)
    warnings: list[str] = []

    async def parse_with_limit(scene: Scene) -> ParsedScene | None:
        async with semaphore:
            try:
                return await parse_scene(scene)
            except LLMError as e:
                warnings.append(f"Scene {scene.index} ({scene.heading or 'untitled'}): {e}")
                return None

    results = await asyncio.gather(*(parse_with_limit(s) for s in scenes))
    parsed = [r for r in results if r is not None]
    return parsed, warnings
