import 'antd/dist/reset.css';
import './global.css';

import { initExternals } from './plugins/externals';
import type { FoxelHostApi, RegisteredPlugin } from './plugins/externals';
import type { PluginItem } from './api/plugins';
import { pluginsApi } from './api/plugins';
import request from './api/client';
import { vfsApi, type VfsEntry } from './api/vfs';

type FrameMode = 'file' | 'app';

type FrameQuery = {
  pluginKey: string;
  mode: FrameMode;
  filePath: string;
  pluginVersion: string;
  pluginStyles: string[] | null;
  entry: VfsEntry | null;
};

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

function tryParseJson<T = unknown>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function getQuery(): FrameQuery {
  const params = new URLSearchParams(window.location.search);
  const pluginKey = (params.get('pluginKey') || '').trim();
  const mode = (params.get('mode') || 'file') as FrameMode;
  const filePath = (params.get('filePath') || '').trim();
  const pluginVersion = (params.get('pluginVersion') || '').trim();

  const rawStyles = (params.get('pluginStyles') || '').trim();
  const parsedStyles = rawStyles ? tryParseJson<unknown>(rawStyles) : null;
  const pluginStyles = Array.isArray(parsedStyles)
    ? parsedStyles.filter((s) => typeof s === 'string' && s.trim().length > 0)
    : null;

  const rawEntry = (params.get('entry') || '').trim();
  const parsedEntry = rawEntry ? tryParseJson<any>(rawEntry) : null;
  const entry: VfsEntry | null =
    parsedEntry && typeof parsedEntry === 'object' && typeof parsedEntry.name === 'string'
      ? {
        name: String(parsedEntry.name),
        is_dir: Boolean(parsedEntry.is_dir),
        size: Number(parsedEntry.size || 0),
        mtime: Number(parsedEntry.mtime || 0),
        type: typeof parsedEntry.type === 'string' ? parsedEntry.type : undefined,
        has_thumbnail: Boolean(parsedEntry.has_thumbnail),
      }
      : null;

  return { pluginKey, mode, filePath, pluginVersion, pluginStyles, entry };
}

function postToParent(data: any) {
  if (window.parent && window.parent !== window) {
    window.parent.postMessage(data, window.location.origin);
  }
}

type TempLinkCache = {
  url: string;
  fetchedAt: number;
  expiresIn: number;
};

const TEMP_LINK_CACHE_PREFIX = 'foxel:tempLink:';
const TEMP_LINK_DEFAULT_EXPIRES_IN = 3600;

function getTempLinkCacheKey(filePath: string) {
  return `${TEMP_LINK_CACHE_PREFIX}${filePath}`;
}

function readTempLinkCache(filePath: string): TempLinkCache | null {
  try {
    const raw = sessionStorage.getItem(getTempLinkCacheKey(filePath));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as TempLinkCache;
    if (!parsed || typeof parsed.url !== 'string') return null;
    if (!parsed.fetchedAt || !parsed.expiresIn) return null;
    if (Date.now() - parsed.fetchedAt >= parsed.expiresIn * 1000 - 10_000) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeTempLinkCache(filePath: string, item: TempLinkCache) {
  try {
    sessionStorage.setItem(getTempLinkCacheKey(filePath), JSON.stringify(item));
  } catch {
    void 0;
  }
}

async function getTempLinkUrl(filePath: string, expiresIn: number = TEMP_LINK_DEFAULT_EXPIRES_IN) {
  const cached = readTempLinkCache(filePath);
  if (cached) return cached.url;

  const tokenData = await vfsApi.getTempLinkToken(filePath, expiresIn);
  const url = typeof tokenData?.url === 'string' && tokenData.url.trim() ? tokenData.url : vfsApi.getTempPublicUrl(tokenData.token);
  writeTempLinkCache(filePath, { url, fetchedAt: Date.now(), expiresIn });
  return url;
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
      return await getTempLinkUrl(filePath);
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

function injectPluginStyles(pluginKey: string, stylePaths: string[], version?: string | null) {
  if (stylePaths.length === 0) return;

  stylePaths.forEach((p) => {
    const href = withVersion(`/api/plugins/${pluginKey}/assets/${p.replace(/^\/+/, '')}`, version);
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);
  });
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

function isLikelyImage(pathOrName: string) {
  return /\.(jpg|jpeg|png|gif|bmp|webp|svg)$/i.test(pathOrName);
}

function preloadImage(url: string) {
  const img = new Image();
  img.decoding = 'async';
  img.src = url;
}

async function buildFileContext(filePath: string, entryOverride: VfsEntry | null) {
  const entryPromise = entryOverride
    ? Promise.resolve(entryOverride)
    : (async () => {
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
      return entry;
    })();

  const downloadUrlPromise = getTempLinkUrl(filePath);
  if (isLikelyImage(filePath)) {
    downloadUrlPromise.then(preloadImage).catch(() => void 0);
  }

  const [entry, downloadUrl] = await Promise.all([entryPromise, downloadUrlPromise]);
  const streamUrl = vfsApi.streamUrl(filePath);

  return { entry, urls: { downloadUrl, streamUrl } };
}

async function main() {
  initExternals();

  const { pluginKey, mode, filePath, pluginVersion, pluginStyles, entry } = getQuery();
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

  const host = createHostApi(pluginKey);

  const pluginPromise = (async () => {
    if (pluginVersion && pluginStyles) {
      injectPluginStyles(pluginKey, pluginStyles, pluginVersion);
      return await loadPluginBundle(pluginKey, pluginVersion);
    }

    const plugin: PluginItem = await pluginsApi.get(pluginKey);
    const resolvedVersion = plugin.version || '';
    injectPluginStyles(pluginKey, getPluginStylePaths(plugin), resolvedVersion);
    return await loadPluginBundle(pluginKey, resolvedVersion);
  })();

  const ctxPromise = mode === 'file' ? buildFileContext(filePath, entry) : Promise.resolve(null);

  let registered: RegisteredPlugin;
  let ctx: Awaited<ReturnType<typeof buildFileContext>> | null;
  try {
    [registered, ctx] = await Promise.all([pluginPromise, ctxPromise]);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    cancelLoading();
    renderStatus(`Failed to load plugin: ${msg}`, true);
    return;
  }

  cancelLoading();

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

      if (!ctx) {
        throw new Error('Missing file context');
      }

      const ret = await registered.mount(root, { filePath, entry: ctx.entry, urls: ctx.urls, host });
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
