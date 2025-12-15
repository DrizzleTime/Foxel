import React, { useRef, useEffect, useCallback } from 'react';
import { Space, Button } from 'antd';
import { FullscreenExitOutlined, FullscreenOutlined, CloseOutlined, MinusOutlined } from '@ant-design/icons';
import type { AppDescriptor, AppComponentProps, AppOpenComponentProps } from './types';
import type { VfsEntry } from '../api/client';

export interface AppWindowItem {
  id: string;
  app: AppDescriptor;
  kind: 'file' | 'app';
  entry?: VfsEntry;
  filePath?: string;
  maximized: boolean;
  minimized: boolean;
  x: number;
  y: number;
  width: number;
  height: number;
}

type AppWindowPatch = Partial<Pick<AppWindowItem, 'maximized' | 'minimized' | 'x' | 'y' | 'width' | 'height'>>;

interface AppWindowsLayerProps {
  windows: AppWindowItem[];
  onClose: (id: string) => void;
  onToggleMax: (id: string) => void;
  onBringToFront: (id: string) => void;
  onUpdateWindow: (id: string, patch: AppWindowPatch) => void;
}

export const AppWindowsLayer: React.FC<AppWindowsLayerProps> = ({ windows, onClose, onToggleMax, onBringToFront, onUpdateWindow }) => {
  const dragRef = useRef<{
    id: string;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
    newX: number;
    newY: number;
  } | null>(null);
  const resizeRef = useRef<{
    id: string;
    dir: string;
    startX: number;
    startY: number;
    origin: { x: number; y: number; w: number; h: number };
    newX: number;
    newY: number;
    newW: number;
    newH: number;
  } | null>(null);

  const windowEls = useRef<Record<string, HTMLDivElement | null>>({});

  const onMouseMove = useCallback((e: MouseEvent) => {
    if (dragRef.current) {
      const { id, startX, startY, originX, originY } = dragRef.current;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      let newX = Math.max(0, originX + dx);
      let newY = Math.max(0, originY + dy);
      dragRef.current.newX = newX;
      dragRef.current.newY = newY;
      const el = windowEls.current[id];
      if (el) {
        el.style.left = newX + 'px';
        el.style.top = newY + 'px';
      }
      return;
    }
    if (resizeRef.current) {
      const { id, dir, startX, startY, origin } = resizeRef.current;
      let { x, y, w, h } = { x: origin.x, y: origin.y, w: origin.w, h: origin.h };
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      const minW = 360;
      const minH = 240;
      if (dir.includes('e')) w = Math.max(minW, origin.w + dx);
      if (dir.includes('s')) h = Math.max(minH, origin.h + dy);
      if (dir.includes('w')) { w = Math.max(minW, origin.w - dx); x = origin.x + (origin.w - w); }
      if (dir.includes('n')) { h = Math.max(minH, origin.h - dy); y = origin.y + (origin.h - h); }
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      x = Math.min(Math.max(0, x), vw - 100);
      y = Math.min(Math.max(0, y), vh - 60);
      resizeRef.current.newX = x;
      resizeRef.current.newY = y;
      resizeRef.current.newW = w;
      resizeRef.current.newH = h;
      const el = windowEls.current[id];
      if (el) {
        el.style.left = x + 'px';
        el.style.top = y + 'px';
        el.style.width = w + 'px';
        el.style.height = h + 'px';
      }
    }
  }, []);

  const onMouseUp = useCallback(() => {
    if (dragRef.current) {
      const { id, newX, newY, originX, originY } = dragRef.current;
      if (newX !== undefined && newY !== undefined && (newX !== originX || newY !== originY)) {
        onUpdateWindow(id, { x: newX, y: newY });
      }
      dragRef.current = null;
    }
    if (resizeRef.current) {
      const { id, newX, newY, newW, newH } = resizeRef.current;
      if (newW && newH) {
        onUpdateWindow(id, { x: newX, y: newY, width: newW, height: newH });
      }
      resizeRef.current = null;
    }
  }, [onUpdateWindow]);

  useEffect(() => {
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [onMouseMove, onMouseUp]);

  const startDrag = (e: React.MouseEvent, w: AppWindowItem) => {
    if (e.detail === 2) return; 
    if (w.maximized) return;
    if ((e.target as HTMLElement).closest('button')) return;
    onBringToFront(w.id);
    dragRef.current = {
      id: w.id,
      startX: e.clientX,
      startY: e.clientY,
      originX: w.x,
      originY: w.y,
      newX: w.x,
      newY: w.y
    };
  };

  const startResize = (e: React.MouseEvent, w: AppWindowItem, dir: string) => {
    e.stopPropagation();
    if (w.maximized) return;
    onBringToFront(w.id);
    resizeRef.current = {
      id: w.id,
      dir,
      startX: e.clientX,
      startY: e.clientY,
      origin: { x: w.x, y: w.y, w: w.width, h: w.height },
      newX: w.x,
      newY: w.y,
      newW: w.width,
      newH: w.height
    };
  };

  const isInteracting = (id: string) =>
    dragRef.current?.id === id || resizeRef.current?.id === id;

  const resizeHandles = (w: AppWindowItem) => {
    const dirs = ['n','s','e','w','ne','nw','se','sw'];
    const cursorMap: Record<string,string> = {
      n:'ns-resize', s:'ns-resize', e:'ew-resize', w:'ew-resize',
      ne:'nesw-resize', sw:'nesw-resize', nw:'nwse-resize', se:'nwse-resize'
    };
    const posStyle: Record<string, React.CSSProperties> = {
      n:{ top:0, left:'50%', transform:'translate(-50%, -50%)', width:'calc(100% - 28px)', height:10 },
      s:{ bottom:0, left:'50%', transform:'translate(-50%, 50%)', width:'calc(100% - 28px)', height:10 },
      e:{ right:0, top:'50%', transform:'translate(50%,-50%)', width:10, height:'calc(100% - 28px)' },
      w:{ left:0, top:'50%', transform:'translate(-50%, -50%)', width:10, height:'calc(100% - 28px)' },
      ne:{ top:0, right:0, transform:'translate(50%,-50%)', width:14, height:14 },
      nw:{ top:0, left:0, transform:'translate(-50%,-50%)', width:14, height:14 },
      se:{ bottom:0, right:0, transform:'translate(50%,50%)', width:14, height:14 },
      sw:{ bottom:0, left:0, transform:'translate(-50%,50%)', width:14, height:14 }
    };
    return dirs.map(d => (
      <div
        key={d}
        onMouseDown={e => startResize(e, w, d)}
        style={{
          position:'absolute',
          ...posStyle[d],
          cursor: cursorMap[d],
          zIndex: 10,
          borderRadius: 4,
          background: 'transparent'
        }}
      />
    ));
  };

  const visibleWindows = windows.filter(w => !w.minimized);

  return (
    <>
      {visibleWindows.map((w, idx) => {
        const isFileWindow = w.kind !== 'app';
        const FileComp = w.app.component as React.FC<AppComponentProps>;
        const OpenComp = w.app.openAppComponent as React.FC<AppOpenComponentProps> | undefined;
        const ContentComp = (isFileWindow ? FileComp : OpenComp) as React.FC<any> | undefined;
        const useSystemWindow = w.app.useSystemWindow !== false; // 默认为 true
        const titleText = isFileWindow ? `${w.app.name} - ${w.entry?.name || ''}` : w.app.name;

        if (!ContentComp) {
          return null;
        }

        if (!useSystemWindow) {
          return (
            <div
              key={w.id}
              ref={el => { windowEls.current[w.id] = el; }}
              style={{
                position: 'fixed',
                top: w.maximized ? 0 : w.y,
                left: w.maximized ? 0 : w.x,
                width: w.maximized ? '100vw' : w.width,
                height: w.maximized ? '100vh' : w.height,
                background: 'transparent',
                border: 'none',
                borderRadius: 0,
                boxShadow: 'none',
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
                zIndex: 3000 + idx
              }}
            >
              <div
                style={{
                  flex: 1,
                  position: 'relative',
                  overflow: 'hidden',
                  background: 'transparent'
                }}
	              >
	                {isFileWindow ? (
	                  <ContentComp
	                    filePath={w.filePath || ''}
	                    entry={w.entry as VfsEntry}
	                    onRequestClose={() => onClose(w.id)}
	                  />
	                ) : (
	                  <ContentComp onRequestClose={() => onClose(w.id)} />
	                )}
	              </div>
	            </div>
	          );
	        }
        // 否则继续使用系统窗口渲染（不改动原有逻辑）
        const interacting = isInteracting(w.id);
        return (
          <div
            key={w.id}
            ref={el => { windowEls.current[w.id] = el; }}
            onMouseDown={() => onBringToFront(w.id)}
            style={{
              position: 'fixed',
              top: w.maximized ? 0 : w.y,     
              left: w.maximized ? 0 : w.x,    
              width: w.maximized ? '100vw' : w.width,
              height: w.maximized ? '100vh' : w.height,
              background: 'var(--ant-color-bg-elevated, var(--ant-color-bg-container))',
              border: '1px solid var(--ant-color-border-secondary, rgba(255,255,255,0.18))',
              borderRadius: w.maximized ? 0 : 12,
              boxShadow: w.maximized
                ? 'none'
                : interacting
                  ? '0 20px 50px -12px rgba(0,0,0,0.35)'
                  : '0 12px 32px -8px rgba(0,0,0,0.25)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              backdropFilter: 'blur(12px) saturate(150%)',
              zIndex: 3000 + idx,
              willChange: 'left,top,width,height',
              transition: interacting ? 'none' : 'top .15s,left .15s,width .15s,height .15s,box-shadow .25s'
            }}
          >
            <div
              onMouseDown={(e) => startDrag(e, w)}
              onDoubleClick={() => onToggleMax(w.id)}
              style={{
                height: 40,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0 12px',
                background: 'var(--ant-color-fill-secondary, rgba(0,0,0,0.25))',
                borderBottom: '1px solid var(--ant-color-border-secondary, rgba(255,255,255,0.1))',
                color: 'var(--ant-color-text, #333)',
                fontSize: 13,
                fontWeight: 600,
                letterSpacing: .2,
                userSelect: 'none',
                cursor: w.maximized ? 'default' : 'grab'
              }}
            >
              <span
                style={{
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  paddingRight: 8,
                  flex: 1
                }}
	              >
	                {titleText}
	              </span>
              <Space size={4}>
                <Button
                  type="text"
                  size="small"
                  aria-label="最小化"
                  icon={<MinusOutlined />}
                  onClick={() => onUpdateWindow(w.id, { minimized: true })}
                  style={{
                    color: 'var(--ant-color-text-secondary, #555)',
                    width: 30,
                    height: 30,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}
                />
                <Button
                  type="text"
                  size="small"
                  aria-label={w.maximized ? '还原' : '最大化'}
                  icon={w.maximized ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                  onClick={() => onToggleMax(w.id)}
                  style={{
                    color: 'var(--ant-color-text-secondary, #555)',
                    width: 30,
                    height: 30,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}
                />
                <Button
                  type="text"
                  size="small"
                  danger
                  aria-label="关闭"
                  icon={<CloseOutlined />}
                  onClick={() => onClose(w.id)}
                  style={{
                    color: 'var(--ant-color-error, #ff4d4f)',
                    width: 30,
                    height: 30,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}
                />
              </Space>
            </div>
            <div
              style={{
                flex: 1,
                background: 'transparent', // Let the app's own background show through
                position: 'relative',
                overflow: 'hidden'
              }}
            >
              {!w.maximized && resizeHandles(w)}
              {isFileWindow ? (
                <ContentComp
                  filePath={w.filePath || ''}
                  entry={w.entry as VfsEntry}
                  onRequestClose={() => onClose(w.id)}
                />
              ) : (
                <ContentComp onRequestClose={() => onClose(w.id)} />
              )}
            </div>
          </div>
        );
      })}
    </>
  );
};
