"""Small regression checks for attachment behavior, not a similarity benchmark."""
import pytest
from pydantic import ValidationError

from photo2craft.compile import compile_plan
from photo2craft.model import Plan


def fixture():
    return dict(schema_version=1, title="Synthetic attachment check", suitability="supported",
                observations=["Synthetic; not photo-derived"], assumptions=[], volumes=[
                    dict(id="body", parent=None, offset=[0, 0, 0], size=[1, .6, .8], shell=True,
                         material="white_concrete", roof=dict(kind="gable", rise=.5,
                         ridge_axis="z", material="deepslate_tiles"), evidence="fixture", inferred=False),
                    dict(id="step", parent="body", offset=[.25, 0, -.1], size=[.5, .1, .1],
                         shell=False, material="stone_bricks", roof=dict(kind="flat", rise=0,
                         ridge_axis="z", material="stone_bricks"), evidence="fixture", inferred=False)],
                details=[dict(id="window", volume="body", face="front", u=.25, v=.3,
                              width=.5, height=.4, material="glass", frame=None,
                              evidence="fixture", inferred=False)])


def test_attachment_tracks_body_and_is_independent_of_volume_order():
    for depth in (.8, 1.5):
        data = fixture()
        data['volumes'][0]['size'][2] = depth
        a = compile_plan(Plan.model_validate(data), 32)
        data['volumes'].reverse()
        b = compile_plan(Plan.model_validate(data), 32)
        assert a.blocks == b.blocks and a.owners == b.owners
        front = a.boxes['body'][0][2]
        window = [p for p, owner in a.owners.items() if owner == 'window']
        assert window and all(p[2] == front for p in window)
        assert a.boxes['step'][1][2] == front
        assert all(0 <= c < 32 for p in a.blocks for c in p)


def test_missing_parent_is_rejected_before_generation():
    data = fixture()
    data['volumes'][1]['parent'] = 'missing'
    with pytest.raises(ValidationError, match='missing parent'):
        Plan.model_validate(data)


def test_gable_detail_does_not_create_floating_blocks():
    data = fixture()
    data['details'][0].update(u=0, v=1, width=1, height=.5)
    plan = Plan.model_validate(data)
    bare = compile_plan(plan.model_copy(update={'details': []}), 32)
    painted = compile_plan(plan, 32)
    assert bare.blocks.keys() == painted.blocks.keys()
    assert any(owner == 'window' for owner in painted.owners.values())
    assert any('face cells painted' in w for w in painted.warnings)
