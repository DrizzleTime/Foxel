/**
 * 胶片带组件
 */
import React, { CSSProperties } from 'react';
import { Typography } from 'antd';
import type { VfsEntry } from '../foxel-types';

interface FilmstripProps {
  shellStyle?: CSSProperties;
  listStyle?: CSSProperties;
  entries: VfsEntry[];
  activeEntry: VfsEntry;
  onSelect: (entry: VfsEntry) => void;
  filmstripRefs: React.MutableRefObject<Record<string, HTMLDivElement | null>>;
  pageInfo: { page: number; pageSize: number; total: number } | null;
  getThumbUrl: (item: VfsEntry) => string;
}

export const Filmstrip: React.FC<FilmstripProps> = ({
  shellStyle,
  listStyle,
  entries,
  activeEntry,
  onSelect,
  filmstripRefs,
  pageInfo,
  getThumbUrl,
}) => {
  return (
    <div style={shellStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <Typography.Text style={{ color: 'rgba(255,255,255,0.72)', fontWeight: 500 }}>
          {`胶片带 · ${entries.length} 张`}
        </Typography.Text>
        {pageInfo && (
          <Typography.Text style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12 }}>
            {`第 ${pageInfo.page} 页 / 共 ${Math.max(1, Math.ceil(pageInfo.total / pageInfo.pageSize))} 页`}
          </Typography.Text>
        )}
      </div>
      <div style={listStyle}>
        {entries.map(item => {
          const active = item.name === activeEntry.name;
          return (
            <div
              key={`${item.name}-${item.mtime || ''}`}
              ref={el => {
                filmstripRefs.current[item.name] = el;
              }}
              onClick={() => onSelect(item)}
              style={{
                width: 84,
                height: 64,
                overflow: 'hidden',
                border: active ? '2px solid #4e9bff' : '2px solid transparent',
                boxShadow: active
                  ? '0 0 0 4px rgba(78,155,255,0.28)'
                  : '0 10px 28px rgba(0,0,0,0.45)',
                cursor: 'pointer',
                position: 'relative',
                flex: '0 0 auto',
              }}
            >
              <img
                src={getThumbUrl(item)}
                alt={item.name}
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                  filter: active ? 'saturate(1)' : 'saturate(0.65)',
                }}
              />
              {active && (
                <div
                  style={{
                    position: 'absolute',
                    bottom: 4,
                    left: 6,
                    right: 6,
                    padding: '2px 4px',
                    background: 'rgba(0,0,0,0.55)',
                    color: '#fff',
                    fontSize: 10,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {item.name}
                </div>
              )}
            </div>
          );
        })}
        {entries.length === 0 && (
          <div style={{ color: 'rgba(255,255,255,0.45)' }}>暂无图片</div>
        )}
      </div>
    </div>
  );
};

