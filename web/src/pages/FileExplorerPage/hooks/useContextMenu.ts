import { useState, useCallback } from 'react';
import type { VfsEntry } from '../../../api/client';

export function useContextMenu() {
  const [ctxMenu, setCtxMenu] = useState<{ entry: VfsEntry; x: number; y: number } | null>(null);
  const [blankCtxMenu, setBlankCtxMenu] = useState<{ x: number; y: number } | null>(null);

  const openContextMenu = useCallback((e: React.MouseEvent, entry: VfsEntry) => {
    e.preventDefault();
    setCtxMenu({ entry, x: e.clientX, y: e.clientY });
  }, []);

  const openBlankContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setBlankCtxMenu({ x: e.clientX, y: e.clientY });
  }, []);

  const closeContextMenus = useCallback(() => {
    setCtxMenu(null);
    setBlankCtxMenu(null);
  }, []);

  return {
    ctxMenu,
    blankCtxMenu,
    openContextMenu,
    openBlankContextMenu,
    closeContextMenus,
  };
}