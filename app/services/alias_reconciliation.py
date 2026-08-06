"""Cross-scene character alias reconciliation — provider-agnostic."""
from app.models.parsing_schemas import CharacterAlias, ParsedScene
from app.services.llm_client import LLMError, generate_json

_FILTER_WORDS = {'she', 'he', 'they', 'her', 'him', 'them', 'it', 'we', 'i', 'you', 'his', 'hers', 'its'}

SYSTEM_PROMPT = """You are given a normalised list of character names extracted from \
different scenes of the same screenplay. Group entries that refer to the SAME individual \
person and pick a single canonical name for each group.

RULES:
1. SAME PERSON means the same individual, not just a shared role or surname. Two \
characters can share a surname and be DIFFERENT people — do NOT merge on surname alone.
2. MERGE only when confident: a full name + first-name shorthand for the same person, or \
a character introduced by name later referred to only by role/title.
3. When uncertain, DO NOT MERGE.
4. CANONICAL NAME: prefer the full proper name over a shorthand or role title.
5. Do not invent or drop names.

Output ONLY JSON:
{"characters": [{"canonical_name": string, "aliases": [string, ...]}]}

Every input name must appear exactly once — as a canonical_name or inside one alias list."""

USER_PROMPT_TEMPLATE = """Character names found across the script:

{name_list}

Apply the grouping rules and output the JSON now."""


def _normalise_name(name: str) -> str:
    return ' '.join(w.capitalize() for w in name.strip().split())


def _is_valid_character_name(name: str) -> bool:
    stripped = name.strip()
    if not stripped or len(stripped) < 2:
        return False
    if stripped.lower() in _FILTER_WORDS:
        return False
    if not any(c.isalpha() for c in stripped):
        return False
    return True


def _collect_names_with_context(scenes: list[ParsedScene]) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for scene in scenes:
        heading = scene.heading or f"scene {scene.scene_index}"
        for raw_name in scene.characters_present:
            if not _is_valid_character_name(raw_name):
                continue
            norm = _normalise_name(raw_name)
            if norm not in seen:
                seen[norm] = heading
    return list(seen.items())


async def reconcile_aliases(scenes: list[ParsedScene]) -> list[CharacterAlias]:
    name_context = _collect_names_with_context(scenes)
    if not name_context:
        return []

    name_list = '\n'.join(f"- {name} (first seen in: {heading})" for name, heading in name_context)
    prompt = USER_PROMPT_TEMPLATE.format(name_list=name_list)

    try:
        data = await generate_json(prompt, system=SYSTEM_PROMPT)
        characters = [
            CharacterAlias(canonical_name=c["canonical_name"], aliases=c.get("aliases", []))
            for c in data.get("characters", [])
        ]
        covered = {_normalise_name(c.canonical_name) for c in characters} | {
            _normalise_name(a) for c in characters for a in c.aliases
        }
        for name, _ in name_context:
            if name not in covered:
                characters.append(CharacterAlias(canonical_name=name, aliases=[]))
        return characters
    except LLMError:
        return [CharacterAlias(canonical_name=name, aliases=[]) for name, _ in name_context]
