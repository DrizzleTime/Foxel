import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { Modal, Checkbox } from 'antd';
import type { VfsEntry } from '../api/client';
import type { AppDescriptor } from '../apps/registry';
import { getAppsForEntry, getDefaultAppForEntry, getAppByKey } from '../apps/registry';
import { useI18n } from '../i18n';
import { useNavigate } from 'react-router';

type WindowBase = {
  id: string;
  app: AppDescriptor;
  maximized: boolean;
  minimized: boolean;
  x: number;
  y: number;
  width: number;
  height: number;
};

export type AppWindowItem =
  | (WindowBase & {
    kind: 'file';
    entry: VfsEntry;
    filePath: string;
  })
  | (WindowBase & {
    kind: 'app';
  });

type AppWindowPatch = Partial<Pick<AppWindowItem, 'maximized' | 'minimized' | 'x' | 'y' | 'width' | 'height'>>;

interface AppWindowsContextValue {
  windows: AppWindowItem[];
  openWithApp: (entry: VfsEntry, app: AppDescriptor, currentPath: string) => void;
  openFileWithDefaultApp: (entry: VfsEntry, currentPath: string) => void;
  confirmOpenWithApp: (entry: VfsEntry, appKey: string, currentPath: string) => void;
  openApp: (app: AppDescriptor) => void;
  closeWindow: (id: string) => void;
  toggleMax: (id: string) => void;
  bringToFront: (id: string) => void;
  updateWindow: (id: string, patch: AppWindowPatch) => void;
  minimizeWindow: (id: string) => void;
  restoreWindow: (id: string) => void;
  toggleMinimize: (id: string) => void;
}

const AppWindowsContext = createContext<AppWindowsContextValue | null>(null);

export const AppWindowsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [windows, setWindows] = useState<AppWindowItem[]>([]);

  const openWithApp = useCallback((entry: VfsEntry, app: AppDescriptor, currentPath: string) => {
    const fullPath = (currentPath === '/' ? '' : currentPath) + '/' + entry.name;
    setWindows(ws => {
      const idx = ws.length;
      const bounds = app.defaultBounds || {};
      const baseX = bounds.x ?? (160 + idx * 32);
      const baseY = bounds.y ?? (100 + idx * 28);
      const baseW = bounds.width ?? 640;
      const baseH = bounds.height ?? 480;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const finalW = Math.min(baseW, vw - 40);
      const finalH = Math.min(baseH, vh - 60);
      const finalX = Math.min(Math.max(0, baseX), vw - finalW - 8);
      const finalY = Math.min(Math.max(0, baseY), vh - finalH - 8);
      return [
        ...ws,
        {
          id: Date.now().toString(36) + Math.random().toString(36).slice(2),
          kind: 'file',
          app,
          entry,
          filePath: fullPath,
          maximized: !!app.defaultMaximized,
          minimized: false,
          x: finalX,
          y: finalY,
          width: finalW,
          height: finalH,
        },
      ];
    });
  }, []);

  const openApp = useCallback((app: AppDescriptor) => {
    if (!app.openAppComponent) {
      return;
    }
    setWindows(ws => {
      const idx = ws.length;
      const bounds = app.defaultBounds || {};
      const baseX = bounds.x ?? (160 + idx * 32);
      const baseY = bounds.y ?? (100 + idx * 28);
      const baseW = bounds.width ?? 640;
      const baseH = bounds.height ?? 480;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const finalW = Math.min(baseW, vw - 40);
      const finalH = Math.min(baseH, vh - 60);
      const finalX = Math.min(Math.max(0, baseX), vw - finalW - 8);
      const finalY = Math.min(Math.max(0, baseY), vh - finalH - 8);
      return [
        ...ws,
        {
          id: Date.now().toString(36) + Math.random().toString(36).slice(2),
          kind: 'app',
          app,
          maximized: !!app.defaultMaximized,
          minimized: false,
          x: finalX,
          y: finalY,
          width: finalW,
          height: finalH,
        },
      ];
    });
  }, []);

  const openFileWithDefaultApp = useCallback((entry: VfsEntry, currentPath: string) => {
    const apps = getAppsForEntry(entry);
    if (!apps.length) {
      const ext = entry.name.split('.').pop()?.toLowerCase() || '';
      const extQuery = ext ? `.${ext}` : entry.name;
      Modal.confirm({
        title: t('Cannot open file'),
        content: t('No app available for this file. Go to App Store to search {ext}?', { ext: extQuery }),
        okText: t('Go to App Store'),
        cancelText: t('Cancel'),
        onOk: () => {
          const params = new URLSearchParams();
          params.set('tab', 'discover');
          if (extQuery) {
            params.set('query', extQuery);
          }
          navigate(`/plugins?${params.toString()}`);
        },
      });
      return;
    }
    const defaultApp = getDefaultAppForEntry(entry) || apps[0];
    openWithApp(entry, defaultApp, currentPath);
  }, [navigate, openWithApp, t]);

  const confirmOpenWithApp = useCallback((entry: VfsEntry, appKey: string, currentPath: string) => {
    const app = getAppByKey(appKey);
    if (!app) {
      Modal.error({ title: t('Error'), content: t('App "{key}" not found.', { key: appKey }) });
      return;
    }
    const ext = entry.name.split('.').pop()?.toLowerCase() || '';
    let setDefault = false;
    Modal.confirm({
      title: t('Open with {app}', { app: app.name }),
      content: (
        <div>
          <div style={{ marginBottom: 8 }}>{t('File')}: {entry.name}</div>
          <Checkbox onChange={e => (setDefault = e.target.checked)}>
            {t('Set as default for .{ext}', { ext })}
          </Checkbox>
        </div>
      ),
      onOk: () => {
        if (setDefault && ext) {
          localStorage.setItem(`app.default.${ext}`, app.key);
        }
        openWithApp(entry, app, currentPath);
      },
    });
  }, [openWithApp, t]);

  const closeWindow = (id: string) => setWindows(ws => ws.filter(w => w.id !== id));
  const toggleMax = (id: string) => setWindows(ws => ws.map(w => (w.id === id ? { ...w, maximized: !w.maximized } : w)));
  const bringToFront = (id: string) => setWindows(ws => {
    const target = ws.find(w => w.id === id);
    if (!target) return ws;
    return [...ws.filter(w => w.id !== id), target];
  });
  const updateWindow = (id: string, patch: AppWindowPatch) =>
    setWindows(ws => ws.map(w => (w.id === id ? { ...w, ...patch } : w)));

  const minimizeWindow = (id: string) => setWindows(ws => ws.map(w => (w.id === id ? { ...w, minimized: true } : w)));
  const restoreWindow = (id: string) => setWindows(ws => {
    const target = ws.find(w => w.id === id);
    if (!target) return ws;
    const restored = { ...target, minimized: false };
    return [...ws.filter(w => w.id !== id), restored];
  });
  const toggleMinimize = (id: string) => setWindows(ws => ws.map(w => (w.id === id ? { ...w, minimized: !w.minimized } : w)));

  const value = useMemo<AppWindowsContextValue>(() => ({
    windows,
    openWithApp,
    openFileWithDefaultApp,
    confirmOpenWithApp,
    openApp,
    closeWindow,
    toggleMax,
    bringToFront,
    updateWindow,
    minimizeWindow,
    restoreWindow,
    toggleMinimize,
  }), [windows, openWithApp, openFileWithDefaultApp, confirmOpenWithApp, openApp]);

  return <AppWindowsContext.Provider value={value}>{children}</AppWindowsContext.Provider>;
};

export function useAppWindows() {
  const ctx = useContext(AppWindowsContext);
  if (!ctx) throw new Error('useAppWindows must be used within AppWindowsProvider');
  return ctx;
}
