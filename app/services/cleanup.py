"""Deterministic text-level fixes run before the LLM sees the script."""
import re

PAGE_NUMBER_RE = re.compile(r'^\d+\.\s*$')
WRITTEN_BY_RE = re.compile(r'^written\s+by:?$', re.I)
CREATED_BY_RE = re.compile(r'^created\s+by:?$', re.I)


def strip_page_numbers(text: str) -> str:
    lines = text.split('\n')
    return '\n'.join(l for l in lines if not PAGE_NUMBER_RE.match(l.strip()))


def strip_title_page(text: str, scene_heading_pattern) -> str:
    lines = text.split('\n')
    i, n = 0, len(lines)

    def is_blank(s): return not s.strip()

    while i < n and is_blank(lines[i]):
        i += 1
    if i >= n:
        return text

    first = lines[i].strip()
    looks_like_title = (
        first and first == first.upper() and len(first) <= 60
        and not scene_heading_pattern.match(first)
    )
    if not looks_like_title:
        return text

    lookahead = [l.strip() for l in lines[i:i + 8]]
    has_credit_marker = any(WRITTEN_BY_RE.match(l) or CREATED_BY_RE.match(l) for l in lookahead)
    if not has_credit_marker:
        return text

    cursor = i + 1
    while cursor < n:
        line = lines[cursor].strip()
        if is_blank(line):
            cursor += 1
            continue
        if WRITTEN_BY_RE.match(line) or CREATED_BY_RE.match(line):
            cursor += 1
            continue
        looks_like_name = (
            line != line.upper() and len(line) <= 60
            and not scene_heading_pattern.match(line)
            and not line.endswith(('.', '!', '?'))
        )
        if looks_like_name:
            cursor += 1
            continue
        break

    remaining = lines[cursor:]
    while remaining and is_blank(remaining[0]):
        remaining = remaining[1:]
    return '\n'.join(remaining)


def merge_more_continuations(text: str) -> str:
    lines = text.split('\n')
    out, i = [], 0
    while i < len(lines):
        if lines[i].strip().upper() == '(MORE)':
            i += 1
            while i < len(lines) and lines[i].strip() == '':
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return '\n'.join(out)


def canonicalize_cue_name(cue_line: str) -> str:
    """Strip trailing parenthetical modifiers and leading punctuation noise
    (e.g. a stray ',' from PDF extraction: ',MAN' -> 'MAN')."""
    name = cue_line.strip()
    while True:
        new_name = re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()
        if new_name == name:
            break
        name = new_name
    name = re.sub(r'^[^A-Za-z]+', '', name)
    return name.rstrip(':').strip()


def normalize_cue_lines(text: str, is_cue_fn) -> str:
    """Rewrite every detected cue line to its clean canonical form BEFORE
    the LLM sees the script — fixes malformed cues like ',MAN' -> 'MAN'
    that would otherwise confuse the LLM's cue-vs-emphasis judgment."""
    lines = text.split('\n')
    out = []
    for line in lines:
        stripped = line.strip()
        if is_cue_fn(stripped):
            clean = canonicalize_cue_name(stripped)
            if clean:
                out.append(clean)
                continue
        out.append(line)
    return '\n'.join(out)


def collapse_duplicate_continuation_cues(text: str, is_cue_fn, canonical_name_fn) -> str:
    """Collapse an orphaned '(CONT'D)' cue immediately followed (across a
    stripped page break) by the same speaker's repeated cue."""
    lines = text.split('\n')
    out, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if is_cue_fn(line) and "CONT'D" in line.upper():
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines) and is_cue_fn(lines[j].strip()):
                name_a = canonical_name_fn(line)
                name_b = canonical_name_fn(lines[j].strip())
                if name_a == name_b:
                    i = j
                    continue
        out.append(lines[i])
        i += 1
    return '\n'.join(out)


def clean_script_text(raw_text: str, is_cue_fn, scene_heading_pattern) -> str:
    text = strip_page_numbers(raw_text)
    text = strip_title_page(text, scene_heading_pattern)
    text = merge_more_continuations(text)
    text = normalize_cue_lines(text, is_cue_fn)
    text = collapse_duplicate_continuation_cues(text, is_cue_fn, canonicalize_cue_name)
    return text


def clean_script_text_default(raw_text: str) -> str:
    from app.services.heuristics import is_character_cue, SCENE_HEADING_RE
    return clean_script_text(raw_text, is_character_cue, SCENE_HEADING_RE)
