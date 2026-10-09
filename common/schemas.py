import re

from pydantic import BaseModel, model_validator
from datetime import datetime

from typing import Any, Callable, Awaitable
from pathlib import Path


class MovieSchema(BaseModel):
    year: int
    name: str


class _Episode(BaseModel):
    series_name: str
    episode_title: str

class ShowSchema(BaseModel):
    year:int
    name: str
    seasons: dict[int, dict[int, _Episode]]


class MusicShema(BaseModel):
    artist: str
    albums: dict[str, list[str]]


class Request(BaseModel):
    transformations: dict[Path, Path]
