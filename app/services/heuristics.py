import re

SCENE_HEADING_RE = re.compile(r'^(INT|EXT|EST|INT\.?/EXT|I/E)[.\s/]', re.I)

CUE_BLACKLIST = [
    'FADE IN', 'FADE OUT', 'FADE TO BLACK', 'FADE TO', 'CUT TO', 'SMASH CUT TO',
    'MATCH CUT TO', 'DISSOLVE TO', 'CONTINUED', 'THE END', 'END OF', 'MONTAGE',
    'INTERCUT', 'BACK TO SCENE', 'TITLE CARD', 'SUPER', 'INSERT', 'TIME CUT',
    'LATER', 'MOMENTS LATER', 'CONTINUOUS',
]


def is_scene_heading(line: str) -> bool:
    return bool(SCENE_HEADING_RE.match(line.strip()))


def is_character_cue(line: str) -> bool:
    t = line.strip()
    if not t or is_scene_heading(t):
        return False
    core = re.sub(r'\s*\([^)]*\)\s*$', '', t).strip()
    if not core or len(core) > 38 or not re.search(r'[A-Za-z]', core):
        return False
    if core != core.upper():
        return False
    upper_no_colon = re.sub(r':$', '', core)
    for term in CUE_BLACKLIST:
        if upper_no_colon == term or upper_no_colon.startswith(term):
            return False
    if re.match(r'^\d+[.)]?$', core):
        return False
    return True
