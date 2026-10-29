import type { KeyboardEvent } from 'react';

interface FileItemActions {
  open: () => void;
  select: () => void;
  menu?: () => void;
}

export function handleFileItemKeyDown(event: KeyboardEvent<HTMLElement>, actions: FileItemActions) {
  if (event.target !== event.currentTarget) return;
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    if (event.key === 'Enter') actions.open();
    else actions.select();
  } else if (actions.menu && (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10'))) {
    event.preventDefault();
    actions.menu();
  } else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) {
    const parent = event.currentTarget.closest('[data-file-items]');
    if (!parent) return;
    const items = Array.from(parent.querySelectorAll<HTMLElement>('[data-file-item]'));
    const index = items.indexOf(event.currentTarget);
    const columns = getComputedStyle(parent).display === 'grid'
      ? getComputedStyle(parent).gridTemplateColumns.split(' ').length : 1;
    const offsets: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -columns, ArrowDown: columns };
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : index + offsets[event.key];
    event.preventDefault();
    items[Math.max(0, Math.min(items.length - 1, next))]?.focus();
  }
}
