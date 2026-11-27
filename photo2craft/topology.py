"""Face connectivity checks shared by the block corrections."""
from collections import deque

import numpy as np


def neighbors(cell):
    x, y, z = cell
    return ((x - 1, y, z), (x + 1, y, z), (x, y - 1, z), (x, y + 1, z),
            (x, y, z - 1), (x, y, z + 1))


def components(occupied):
    remaining = set(map(tuple, np.argwhere(occupied).tolist()))
    while remaining:
        start = remaining.pop()
        component = {start}
        queue = deque([start])
        while queue:
            for point in neighbors(queue.popleft()):
                if point in remaining:
                    remaining.remove(point)
                    component.add(point)
                    queue.append(point)
        yield component


def keeps_connections(before, after, *, allow_discard=False):
    labels = {point: label for label, part in enumerate(components(after)) for point in part}
    existing = set(map(tuple, np.argwhere(before).tolist()))
    if set(labels.values()) != {labels[point] for point in existing if point in labels}:
        return False
    for part in components(before):
        retained = {labels[point] for point in part if point in labels}
        if len(retained) > 1 or (len(part) > 1 and not retained and not allow_discard):
            return False
    return True


def trim_connected(occupied, outside):
    candidate = occupied.copy()
    candidate[tuple(outside.T)] = False
    if keeps_connections(occupied, candidate, allow_discard=True):
        return candidate

    # A removal is safe if its immediate neighbors still share a local path.
    # Isolated components can still be removed when Clay marks the entire component.
    candidate = np.pad(occupied, 1)
    for point in outside + 1:
        x, y, z = point
        neighborhood = candidate[x - 1:x + 2, y - 1:y + 2, z - 1:z + 2].copy()
        neighborhood[1, 1, 1] = False
        touching = {cell for cell in neighbors((1, 1, 1)) if neighborhood[cell]}
        if len(touching) < 2 or any(touching <= part for part in components(neighborhood)):
            candidate[x, y, z] = False
    return candidate[1:-1, 1:-1, 1:-1].copy()
