"""Compile one saved document identically for CLI, viewer, and future exports."""
from .compile import compile_plan


def compile_document(document, extent=48):
    if document.schema_version in (2, 3):
        from .spatial import check_quantized_relations, resolve_spatial
        relations = document.spatial_plan() if document.schema_version == 3 else document
        baseline = document.baseline if document.schema_version == 3 else None
        plan, resolution = resolve_spatial(relations, baseline)
    else:
        plan, resolution = document, None
    result = compile_plan(plan, extent)
    if resolution is not None:
        result.warnings.extend(resolution['warnings'])
        check_quantized_relations(relations, result)
        if document.schema_version == 3:
            frozen = compile_plan(document.baseline, extent)
            if any(result.boxes[vid] != box for vid, box in frozen.boxes.items()):
                raise ValueError('frozen baseline changed after block rounding')
            if any(result.blocks.get(pos) != material for pos, material in frozen.blocks.items()):
                raise ValueError('addition overwrote a frozen baseline block')
            resolution['baseline_blocks_unchanged'] = True
    return plan, result, resolution
