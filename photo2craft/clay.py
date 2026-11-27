"""Compare voxel silhouettes with the original TRELLIS.2 Clay cameras."""
from math import cos, radians, sin, tan

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .topology import trim_connected

RESOLUTION = 256
RADIUS = 2
FOV = 36
ELEVATION = 20
MIN_ALIGNMENT = .9
MAX_COVERAGE_LOSS = .003


def project(points, yaw):
    # GLB export maps TRELLIS (x, y, z) to (x, z, -y).
    a, b = radians(yaw), radians(ELEVATION)
    direction = np.array([sin(a) * cos(b), sin(b), cos(a) * cos(b)])
    right = np.array([cos(a), 0, -sin(a)])
    up = np.cross(direction, right)
    focal = RESOLUTION / (2 * tan(radians(FOV / 2)))
    factor = focal / (RADIUS - points @ direction)
    return RESOLUTION / 2 + np.stack((points @ right, -points @ up), axis=-1) * factor[..., None]


def raster_mask(polygons):
    image = Image.new("1", (RESOLUTION, RESOLUTION))
    draw = ImageDraw.Draw(image)
    for polygon in np.rint(polygons).astype(int).tolist():
        draw.polygon([tuple(point) for point in polygon], fill=1)
    return np.asarray(image)


def clay_mask(path):
    with Image.open(path, formats=["JPEG"]) as image:
        gray = image.convert("L").resize((RESOLUTION, RESOLUTION), Image.Resampling.LANCZOS)
    foreground = gray.point(lambda value: 255 if value > 24 else 0)
    # Only the background connected to the border counts as outside the silhouette.
    marked = ImageOps.expand(foreground, border=1, fill=0)
    ImageDraw.floodfill(marked, (0, 0), 128)
    return np.asarray(marked)[1:-1, 1:-1] != 128


def surface_quads(occupied):
    padded = np.pad(occupied, 1)
    quads = []
    for axis in range(3):
        other_axes = [i for i in range(3) if i != axis]
        for side in (0, 1):
            neighbor = [slice(1, -1)] * 3
            neighbor[axis] = slice(2, None) if side else slice(None, -2)
            exposed = np.argwhere(occupied & ~padded[tuple(neighbor)])
            offsets = np.zeros((4, 3), dtype=int)
            offsets[:, axis] = side
            offsets[:, other_axes] = [[0, 0], [1, 0], [1, 1], [0, 1]]
            quads.append(exposed[:, None, :] + offsets)
    return np.concatenate(quads)


def overlap(target, actual):
    intersection = np.count_nonzero(target & actual)
    union = np.count_nonzero(target | actual)
    return float(intersection / union) if union else 0.0


def review_clay(original, grid, vertices, faces, paths, front_yaw, *, protected=None):
    result = {"removed": 0, "views": []}
    if not paths:
        return original, result
    if np.linalg.norm(vertices, axis=1).max() >= RADIUS - .1:
        raise ValueError("Clay와 비교하려면 같은 생성에서 받은 TRELLIS.2 GLB를 지정해 주세요.")

    result["camera"] = {"target": grid.viewer_target(), "radius": RADIUS * grid.scale, "fov": FOV}
    points = np.argwhere(original)
    centers = grid.world_points(points + .5)
    votes = np.zeros(len(points), dtype=np.uint8)
    matched = []
    for index, path in paths.items():
        yaw = (196 - 45 * index) % 360
        target = clay_mask(path)
        mesh_mask = raster_mask(project(vertices, yaw)[faces])
        fit = overlap(target, mesh_mask)
        view = {"index": index, "yaw": (yaw - front_yaw) % 360, "elevation": ELEVATION,
                "alignment": round(fit, 4), "matched": fit >= MIN_ALIGNMENT}
        result["views"].append(view)
        if view["matched"]:
            expanded = Image.fromarray(target.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(3))
            expanded = np.pad(np.asarray(expanded) > 0, 1)
            pixels = np.clip(np.floor(project(centers, yaw)).astype(int), -1, RESOLUTION) + 1
            votes += ~expanded[pixels[:, 1], pixels[:, 0]]
            matched.append((yaw, target, view))

    result["aligned_views"] = len(matched)
    outside = points[votes >= 2]
    if protected is not None:
        outside = outside[~protected[tuple(outside.T)]]
    if len(matched) < 2 or not len(outside) or len(outside) == len(points):
        return original, result

    candidate = trim_connected(original, outside)
    removed = int(np.count_nonzero(original & ~candidate))
    if not removed:
        return original, result
    before_faces = grid.world_points(surface_quads(original))
    after_faces = grid.world_points(surface_quads(candidate))
    before_scores, after_scores, losses = [], [], []
    for yaw, target, view in matched:
        before_mask = raster_mask(project(before_faces, yaw))
        after_mask = raster_mask(project(after_faces, yaw))
        before_scores.append(overlap(target, before_mask))
        after_scores.append(overlap(target, after_mask))
        losses.append(np.count_nonzero(target & before_mask & ~after_mask) / np.count_nonzero(target))
    accepted = sum(after_scores) > sum(before_scores) and max(losses) <= MAX_COVERAGE_LOSS
    for (_, _, view), before_score, after_score in zip(matched, before_scores, after_scores):
        view["before_iou"] = round(before_score, 4)
        view["after_iou"] = round(after_score if accepted else before_score, 4)
    if accepted:
        result["removed"] = removed
        return candidate, result
    return original, result
