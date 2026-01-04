/**
 * 文本编辑器主组件
 */
import React, { useState, useEffect, useCallback, useMemo, Suspense, lazy } from 'react';
import { Layout, Spin, Button, Space, message } from 'antd';
import type { PluginContext } from './foxel-types';
import { getMonacoLanguage } from './utils';

// 懒加载编辑器组件（由插件自己提供）
const MonacoEditor = lazy(() => import('@monaco-editor/react').then(m => ({ default: m.default })));
const MDEditor = lazy(() => import('@uiw/react-md-editor').then(m => ({ default: m.default })));

const { Header, Content } = Layout;
const MAX_PREVIEW_BYTES = 1024 * 1024; // 1MB

export const TextEditorApp: React.FC<PluginContext> = ({ filePath, entry }) => {
  const { foxelApi } = window.__FOXEL_EXTERNALS__;
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [content, setContent] = useState('');
  const [initialContent, setInitialContent] = useState('');
  const [truncated, setTruncated] = useState(false);
  const isDirty = content !== initialContent;
  
  const ext = useMemo(() => entry.name.split('.').pop()?.toLowerCase() || '', [entry.name]);
  const isMarkdown = ext === 'md' || ext === 'markdown';
  const monacoLanguage = useMemo(() => getMonacoLanguage(ext), [ext]);

  useEffect(() => {
    const loadFile = async () => {
      try {
        setLoading(true);
        setTruncated(false);
        const shouldTruncate = (entry.size || 0) > MAX_PREVIEW_BYTES;

        if (shouldTruncate) {
          // 大文件使用 Range 请求读取部分内容
          const cleaned = filePath.replace(/^\/+/, '');
          const resp = await foxelApi.request(`/fs/file/${encodeURI(cleaned)}`, {
            method: 'GET',
            headers: { Range: `bytes=0-${MAX_PREVIEW_BYTES - 1}` },
            rawResponse: true,
          });
          const buf = await resp.arrayBuffer();
          const text = new TextDecoder().decode(buf);
          setContent(text);
          setInitialContent(text);
          setTruncated(true);
        } else {
          const data = await foxelApi.vfs.readFile(filePath);
          const text = typeof data === 'string' ? data : new TextDecoder().decode(data as ArrayBuffer);
          setContent(text);
          setInitialContent(text);
        }
      } catch (error) {
        message.error(`加载文件失败: ${error instanceof Error ? error.message : '未知错误'}`);
      } finally {
        setLoading(false);
      }
    };
    loadFile();
  }, [filePath, entry.size, foxelApi]);

  const handleSave = useCallback(async () => {
    if (truncated) {
      message.warning('大文件仅预览前 1MB，已禁用保存');
      return;
    }
    if (!isDirty) return;
    try {
      setSaving(true);
      const blob = new Blob([content], { type: 'text/plain' });
      await foxelApi.vfs.uploadFile(filePath, blob);
      setInitialContent(content);
      message.success('保存成功');
    } catch (error) {
      message.error(`保存文件失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setSaving(false);
    }
  }, [content, filePath, isDirty, truncated, foxelApi]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 's') {
        event.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleSave]);

  const headerStyle: React.CSSProperties = {
    background: 'var(--ant-color-bg-layout, #f0f2f5)',
    padding: '0 16px',
    height: 40,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottom: '1px solid var(--ant-color-border-secondary, #d9d9d9)',
  };

  return (
    <Layout style={{ height: '100%', background: 'var(--ant-color-bg-container, #ffffff)' }}>
      <Header style={headerStyle}>
        <span style={{ color: 'var(--ant-color-text, rgba(0,0,0,0.88))' }}>
          {entry.name}
          {isDirty ? ' *' : ''}
          {truncated ? ' （大文件仅预览前 1MB，编辑与保存已禁用）' : ''}
        </span>
        <Space>
          <Button type="primary" size="small" onClick={handleSave} loading={saving} disabled={!isDirty || truncated}>
            保存
          </Button>
        </Space>
      </Header>
      <Content style={{ position: 'relative', overflow: 'auto', height: 'calc(100% - 40px)' }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
            <Spin />
          </div>
        ) : isMarkdown ? (
          <Suspense fallback={<Spin style={{ marginTop: 24 }} />}>
            <div data-color-mode="light" style={{ height: '100%' }}>
              <MDEditor
                value={content}
                onChange={(val) => setContent(val || '')}
                height="100%"
                preview={truncated ? 'preview' : 'live'}
                hideToolbar={truncated}
              />
            </div>
          </Suspense>
        ) : (
          <Suspense fallback={<Spin style={{ marginTop: 24 }} />}>
            <MonacoEditor
              value={content}
              onChange={(val) => setContent(val || '')}
              height="100%"
              language={monacoLanguage}
              theme="vs"
              options={{
                readOnly: truncated,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                fontSize: 13,
              }}
            />
          </Suspense>
        )}
      </Content>
    </Layout>
  );
};
