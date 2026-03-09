import React, { useRef, useState, useEffect } from 'react';
import { Tooltip, theme, Button } from 'antd';
import { FolderFilled, PictureOutlined, MoreOutlined } from '@ant-design/icons';
import type { VfsEntry } from '../../../api/client';
import { getFileIcon } from './FileIcons';
import { EmptyState } from './EmptyState';
import { useTheme } from '../../../contexts/ThemeContext';
import { useI18n } from '../../../i18n';

interface Props {
  entries: VfsEntry[];
  thumbs: Record<string, string>;
  selectedEntries: string[];
  path: string;
  mobile?: boolean;
  onSelect: (e: VfsEntry, additive?: boolean) => void;
  onSelectRange: (names: string[]) => void;
  onOpen: (e: VfsEntry) => void;
  onContextMenu: (e: React.MouseEvent, entry: VfsEntry) => void;
  onOpenMenu?: (entry: VfsEntry, anchor: HTMLElement) => void;
}

const formatSize = (size: number) => {
  if (size < 1024) return size + ' B';
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB';
  if (size < 1024 * 1024 * 1024) return (size / 1024 / 1024).toFixed(1) + ' MB';
  return (size / 1024 / 1024 / 1024).toFixed(1) + ' GB';
};

export const GridView: React.FC<Props> = ({ entries, thumbs, selectedEntries, path, mobile = false, onSelect, onSelectRange, onOpen, onContextMenu, onOpenMenu }) => {
  const { token } = theme.useToken();
  const { resolvedMode } = useTheme();
  const { t } = useI18n();

  const lightenColor = (hex: string, amount: number) => {
    const parseHex = (h: string) => {
      const s = h.replace('#', '');
      const n = s.length === 3 ? s.split('').map((c) => c + c).join('') : s;
      const num = parseInt(n, 16);
      if (Number.isNaN(num) || n.length !== 6) return null;
      return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255 };
    };
    const rgb = parseHex(hex);
    if (!rgb) return hex;
    const mix = (c: number) => Math.round(c + (255 - c) * amount);
    const toHex = (v: number) => v.toString(16).padStart(2, '0');
    return `#${toHex(mix(rgb.r))}${toHex(mix(rgb.g))}${toHex(mix(rgb.b))}`;
  };

  const toRgba = (hex: string, alpha: number) => {
    const s = hex.replace('#', '');
    const normalized = s.length === 3 ? s.split('').map((c) => c + c).join('') : s;
    const num = parseInt(normalized, 16);
    if (Number.isNaN(num) || normalized.length !== 6) {
      return `rgba(22, 119, 255, ${alpha})`;
    }
    const r = (num >> 16) & 255;
    const g = (num >> 8) & 255;
    const b = num & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  };

  const containerRef = useRef<HTMLDivElement | null>(null);
  const itemRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const startRef = useRef<{ x: number; y: number } | null>(null);
  const [rect, setRect] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const [selecting, setSelecting] = useState(false);

  useEffect(() => {
    if (mobile) return;
    const grid = containerRef.current;
    const scrollContainer = grid?.parentElement;
    if (!scrollContainer) return;

    const onBlankMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return;
      if (e.target !== scrollContainer) return;
      startRef.current = { x: e.clientX, y: e.clientY };
      setSelecting(true);
      setRect({ left: e.clientX, top: e.clientY, width: 0, height: 0 });
      e.preventDefault();
    };

    scrollContainer.addEventListener('mousedown', onBlankMouseDown);
    return () => scrollContainer.removeEventListener('mousedown', onBlankMouseDown);
  }, [mobile]);

  useEffect(() => {
    if (mobile) return;
    const onMove = (ev: MouseEvent) => {
      if (!startRef.current) return;
      const cx = ev.clientX;
      const cy = ev.clientY;
      const s = startRef.current;
      const left = Math.min(s.x, cx);
      const top = Math.min(s.y, cy);
      const width = Math.abs(cx - s.x);
      const height = Math.abs(cy - s.y);
      setRect({ left, top, width, height });
    };
    const onUp = () => {
      if (!startRef.current) return;
      setSelecting(false);
      const currentRect = rect;
      if (currentRect) {
        const sel: string[] = [];
        entries.forEach((ent) => {
          const el = itemRefs.current[ent.name];
          if (!el) return;
          const br = el.getBoundingClientRect();
          const rr = { left: currentRect.left, top: currentRect.top, right: currentRect.left + currentRect.width, bottom: currentRect.top + currentRect.height };
          const br2 = { left: br.left, top: br.top, right: br.right, bottom: br.bottom };
          const intersect = !(br2.left > rr.right || br2.right < rr.left || br2.top > rr.bottom || br2.bottom < rr.top);
          if (intersect) sel.push(ent.name);
        });
        if (sel.length > 0) onSelectRange(sel);
      }
      startRef.current = null;
      setRect(null);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    if (selecting) {
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    }
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [entries, mobile, onSelectRange, rect, selecting]);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (mobile || e.button !== 0) return;
    const target = e.target as HTMLElement;
    if (target.closest('.fx-grid-item')) {
      return;
    }
    startRef.current = { x: e.clientX, y: e.clientY };
    setSelecting(true);
    setRect({ left: e.clientX, top: e.clientY, width: 0, height: 0 });
    e.preventDefault();
  };

  return (
    <div className="fx-grid" style={{ padding: mobile ? 12 : 16 }} ref={containerRef} onMouseDown={handleMouseDown}>
      {entries.map((ent) => {
        const isImg = thumbs[ent.name];
        const ext = ent.name.split('.').pop()?.toLowerCase();
        const isPictureType = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext || '');
        const isSelected = selectedEntries.includes(ent.name);

        return (
          <div
            key={ent.name}
            ref={(el) => {
              itemRefs.current[ent.name] = el;
            }}
            className={['fx-grid-item', isSelected ? 'selected' : '', ent.is_dir ? 'dir' : 'file'].join(' ')}
            onClick={(ev) => {
              if (mobile) {
                onOpen(ent);
                return;
              }
              onSelect(ent, ev.ctrlKey || ev.metaKey);
            }}
            onDoubleClick={() => {
              if (!mobile) onOpen(ent);
            }}
            onContextMenu={(e) => {
              if (!mobile) onContextMenu(e, ent);
            }}
            style={{ userSelect: 'none' }}
          >
            {mobile && onOpenMenu && (
              <Button
                size="small"
                type="text"
                icon={<MoreOutlined />}
                aria-label={t('More')}
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenMenu(ent, e.currentTarget);
                }}
                style={{ position: 'absolute', top: 4, right: 4, zIndex: 2 }}
              />
            )}
            <div className="thumb" style={{ background: 'var(--ant-color-bg-container, #fff)' }}>
              {ent.is_dir && (
                <FolderFilled
                  style={{
                    fontSize: 32,
                    color: resolvedMode === 'dark' ? lightenColor(String(token.colorPrimary || '#111111'), 0.72) : token.colorPrimary,
                  }}
                />
              )}
              {!ent.is_dir && (isImg ? <img src={isImg} alt={ent.name} style={{ maxWidth: '100%', maxHeight: '100%' }} /> : isPictureType ? <PictureOutlined style={{ fontSize: 32, color: resolvedMode === 'dark' ? lightenColor(String(token.colorPrimary || '#111111'), 0.72) : 'var(--ant-color-text-tertiary, #8c8c8c)' }} /> : getFileIcon(ent.name, 32, resolvedMode))}
              {ent.type === 'mount' && <span className="badge">M</span>}
            </div>
            <Tooltip title={ent.name}>
              <div className="name ellipsis" style={{ userSelect: 'none' }}>{ent.name}</div>
            </Tooltip>
            <div className="meta ellipsis" style={{ fontSize: 11, color: token.colorTextSecondary, userSelect: 'none' }}>
              {ent.is_dir ? t('Folder') : formatSize(ent.size)}
            </div>
          </div>
        );
      })}
      {!mobile && rect && (
        <div
          style={{
            position: 'fixed',
            left: rect.left,
            top: rect.top,
            width: rect.width,
            height: rect.height,
            border: '1px dashed var(--ant-color-border, rgba(0,0,0,0.4))',
            background: toRgba(String(token.colorPrimary || '#1677ff'), 0.16),
            zIndex: 999,
          }}
        />
      )}
      {entries.length === 0 && <EmptyState isRoot={path === '/'} />}
    </div>
  );
};
