export function selectionBounds(first, second) {
  return [
    first.slice(0, 3).map((value, axis) => Math.min(value, second[axis])),
    first.slice(0, 3).map((value, axis) => Math.max(value, second[axis])),
  ];
}

export function indicesInBounds(blocks, bounds, removed) {
  const [minimum, maximum] = bounds;
  return blocks.reduce((selected, block, index) => {
    if (!removed.has(index) && minimum.every((low, axis) => low <= block[axis] && block[axis] <= maximum[axis])) {
      selected.add(index);
    }
    return selected;
  }, new Set());
}

export function createBlockEditor(onChange) {
  const $ = (id) => document.getElementById(id);
  const panel = $('block-editor');
  const toggle = $('edit-toggle');
  const mode = $('edit-mode');
  const apply = $('edit-apply');
  const undo = $('edit-undo');
  const download = $('edit-download');
  const revisions = new Map();
  const empty = new Set();
  let data, active = false, anchor, bounds, selected = empty;

  function revision() { return revisions.get(data?.id); }
  function removedRows() { return revision()?.removed ?? empty; }
  function clear() { anchor = bounds = undefined; selected = empty; }

  function update() {
    panel.hidden = !data?.editable;
    toggle.setAttribute('aria-pressed', String(active));
    toggle.textContent = active ? '선택 종료' : '블록 편집';
    $('edit-options').hidden = !active;
    apply.disabled = !active || selected.size === 0 || selected.size === data.block_count - removedRows().size;
    undo.hidden = !revision()?.steps.length;
    download.hidden = undo.hidden;
    const removed = removedRows().size;
    let message = removed ? '제거한 블록 ' + removed.toLocaleString('ko-KR') + '개' : '블록을 클릭해 제거할 수 있습니다.';
    if (active && mode.value === 'single') message = '제거할 블록 하나를 클릭하세요.';
    if (active && mode.value === 'area') message = anchor ? '두 번째 모서리 블록을 클릭하세요.' : '첫 번째 모서리 블록을 클릭하세요.';
    if (selected.size) message = apply.disabled ? '최소 한 블록을 남겨 주세요.'
      : '주황색 블록 ' + selected.size.toLocaleString('ko-KR') + '개 선택';
    $('edit-status').textContent = message;
  }

  function repaint() {
    update();
    onChange();
  }

  toggle.addEventListener('click', () => {
    active = !active;
    clear();
    repaint();
  });
  mode.addEventListener('change', () => {
    clear();
    repaint();
  });
  apply.addEventListener('click', () => {
    if (apply.disabled) return;
    const edit = revision() ?? { removed: new Set(), steps: [] };
    edit.steps.push(selected);
    for (const index of selected) edit.removed.add(index);
    revisions.set(data.id, edit);
    clear();
    repaint();
  });
  undo.addEventListener('click', () => {
    const edit = revision();
    const step = edit?.steps.pop();
    if (!step) return;
    for (const index of step) edit.removed.delete(index);
    clear();
    repaint();
  });
  download.addEventListener('click', () => {
    const removal = removedRows();
    if (!removal.size) return;
    const blocks = data.scene.blocks.filter((_, index) => !removal.has(index));
    const result = { ...data.scene, blocks };
    const url = URL.createObjectURL(new Blob([JSON.stringify(result), '\n'], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'blocks-' + data.id + '-edited.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  return {
    open(example) {
      data = example;
      active = false;
      clear();
      update();
    },
    pick(index) {
      if (!active || index === undefined) return;
      const block = data.scene.blocks[index];
      if (mode.value === 'area' && !anchor) {
        clear();
        anchor = block;
      } else {
        bounds = selectionBounds(anchor ?? block, block);
        anchor = undefined;
        selected = indicesInBounds(data.scene.blocks, bounds, removedRows());
      }
      repaint();
    },
    cancelSelection() {
      if (!active) return;
      clear();
      repaint();
    },
    get active() { return active; },
    get bounds() { return bounds ?? (anchor && selectionBounds(anchor, anchor)); },
    get selected() { return selected; },
    get removed() { return removedRows(); },
  };
}
