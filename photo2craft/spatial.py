"""Small semantic attachment plan, resolved to the existing voxel compiler input."""
from typing import Annotated, Literal

from pydantic import Field, ValidationInfo, model_validator

from .model import Identifier, Material, Model, Plan, Ratio, Roof, SurfaceDetail, Unit, Volume


class Body(Model):
    id: Identifier
    size: tuple[Ratio, Ratio, Ratio]
    material: Material
    roof: Roof
    evidence: Annotated[str, Field(min_length=1, max_length=400)]
    inferred: bool


class Attachment(Model):
    host: Identifier
    face: Literal['front', 'back', 'left', 'right', 'top']
    anchor: tuple[Unit, Unit]


class Vertical(Model):
    mode: Literal['face', 'on_top', 'align_top', 'between']
    lower: Identifier | None
    upper: Identifier | None

    @model_validator(mode='after')
    def references(self):
        expected = {'face': (False, False), 'on_top': (True, False),
                    'align_top': (False, True), 'between': (True, True)}[self.mode]
        if (self.lower is not None, self.upper is not None) != expected:
            raise ValueError(f'{self.mode}: invalid lower/upper references')
        return self


class AttachedPart(Model):
    id: Identifier
    width: Ratio
    height: Ratio | None
    depth: Ratio
    attachment: Attachment
    vertical: Vertical
    shell: bool
    material: Material
    roof: Roof
    evidence: Annotated[str, Field(min_length=1, max_length=400)]
    inferred: bool

    @model_validator(mode='after')
    def derived_height(self):
        if (self.height is None) != (self.vertical.mode == 'between'):
            raise ValueError('height must be null exactly when vertical.mode=between')
        return self


class OpenSpace(Model):
    id: Identifier
    lower: Identifier
    upper: Identifier
    allowed_parts: Annotated[list[Identifier], Field(max_length=24)]


class SpatialPlan(Model):
    schema_version: Literal[2]
    title: Annotated[str, Field(min_length=1, max_length=160)]
    view: Literal['front', 'front_left', 'front_right']
    suitability: Literal['supported', 'approximate', 'unsupported']
    observations: Annotated[list[str], Field(min_length=1, max_length=12)]
    assumptions: Annotated[list[str], Field(max_length=12)]
    body: Body
    parts: Annotated[list[AttachedPart], Field(max_length=23)]
    details: Annotated[list[SurfaceDetail], Field(max_length=60)]
    open_spaces: Annotated[list[OpenSpace], Field(max_length=8)]

    @model_validator(mode='after')
    def graph(self, info: ValidationInfo):
        if self.body.size[0] != 1:
            raise ValueError('body width must be 1; its other dimensions are H/W and D/W')
        parts = {p.id: p for p in self.parts}
        fixed_ids = set((info.context or {}).get('fixed_ids', []))
        geometry_ids = {self.body.id, *parts, *fixed_ids}
        all_ids = [self.body.id] + list(fixed_ids) + [p.id for p in self.parts] + [d.id for d in self.details] + [s.id for s in self.open_spaces]
        if len(set(all_ids)) != len(all_ids):
            raise ValueError('all geometry/detail/open-space IDs must be unique')
        state = {}

        def visit(vid):
            if vid not in geometry_ids:
                raise ValueError(f'missing geometry reference: {vid}')
            if vid == self.body.id or vid in fixed_ids or state.get(vid) == 'done':
                return
            if state.get(vid) == 'visiting':
                raise ValueError(f'cyclic spatial relation: {vid}')
            state[vid] = 'visiting'
            p = parts[vid]
            for ref in (p.attachment.host, p.vertical.lower, p.vertical.upper):
                if ref is not None:
                    visit(ref)
            state[vid] = 'done'

        for vid in geometry_ids:
            visit(vid)
        if any(d.volume not in geometry_ids for d in self.details):
            raise ValueError('detail references missing geometry')
        for s in self.open_spaces:
            if s.lower == s.upper or any(ref not in geometry_ids for ref in [s.lower, s.upper, *s.allowed_parts]):
                raise ValueError(f'{s.id}: invalid open-space reference')
        return self


class AttachmentProposal(Model):
    parts: Annotated[list[AttachedPart], Field(max_length=8)]
    open_spaces: Annotated[list[OpenSpace], Field(max_length=4)]
    notes: Annotated[list[str], Field(max_length=8)]


class OverlayPlan(Model):
    """Baseline is inserted by local code, never generated/replaced by the AI."""
    schema_version: Literal[3]
    baseline: Plan
    additions: AttachmentProposal

    def spatial_plan(self):
        root = next(v for v in self.baseline.volumes if v.parent is None)
        body = {name: getattr(root, name) for name in Body.model_fields}
        return SpatialPlan.model_validate(dict(
            schema_version=2, title=self.baseline.title, view=self.baseline.view,
            suitability=self.baseline.suitability, observations=self.baseline.observations,
            assumptions=self.baseline.assumptions, body=body, parts=self.additions.parts,
            details=self.baseline.details, open_spaces=self.additions.open_spaces),
            context={'fixed_ids': [v.id for v in self.baseline.volumes if v.id != root.id]})


def _overlap(a, b, axes):
    return all(min(a[0][i]+a[1][i], b[0][i]+b[1][i]) - max(a[0][i], b[0][i]) > 1e-8 for i in axes)


def resolve_spatial(plan: SpatialPlan, baseline: Plan | None = None):
    """Face touching, shared top heights, and support lengths are code-owned."""
    parts = {p.id: p for p in plan.parts}
    body_size = plan.body.size
    resolved = {plan.body.id: ((0., 0., 0.), body_size)}
    report = {'format': 'photo2craft-spatial-resolution-v1', 'boxes': {}, 'relations': [], 'open_spaces': [], 'adjustments': [], 'warnings': []}
    if baseline is not None:
        fixed = {v.id: v for v in baseline.volumes}

        def resolve_fixed(vid):
            if vid in resolved:
                return resolved[vid]
            v = fixed[vid]
            po, ps = resolve_fixed(v.parent)
            box = (tuple(po[i]+ps[i]*v.offset[i] for i in range(3)),
                   tuple(ps[i]*v.size[i] for i in range(3)))
            resolved[vid] = box
            return box

        for vid in fixed:
            resolve_fixed(vid)
        lower_bound = tuple(min(o[i] for o, s in resolved.values()) for i in range(3))
        upper_bound = tuple(max(o[i]+s[i]+(s[1]*fixed[vid].roof.rise
                              if i == 1 and fixed[vid].roof.kind != 'none' else 0)
                              for vid, (o, s) in resolved.items()) for i in range(3))
        report['frozen_geometry_ids'] = list(fixed)
        report['frozen_bounds'] = [lower_bound, upper_bound]

    def resolve(vid):
        if vid in resolved:
            return resolved[vid]
        p = parts[vid]
        ho, hs = resolve(p.attachment.host)
        u, v = p.attachment.anchor
        w, d = p.width*body_size[0], p.depth*body_size[2]
        h = p.height*body_size[1] if p.height is not None else 0.
        face = p.attachment.face
        if face in ('front', 'back'):
            x, y = ho[0]+u*hs[0]-w/2, ho[1]+v*hs[1]-h/2
            z = ho[2]-d if face == 'front' else ho[2]+hs[2]
        elif face in ('left', 'right'):
            z, y = ho[2]+u*hs[2]-d/2, ho[1]+v*hs[1]-h/2
            x = ho[0]-w if face == 'left' else ho[0]+hs[0]
        else:
            x, y, z = ho[0]+u*hs[0]-w/2, ho[1]+hs[1], ho[2]+v*hs[2]-d/2
        rule = p.vertical
        if rule.lower:
            lo, ls = resolve(rule.lower)
            y = lo[1]+ls[1]
        if rule.upper:
            up, us = resolve(rule.upper)
            if rule.mode == 'align_top':
                y = up[1]+us[1]-h
            else:
                h = up[1]-y
                if h <= 1e-8:
                    raise ValueError(f'{vid}: no positive height between supports')
        result = ((x, y, z), (w, h, d))
        # Constrain only independent plain boxes. Never stretch a support or
        # silently move a shared height; dependent parts resolve from this box.
        if baseline is not None and rule.mode == 'face' and (p.roof.kind == 'none' or p.roof.rise == 0):
            start = tuple(max(result[0][i], lower_bound[i]) for i in range(3))
            stop = tuple(min(result[0][i]+result[1][i], upper_bound[i]) for i in range(3))
            if any(b-a <= 1e-8 for a, b in zip(start, stop)):
                raise ValueError(f'{vid}: no volume inside frozen baseline bounds')
            clipped = (start, tuple(b-a for a, b in zip(start, stop)))
            if any(abs(result[k][i]-clipped[k][i]) > 1e-8 for k in (0, 1) for i in range(3)):
                report['adjustments'].append({'part': vid, 'rule': 'clip_plain_box_to_frozen_bounds',
                                              'before': result, 'after': clipped})
                report['warnings'].append(f'{vid}: plain box clipped to frozen baseline bounds')
                result = clipped
                (x, y, z), (w, h, d) = result
        if face == 'top' and abs(y-(ho[1]+hs[1])) > 1e-8:
            raise ValueError(f'{vid}: vertical relation detaches the part from its host top')
        # Vertical wall attachments must actually intersect the host face in height
        # and along its width. A corner or a plane on its own is not an attachment.
        axes = (0, 1) if face in ('front', 'back') else (1, 2) if face in ('left', 'right') else (0, 2)
        if not _overlap(result, (ho, hs), axes):
            raise ValueError(f'{vid}: misses the host face')
        for ref in (rule.lower, rule.upper if rule.mode == 'between' else None):
            if ref and not _overlap(result, resolved[ref], (0, 2)):
                raise ValueError(f'{vid}: support {ref} has no footprint overlap')
        resolved[vid] = result
        report['relations'].append({'part': vid, 'host': p.attachment.host, 'face': face,
                                    'vertical': rule.model_dump(), 'resolved_height': h})
        return result

    for vid in parts:
        resolve(vid)
        if baseline is not None:
            o, s = resolved[vid]
            roof = parts[vid].roof
            top = tuple(o[i]+s[i]+(s[1]*roof.rise if i == 1 and roof.kind != 'none' else 0) for i in range(3))
            if any(o[i] < lower_bound[i]-1e-8 or top[i] > upper_bound[i]+1e-8 for i in range(3)):
                raise ValueError(f'{vid}: addition exceeds frozen baseline bounds')
    volumes = [Volume(id=plan.body.id, parent=None, offset=(0, 0, 0), size=body_size,
                       shell=True, material=plan.body.material, roof=plan.body.roof,
                       evidence=plan.body.evidence, inferred=plan.body.inferred)]
    if baseline is not None:
        volumes = list(baseline.volumes)
    for vid, p in parts.items():
        origin, size = resolved[vid]
        volumes.append(Volume(id=vid, parent=plan.body.id,
                              offset=tuple(origin[i]/body_size[i] for i in range(3)),
                              size=tuple(size[i]/body_size[i] for i in range(3)),
                              shell=p.shell, material=p.material, roof=p.roof,
                              evidence=p.evidence, inferred=p.inferred))
    for s in plan.open_spaces:
        lo, ls = resolved[s.lower]
        up, us = resolved[s.upper]
        start = (max(lo[0], up[0]), lo[1]+ls[1], max(lo[2], up[2]))
        stop = (min(lo[0]+ls[0], up[0]+us[0]), up[1], min(lo[2]+ls[2], up[2]+us[2]))
        if any(b-a <= 1e-8 for a, b in zip(start, stop)):
            raise ValueError(f'{s.id}: no open volume between lower and upper')
        region = start, tuple(b-a for a, b in zip(start, stop))
        blocked = []
        for vid, box in resolved.items():
            if vid not in {s.lower, s.upper, *s.allowed_parts} and _overlap(region, box, (0, 1, 2)):
                report['warnings'].append(f'{s.id}: {vid} occupies the declared open space')
                blocked.append(vid)
        report['open_spaces'].append({'id': s.id, 'origin': start, 'size': region[1],
                                      'allowed_parts': s.allowed_parts, 'blocked_by': blocked})
    report['boxes'] = {vid: {'origin': o, 'size': s} for vid, (o, s) in resolved.items()}
    legacy = Plan(schema_version=1, title=plan.title, view=plan.view, suitability=plan.suitability,
                  observations=plan.observations, assumptions=plan.assumptions, volumes=volumes, details=plan.details)
    return legacy, report


def check_quantized_relations(plan: SpatialPlan, build):
    """Report relation loss caused by one-block rounding/collapsed slender parts."""
    def contact(a, b):
        return all(min(a[1][i], b[1][i]) > max(a[0][i], b[0][i]) for i in (0, 2))

    def has_voxel_contact(a, b):
        # a is immediately below b. Check actual occupancy, not just box overlap.
        return any((x, a[1][1]-1, z) in build.blocks and (x, b[0][1], z) in build.blocks
                   for x in range(max(a[0][0], b[0][0]), min(a[1][0], b[1][0]))
                   for z in range(max(a[0][2], b[0][2]), min(a[1][2], b[1][2])))

    for p in plan.parts:
        box, rule = build.boxes[p.id], p.vertical
        if rule.lower:
            lower = build.boxes[rule.lower]
            if box[0][1] != lower[1][1] or not contact(box, lower) or not has_voxel_contact(lower, box):
                build.warnings.append(f'{p.id}: lower contact lost after block rounding')
        if rule.upper:
            upper = build.boxes[rule.upper]
            if rule.mode == 'between' and (box[1][1] != upper[0][1] or not contact(box, upper) or not has_voxel_contact(box, upper)):
                build.warnings.append(f'{p.id}: upper contact lost after block rounding')
            elif rule.mode == 'align_top' and box[1][1] != upper[1][1]:
                build.warnings.append(f'{p.id}: top alignment lost after block rounding')
