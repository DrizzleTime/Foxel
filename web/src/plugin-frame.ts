import 'antd/dist/reset.css';
import './global.css';

import { initExternals } from './plugins/externals';
import type { FoxelHostApi, RegisteredPlugin } from './plugins/externals';
import type { PluginItem } from './api/plugins';
import { pluginsApi } from './api/plugins';
import request from './api/client';
import { vfsApi, type VfsEntry } from './api/vfs';

type FrameMode = 'file' | 'app';

function renderStatus(text: string, isError: boolean = false) {
  const root = document.getElementById('root');
  if (!root) return;

  root.innerHTML = '';
  const el = document.createElement('div');
  el.style.cssText = [
    'height:100%',
    'display:flex',
    'align-items:center',
    'justify-content:center',
    'padding:16px',
    'box-sizing:border-box',
    `color:${isError ? 'red' : 'rgba(0,0,0,0.65)'}`,
    'font-size:14px',
    'white-space:pre-wrap',
  ].join(';');
  el.textContent = text;
  root.appendChild(el);
}

function scheduleStatus(text: string, delayMs: number) {
  let canceled = false;
  const t = window.setTimeout(() => {
    if (canceled) return;
    renderStatus(text);
  }, delayMs);

  return () => {
    canceled = true;
    window.clearTimeout(t);
  };
}

function getQuery() {
  const params = new URLSearchParams(window.location.search);
  const pluginKey = (params.get('pluginKey') || '').trim();
  const mode = (params.get('mode') || 'file') as FrameMode;
  const filePath = (params.get('filePath') || '').trim();
  return { pluginKey, mode, filePath };
}

function postToParent(data: any) {
  if (window.parent && window.parent !== window) {
    window.parent.postMessage(data, window.location.origin);
  }
}

function createHostApi(pluginKey: string): FoxelHostApi {
  const showMessage: FoxelHostApi['showMessage'] = (type, content) => {
    const antd = window.__FOXEL_EXTERNALS__?.antd;
    const msg = antd?.message;
    if (!msg) return;
    switch (type) {
      case 'success':
        msg.success(content);
        break;
      case 'error':
        msg.error(content);
        break;
      case 'warning':
        msg.warning(content);
        break;
      case 'info':
      default:
        msg.info(content);
        break;
    }
  };

  return {
    close: () => postToParent({ type: 'foxel-plugin:close', pluginKey }),
    openPath: (path) => postToParent({ type: 'foxel-plugin:openPath', pluginKey, path }),
    openFile: (filePath, appKey) =>
      postToParent({ type: 'foxel-plugin:openFile', pluginKey, filePath, appKey }),
    showMessage,
    callApi: async <T = unknown>(path: string, options?: RequestInit & { json?: unknown }) =>
      request<T>(path, options),
    getTempLink: async (filePath: string) => {
      const token = await vfsApi.getTempLinkToken(filePath);
      return vfsApi.getTempPublicUrl(token.token);
    },
    getStreamUrl: (filePath: string) => vfsApi.streamUrl(filePath),
  };
}

function getPluginStylePaths(plugin: PluginItem): string[] {
  const styles = (plugin.manifest as any)?.frontend?.styles as unknown;
  if (!Array.isArray(styles)) return [];
  return styles.filter((s) => typeof s === 'string' && s.trim().length > 0);
}

function withVersion(url: string, version?: string | null): string {
  const v = typeof version === 'string' ? version.trim() : '';
  if (!v) return url;
  const u = new URL(url, window.location.origin);
  u.searchParams.set('v', v);
  return u.pathname + u.search;
}

async function loadPluginStyles(pluginKey: string, plugin: PluginItem, version?: string | null) {
  const stylePaths = getPluginStylePaths(plugin);
  if (stylePaths.length === 0) return;

  const tasks = stylePaths.map(
    (p) =>
      new Promise<void>((resolve) => {
        const href = withVersion(
          `/api/plugins/${pluginKey}/assets/${p.replace(/^\/+/, '')}`,
          version
        );
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        link.onload = () => resolve();
        link.onerror = () => resolve();
        document.head.appendChild(link);
      })
  );

  await Promise.all(tasks);
}

async function loadPluginBundle(pluginKey: string, version?: string | null): Promise<RegisteredPlugin> {
  const url = withVersion(`/api/plugins/${pluginKey}/bundle.js`, version);

  return new Promise<RegisteredPlugin>((resolve, reject) => {
    let done = false;
    const t = window.setTimeout(() => {
      if (done) return;
      done = true;
      reject(new Error('Plugin did not call FoxelRegister'));
    }, 15000);

    window.FoxelRegister = (p: RegisteredPlugin) => {
      if (done) return;
      done = true;
      window.clearTimeout(t);
      resolve(p);
    };

    const script = document.createElement('script');
    script.src = url;
    script.async = true;
    script.onerror = () => {
      if (done) return;
      done = true;
      window.clearTimeout(t);
      reject(new Error('Failed to load plugin script: ' + url));
    };
    document.head.appendChild(script);
  });
}

async function buildFileContext(filePath: string) {
  const stat = (await vfsApi.stat(filePath)) as any;
  const name =
    typeof stat?.name === 'string' && stat.name.trim().length > 0
      ? stat.name
      : filePath.replace(/\\/g, '/').split('/').filter(Boolean).pop() || 'unknown';

  const entry: VfsEntry = {
    name,
    is_dir: Boolean(stat?.is_dir),
    size: Number(stat?.size || 0),
    mtime: Number(stat?.mtime || 0),
    type: typeof stat?.type === 'string' ? stat.type : undefined,
    has_thumbnail: Boolean(stat?.has_thumbnail),
  };

  const token = await vfsApi.getTempLinkToken(filePath);
  const downloadUrl = vfsApi.getTempPublicUrl(token.token);
  const streamUrl = vfsApi.streamUrl(filePath);

  return { entry, urls: { downloadUrl, streamUrl } };
}

async function main() {
  initExternals();

  const { pluginKey, mode, filePath } = getQuery();
  if (!pluginKey) {
    renderStatus('Missing pluginKey in query string', true);
    return;
  }

  const root = document.getElementById('root');
  if (!root) {
    renderStatus('Missing #root container', true);
    return;
  }

  const cancelLoading = scheduleStatus('Loading plugin...', 200);

  let plugin: PluginItem;
  try {
    plugin = await pluginsApi.get(pluginKey);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    cancelLoading();
    renderStatus(`Failed to load plugin info: ${msg}`, true);
    return;
  }

  try {
    await loadPluginStyles(pluginKey, plugin, plugin.version);
  } catch {
    // ignore
  }

  let registered: RegisteredPlugin;
  try {
    registered = await loadPluginBundle(pluginKey, plugin.version);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    cancelLoading();
    renderStatus(`Failed to load plugin bundle: ${msg}`, true);
    return;
  }

  cancelLoading();
  const host = createHostApi(pluginKey);

  let cleanup: (() => void) | null = null;
  const mountError = async () => {
    try {
      root.innerHTML = '';

      if (mode === 'app') {
        if (typeof registered.mountApp !== 'function') {
          throw new Error('This plugin does not support standalone mode');
        }
        const ret = await registered.mountApp(root, { host });
        if (typeof ret === 'function') cleanup = ret;
        return;
      }

      if (!filePath) {
        throw new Error('Missing filePath in query string');
      }

      const { entry, urls } = await buildFileContext(filePath);
      const ret = await registered.mount(root, { filePath, entry, urls, host });
      if (typeof ret === 'function') cleanup = ret;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      renderStatus(`Plugin runtime error: ${msg}`, true);
    }
  };

  await mountError();

  window.addEventListener('beforeunload', () => {
    try {
      cleanup?.();
    } catch {
      void 0;
    }
  });
}

void main();
