"""Only the new solver's contact, dependency, and clear-space behavior."""
import copy

import pytest
from pydantic import ValidationError

from photo2craft.compile import compile_plan
from photo2craft.spatial import OverlayPlan, SpatialPlan, check_quantized_relations, resolve_spatial


def assembly():
    def part(vid, width, height, depth, host, face, anchor, mode='face', lower=None, upper=None):
        return dict(id=vid, width=width, height=height, depth=depth,
                    attachment=dict(host=host, face=face, anchor=anchor),
                    vertical=dict(mode=mode, lower=lower, upper=upper), shell=False,
                    material='stone_bricks', roof=dict(kind='none', rise=0, ridge_axis='z', material='stone_bricks'),
                    evidence='Synthetic relation example, not photo analysis', inferred=False)
    return dict(schema_version=2, title='Synthetic supported open canopy', view='front_right',
                suitability='supported', observations=['Synthetic example'], assumptions=[],
                body=dict(id='body', size=[1, .6, .8], material='white_concrete',
                          roof=dict(kind='gable', rise=.5, ridge_axis='z', material='deepslate_tiles'),
                          evidence='Synthetic body', inferred=False),
                parts=[part('floor', 1, .05, .25, 'body', 'front', [.5, .025]),
                       part('canopy', 1, .05, .25, 'body', 'front', [.5, .5], 'align_top', upper='body'),
                       part('post_left', .04, None, .04, 'floor', 'top', [.1, .1], 'between', 'floor', 'canopy'),
                       part('post_right', .04, None, .04, 'floor', 'top', [.9, .1], 'between', 'floor', 'canopy')],
                details=[], open_spaces=[dict(id='clear_area', lower='floor', upper='canopy',
                                              allowed_parts=['post_left', 'post_right'])])


def test_derived_contacts_survive_size_change_rounding_and_input_reordering():
    for height, extent in [(.6, 48), (.9, 32)]:
        data = assembly()
        data['body']['size'][1] = height
        plan = SpatialPlan.model_validate(data)
        legacy, report = resolve_spatial(plan)
        result = compile_plan(legacy, extent)
        check_quantized_relations(plan, result)
        assert not report['warnings'] and not result.warnings
        floor, canopy = result.boxes['floor'], result.boxes['canopy']
        for pid in ['post_left', 'post_right']:
            box = result.boxes[pid]
            assert box[0][1] == floor[1][1]
            assert box[1][1] == canopy[0][1]
        center = tuple((floor[0][i]+floor[1][i])//2 if i != 1 else (floor[1][1]+canopy[0][1])//2 for i in range(3))
        assert center not in result.blocks
        data['parts'].reverse()
        other, _ = resolve_spatial(SpatialPlan.model_validate(data))
        assert compile_plan(other, extent).blocks == result.blocks


def test_invalid_support_graph_and_missed_support_are_rejected():
    data = assembly()
    data['parts'][1]['vertical']['upper'] = 'post_left'
    with pytest.raises(ValidationError, match='cyclic'):
        SpatialPlan.model_validate(data)
    data = assembly()
    data['parts'][1]['depth'] = .02
    with pytest.raises(ValueError, match='footprint overlap'):
        resolve_spatial(SpatialPlan.model_validate(data))
    data = assembly()
    data['parts'][2]['vertical']['lower'] = 'body'
    with pytest.raises(ValueError, match='no positive height'):
        resolve_spatial(SpatialPlan.model_validate(data))


def test_open_space_reports_an_unapproved_box_without_carving_it():
    data = assembly()
    obstruction = copy.deepcopy(data['parts'][0])
    obstruction.update(id='obstruction', width=.8, height=.3, depth=.2,
                       attachment=dict(host='floor', face='top', anchor=[.5, .5]))
    data['parts'].append(obstruction)
    legacy, report = resolve_spatial(SpatialPlan.model_validate(data))
    assert any('obstruction occupies' in w for w in report['warnings'])
    assert any(v.id == 'obstruction' for v in legacy.volumes)


def test_additions_preserve_baseline_and_reject_envelope_growth():
    data = assembly()
    bare = copy.deepcopy(data)
    bare['parts'] = bare['parts'][:2]
    bare['open_spaces'] = []
    baseline, _ = resolve_spatial(SpatialPlan.model_validate(bare))
    before = baseline.model_dump()
    overlay = OverlayPlan.model_validate(dict(schema_version=3, baseline=before,
        additions=dict(parts=data['parts'][2:], open_spaces=data['open_spaces'], notes=[])))
    plan = overlay.spatial_plan()
    enriched, report = resolve_spatial(plan, baseline)
    frozen = compile_plan(baseline)
    result = compile_plan(enriched)
    assert baseline.model_dump() == before
    assert all(result.boxes[vid] == box for vid, box in frozen.boxes.items())
    assert all(result.blocks[p] == material for p, material in frozen.blocks.items())
    assert set(report['frozen_geometry_ids']) == {v.id for v in baseline.volumes}
    clipped = overlay.model_copy(deep=True)
    slab = copy.deepcopy(data['parts'][0])
    slab.update(id='extra_slab', depth=.6,
                attachment=dict(host='body', face='front', anchor=[.5, .3]))
    from photo2craft.spatial import AttachedPart
    clipped.additions.parts.append(AttachedPart.model_validate(slab))
    _, correction = resolve_spatial(clipped.spatial_plan(), baseline)
    assert correction['adjustments'][0]['part'] == 'extra_slab'
    assert correction['boxes']['extra_slab']['origin'][2] == report['frozen_bounds'][0][2]
    overlay.additions.parts[0].depth = .6
    with pytest.raises(ValueError, match='frozen baseline bounds'):
        resolve_spatial(overlay.spatial_plan(), baseline)
