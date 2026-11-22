"""Resolve proportional attachments, rasterize shells/roofs, then paint wall details."""
from collections import Counter
from dataclasses import dataclass
from math import floor

from .model import Plan

Point = tuple[int, int, int]
COLORS = {
    "white_concrete": "#e6e2d5", "light_gray_concrete": "#a8aaa2",
    "gray_concrete": "#696c70", "black_concrete": "#24282c",
    "red_concrete": "#ac3030", "yellow_concrete": "#d9b92d",
    "bricks": "#985b46", "stone_bricks": "#848984", "sandstone": "#dac796",
    "oak_planks": "#b38e58", "dark_oak_planks": "#58432d",
    "deepslate_tiles": "#3b4149", "glass": "#6f9aa5",
}


@dataclass
class Build:
    blocks: dict[Point, str]
    owners: dict[Point, str]
    boxes: dict[str, tuple[Point, Point]]
    warnings: list[str]

    def as_dict(self):
        palette = sorted(set(self.blocks.values()))
        indices = {name: i for i, name in enumerate(palette)}
        return {
            "format": "photo2craft-blocks-v1",
            "axes": "x=right, y=up, z=back; front is z-min",
            "palette": ["minecraft:" + m for m in palette],
            "blocks": [[*p, indices[self.blocks[p]], self.owners[p]] for p in sorted(self.blocks)],
            "boxes": self.boxes,
            "warnings": self.warnings,
        }


def compile_plan(plan: Plan, extent: int = 48) -> Build:
    if not 16 <= extent <= 64:
        raise ValueError("extent must be between 16 and 64 blocks")
    if plan.suitability == "unsupported":
        raise ValueError("analysis marked this photo unsupported; no build was fabricated")
    volumes = {v.id: v for v in plan.volumes}
    resolved, depths = {}, {}

    def resolve(vid):
        if vid in resolved:
            return resolved[vid]
        v = volumes[vid]
        if v.parent is None:
            origin, size, depth = (0.0, 0.0, 0.0), v.size, 0
        else:
            po, ps = resolve(v.parent)
            origin = tuple(po[i] + ps[i] * v.offset[i] for i in range(3))
            size = tuple(ps[i] * v.size[i] for i in range(3))
            depth = depths[v.parent] + 1
        depths[vid] = depth
        resolved[vid] = origin, size
        return origin, size

    for vid in volumes:
        resolve(vid)
    lo = [min(o[i] for o, s in resolved.values()) for i in range(3)]
    hi = [max(o[i] + s[i] + (s[1] * volumes[k].roof.rise
              if i == 1 and volumes[k].roof.kind != "none" else 0)
              for k, (o, s) in resolved.items()) for i in range(3)]
    scale = extent / max(b - a for a, b in zip(lo, hi))
    warnings, boxes, roof_tops = [], {}, {}

    def q(value, axis):
        return max(0, min(extent, floor((value - lo[axis]) * scale + 0.5)))

    for vid, (o, s) in resolved.items():
        start, stop = [], []
        for i in range(3):
            a, b = q(o[i], i), q(o[i] + s[i], i)
            if b <= a:
                a = min(a, extent - 1)
                b = a + 1
                warnings.append(f"{vid}: axis {i} expanded to one block after rounding")
            start.append(a)
            stop.append(b)
        boxes[vid] = tuple(start), tuple(stop)
        roof = volumes[vid].roof
        top = q(o[1] + s[1] * (1 + roof.rise), 1)
        if roof.kind != "none" and top <= stop[1]:
            warnings.append(f"{vid}: roof lost at this resolution")
        roof_tops[vid] = top

    blocks, owners = {}, {}

    def put(p, material, owner):
        blocks[p], owners[p] = material, owner

    # Children overwrite parents, independent of the order received from the AI.
    for vid in sorted(volumes, key=lambda k: (depths[k], k)):
        v = volumes[vid]
        (x0, y0, z0), (x1, y1, z1) = boxes[vid]
        for x in range(x0, x1):
            for y in range(y0, y1):
                for z in range(z0, z1):
                    boundary = x in (x0, x1-1) or y in (y0, y1-1) or z in (z0, z1-1)
                    if not v.shell or boundary:
                        put((x, y, z), v.material, vid)
        roof = v.roof
        rise = roof_tops[vid] - y1
        if roof.kind == "none" or rise <= 0:
            continue
        span = x1-x0 if roof.ridge_axis == "z" else z1-z0

        def height(across):
            if roof.kind == "flat":
                return rise
            distance = min(across, span-1-across)
            return 1 + floor((rise-1) * distance / max(1, (span-1)//2) + 0.5)

        for x in range(x0, x1):
            for z in range(z0, z1):
                a = x-x0 if roof.ridge_axis == "z" else z-z0
                h = height(a)
                neighbor_h = [height(n) for n in (a-1, a+1) if 0 <= n < span]
                slope_start = min([h-1] + neighbor_h)
                end = z in (z0, z1-1) if roof.ridge_axis == "z" else x in (x0, x1-1)
                for y in range(h):
                    roof_surface = y >= slope_start
                    if roof.kind == "flat" or roof_surface or end:
                        put((x, y1+y, z), roof.material if roof_surface or roof.kind == "flat" else v.material, vid)

    # Paint only the named volume's existing face, including gable end walls.
    # No detail may create floating glass in empty space or overwrite another volume.
    for d in sorted(plan.details, key=lambda d: d.id):
        (x0, y0, z0), (x1, y1, z1) = boxes[d.volume]
        along_x = d.face in ("front", "back")
        start, end = (x0, x1) if along_x else (z0, z1)
        length, height = end-start, y1-y0
        a0 = min(end-1, start + floor(d.u * length + 0.5))
        a1 = min(end, max(a0+1, start + floor((d.u+d.width) * length + 0.5)))
        b0 = y0 + floor(d.v * height + 0.5)
        b1 = max(b0+1, y0 + floor((d.v+d.height) * height + 0.5))
        count = 0
        for a in range(a0, a1):
            for b in range(b0, b1):
                if along_x:
                    p = (a, b, z0 if d.face == "front" else z1-1)
                else:
                    p = (x0 if d.face == "left" else x1-1, b, a)
                if owners.get(p) != d.volume:
                    continue
                # Avoid a frame consuming a narrow opening entirely.
                framed = d.frame and a1-a0 >= 3 and b1-b0 >= 3
                edge = a in (a0, a1-1) or b in (b0, b1-1)
                put(p, d.frame if framed and edge else d.material, d.id)
                count += 1
        expected = (a1-a0) * (b1-b0)
        if count < expected:
            warnings.append(f"{d.id}: {count}/{expected} face cells painted (absent/occluded/overlapping)")

    owned = Counter(owners.values())
    for vid in volumes:
        if not owned[vid]:
            warnings.append(f"{vid}: entirely overwritten")
    if plan.suitability == "approximate":
        warnings.append("analysis marked this building approximate")
    return Build(blocks, owners, boxes, warnings)
