from dataclasses import dataclass
from app.services.heuristics import is_scene_heading


@dataclass
class Scene:
    index: int
    heading: str
    body: str


def split_into_scenes(cleaned_text: str) -> list[Scene]:
    lines = cleaned_text.split('\n')
    scenes: list[Scene] = []
    current_heading = ''
    current_lines: list[str] = []
    scene_index = 0

    def flush():
        nonlocal current_lines, current_heading, scene_index
        if current_lines or current_heading:
            body = '\n'.join(current_lines).strip('\n')
            scenes.append(Scene(index=scene_index, heading=current_heading, body=body))
            scene_index += 1
        current_lines = []

    for line in lines:
        if is_scene_heading(line):
            flush()
            current_heading = line.strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    flush()
    return scenes
