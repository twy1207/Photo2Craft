"""Relative volumes and wall-bound details; all coordinates are building-local."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(allow_inf_nan=False)]
Ratio = Annotated[Number, Field(gt=0, le=4)]
Offset = Annotated[Number, Field(ge=-4, le=4)]
Unit = Annotated[Number, Field(ge=0, le=1)]
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
Material = Literal[
    "white_concrete", "light_gray_concrete", "gray_concrete", "black_concrete",
    "red_concrete", "yellow_concrete", "bricks", "stone_bricks", "sandstone",
    "oak_planks", "dark_oak_planks", "deepslate_tiles", "glass",
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Roof(Model):
    kind: Literal["none", "flat", "gable"]
    rise: Annotated[Number, Field(ge=0, le=2)]
    ridge_axis: Literal["x", "z"]
    material: Material

    @model_validator(mode="after")
    def check_rise(self):
        if self.kind == "gable" and self.rise <= 0:
            raise ValueError("a gable needs a positive rise relative to its body's height")
        return self


class Volume(Model):
    id: Identifier
    parent: Identifier | None
    offset: tuple[Offset, Offset, Offset]
    size: tuple[Ratio, Ratio, Ratio]
    shell: bool
    material: Material
    roof: Roof
    evidence: Annotated[str, Field(min_length=1, max_length=400)]
    inferred: bool


class SurfaceDetail(Model):
    id: Identifier
    volume: Identifier
    face: Literal["front", "back", "left", "right"]
    # U increases along world X (front/back) or Z (left/right), not camera-left.
    u: Unit
    v: Annotated[Number, Field(ge=0, le=3)]
    width: Annotated[Number, Field(gt=0, le=1)]
    height: Annotated[Number, Field(gt=0, le=3)]
    material: Material
    frame: Material | None
    evidence: Annotated[str, Field(min_length=1, max_length=400)]
    inferred: bool

    @model_validator(mode="after")
    def within_face(self):
        if self.u + self.width > 1.000001 or self.v + self.height > 3.000001:
            raise ValueError("surface detail exceeds the face coordinate range")
        return self


class Plan(Model):
    schema_version: Literal[1]
    title: Annotated[str, Field(min_length=1, max_length=160)]
    view: Literal["front", "front_left", "front_right"] = "front_right"
    suitability: Literal["supported", "approximate", "unsupported"]
    observations: Annotated[list[str], Field(min_length=1, max_length=12)]
    assumptions: Annotated[list[str], Field(max_length=12)]
    volumes: Annotated[list[Volume], Field(min_length=1, max_length=24)]
    details: Annotated[list[SurfaceDetail], Field(max_length=60)]

    @model_validator(mode="after")
    def relationships(self):
        ids = [v.id for v in self.volumes] + [d.id for d in self.details]
        if len(ids) != len(set(ids)):
            raise ValueError("all volume and detail IDs must be unique")
        volumes = {v.id: v for v in self.volumes}
        roots = [v for v in self.volumes if v.parent is None]
        if len(roots) != 1 or roots[0].offset != (0, 0, 0) or roots[0].size[0] != 1:
            raise ValueError("exactly one root: offset=[0,0,0], size=[1,height/width,depth/width]")
        for v in self.volumes:
            seen = {v.id}
            parent = v.parent
            while parent is not None:
                if parent not in volumes or parent in seen:
                    raise ValueError(f"{v.id}: missing parent or cyclic attachment")
                seen.add(parent)
                parent = volumes[parent].parent
        if any(d.volume not in volumes for d in self.details):
            raise ValueError("detail refers to a missing volume")
        return self
