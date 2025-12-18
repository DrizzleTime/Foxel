import type { VfsEntry } from '../api/client';
import type { AppDescriptor } from './types';
import React from 'react';
import { pluginsApi, type PluginItem } from '../api/plugins';
import { PluginAppHost, PluginAppOpenHost } from './PluginHost';
const apps: AppDescriptor[] = [];

// 使用 import.meta.glob 动态导入所有应用
const appModules = import.meta.glob('./*/index.ts');

async function loadApps() {
  for (const path in appModules) {
    const module = await appModules[path]();
    if (module && typeof module === 'object' && 'descriptor' in module) {
      const descriptor = (module as { descriptor: AppDescriptor }).descriptor;
      if (!apps.find(a => a.key === descriptor.key)) {
        apps.push(descriptor);
      }
    }
  }
  try {
    const items = await pluginsApi.list();
    items.filter(p => p.enabled !== false).forEach((p) => registerPluginAsApp(p));
  } catch { void 0; }
}

function registerPluginAsApp(p: PluginItem) {
  const key = 'plugin:' + p.id;
  if (apps.find(a => a.key === key)) return;
  const supported = (entry: VfsEntry) => {
    if (entry.is_dir) return false;
    const ext = entry.name.split('.').pop()?.toLowerCase() || '';
    if (!p.supported_exts || p.supported_exts.length === 0) return true;
    return p.supported_exts.includes(ext);
  };
  apps.push({
    key,
    name: p.name || `插件 ${p.id}`,
    supported,
    component: (props: any) => React.createElement(PluginAppHost, { plugin: p, ...props }),
    openAppComponent: p.open_app ? ((props: any) => React.createElement(PluginAppOpenHost, { plugin: p, ...props })) : undefined,
    iconUrl: p.icon || undefined,
    default: false,
    defaultBounds: p.default_bounds || undefined,
    defaultMaximized: p.default_maximized || undefined,
  });
}

const appsLoadedPromise = loadApps();

export async function ensureAppsLoaded() {
  await appsLoadedPromise;
}

export function listSystemApps(): AppDescriptor[] {
  return apps.filter(a => !a.key.startsWith('plugin:'));
}

export function getAppsForEntry(entry: VfsEntry): AppDescriptor[] {
  return apps.filter(a => a.supported(entry));
}

export function getAppByKey(key: string): AppDescriptor | undefined {
  return apps.find(a => a.key === key);
}

export function getDefaultAppForEntry(entry: VfsEntry): AppDescriptor | undefined {
  if (entry.is_dir) return;
  const ext = entry.name.split('.').pop()?.toLowerCase() || '';
  if (!ext) return apps.find(a => a.supported(entry) && a.default);
  const saved = localStorage.getItem(`app.default.${ext}`);
  if (saved) {
    return apps.find(a => a.key === saved && a.supported(entry)) || undefined;
  }
  return apps.find(a => a.supported(entry) && a.default);
}

export type { AppDescriptor };
export type { AppComponentProps } from './types';

export async function reloadPluginApps() {
  try {
    const items = await pluginsApi.list();
    const keepKeys = new Set(items.filter(p => p.enabled !== false).map(p => 'plugin:' + p.id));
    for (let i = apps.length - 1; i >= 0; i--) {
      const a = apps[i];
      if (a.key.startsWith('plugin:') && !keepKeys.has(a.key)) {
        apps.splice(i, 1);
      }
    }
    items.filter(p => p.enabled !== false).forEach(p => {
      const key = 'plugin:' + p.id;
      const existing = apps.find(a => a.key === key);
      if (!existing) {
        registerPluginAsApp(p);
      } else {
        existing.name = p.name || `插件 ${p.id}`;
        existing.defaultBounds = p.default_bounds || undefined;
        existing.defaultMaximized = p.default_maximized || undefined;
        existing.iconUrl = p.icon || existing.iconUrl;
        existing.openAppComponent = p.open_app
          ? ((props: any) => React.createElement(PluginAppOpenHost, { plugin: p, ...props }))
          : undefined;
      }
    });
  } catch { void 0; }
}
