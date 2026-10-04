"""Strict JSON request contracts; domain services receive plain values."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Identity(Body):
    nickname: Annotated[str, Field(min_length=1, max_length=24)]
    character_id: str = "coral"


class Create(Identity):
    mode: Literal["demo", "normal"] = "demo"


class MusicAdmission(Identity):
    room_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None


class Settings(Body):
    round_count: Literal[5, 10, 15] = 10
    answer_seconds: Literal[10, 20, 30] = 20
    difficulty: Literal["easy", "mixed", "hard"] = "mixed"
    decoys_enabled: bool = True


class Command(Body):
    request_id: Annotated[str, Field(min_length=1, max_length=128)]


class Start(Command):
    room_revision: Annotated[int, Field(ge=0)]
    lease_id: str


class Preload(Command):
    lease_id: str
    candidate_id: str
    ok: bool
    waveform: (
        Annotated[
            list[Annotated[float, Field(ge=0, le=1)]],
            Field(min_length=8, max_length=64),
        ]
        | None
    ) = None


class Ready(Body):
    readiness_generation: Annotated[int, Field(ge=1)]
    lease_id: str | None = None


class UpcomingReady(Ready):
    browser_id: Annotated[str, Field(min_length=1, max_length=128)]


class Recovery(Command):
    readiness_generation: Annotated[int, Field(ge=1)]


class Continue(Recovery):
    exclude_player_ids: Annotated[list[str], Field(max_length=10)]


class Failure(Recovery):
    lease_id: str
    reason: Annotated[str, Field(max_length=100)] = "audio_failed"


class Answer(Body):
    song_guess_token: Annotated[str, Field(min_length=1, max_length=12000)] | None = (
        None
    )
    who_player_ids: Annotated[list[str], Field(max_length=10)] = []


class Controller(Body):
    tab_id: Annotated[str, Field(min_length=1, max_length=128)]
    takeover: bool = False


class SongSelection(Body):
    token: Annotated[str, Field(min_length=1, max_length=12000)]
