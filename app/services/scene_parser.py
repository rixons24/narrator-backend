"""Step 2: per-scene LLM structuring — provider-agnostic (Groq or Ollama)."""
import asyncio

from app.models.parsing_schemas import DialogueElement, ParsedScene
from app.services.llm_client import LLMError, LLMTimeoutError, generate_json
from app.services.scene_splitter import Scene

SYSTEM_PROMPT = """You are a screenplay structuring engine. You read one scene of a \
professionally formatted screenplay (already cleaned of page numbers and title-page \
credits) and output ONLY a single JSON object describing its structure. No prose, no \
explanation, no markdown code fences — JSON only.

CRITICAL: MERGE LINE-WRAPPED TEXT — read this first.
Raw screenplay text is extracted with hard line breaks at the original page's text \
width. A single sentence or paragraph is almost always split across multiple \
consecutive raw lines purely because of page-width wrapping — this is NOT a \
paragraph break and NOT a new element. You MUST merge these back into one element.

Example of INCORRECT output (splitting a wrapped sentence into three elements, and \
worse, changing speaker mid-sentence):
  Raw input:
    DANIEL MOLLOY (V.O.)
    There's stories out there that need to be
    told. There's shit out there that's, you
    know...wrong. People need to know about it.
  WRONG: [
    {{"type":"dialogue","speaker":"DANIEL MOLLOY","text":"There's stories out there that need to be"}},
    {{"type":"action","text":"told. There's shit out there that's, you"}},
    {{"type":"action","text":"know...wrong. People need to know about it."}}
  ]
  CORRECT: [
    {{"type":"dialogue","speaker":"DANIEL MOLLOY","text":"There's stories out there that need to be told. There's shit out there that's, you know...wrong. People need to know about it."}}
  ]
This same merging applies to action paragraphs — three consecutive raw lines of \
scene description are one "action" element, not three.

CRITICAL DISAMBIGUATION RULE — cue vs. emphasis vs. section label:
Screenwriters frequently write short, ALL-CAPS sentences for dramatic emphasis that are \
NOT character cues, e.g. "THE ROOM ERUPTS IN GUNFIRE." Title sequences and montages also \
often use short ALL-CAPS section/act labels (e.g. "OVERTURE", a card title reveal) that \
are followed by visual description or a transition instruction — these are NOT character \
cues either. A real character cue is followed by spoken dialogue in normal sentence case \
on the next non-blank line — something a person would actually SAY out loud.

Example of INCORRECT output (treating a section label as if it were a speaking character):
  Raw input:
    OVERTURE
    Slow. Maddeningly slow, YAYOI KUSAMA'S AFTERMATH OF
    OBLITERATION OF ETERNITY surrounds the title card.
  WRONG: {{"type":"dialogue","speaker":"OVERTURE","text":"Slow. Maddeningly slow..."}}
  CORRECT: {{"type":"action","text":"OVERTURE. Slow. Maddeningly slow, YAYOI KUSAMA'S AFTERMATH OF OBLITERATION OF ETERNITY surrounds the title card."}}
Same logic applies to a title-card reveal like "INTERVIEW WITH THE VAMPIRE" followed by \
"SMASH TO BLACK" — neither is dialogue; both are action/production description.

When in doubt: does the next line read like something a person would SAY out loud? If \
yes, the all-caps line above it was a cue. If not — if it's description, a transition \
instruction (CUT TO:, SMASH TO BLACK), or a section/title label — classify both as \
"action".

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
