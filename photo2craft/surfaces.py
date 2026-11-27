"""Regularize broad surfaces using depth samples from the input mesh."""
from collections import deque

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .topology import keeps_connections


def axis_depths(triangles, shape, axis):
    """Intersect rays through grid-cell centers with the mesh, from both sides."""
    lateral = [i for i in range(3) if i != axis]
    dimensions = shape[lateral]
    xy = triangles[:, :, lateral]
    edge_u, edge_v = xy[:, 1] - xy[:, 0], xy[:, 2] - xy[:, 0]
    determinant = edge_u[:, 0] * edge_v[:, 1] - edge_u[:, 1] * edge_v[:, 0]
    lower = np.maximum(0, np.ceil(xy.min(axis=1) - .5 - 1e-8).astype(int))
    upper = np.minimum(dimensions - 1, np.floor(xy.max(axis=1) - .5 + 1e-8).astype(int))
    valid = (np.abs(determinant) > 1e-8) & np.all(upper >= lower, axis=1)
    xy, edge_u, edge_v, determinant = xy[valid], edge_u[valid], edge_v[valid], determinant[valid]
    height = triangles[valid, :, axis]
    lower, upper = lower[valid], upper[valid]
    width = upper[:, 1] - lower[:, 1] + 1
    counts = (upper[:, 0] - lower[:, 0] + 1) * width
    offsets = np.concatenate(([0], np.cumsum(counts)))
    nearest = np.full(tuple(dimensions), np.inf)
    furthest = np.full(tuple(dimensions), -np.inf)
    first = 0
    while first < len(counts):
        stop = np.searchsorted(offsets, offsets[first] + 65_536, side="right") - 1
        stop = max(first + 1, min(stop, len(counts)))
        indices = np.repeat(np.arange(first, stop), counts[first:stop])
        local = np.arange(offsets[first], offsets[stop]) - offsets[indices]
        cells = lower[indices] + np.column_stack((local // width[indices], local % width[indices]))
        dx, dy = (cells + .5 - xy[indices, 0]).T
        u = (dx * edge_v[indices, 1] - dy * edge_v[indices, 0]) / determinant[indices]
        v = (edge_u[indices, 0] * dy - edge_u[indices, 1] * dx) / determinant[indices]
        hit = (u >= -1e-8) & (v >= -1e-8) & (u + v <= 1 + 1e-8)
        z0, z1, z2 = height[indices[hit]].T
        depth = z0 + u[hit] * (z1 - z0) + v[hit] * (z2 - z0)
        xy_indices = tuple(cells[hit].T)
        np.minimum.at(nearest, xy_indices, depth)
        np.maximum.at(furthest, xy_indices, depth)
        first = stop
    return nearest, furthest


def mesh_depths(vertices, faces, shape):
    triangles = vertices[faces]
    dimensions = np.array(shape)
    return {axis: axis_depths(triangles, dimensions, axis) for axis in (0, 1, 2)}


def exposed_levels(occupied, axis, side):
    columns = np.moveaxis(occupied, axis, -1)
    levels = columns.shape[-1] - 1 - columns[..., ::-1].argmax(-1) if side else columns.argmax(-1)
    return np.where(columns.any(axis=-1), levels, -1)


def level_neighbors(depth, direction):
    profile = np.moveaxis(depth, direction, 0)
    finite = np.isfinite(profile[1:]) & np.isfinite(profile[:-1])
    change = np.full(finite.shape, np.inf)
    np.subtract(profile[1:], profile[:-1], out=change, where=finite)
    return np.abs(change) <= .14


def protect_even_faces(occupied, depths):
    """Keep the blocks that form an even row on an existing roof, wall, or floor."""
    protected = np.zeros_like(occupied)
    for axis, sides in depths.items():
        for side, depth in enumerate(sides):
            levels = exposed_levels(occupied, axis, side)
            keep = np.zeros(levels.shape, dtype=bool)
            for direction in (0, 1):
                projected = np.moveaxis(levels, direction, 0)
                pair = (projected[1:] >= 0) & (projected[1:] == projected[:-1])
                pair &= level_neighbors(depth, direction)
                marked = np.moveaxis(keep, direction, 0)
                marked[1:] |= pair
                marked[:-1] |= pair
            coords = keep.nonzero()
            np.moveaxis(protected, axis, -1)[(*coords, levels[coords])] = True
    return protected


def surface_steps(occupied, depths):
    counts = []
    for axis, sides in depths.items():
        for side, depth in enumerate(sides):
            # Floor repairs may intentionally extend the bottom of a wall.
            if axis == 1 and not side:
                continue
            levels = exposed_levels(occupied, axis, side)
            if axis == 1:
                above_base = depth >= occupied.shape[1] * .27
            else:
                height_axis = 0 if axis == 0 else 1
                above_base = np.indices(depth.shape)[height_axis] >= occupied.shape[1] * .27
            total = 0
            for direction in (0, 1):
                projected = np.moveaxis(levels, direction, 0)
                interior = np.moveaxis(above_base, direction, 0)
                unequal = (projected[1:] != projected[:-1]) & ((projected[1:] >= 0) | (projected[:-1] >= 0))
                total += int(np.count_nonzero(unequal & interior[1:] & interior[:-1]
                                             & level_neighbors(depth, direction)))
            counts.append(total)
    return counts


def neighboring_cells(cell):
    x, y = cell
    return (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)


def coherent_patches(centers, fits):
    index = {tuple(cell): i for i, cell in enumerate(centers.tolist())}
    pending = set(index)
    while pending:
        first = pending.pop()
        members = [index[first]]
        queue = deque([first])
        while queue:
            cell = queue.popleft()
            dx, dy, height = fits[index[cell]]
            for point in neighboring_cells(cell):
                if point not in pending:
                    continue
                ux, uy, other_height = fits[index[point]]
                step = point[0] - cell[0], point[1] - cell[1]
                if max(abs(dx - ux), abs(dy - uy)) > .1:
                    continue
                predicted_step = ((dx + ux) * step[0] + (dy + uy) * step[1]) / 2
                if abs(height + predicted_step - other_height) > .35:
                    continue
                pending.remove(point)
                queue.append(point)
                members.append(index[point])
        yield np.asarray(members, dtype=int)


def patch_fit(points, depth, local_fits):
    reference = np.median(local_fits, axis=0)
    slope = reference[:2]
    if not slope.any():
        return np.array([0, 0, np.median(depth)])
    offset = np.median(depth - points @ slope)
    inliers = np.abs(depth - points @ slope - offset) <= .45
    if inliers.mean() < .85:
        return None
    design = np.column_stack((points[inliers], np.ones(np.count_nonzero(inliers))))
    fitted, _, rank, _ = np.linalg.lstsq(design, depth[inliers], rcond=None)
    if rank != 3 or np.max(np.abs(fitted[:2] - slope)) > .08:
        return None
    # Keep a vertical wall vertical, even if its profile is diagonal in plan.
    fitted[:2] = np.where(slope == 0, 0, fitted[:2])
    fitted[2] = np.median(depth[inliers] - points[inliers] @ fitted[:2])
    return fitted


def roof_gaps(depth, region, taken, fitted):
    """Find small enclosed, smooth deviations within a confidently fitted roof."""
    mask = np.zeros(depth.shape, dtype=bool)
    mask[tuple(region.T)] = True
    row = np.maximum.accumulate(mask, axis=1) & np.maximum.accumulate(mask[:, ::-1], axis=1)[:, ::-1]
    col = np.maximum.accumulate(mask, axis=0) & np.maximum.accumulate(mask[::-1], axis=0)[::-1]
    interior = row & col & ~mask
    if not 0 < int(interior.sum()) <= 81 or (interior & taken).any():
        return np.empty((0, 2), dtype=int)

    points = np.argwhere(interior)
    residual = depth - (np.indices(depth.shape).transpose(1, 2, 0) @ fitted[:2] + fitted[2])
    errors = residual[tuple(points.T)]
    if not np.isfinite(errors).all() or np.max(np.abs(errors)) > 1.65:
        return np.empty((0, 2), dtype=int)
    for x, y in points.tolist():
        adjacent = [residual[other] for other in neighboring_cells((x, y))]
        if any(abs(value - residual[x, y]) > .8 for value in adjacent):
            return np.empty((0, 2), dtype=int)
    return points


def fit_connected_planes(depth, centers, fits, *, fill_roof=False):
    taken = np.zeros(depth.shape, dtype=bool)
    taken[tuple(centers.T)] = True
    extensions, extension_fits = [], []
    for members in coherent_patches(centers, fits):
        if len(members) < 12:
            continue
        region = centers[members]
        measured = depth[tuple(region.T)]
        fitted = patch_fit(region, measured, fits[members])
        if fitted is None:
            continue
        predicted = region @ fitted[:2] + fitted[2]
        if (np.abs(predicted - measured) <= .52).mean() < .88:
            continue
        fits[members, :2] = fitted[:2]
        fits[members, 2] = predicted
        if fill_roof:
            extra = roof_gaps(depth, region, taken, fitted)
            if len(extra):
                taken[tuple(extra.T)] = True
                extensions.append(extra)
                extension_fits.append(np.column_stack((np.tile(fitted[:2], (len(extra), 1)),
                                                       extra @ fitted[:2] + fitted[2])))
    if extensions:
        return np.concatenate((centers, *extensions)), np.concatenate((fits, *extension_fits))
    return centers, fits


def plane_targets(depth, axis, side, shape):
    """Return supported voxel boundaries, leaving small features and edges alone."""
    radius = 3
    width = 2 * radius + 1
    if min(depth.shape) < width:
        return np.empty((0, 2), dtype=int), np.empty(0, dtype=int)
    centers = np.argwhere(sliding_window_view(np.isfinite(depth), (width, width)).all(axis=(2, 3)))
    if not len(centers):
        return centers, np.empty(0, dtype=int)
    local = np.arange(-radius, radius + 1)
    x, y = np.meshgrid(local, local, indexing="ij")
    design = np.column_stack((x.ravel(), y.ravel(), np.ones(width ** 2)))
    neighborhoods = sliding_window_view(depth, (width, width))
    samples = neighborhoods[tuple(centers.T)].reshape(-1, width ** 2)
    fit = samples @ np.linalg.pinv(design).T

    # Refit after discarding depth samples from a different surface in the neighborhood.
    residuals = np.abs(samples - fit @ design.T)
    weights = (residuals <= .55).astype(float)
    supported = weights.sum(axis=1) >= width ** 2 * .82
    centers, samples, weights = centers[supported] + radius, samples[supported], weights[supported]
    if not len(centers):
        return centers, np.empty(0, dtype=int)
    weighted = weights[:, :, None] * design
    normal = design.T @ weighted
    rhs = (weighted.transpose(0, 2, 1) @ samples[:, :, None])
    fit = np.linalg.solve(normal, rhs)[:, :, 0]

    center = width ** 2 // 2
    measured = samples[:, center]
    residuals = np.abs(samples - fit @ design.T)
    supported = (residuals <= .52).mean(axis=1) >= .88
    # Protect corners and openings. One isolated noisy depth may vary more than its neighbors.
    nearby = [center - width, center - 1, center + 1, center + width]
    supported &= (residuals[:, nearby] <= .78).all(axis=1)
    supported &= np.abs(measured - fit[:, 2]) <= 1.05
    slopes = fit[:, :2]
    if axis != 1:
        vertical = 0 if axis == 0 else 1
        supported &= np.abs(slopes[:, vertical]) <= .11
        slopes[:, vertical] = 0
    elif side == 0:
        supported &= np.max(np.abs(slopes), axis=1) <= .11
    else:
        supported &= np.max(np.abs(slopes), axis=1) <= 1.65
        # Looking down also sees terraces and entry steps. Their borders belong to the base.
        supported &= measured >= shape[axis] * .27

    flat = np.max(np.abs(slopes), axis=1) <= .1
    # Use the observed median on flat patches, even near an integer boundary.
    plane = fit[:, 2]
    plane[flat] = np.median(samples[flat], axis=1)
    slopes[flat] = 0
    centers, fit = fit_connected_planes(depth, centers[supported], fit[supported], fill_roof=axis == 1 and bool(side))
    # A triangle can touch any point in a cell, including its high or low corner.
    extreme = fit[:, 2] + (.5 if side else -.5) * np.abs(fit[:, :2]).sum(axis=1)
    target = np.clip(np.floor(extreme + 1e-8).astype(int), 0, shape[axis] - 1)
    return centers, target


def edge_runs(edges):
    """Trace straight exterior wall lines, allowing one cell of lateral variation."""
    start = 0
    while start < len(edges):
        if edges[start] < 0:
            start += 1
            continue
        stop = start + 1
        low = high = edges[start]
        while stop < len(edges) and edges[stop] >= 0:
            edge = edges[stop]
            if max(high, edge) - min(low, edge) > 1:
                break
            low, high = min(low, edge), max(high, edge)
            stop += 1
        if stop - start >= 6:
            yield np.arange(start, stop)
        start = stop


def bridge_footing_profile(profile):
    """Match a shallow rise bounded by two level spans."""
    bridged = profile.copy()
    if len(profile) < 7:
        return bridged
    for level in np.unique(profile):
        anchors = np.flatnonzero(sliding_window_view(profile == level, 3).all(axis=-1))
        for start, stop in zip(anchors[:-1] + 3, anchors[1:]):
            gap = profile[start:stop]
            if 0 < len(gap) <= len(profile) // 2 and (gap == level + 1).all():
                bridged[start:stop] = level
    # Carry an existing level to a nearby end of the same wall profile.
    for trace, output in ((profile, bridged), (profile[::-1], bridged[::-1])):
        end = trace[-1]
        different = np.flatnonzero(trace != end)
        if not len(different):
            continue
        start = different[-1] + 1
        if start >= 3 and len(trace) - start <= 5 and (trace[start - 3:start] == end - 1).all():
            output[start:] = end - 1
    return bridged


def fill_wall_footings(occupied, depth, *, contact=None, excluded=None):
    """Fill short gaps below a wall with a supported, locally level base."""
    height = occupied.shape[1]
    layers = np.arange(height)[None, :, None]
    bottom = exposed_levels(occupied, 1, 0)
    if contact is None:
        contact = bottom
    limit = max(3, round(height * .22))
    wall_run = (layers >= bottom[:, None, :]) & (layers < bottom[:, None, :] + 5)
    wall = ((occupied & wall_run).sum(axis=1) >= 3) & (bottom >= 0) & (bottom <= limit + 2)
    depth_level = np.floor(np.where(np.isfinite(depth), depth, -1)).astype(int)
    protected = np.zeros_like(wall)
    for level in range(limit + 3):
        slab = (bottom == level) & (depth_level == level)
        neighborhood = sliding_window_view(np.pad(slab, 2), (5, 5))
        protected |= slab & (neighborhood.sum(axis=(-1, -2)) >= 8)

    fill_level = np.full(bottom.shape, -1)
    for axis in (0, 1):
        profile = np.min(np.where(contact >= 0, contact, height), axis=axis)
        bridged = bridge_footing_profile(profile)
        walls = np.moveaxis(wall, axis, 0)
        levels = np.moveaxis(bottom, axis, 0)
        preserve = np.moveaxis(protected, axis, 0)
        destination = np.moveaxis(fill_level, axis, 0)
        for side in (0, 1):
            edge = walls.argmax(axis=0) if not side else walls.shape[0] - 1 - walls[::-1].argmax(axis=0)
            edge = np.where(walls.any(axis=0), edge, -1)
            for run in edge_runs(edge):
                trace = edge[run]
                base = levels[trace, run]
                stable = [value for value in np.unique(base) if value <= limit
                          and sliding_window_view(base == value, 6).all(axis=-1).any()]
                if not stable:
                    continue
                level = int(stable[0])
                spans = bridged[run] < profile[run]
                target = np.where(spans, np.minimum(level, bridged[run]), level)
                gap = (base > target) & (base <= target + 2 + spans) & (spans | ~preserve[trace, run])
                key = trace[gap], run[gap]
                destination[key] = np.maximum(destination[key], target[gap])
    fill = ((fill_level[:, None, :] >= 0) & (layers >= fill_level[:, None, :])
            & (layers < bottom[:, None, :]))
    if excluded is not None:
        fill &= ~(fill & excluded).any(axis=1)[:, None, :]
    return occupied | fill


def align_boundary(occupied, depth, axis, side, shape, *, excluded=None):
    projected = np.moveaxis(occupied, axis, -1)
    centers, targets = plane_targets(depth, axis, side, shape)
    if not len(centers):
        return
    rays = projected[tuple(centers.T)]
    extents = rays.argmax(axis=1) if not side else shape[axis] - 1 - rays[:, ::-1].argmax(axis=1)
    distance = np.abs(extents - targets)
    limit = 2 if axis == 1 and side else 1
    change = rays.any(axis=1) & (distance > 0) & (distance <= limit)
    centers, targets, extents = centers[change], targets[change], extents[change]
    shave = targets < extents if side else targets > extents
    layers = np.arange(shape[axis])
    between = (layers >= np.minimum(extents, targets)[:, None]) & (layers <= np.maximum(extents, targets)[:, None])
    updated = rays[change]
    updated[between] = np.broadcast_to(~shave[:, None], between.shape)[between]
    updated[np.arange(len(targets)), targets] = True
    if excluded is not None:
        blocked = np.moveaxis(excluded, axis, -1)[tuple(centers.T)]
        conflicts = (updated & blocked).any(axis=1)
        updated[conflicts] = rays[change][conflicts]
    projected[tuple(centers.T)] = updated


def regularize_surfaces(occupied, depths, *, contact=None, excluded=None):
    """Polish floor, roof, and walls independently so risky changes can be skipped."""
    result = occupied
    shape = np.array(occupied.shape)
    stages = {
        "floor": [],
        "roof": [(1, 1)],
        "walls": [(0, 0), (0, 1), (2, 0), (2, 1)],
    }
    diagnostics = {}
    steps = surface_steps(result, depths)
    for category, sides in stages.items():
        candidate = result.copy()
        for axis, side in sides:
            align_boundary(candidate, depths[axis][side], axis, side, shape, excluded=excluded)
        if category == "floor":
            candidate = fill_wall_footings(candidate, depths[1][0], contact=contact, excluded=excluded)
        if np.array_equal(candidate, result) or not keeps_connections(result, candidate):
            continue
        new_steps = surface_steps(candidate, depths)
        if any(new > old for old, new in zip(steps, new_steps)):
            continue
        diagnostics[category] = {
            "added": int(np.count_nonzero(candidate & ~result)),
            "removed": int(np.count_nonzero(result & ~candidate)),
        }
        result = candidate
        steps = new_steps
    return result, diagnostics
