from typing import Literal
from pydantic import BaseModel, Field

ElementType = Literal["action", "dialogue", "parenthetical"]


class DialogueElement(BaseModel):
    type: ElementType
    speaker: str | None = None
    text: str


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
