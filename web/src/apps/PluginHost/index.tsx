import React, { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import type { AppComponentProps, AppOpenComponentProps } from '../types';
import type { PluginItem } from '../../api/plugins';
import { useI18n } from '../../i18n';
import { useNavigate } from 'react-router';
import { useAppWindows } from '../../contexts/AppWindowsContext';
import { vfsApi, type VfsEntry } from '../../api/client';
import { getAppByKey, getAppsForEntry, getDefaultAppForEntry } from '../registry';
import { isHostRequest, PLUGIN_PROTOCOL_VERSION, requireVfsPath, type HostResult } from '../../plugins/protocol';

export interface PluginAppHostProps extends AppComponentProps {
  plugin: PluginItem;
}

function buildPluginFrameUrl(params: Record<string, string>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (typeof v !== 'string') return;
    const value = v.trim();
    if (!value) return;
    qs.set(k, value);
  });
  return `/plugin-frame.html?${qs.toString()}`;
}

function unloadPluginFrame(iframe: HTMLIFrameElement | null) {
  const frameWindow = iframe?.contentWindow;
  if (!iframe || !frameWindow) return;
  // Keep the document alive until a pending asynchronous mount has disposed.
  iframe.style.display = 'none';
  if (!('moveBefore' in document.body) || !iframe.isConnected) {
    // Older browsers release the document via pagehide during normal DOM removal.
    frameWindow.postMessage({ type: 'foxel-plugin:unload' }, window.location.origin);
    return;
  }
  document.body.moveBefore(iframe, null);
  const finish = () => {
    window.clearTimeout(timer);
    window.removeEventListener('message', onMessage);
    iframe.src = 'about:blank';
    iframe.remove();
  };
  const onMessage = (event: MessageEvent) => {
    if (event.origin === window.location.origin && event.source === frameWindow
      && event.data?.type === 'foxel-plugin:unloaded') finish();
  };
  const timer = window.setTimeout(finish, 5000);
  window.addEventListener('message', onMessage);
  frameWindow.postMessage({ type: 'foxel-plugin:unload' }, window.location.origin);
}

function usePluginMessages(iframeRef: React.RefObject<HTMLIFrameElement | null>, pluginKey: string,
  onRequestClose: () => void) {
  const navigate = useNavigate();
  const { openWithApp } = useAppWindows();
  const actions = useRef({ navigate, openWithApp, onRequestClose });
  actions.current = { navigate, openWithApp, onRequestClose };
  useEffect(() => {
    let disposed = false;
    const onMessage = async (event: MessageEvent) => {
      const iframe = iframeRef.current;
      if (event.origin !== window.location.origin || event.source !== iframe?.contentWindow) return;
      const data: unknown = event.data;
      if (!isHostRequest(data) || data.pluginKey !== pluginKey) return;
      const reply: HostResult = { type: 'foxel-plugin:result', protocol: PLUGIN_PROTOCOL_VERSION,
        pluginKey, id: data.id };
      try {
        if (data.method === 'openPath') {
          const path = requireVfsPath(data.params.path);
          const stat = await vfsApi.stat(path) as VfsEntry;
          if (!stat.is_dir) throw new Error('Path is not a directory');
          if (disposed || iframe !== iframeRef.current) throw new Error('Plugin window closed');
          actions.current.navigate('/files' + (path === '/' ? '' : path.split('/').map(encodeURIComponent).join('/')));
        } else if (data.method === 'openFile') {
          const path = requireVfsPath(data.params.filePath);
          if (data.params.appKey !== undefined && typeof data.params.appKey !== 'string') {
            throw new Error('Invalid appKey');
          }
          const stat = await vfsApi.stat(path) as VfsEntry;
          const entry = { ...stat, name: path.split('/').pop() || stat.name };
          if (entry.is_dir) throw new Error('Path is not a file');
          const app = typeof data.params.appKey === 'string'
            ? getAppByKey(data.params.appKey) || getAppByKey(`plugin:${data.params.appKey}`)
            : getDefaultAppForEntry(entry) || getAppsForEntry(entry)[0];
          if (!app || !app.supported(entry)) throw new Error('No compatible application');
          if (disposed || iframe !== iframeRef.current) throw new Error('Plugin window closed');
          actions.current.openWithApp(entry, app, path.slice(0, path.lastIndexOf('/')) || '/');
        }
      } catch (error) {
        reply.error = error instanceof Error ? error.message : String(error);
      }
      iframe?.contentWindow?.postMessage(reply, window.location.origin);
      if (data.method === 'close' && !reply.error) actions.current.onRequestClose();
    };
    window.addEventListener('message', onMessage);
    return () => {
      disposed = true;
      window.removeEventListener('message', onMessage);

    };
  }, [iframeRef, pluginKey]);
}

function PluginFrame({ frameRef, src, title }: {
  frameRef: React.RefObject<HTMLIFrameElement | null>; src: string; title: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const iframe = document.createElement('iframe');
    iframe.style.cssText = 'width:100%;height:100%;border:0;display:block';
    iframe.title = title;
    iframe.src = src;
    frameRef.current = iframe;
    container.current?.appendChild(iframe);
    return () => {
      frameRef.current = null;
      unloadPluginFrame(iframe);
    };
  }, [frameRef, src, title]);
  return <div ref={container} style={{ width: '100%', height: '100%' }} />;
}

/**
 * 插件宿主组件 - 文件打开模式
 * 使用 iframe 隔离渲染与样式，避免插件污染宿主 DOM/CSS。
 * 注意：同源且不加 sandbox 时，不是安全沙箱（插件仍可通过 window.parent 访问宿主）。
 */
export const PluginAppHost: React.FC<PluginAppHostProps> = ({
  plugin,
  filePath,
  entry,
  onRequestClose,
}) => {
  const { lang } = useI18n();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  usePluginMessages(iframeRef, plugin.key, onRequestClose);

  const src = useMemo(
    () =>
      buildPluginFrameUrl({
        pluginKey: plugin.key,
        pluginVersion: plugin.content_hash || plugin.version || '',
        mode: 'file',
        lang,
        filePath,
        entry: JSON.stringify(entry),
      }),
    [plugin, filePath, entry, lang]
  );



  return (
    <PluginFrame
      frameRef={iframeRef}
      src={src}
      title={`plugin:${plugin.key}`}
    />
  );
};

export interface PluginAppOpenHostProps extends AppOpenComponentProps {
  plugin: PluginItem;
}

/**
 * 插件宿主组件 - 独立应用模式
 * 使用 iframe 隔离渲染与样式，避免插件污染宿主 DOM/CSS。
 * 注意：同源且不加 sandbox 时，不是安全沙箱（插件仍可通过 window.parent 访问宿主）。
 */
export const PluginAppOpenHost: React.FC<PluginAppOpenHostProps> = ({ plugin, onRequestClose }) => {
  const { lang } = useI18n();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  usePluginMessages(iframeRef, plugin.key, onRequestClose);

  const src = useMemo(
    () =>
      buildPluginFrameUrl({
        pluginKey: plugin.key,
        pluginVersion: plugin.content_hash || plugin.version || '',
        mode: 'app',
        lang,
      }),
    [plugin, lang]
  );



  return (
    <PluginFrame
      frameRef={iframeRef}
      src={src}
      title={`plugin:${plugin.key}:app`}
    />
  );
};
