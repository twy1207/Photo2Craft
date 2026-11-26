"""Voxelize a GLB surface using triangle–unit-cube intersection."""
from dataclasses import dataclass
from hashlib import sha256
from math import cos, isfinite, radians, sin
import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image

from .clay import review_clay
from .compile import Build
from .trellis import verify_glb

EPSILON = 1e-8
CANDIDATES_PER_BATCH = 65_536
REVIEW_FORMAT = "photo2craft-mesh-review-v1"
PHOTO_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


@dataclass(frozen=True)
class BlockGrid:
    rotation: np.ndarray
    minimum: np.ndarray
    scale: float
    size: np.ndarray

    def world_points(self, points):
        return (points / self.scale + self.minimum) @ self.rotation.T

    def viewer_target(self):
        origin = -self.minimum * self.scale
        width, _, depth = self.size
        return [float(origin[0] - width / 2), float(origin[1]), float(depth / 2 - origin[2])]


def grid_coordinates(vertices, front_yaw, extent):
    if not 16 <= extent <= 64:
        raise ValueError("블록 크기는 16부터 64 사이로 지정해 주세요.")
    if not isfinite(front_yaw):
        raise ValueError("정면 각도는 유한한 숫자로 지정해 주세요.")
    angle = radians(front_yaw % 360)
    c, s = cos(angle), sin(angle)
    rotation = np.array([[c, 0, -s], [0, 1, 0], [-s, 0, -c]])
    oriented = vertices @ rotation
    minimum = oriented.min(axis=0)
    oriented -= minimum
    longest = oriented.max()
    if not isfinite(longest) or longest <= EPSILON:
        raise ValueError("GLB에 사용할 수 있는 크기가 없습니다.")
    scale = extent / longest
    positions = oriented * scale
    size = np.clip(np.ceil(positions.max(axis=0) - EPSILON).astype(int), 1, extent)
    return positions, BlockGrid(rotation, minimum, float(scale), size)


def axis_overlaps(triangles, axes):
    # The radius of a centered unit cube projected onto each axis.
    radius = 0.5 * np.abs(axes).sum(axis=1)
    projections = np.einsum("tvc,tc->tv", triangles, axes)
    return ((projections.min(axis=1) <= radius + EPSILON) &
            (projections.max(axis=1) >= -radius - EPSILON))


def triangle_cube_overlap(triangles, edges, normals):
    # Grid bounds already check the three cube axes.
    keep = axis_overlaps(triangles, normals)
    for edge in np.moveaxis(edges, 1, 0):
        for cube_axis in np.eye(3):
            keep &= axis_overlaps(triangles, np.cross(edge, cube_axis))
    return keep


def voxelize(vertices, faces, shape):
    triangles = vertices[faces]
    edges = np.roll(triangles, -1, axis=1) - triangles
    normals = np.cross(edges[:, 0], edges[:, 1])
    valid = (normals * normals).sum(axis=1) > EPSILON**2
    triangles, edges, normals = triangles[valid], edges[valid], normals[valid]

    lower = np.clip(np.floor(triangles.min(axis=1)).astype(int), 0, shape - 1)
    upper = np.clip(np.floor(triangles.max(axis=1)).astype(int), 0, shape - 1)
    sizes = upper - lower + 1
    counts = sizes.prod(axis=1)
    offsets = np.concatenate(([0], np.cumsum(counts)))
    occupied = np.zeros(tuple(shape), dtype=bool)
    first = 0
    while first < len(triangles):
        stop = np.searchsorted(offsets, offsets[first] + CANDIDATES_PER_BATCH, side="right") - 1
        stop = min(len(triangles), max(first + 1, stop))
        indices = np.repeat(np.arange(first, stop), counts[first:stop])
        local_index = np.arange(offsets[first], offsets[stop]) - offsets[indices]
        y_size, z_size = sizes[indices, 1], sizes[indices, 2]
        cells = lower[indices] + np.column_stack((
            local_index // (y_size * z_size),
            (local_index // z_size) % y_size,
            local_index % z_size,
        ))
        centered = triangles[indices] - (cells + 0.5)[:, None, :]
        hits = cells[triangle_cube_overlap(centered, edges[indices], normals[indices])]
        occupied[tuple(hits.T)] = True
        first = stop
    return occupied


def build_from_grid(occupied):
    points = [tuple(point) for point in np.argwhere(occupied).tolist()]
    if not points:
        raise ValueError("GLB에서 채워진 블록을 찾지 못했습니다.")
    return Build(dict.fromkeys(points, "white_concrete"), dict.fromkeys(points, "mesh"), {}, [])


def load_geometry(path):
    import trimesh

    verify_glb(path)
    try:
        mesh = trimesh.load_scene(path, process=False, skip_materials=True).to_mesh()
    except (TypeError, ValueError, IndexError, KeyError, OSError) as exc:
        raise ValueError(f"GLB 삼각형을 읽지 못했습니다 ({type(exc).__name__}).") from None
    if not len(mesh.faces) or not np.isfinite(mesh.vertices).all():
        raise ValueError("GLB에 유효한 삼각형이 없습니다.")
    return mesh.vertices, mesh.faces


def write_review(mesh: Path, out: Path, *, photo=None, clay=None, front_yaw=0, extent=48):
    if out.exists():
        raise ValueError("새 출력 폴더를 지정해 주세요.")
    vertices, faces = load_geometry(mesh)
    positions, grid = grid_coordinates(vertices, front_yaw, extent)
    original = voxelize(positions, faces, grid.size)
    original_build = build_from_grid(original)
    clay_paths = {}
    if clay is not None:
        if not clay.is_dir():
            raise ValueError("Clay 이미지 폴더를 찾지 못했습니다.")
        for index in range(8):
            for name in (f"view-{index:02d}.jpg", f"clay-{index}.jpg"):
                path = clay / name
                if path.is_file():
                    clay_paths[index] = path
                    break
        if not clay_paths:
            raise ValueError("Clay 폴더에서 비교할 JPEG를 찾지 못했습니다.")

    corrected, comparison = review_clay(original, grid, vertices, faces, clay_paths, front_yaw)
    final_build = build_from_grid(corrected) if comparison["removed"] else original_build
    photo_name = None
    if photo is not None:
        with Image.open(photo) as image:
            extension = PHOTO_FORMATS.get(image.format)
            if extension is None:
                raise ValueError("원본 사진은 JPEG, PNG, WebP로 지정해 주세요.")
            image.verify()
        photo_name = f"photo.{extension}"

    report = {
        "format": REVIEW_FORMAT,
        "mesh_sha256": sha256(mesh.read_bytes()).hexdigest(),
        "extent": extent,
        "front_yaw": front_yaw % 360,
        "size": grid.size.tolist(),
        "photo": photo_name,
        "before_count": len(original_build.blocks),
        "after_count": len(final_build.blocks),
        **comparison,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".voxelize-", dir=out.parent) as work:
        stage = Path(work) / "review"
        stage.mkdir()
        documents = {"blocks.json": final_build.as_dict(), "mesh-review.json": report}
        if clay_paths:
            documents["blocks-before.json"] = original_build.as_dict()
            (stage / "clay").mkdir()
            for index, source in clay_paths.items():
                copyfile(source, stage / "clay" / f"view-{index:02d}.jpg")
        if photo_name:
            copyfile(photo, stage / photo_name)
        for name, data in documents.items():
            (stage / name).write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        stage.rename(out)
    print(f"블록 {report['before_count']:,} → {report['after_count']:,}개 - {out}")
