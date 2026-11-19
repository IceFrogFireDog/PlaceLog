from typing import Literal

from pydantic import BaseModel

MapMode = Literal["WORLD", "FRIENDS", "ME"]


class MapCluster(BaseModel):
    kind: Literal["cluster"] = "cluster"
    id: str
    latitude: float
    longitude: float
    photo_count: int
    place_count: int
    label: str


class MapPlace(BaseModel):
    kind: Literal["place"] = "place"
    place_id: str
    name: str
    latitude: float
    longitude: float
    photo_count: int


class MapResponse(BaseModel):
    mode: MapMode
    zoom: int
    items: list[MapCluster | MapPlace]
    truncated: bool = False
