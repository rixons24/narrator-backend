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
direction — attribute it to the same speaker, type "parenthetical"."""

# Appended to the base prompt only when detect_sound_effects=True on the
# request — kept separate so scripts that don't want this get a shorter,
# cheaper, unmodified prompt with zero behavior change from before.
SFX_PROMPT_ADDENDUM = """

SOUND EFFECT DETECTION (enabled for this request):
Within "action" elements, identify specific moments that describe a distinct, \
literal SOUND a listener would actually hear — not general visual description. \
Genuine sound cues: gunshots, explosions, thunder, a door creaking, glass \
breaking, a phone ringing, an engine revving, footsteps on gravel, a scream, \
a car crash. NOT sound cues: a character's appearance, a room's visual \
description, an emotional state, or an action with no inherent distinct sound \
(e.g. "He nods." or "She reads the letter." produce no meaningful audio).

Be conservative — most action lines are NOT sound cues. Only flag lines where \
the sound is clearly the point of the sentence.

When an action element contains a genuine sound cue, add an "sfx_prompt" field \
to that element: a short, clean phrase describing just the sound, suitable for \
an audio-generation model — e.g. raw text "A DEAFENING ROAR. Marty finds the \
flashlight..." becomes sfx_prompt "A deafening roar". If an action element has \
no sound cue, omit the sfx_prompt field entirely (or set it to null) — do not \
force one."""

BASE_OUTPUT_SCHEMA = """
OUTPUT SCHEMA:
{{
  "location": string or null,
  "time_of_day": string or null,
  "characters_present": [string],
  "elements": [
    {{"type": "action", "text": string{sfx_field}}},
    {{"type": "dialogue", "speaker": string, "text": string}},
    {{"type": "parenthetical", "speaker": string, "text": string}}
  ]
}}

Preserve element order. Merge consecutive raw lines belonging to the same action \
paragraph or dialogue speech into one element."""

USER_PROMPT_TEMPLATE = """Scene heading: {heading}

Scene text:
{body}

Output the JSON object for this scene now."""

COLD_START_RETRY_DELAY = 5


def _build_system_prompt(detect_sound_effects: bool) -> str:
    schema = BASE_OUTPUT_SCHEMA.format(
        sfx_field=', "sfx_prompt": string (optional, only if a genuine sound cue)' if detect_sound_effects else ''
    )
    prompt = SYSTEM_PROMPT + schema
    if detect_sound_effects:
        prompt += SFX_PROMPT_ADDENDUM
    return prompt


async def parse_scene(scene: Scene, detect_sound_effects: bool = False) -> ParsedScene:
    prompt = USER_PROMPT_TEMPLATE.format(heading=scene.heading or "(none)", body=scene.body)
    system_prompt = _build_system_prompt(detect_sound_effects)

    async def _call() -> dict:
        return await generate_json(prompt, system=system_prompt)

    try:
        data = await _call()
    except LLMTimeoutError:
        await asyncio.sleep(COLD_START_RETRY_DELAY)
        data = await _call()

    elements = [
        DialogueElement(
            type=el.get("type", "action"),
            speaker=el.get("speaker"),
            text=el.get("text", ""),
            sfx_prompt=el.get("sfx_prompt"),
        )
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
    scenes: list[Scene], max_concurrent: int = 4, detect_sound_effects: bool = False,
) -> tuple[list[ParsedScene], list[str]]:
    """max_concurrent=4 default — cloud API providers (Groq) handle much
    higher concurrency than a single local GPU could, so this is bumped up
    from the local-Ollama default of 2."""
    semaphore = asyncio.Semaphore(max_concurrent)
    warnings: list[str] = []

    async def parse_with_limit(scene: Scene) -> ParsedScene | None:
        async with semaphore:
            try:
                return await parse_scene(scene, detect_sound_effects=detect_sound_effects)
            except LLMError as e:
                warnings.append(f"Scene {scene.index} ({scene.heading or 'untitled'}): {e}")
                return None

    results = await asyncio.gather(*(parse_with_limit(s) for s in scenes))
    parsed = [r for r in results if r is not None]
    return parsed, warnings
