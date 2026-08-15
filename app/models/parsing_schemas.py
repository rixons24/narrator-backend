from typing import Literal
from pydantic import BaseModel, Field

ElementType = Literal["action", "dialogue", "parenthetical"]


class DialogueElement(BaseModel):
    type: ElementType
    speaker: str | None = None
    text: str
    # Populated only when sound-effect detection is requested (see
    # ParseRequest.detect_sound_effects). A short, clean phrase suitable
    # for an audio-generation model (e.g. "A deafening roar" rather than
    # the raw screenplay line), or None if this line isn't a sound cue.
    sfx_prompt: str | None = None


class ParsedScene(BaseModel):
    scene_index: int
    heading: str
    location: str | None = None
    time_of_day: str | None = None
    characters_present: list[str] = Field(default_factory=list)
    elements: list[DialogueElement] = Field(default_factory=list)


class CharacterAlias(BaseModel):
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)


class ParsedScript(BaseModel):
    title: str | None = None
    scenes: list[ParsedScene]
    characters: list[CharacterAlias] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
