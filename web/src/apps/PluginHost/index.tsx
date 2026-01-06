import React, { useEffect, useMemo, useRef } from 'react';
import type { AppComponentProps, AppOpenComponentProps } from '../types';
import type { PluginItem } from '../../api/plugins';

export interface PluginAppHostProps extends AppComponentProps {
  plugin: PluginItem;
}

function buildPluginFrameUrl(params: Record<string, string>): string {
  const qs = new URLSearchParams(params);
  return `/plugin-frame.html?${qs.toString()}`;
}

/**
 * 插件宿主组件 - 文件打开模式
 * 使用 iframe 隔离渲染与样式，避免插件污染宿主 DOM/CSS。
 * 注意：同源且不加 sandbox 时，不是安全沙箱（插件仍可通过 window.parent 访问宿主）。
 */
export const PluginAppHost: React.FC<PluginAppHostProps> = ({
  plugin,
  filePath,
  onRequestClose,
}) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const onCloseRef = useRef(onRequestClose);
  onCloseRef.current = onRequestClose;

  const src = useMemo(
    () =>
      buildPluginFrameUrl({
        pluginKey: plugin.key,
        mode: 'file',
        filePath,
      }),
    [plugin.key, filePath]
  );

  useEffect(() => {
    const onMessage = (ev: MessageEvent) => {
      if (ev.origin !== window.location.origin) return;
      if (ev.source !== iframeRef.current?.contentWindow) return;
      const data = ev.data as any;
      if (!data || typeof data !== 'object') return;
      if (data.type === 'foxel-plugin:close' && data.pluginKey === plugin.key) {
        onCloseRef.current();
      }
    };

    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [plugin.key]);

  return (
    <iframe
      ref={iframeRef}
      src={src}
      title={`plugin:${plugin.key}`}
      style={{ width: '100%', height: '100%', border: 0, display: 'block' }}
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
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const onCloseRef = useRef(onRequestClose);
  onCloseRef.current = onRequestClose;

  const src = useMemo(
    () =>
      buildPluginFrameUrl({
        pluginKey: plugin.key,
        mode: 'app',
      }),
    [plugin.key]
  );

  useEffect(() => {
    const onMessage = (ev: MessageEvent) => {
      if (ev.origin !== window.location.origin) return;
      if (ev.source !== iframeRef.current?.contentWindow) return;
      const data = ev.data as any;
      if (!data || typeof data !== 'object') return;
      if (data.type === 'foxel-plugin:close' && data.pluginKey === plugin.key) {
        onCloseRef.current();
      }
    };

    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [plugin.key]);

  return (
    <iframe
      ref={iframeRef}
      src={src}
      title={`plugin:${plugin.key}:app`}
      style={{ width: '100%', height: '100%', border: 0, display: 'block' }}
    />
  );
};
