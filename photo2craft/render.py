"""Small CPU renderer for inspection; no external assets or browser required."""
from math import cos, radians, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .compile import Build, COLORS

# Vertices for faces with outward normals, in unit cube coordinates.
FACES = (
    ((1, 0, 0), ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))),
    ((-1, 0, 0), ((0, 0, 1), (0, 1, 1), (0, 1, 0), (0, 0, 0))),
    ((0, 1, 0), ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0))),
    ((0, -1, 0), ((0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 0, 1))),
    ((0, 0, 1), ((1, 0, 1), (1, 1, 1), (0, 1, 1), (0, 0, 1))),
    ((0, 0, -1), ((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0))),
)


def render(build: Build, yaw: float, elevation: float, size=(680, 520)) -> Image.Image:
    """Orthographic visible faces, shaded by direction. Glass is deliberately opaque."""
    yaw, elevation = radians(yaw), radians(elevation)
    camera = (sin(yaw)*cos(elevation), sin(elevation), -cos(yaw)*cos(elevation))

    def project(p):
        x, y, z = p
        return cos(yaw)*x + sin(yaw)*z, sin(yaw)*sin(elevation)*x - cos(elevation)*y - cos(yaw)*sin(elevation)*z

    faces = []
    for pos, material in build.blocks.items():
        for normal, vertices in FACES:
            facing = sum(a*b for a, b in zip(normal, camera))
            neighbor = tuple(a+b for a, b in zip(pos, normal))
            if facing <= 1e-8 or neighbor in build.blocks:
                continue
            world = [tuple(a+b for a, b in zip(pos, v)) for v in vertices]
            depth = sum(sum(p[i]*camera[i] for i in range(3)) for p in world) / 4
            brightness = .96 if normal[1] else (.78 if normal[0] else .88)
            color = COLORS[material]
            rgb = tuple(round(int(color[i:i+2], 16)*brightness) for i in (1, 3, 5))
            faces.append((depth, [project(p) for p in world], rgb))
    points = [p for _, poly, _ in faces for p in poly]
    if not points:
        raise ValueError("nothing to render")
    lo = [min(p[i] for p in points) for i in range(2)]
    hi = [max(p[i] for p in points) for i in range(2)]
    factor = min((size[i]-50)/max(1, hi[i]-lo[i]) for i in range(2))
    origin = [(size[i]-(hi[i]-lo[i])*factor)/2 for i in range(2)]
    im = Image.new("RGB", (size[0]*2, size[1]*2), "#edf0f2")
    draw = ImageDraw.Draw(im)
    for _, poly, rgb in sorted(faces, key=lambda f: f[0]):
        xy = [tuple(2*(origin[i]+(p[i]-lo[i])*factor) for i in range(2)) for p in poly]
        draw.polygon(xy, fill=rgb)
    return im.resize(size, Image.Resampling.LANCZOS)


def write_comparison(build: Build, photo: Path | None, destination: Path, view="front_right"):
    sheet = Image.new("RGB", (1440, 1080), "#ffffff")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=20)
    yaw = {"front": 0, "front_left": -35, "front_right": 35}[view]
    slots = ((20, 20, "INPUT PHOTO" if photo else "SYNTHETIC PLAN / FRONT + LEFT"), (740, 20, view.upper().replace('_', ' + ') + " (orthographic)"),
             (20, 550, "FRONT (orthographic)"), (740, 550, "OPPOSITE VIEW (inferred areas)"))
    if photo:
        with Image.open(photo) as source:
            first = ImageOps.contain(ImageOps.exif_transpose(source).convert("RGB"), (680, 480))
    else:
        first = render(build, -40, 22, (680, 480))
    pictures = (first, render(build, yaw, 18, (680, 480)),
                render(build, 0, 0, (680, 480)), render(build, yaw+180, 22, (680, 480)))
    for (x, y, title), picture in zip(slots, pictures):
        draw.text((x, y), title, fill="#273844", font=font)
        sheet.paste(picture, (x+(680-picture.width)//2, y+32+(480-picture.height)//2))
    draw.text((20, 1050), "Flat block colors; opaque glass. Views are not camera-calibrated. Photo credits: source.json.",
              fill="#53616b", font=ImageFont.load_default(size=16))
    sheet.save(destination)
