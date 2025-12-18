import React, { useState, useEffect, useCallback, useRef, useMemo, Suspense } from 'react';
import { Layout, Spin, Button, Space, message } from 'antd';
import type { AppComponentProps } from '../types';
import { vfsApi } from '../../api/vfs';
import request from '../../api/client';

const MonacoEditor = React.lazy(() => import('@monaco-editor/react'));
const MarkdownEditor = React.lazy(() => import('@uiw/react-md-editor'));

const { Header, Content } = Layout;

const MAX_PREVIEW_BYTES = 1024 * 1024; // 1MB

export const TextEditorApp: React.FC<AppComponentProps> = ({ filePath, entry, onRequestClose }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [content, setContent] = useState('');
  const [initialContent, setInitialContent] = useState('');
  const [truncated, setTruncated] = useState(false);
  const isDirty = content !== initialContent;
  const onRequestCloseRef = useRef(onRequestClose);
  onRequestCloseRef.current = onRequestClose;

  const ext = useMemo(() => entry.name.split('.').pop()?.toLowerCase() || '', [entry.name]);
  const isMarkdown = ext === 'md' || ext === 'markdown';
  const monacoLanguage = useMemo(() => {
    switch (ext) {
      // Web technologies
      case 'js':
      case 'jsx':
        return 'javascript';
      case 'ts':
      case 'tsx':
        return 'typescript';
      case 'html':
      case 'htm':
        return 'html';
      case 'css':
        return 'css';
      case 'scss':
      case 'sass':
        return 'scss';
      case 'less':
        return 'less';
      case 'vue':
        return 'html'; // Vue files are primarily HTML with some JS/TS
      
      // Data formats
      case 'json':
        return 'json';
      case 'yaml':
      case 'yml':
        return 'yaml';
      case 'xml':
        return 'xml';
      case 'toml':
        return 'ini'; // TOML is similar to INI
      case 'ini':
      case 'cfg':
      case 'conf':
        return 'ini';
      
      // Programming languages
      case 'py':
        return 'python';
      case 'java':
        return 'java';
      case 'c':
        return 'c';
      case 'cpp':
      case 'cc':
      case 'cxx':
        return 'cpp';
      case 'h':
      case 'hpp':
      case 'hxx':
        return 'cpp'; // Header files use C++ highlighting
      case 'php':
        return 'php';
      case 'rb':
        return 'ruby';
      case 'go':
        return 'go';
      case 'rs':
        return 'rust';
      case 'swift':
        return 'swift';
      case 'kt':
        return 'kotlin';
      case 'scala':
        return 'scala';
      case 'cs':
        return 'csharp';
      case 'fs':
        return 'fsharp';
      case 'vb':
        return 'vb';
      case 'pl':
      case 'pm':
        return 'perl';
      case 'r':
        return 'r';
      case 'lua':
        return 'lua';
      case 'dart':
        return 'dart';
      
      // Database
      case 'sql':
        return 'sql';
      
      // Shell and scripts
      case 'sh':
      case 'bash':
      case 'zsh':
      case 'fish':
        return 'shell';
      case 'ps1':
        return 'powershell';
      case 'bat':
      case 'cmd':
        return 'bat';
      
      // Build and config files
      case 'dockerfile':
        return 'dockerfile';
      case 'makefile':
        return 'makefile';
      case 'gradle':
        return 'groovy';
      case 'cmake':
        return 'cmake';
      
      // Markdown
      case 'md':
      case 'markdown':
        return 'markdown';
      
      // Plain text and logs
      case 'txt':
      case 'log':
      case 'gitignore':
      case 'gitattributes':
      case 'editorconfig':
      case 'prettierrc':
      default:
        return 'plaintext';
    }
  }, [ext]);

  useEffect(() => {
    const loadFile = async () => {
      try {
        setLoading(true);
        setTruncated(false);
        const shouldTruncate = (entry.size ?? 0) > MAX_PREVIEW_BYTES;
        if (shouldTruncate) {
          const enc = encodeURI(filePath.replace(/^\/+/, ''));
          const resp = await request(`/fs/file/${enc}`, {
            method: 'GET',
            headers: { Range: `bytes=0-${MAX_PREVIEW_BYTES - 1}` },
            rawResponse: true,
          });
          const buf = await (resp as Response).arrayBuffer();
          const text = new TextDecoder().decode(buf);
          setContent(text);
          setInitialContent(text);
          setTruncated(true);
        } else {
          const data = await vfsApi.readFile(filePath);
          const text = typeof data === 'string' ? data : new TextDecoder().decode(data);
          setContent(text);
          setInitialContent(text);
        }
      } catch (error) {
        message.error(`加载文件失败: ${error instanceof Error ? error.message : '未知错误'}`);
        onRequestCloseRef.current();
      } finally {
        setLoading(false);
      }
    };
    loadFile();
  }, [filePath, entry.size]);
  const handleSave = useCallback(async () => {
    if (truncated) {
      message.warning('大文件仅预览前 1MB，已禁用保存');
      return;
    }
    if (!isDirty) return;
    try {
      setSaving(true);
      const blob = new Blob([content], { type: 'text/plain' });
      await vfsApi.uploadFile(filePath, blob);
      setInitialContent(content);
      message.success('保存成功');
    } catch (error) {
      message.error(`保存文件失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setSaving(false);
    }
  }, [content, filePath, isDirty, truncated]);

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

  return (
    <Layout style={{ height: '100%', background: 'var(--ant-color-bg-container, #ffffff)' }}>
      <Header
        style={{
          background: 'var(--ant-color-bg-layout, #f0f2f5)',
          padding: '0 16px',
          height: 40,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid var(--ant-color-border-secondary, #d9d9d9)'
        }}
      >
        <span style={{ color: 'var(--ant-color-text, rgba(0,0,0,0.88))' }}>
          {entry.name} {isDirty && '*'} {truncated && '（大文件仅预览前 1MB，编辑与保存已禁用）'}
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
        ) : (
          isMarkdown ? (
            <Suspense fallback={<Spin style={{ marginTop: 24 }} />}>
              <MarkdownEditor
                value={content}
                onChange={(val) => setContent(val || '')}
                height="100%"
                preview={truncated ? 'preview' : 'live'}
              />
            </Suspense>
          ) : (
            <Suspense fallback={<Spin style={{ marginTop: 24 }} />}>
              <MonacoEditor
                value={content}
                onChange={(val) => setContent(val || '')}
                height="100%"
                language={monacoLanguage}
                options={{
                  readOnly: truncated,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  wordWrap: 'on',
                  fontSize: 13,
                }}
              />
            </Suspense>
          )
        )}
      </Content>
    </Layout>
  );
};
