"""Orchestrates cleanup -> scene split -> LLM structuring -> alias reconciliation."""
from app.models.parsing_schemas import ParsedScript
from app.services.alias_reconciliation import reconcile_aliases
from app.services.cleanup import clean_script_text_default
from app.services.scene_parser import parse_scene, parse_script_scenes
from app.services.scene_splitter import split_into_scenes
from app.services.llm_client import LLMError


async def parse_script(
    raw_text: str,
    title: str | None = None,
    detect_sound_effects: bool = False,
    on_progress=None,
) -> ParsedScript:
    cleaned = clean_script_text_default(raw_text)
    scenes = split_into_scenes(cleaned)

    if not scenes:
        return ParsedScript(
            title=title, scenes=[], characters=[],
            warnings=["No scenes found — check script has INT./EXT. headings."]
        )

    total = len(scenes)
    warnings: list[str] = []
    parsed_scenes = []

    # Warm-up: scene 0 alone first (matters more for local Ollama cold-start,
    # harmless overhead for Groq)
    first = scenes[0]
    try:
        parsed_scenes.append(await parse_scene(first, detect_sound_effects=detect_sound_effects))
    except LLMError as e:
        warnings.append(f"Scene {first.index} ({first.heading or 'untitled'}): {e}")
    if on_progress:
        on_progress(1, total)

    if len(scenes) > 1:
        def _rest_progress(done: int, rest_total: int):
            # done/rest_total covers scenes[1:] — offset by the warm-up scene
            # already counted above so the caller sees one consistent total.
            if on_progress:
                on_progress(1 + done, total)

        rest_parsed, rest_warnings = await parse_script_scenes(
            scenes[1:], detect_sound_effects=detect_sound_effects, on_progress=_rest_progress,
        )
        parsed_scenes.extend(rest_parsed)
        warnings.extend(rest_warnings)

    parsed_scenes.sort(key=lambda s: s.scene_index)
    characters = await reconcile_aliases(parsed_scenes)

    return ParsedScript(title=title, scenes=parsed_scenes, characters=characters, warnings=warnings)
