import pytest


def test_roof_interpolation_keeps_the_edge_between_planes():
    np = pytest.importorskip("numpy")
    from photo2craft.surfaces import plane_targets

    x = np.indices((20, 15))[0]
    depth = 7.2 + .5 * x
    depth[6, 7] += .9
    depth[11:] += 3
    centers, levels = plane_targets(depth, 1, 1, np.array([20, 23, 15]))
    targets = dict(zip(map(tuple, centers.tolist()), levels.tolist()))

    assert targets[(6, 7)] == 10
    assert targets[(15, 7)] == 17
    assert (10, 7) not in targets and (11, 7) not in targets


def test_joined_roof_plane_smooths_a_broad_bump_and_preserves_a_step():
    np = pytest.importorskip("numpy")
    from photo2craft.surfaces import align_boundary

    shape = np.array([27, 32, 26])
    x, z = np.indices((27, 26))
    plane = 7.2 + .5 * x + .22 * z
    smooth_bump = 1.4 * np.exp(-((x - 13) ** 2 + (z - 12) ** 2) / 3.5)
    step = 1.5 * ((abs(x - 13) < 2) & (abs(z - 12) < 2))
    levels = np.arange(shape[1])[None, :, None]

    smooth_result = plane + smooth_bump
    occupied = levels <= np.floor(smooth_result[:, None, :] + .36)
    assert np.flatnonzero(occupied[13, :, 12])[-1] == 18
    align_boundary(occupied, smooth_result, 1, 1, shape)
    assert np.flatnonzero(occupied[13, :, 12])[-1] == 16

    stepped_result = plane + step
    occupied = levels <= np.floor(stepped_result[:, None, :] + .36)
    align_boundary(occupied, stepped_result, 1, 1, shape)
    assert np.flatnonzero(occupied[13, :, 12])[-1] == 18


def test_wall_footing_fills_a_short_gap_and_keeps_a_raised_slab():
    np = pytest.importorskip("numpy")
    from photo2craft.surfaces import fill_wall_footings

    occupied = np.zeros((18, 14, 22), dtype=bool)
    occupied[3:12, 1:10, 2:19] = True
    occupied[11, 1:3, 9:12] = False
    occupied[3:12, 1:3, 15:19] = False
    depth = np.where(occupied.any(axis=1), occupied.argmax(axis=1) + .2, np.inf)

    result = fill_wall_footings(occupied, depth)

    expected = occupied.copy()
    expected[11, 1:3, 9:12] = True
    np.testing.assert_array_equal(result, expected)


def test_surface_alignment_respects_a_block_already_removed_by_clay():
    np = pytest.importorskip("numpy")
    from photo2craft.surfaces import align_boundary

    shape = np.array([15, 15, 15])
    occupied = np.zeros(shape, dtype=bool)
    occupied[:, :8, :] = True
    depth = np.full((15, 15), 8.4)
    excluded = np.zeros_like(occupied)
    excluded[7, 8, 7] = True

    align_boundary(occupied, depth, 1, 1, shape, excluded=excluded)

    assert occupied[7, 8, 6]
    assert not occupied[7, 8, 7]
    assert occupied[7, 7, 7]


def test_equal_roof_steps_are_protected_from_clay_misses():
    np = pytest.importorskip("numpy")
    from photo2craft.surfaces import protect_even_faces

    occupied = np.zeros((3, 7, 3), dtype=bool)
    occupied[:2, 4, 1] = True
    occupied[2, 5, 1] = True
    low = np.full((3, 3), np.inf)
    high = np.full((3, 3), -np.inf)
    high[:, 1] = 4.2

    protected = protect_even_faces(occupied, {1: (low, high)})

    assert protected[:2, 4, 1].all()
    assert not protected[2, 5, 1]


def test_wall_plane_uses_the_vertical_axis_of_the_projection():
    np = pytest.importorskip("numpy")
    from photo2craft.surfaces import plane_targets

    y, z = np.indices((20, 20))
    shape = np.array([20, 20, 20])

    centers, _ = plane_targets(7.2 + .45 * z, 0, 1, shape)
    assert [8, 7] in centers.tolist()
    centers, _ = plane_targets(7.2 + .45 * y, 0, 1, shape)
    assert not len(centers)


def test_footing_bridges_one_layer_without_extending_a_two_layer_step():
    np = pytest.importorskip("numpy")
    from photo2craft.surfaces import bridge_footing_profile

    profile = np.array([0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 1])
    np.testing.assert_array_equal(bridge_footing_profile(profile), np.zeros_like(profile))
    profile = np.array([0, 0, 0, 2, 2, 2, 0, 0, 0, 2, 2])
    np.testing.assert_array_equal(bridge_footing_profile(profile), profile)


def test_clay_trim_removes_tips_and_detached_noise_without_cutting_a_link():
    np = pytest.importorskip("numpy")
    from photo2craft.topology import keeps_connections, trim_connected

    occupied = np.zeros((7, 5, 5), dtype=bool)
    occupied[1:6, 2, 2] = True
    occupied[1, 0, :2] = True
    outside = np.array([[3, 2, 2], [5, 2, 2], [1, 0, 0], [1, 0, 1]])

    result = trim_connected(occupied, outside)

    assert result[3, 2, 2]
    assert not result[5, 2, 2]
    assert not result[1, 0, :2].any()
    assert keeps_connections(occupied, result, allow_discard=True)
