import { pluginsApi, type PluginManifestUpdate, type PluginItem } from '../api/plugins';

export interface RegisteredPlugin {
  mount: (container: HTMLElement, ctx: {
    filePath: string;
    entry: any;
    urls: { downloadUrl: string };
    host: HostApi;
  }) => void | Promise<void>;
  unmount?: (container: HTMLElement) => void | Promise<void>;

  mountApp?: (container: HTMLElement, ctx: { host: HostApi }) => void | Promise<void>;
  unmountApp?: (container: HTMLElement) => void | Promise<void>;

  key?: string;
  name?: string;
  version?: string;
  supportedExts?: string[];
  defaultBounds?: { x?: number; y?: number; width?: number; height?: number };
  defaultMaximized?: boolean;
  icon?: string;
  description?: string;
  author?: string;
  website?: string;
  github?: string;
}

export interface HostApi {
  close: () => void;
}

const loadedPlugins = new Map<string, RegisteredPlugin>();
const waiters = new Map<string, ((p: RegisteredPlugin) => void)[]>();
const injected = new Set<string>();

declare global {
  interface Window { FoxelRegister?: (plugin: RegisteredPlugin) => void; }
}

window.FoxelRegister = (plugin: RegisteredPlugin) => {
  const pendingUrl = sessionStorage.getItem('foxel:pendingPluginUrl') || '';
  if (pendingUrl) {
    loadedPlugins.set(pendingUrl, plugin);
    const resolvers = waiters.get(pendingUrl) || [];
    resolvers.forEach(fn => fn(plugin));
    waiters.delete(pendingUrl);
    sessionStorage.removeItem('foxel:pendingPluginUrl');
  } else {
    const anyUrl = Array.from(waiters.keys())[0];
    if (anyUrl) {
      loadedPlugins.set(anyUrl, plugin);
      const resolvers = waiters.get(anyUrl) || [];
      resolvers.forEach(fn => fn(plugin));
      waiters.delete(anyUrl);
    }
  }
};

export async function loadPluginFromUrl(url: string): Promise<RegisteredPlugin> {
  const existing = loadedPlugins.get(url);
  if (existing) return existing;
  return new Promise<RegisteredPlugin>((resolve, reject) => {
    const arr = waiters.get(url) || [];
    arr.push(resolve);
    waiters.set(url, arr);

    const ready = loadedPlugins.get(url);
    if (ready) {
      const resolvers = waiters.get(url) || [];
      resolvers.forEach(fn => fn(ready));
      waiters.delete(url);
      return;
    }

    sessionStorage.setItem('foxel:pendingPluginUrl', url);

    if (!injected.has(url)) {
      injected.add(url);
      const script = document.createElement('script');
      script.src = url;
      script.async = true;
      script.onerror = () => {
        waiters.delete(url);
        reject(new Error('Failed to load plugin script: ' + url));
      };
      document.head.appendChild(script);
    }

    const t = setTimeout(() => {
      if (!loadedPlugins.get(url)) {
        waiters.delete(url);
        reject(new Error('Plugin did not call FoxelRegister: ' + url));
      }
    }, 15000);

    const last = arr[arr.length - 1];
    arr[arr.length - 1] = (p: RegisteredPlugin) => { clearTimeout(t); last(p); };
  });
}

export function getPluginBundleUrl(pluginId: number) {
  return `/api/plugins/${pluginId}/bundle.js`;
}

export async function loadPlugin(plugin: Pick<PluginItem, 'id' | 'url'>): Promise<RegisteredPlugin> {
  const bundleUrl = getPluginBundleUrl(plugin.id);
  try {
    return await loadPluginFromUrl(bundleUrl);
  } catch (e) {
    if (plugin.url && plugin.url !== bundleUrl) {
      try {
        return await loadPluginFromUrl(plugin.url);
      } catch {
        throw e;
      }
    }
    throw e;
  }
}

export async function ensureManifest(pluginId: number, plugin: RegisteredPlugin) {
  const manifest: PluginManifestUpdate = {
    key: plugin.key,
    name: plugin.name,
    version: plugin.version,
    open_app: typeof plugin.mountApp === 'function',
    supported_exts: plugin.supportedExts,
    default_bounds: plugin.defaultBounds,
    default_maximized: plugin.defaultMaximized,
    icon: plugin.icon,
    description: plugin.description,
    author: plugin.author,
    website: plugin.website,
    github: plugin.github,
  };
  try { console.debug('[foxel] report manifest', pluginId, manifest); } catch { void 0; }
  const key = `foxel:manifestReported:${pluginId}`;
  if (sessionStorage.getItem(key) === '1') return;
  try {
    await pluginsApi.updateManifest(pluginId, manifest);
    sessionStorage.setItem(key, '1');
  } catch {
    void 0;
  }
}
