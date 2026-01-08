import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Avatar, Button, Divider, Drawer, Flex, Input, List, Space, Switch, Tag, Typography, message, theme } from 'antd';
import { RobotOutlined, SendOutlined, FolderOpenOutlined, DeleteOutlined, ToolOutlined, DownOutlined, UpOutlined, CodeOutlined, CopyOutlined, LoadingOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import PathSelectorModal from './PathSelectorModal';
import { agentApi, type AgentChatMessage, type PendingToolCall } from '../api/agent';
import { useI18n } from '../i18n';
import '../styles/ai-agent.css';

const { Text, Paragraph } = Typography;

function normalizePath(p?: string | null): string | null {
  if (!p) return null;
  const s = ('/' + p).replace(/\/+/, '/').replace(/\\/g, '/').replace(/\/+$/, '') || '/';
  return s;
}

function extractTextContent(content: any): string {
  if (content == null) return '';
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    const parts: string[] = [];
    for (const item of content) {
      if (typeof item === 'string') {
        if (item.trim()) parts.push(item);
        continue;
      }
      const text = typeof item?.text === 'string' ? item.text : '';
      if (text.trim()) parts.push(text);
    }
    return parts.join('\n');
  }
  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return String(content);
  }
}

function tryParseJson<T = any>(raw: string): T | null {
  if (typeof raw !== 'string') return null;
  const s = raw.trim();
  if (!s) return null;
  try {
    return JSON.parse(s) as T;
  } catch {
    return null;
  }
}

function shortId(id: string, keep: number = 6): string {
  const s = String(id || '');
  if (s.length <= keep * 2 + 3) return s;
  return `${s.slice(0, keep)}…${s.slice(-keep)}`;
}

interface AiAgentWidgetProps {
  currentPath?: string | null;
  open: boolean;
  onOpenChange(open: boolean): void;
}

const AiAgentWidget = memo(function AiAgentWidget({ currentPath, open, onOpenChange }: AiAgentWidgetProps) {
  const { t } = useI18n();
  const { token } = theme.useToken();
  const [autoExecute, setAutoExecute] = useState(false);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<AgentChatMessage[]>([]);
  const [pending, setPending] = useState<PendingToolCall[]>([]);
  const [pathModalOpen, setPathModalOpen] = useState(false);
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({});
  const [expandedRaw, setExpandedRaw] = useState<Record<string, boolean>>({});
  const [runningTools, setRunningTools] = useState<Record<string, string>>({});
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const streamControllerRef = useRef<AbortController | null>(null);
  const streamSeqRef = useRef(0);
  const baseMessagesRef = useRef<AgentChatMessage[]>([]);
  const assistantIndexRef = useRef<Record<string, number>>({});
  const toolNameByIdRef = useRef<Record<string, string>>({});

  const effectivePath = useMemo(() => normalizePath(currentPath), [currentPath]);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(scrollToBottom, 0);
    return () => window.clearTimeout(t);
  }, [messages, open, pending, scrollToBottom]);

  useEffect(() => {
    return () => {
      streamControllerRef.current?.abort();
    };
  }, []);

  const toolCallsById = useMemo(() => {
    const map = new Map<string, { name: string; args: Record<string, any> }>();
    for (const msg of messages) {
      if (!msg || typeof msg !== 'object') continue;
      if (msg.role !== 'assistant') continue;
      const toolCalls = (msg as any).tool_calls;
      if (!Array.isArray(toolCalls)) continue;
      for (const call of toolCalls) {
        const id = typeof call?.id === 'string' ? call.id : '';
        const fn = call?.function;
        const name = typeof fn?.name === 'string' ? fn.name : '';
        const rawArgs = typeof fn?.arguments === 'string' ? fn.arguments : '';
        if (!id || !name) continue;
        const parsedArgs = tryParseJson<Record<string, any>>(rawArgs) || {};
        map.set(id, { name, args: parsedArgs });
      }
    }
    return map;
  }, [messages]);

  const runStream = useCallback(async (payload: Partial<Parameters<typeof agentApi.chat>[0]> & { messages: AgentChatMessage[] }) => {
    streamControllerRef.current?.abort();
    const controller = new AbortController();
    streamControllerRef.current = controller;
    streamSeqRef.current += 1;
    const seq = streamSeqRef.current;

    baseMessagesRef.current = payload.messages;
    assistantIndexRef.current = {};

    setLoading(true);
    const approvedIds = payload.approved_tool_call_ids || [];
    if (Array.isArray(approvedIds) && approvedIds.length > 0) {
      const preRunning: Record<string, string> = {};
      approvedIds.forEach((id) => {
        if (typeof id === 'string' && id.trim()) preRunning[id] = '';
      });
      setRunningTools(preRunning);
    } else {
      setRunningTools({});
    }

    try {
      await agentApi.chatStream(
        {
          messages: payload.messages,
          auto_execute: autoExecute,
          context: effectivePath ? { current_path: effectivePath } : undefined,
          approved_tool_call_ids: payload.approved_tool_call_ids,
          rejected_tool_call_ids: payload.rejected_tool_call_ids,
        },
        (evt) => {
          if (seq !== streamSeqRef.current) return;
          switch (evt.event) {
            case 'assistant_start': {
              const id = String((evt.data as any)?.id || '');
              if (!id) return;
              setMessages((prev) => {
                const idx = prev.length;
                assistantIndexRef.current[id] = idx;
                return [...prev, { role: 'assistant', content: '' }];
              });
              return;
            }
            case 'assistant_delta': {
              const id = String((evt.data as any)?.id || '');
              const delta = String((evt.data as any)?.delta || '');
              if (!id || !delta) return;
              setMessages((prev) => {
                const idx = assistantIndexRef.current[id];
                if (idx === undefined || idx < 0 || idx >= prev.length) return prev;
                const cur = prev[idx] as any;
                const curContent = typeof cur?.content === 'string' ? cur.content : extractTextContent(cur?.content);
                const next = prev.slice();
                next[idx] = { ...cur, content: (curContent || '') + delta };
                return next;
              });
              return;
            }
            case 'assistant_end': {
              const id = String((evt.data as any)?.id || '');
              const msg = (evt.data as any)?.message;
              if (!id || !msg || typeof msg !== 'object') return;
              setMessages((prev) => {
                const idx = assistantIndexRef.current[id];
                if (idx === undefined || idx < 0 || idx >= prev.length) return prev;
                const next = prev.slice();
                next[idx] = msg;
                return next;
              });
              delete assistantIndexRef.current[id];
              return;
            }
            case 'tool_start': {
              const toolCallId = String((evt.data as any)?.tool_call_id || '');
              const name = String((evt.data as any)?.name || '');
              if (!toolCallId) return;
              if (name) toolNameByIdRef.current[toolCallId] = name;
              setRunningTools((prev) => ({ ...prev, [toolCallId]: name || prev[toolCallId] || '' }));
              return;
            }
            case 'tool_end': {
              const toolCallId = String((evt.data as any)?.tool_call_id || '');
              const name = String((evt.data as any)?.name || '');
              const msg = (evt.data as any)?.message;
              if (toolCallId && name) toolNameByIdRef.current[toolCallId] = name;
              if (toolCallId) {
                setRunningTools((prev) => {
                  const next = { ...prev };
                  delete next[toolCallId];
                  return next;
                });
              }
              if (msg && typeof msg === 'object') {
                setMessages((prev) => [...prev, msg]);
              }
              return;
            }
            case 'pending': {
              const items = Array.isArray((evt.data as any)?.pending_tool_calls) ? (evt.data as any).pending_tool_calls : [];
              setPending(items);
              return;
            }
            case 'done': {
              const base = baseMessagesRef.current || [];
              const newMessages = Array.isArray((evt.data as any)?.messages) ? (evt.data as any).messages : [];
              const nextPending = Array.isArray((evt.data as any)?.pending_tool_calls) ? (evt.data as any).pending_tool_calls : [];
              setMessages([...base, ...newMessages]);
              setPending(nextPending);
              setRunningTools({});
              assistantIndexRef.current = {};
              return;
            }
            default:
              return;
          }
        },
        { signal: controller.signal }
      );
    } catch (err: any) {
      if (controller.signal.aborted) return;
      message.error(err?.message || t('Operation failed'));
    } finally {
      if (seq === streamSeqRef.current) {
        setLoading(false);
        if (controller.signal.aborted) {
          setRunningTools({});
          assistantIndexRef.current = {};
        }
      }
    }
  }, [autoExecute, effectivePath, t]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text) return;
    if (pending.length > 0) {
      message.warning(t('Please confirm pending actions first'));
      return;
    }
    const nextUserMsg: AgentChatMessage = { role: 'user', content: text };
    setInput('');
    const base = [...messages, nextUserMsg];
    setMessages(base);
    setPending([]);
    await runStream({ messages: base });
  }, [input, messages, pending.length, runStream, t]);

  const clearChat = useCallback(() => {
    streamControllerRef.current?.abort();
    setMessages([]);
    setPending([]);
    setExpandedTools({});
    setExpandedRaw({});
    setRunningTools({});
  }, []);

  const approveOne = useCallback(async (id: string) => {
    await runStream({ messages, approved_tool_call_ids: [id] });
  }, [messages, runStream]);

  const rejectOne = useCallback(async (id: string) => {
    await runStream({ messages, rejected_tool_call_ids: [id] });
  }, [messages, runStream]);

  const approveAll = useCallback(async () => {
    const ids = pending.map((p) => p.id).filter(Boolean);
    if (ids.length === 0) return;
    await runStream({ messages, approved_tool_call_ids: ids });
  }, [messages, pending, runStream]);

  const rejectAll = useCallback(async () => {
    const ids = pending.map((p) => p.id).filter(Boolean);
    if (ids.length === 0) return;
    await runStream({ messages, rejected_tool_call_ids: ids });
  }, [messages, pending, runStream]);

  const handlePathSelected = useCallback((path: string) => {
    const p = normalizePath(path) || '/';
    setInput((prev) => (prev.trim() ? `${prev.trim()} ${p}` : p));
    setPathModalOpen(false);
  }, []);

  const messageItems = useMemo(() => {
    return messages.filter((m) => {
      if (!m || typeof m !== 'object') return false;
      const role = typeof (m as any).role === 'string' ? String((m as any).role) : '';
      if (!role || role === 'system') return false;
      if (role === 'assistant') {
        const text = extractTextContent((m as any).content);
        return !!text.trim();
      }
      return true;
    });
  }, [messages]);

  const runningToolEntries = useMemo(() => Object.entries(runningTools).filter(([id]) => !!id), [runningTools]);
  const runningToolCount = runningToolEntries.length;

  const copyToClipboard = useCallback(async (raw: string) => {
    try {
      await navigator.clipboard.writeText(raw);
      message.success(t('Copied'));
    } catch (err: any) {
      message.error(err?.message || t('Operation failed'));
    }
  }, [t]);

  const renderToolResultSummary = useCallback((toolName: string, rawContent: string, toolArgs?: Record<string, any> | null) => {
    const data = tryParseJson<Record<string, any>>(rawContent);
    if (!data) return '';

    if (data.canceled) return t('Canceled');
    if (data.error) return `${t('Error')}: ${String(data.error)}`;

    if (toolName === 'processors_list') {
      const processors = Array.isArray(data.processors) ? data.processors : [];
      return `${t('Processors')}: ${processors.length}`;
    }
    if (toolName === 'processors_run') {
      const ctx = (() => {
        const processorType = typeof toolArgs?.processor_type === 'string' ? toolArgs.processor_type.trim() : '';
        const path = typeof toolArgs?.path === 'string' ? toolArgs.path.trim() : '';
        const parts = [processorType, path].filter(Boolean);
        return parts.length ? parts.join(' · ') : '';
      })();
      if (typeof data.task_id === 'string') {
        return ctx ? `${t('Task submitted')}: ${ctx} · ${shortId(data.task_id)}` : `${t('Task submitted')}: ${shortId(data.task_id)}`;
      }
      const taskIds = Array.isArray(data.task_ids) ? data.task_ids : [];
      const scheduled = typeof data.scheduled === 'number' ? data.scheduled : taskIds.length;
      if (scheduled) return ctx ? `${t('Tasks submitted')}: ${ctx} · ${scheduled}` : `${t('Tasks submitted')}: ${scheduled}`;
      return t('Task submitted');
    }
    if (toolName === 'vfs_list_dir') {
      const path = typeof data.path === 'string' ? data.path : '';
      const entries = Array.isArray(data.entries) ? data.entries : [];
      const names = entries
        .map((it: any) => String(it?.name || '').trim())
        .filter(Boolean)
        .slice(0, 3);
      const head = `${t('Directory')}: ${path || '/'}`;
      const tail = `${entries.length} ${t('items')}`;
      const sample = names.length ? ` · ${names.join(', ')}` : '';
      return `${head} · ${tail}${sample}`;
    }
    if (toolName === 'vfs_search') {
      const query = typeof data.query === 'string' ? data.query : '';
      const items = Array.isArray(data.items) ? data.items : [];
      return `${t('Search')}: ${query || '-'} · ${items.length} ${t('results')}`;
    }
    if (toolName === 'vfs_stat') {
      const isDir = Boolean(data.is_dir);
      const path = typeof data.path === 'string' ? data.path : '';
      return `${t('Info')}: ${path || '-'} · ${isDir ? t('Folder') : t('File')}`;
    }
    if (toolName === 'vfs_read_text') {
      const path = typeof data.path === 'string' ? data.path : '';
      const length = typeof data.length === 'number' ? data.length : undefined;
      const truncated = Boolean(data.truncated);
      const tail = length != null ? ` · ${length} ${t('chars')}${truncated ? `(${t('Truncated')})` : ''}` : '';
      return `${t('Read')}: ${path || '-'}${tail}`;
    }
    if (toolName === 'vfs_write_text') {
      const path = typeof data.path === 'string' ? data.path : '';
      const bytes = typeof data.bytes === 'number' ? data.bytes : undefined;
      return `${t('Write')}: ${path || '-'}${bytes != null ? ` · ${bytes} bytes` : ''}`;
    }
    if (toolName === 'vfs_mkdir') {
      const path = typeof data.path === 'string' ? data.path : '';
      return `${t('Created')}: ${path || '-'}`;
    }
    if (toolName === 'vfs_delete') {
      const path = typeof data.path === 'string' ? data.path : '';
      return `${t('Deleted')}: ${path || '-'}`;
    }
    if (toolName === 'vfs_move') {
      const src = typeof data.src === 'string' ? data.src : '';
      const dst = typeof data.dst === 'string' ? data.dst : '';
      return `${t('Moved')}: ${src || '-'} → ${dst || '-'}`;
    }
    if (toolName === 'vfs_copy') {
      const src = typeof data.src === 'string' ? data.src : '';
      const dst = typeof data.dst === 'string' ? data.dst : '';
      return `${t('Copied')}: ${src || '-'} → ${dst || '-'}`;
    }
    if (toolName === 'vfs_rename') {
      const src = typeof data.src === 'string' ? data.src : '';
      const dst = typeof data.dst === 'string' ? data.dst : '';
      return `${t('Renamed')}: ${src || '-'} → ${dst || '-'}`;
    }
    return '';
  }, [t]);

  const renderToolDetails = useCallback((toolKey: string, toolName: string, rawContent: string) => {
    const data = tryParseJson<Record<string, any>>(rawContent);
    const showRaw = !!expandedRaw[toolKey];
    const toggleRaw = () => setExpandedRaw((prev) => ({ ...prev, [toolKey]: !prev[toolKey] }));

    const rawJson = (() => {
      if (!rawContent?.trim()) return '';
      const parsed = tryParseJson<any>(rawContent);
      if (!parsed) return rawContent;
      try {
        return JSON.stringify(parsed, null, 2);
      } catch {
        return rawContent;
      }
    })();

    const header = (
      <Space size={10} wrap>
        <Button
          type="text"
          size="small"
          icon={<CodeOutlined />}
          onClick={(e) => { e.stopPropagation(); toggleRaw(); }}
        >
          {t('Raw JSON')}
        </Button>
        {showRaw && (
          <Button
            type="text"
            size="small"
            icon={<CopyOutlined />}
            onClick={(e) => { e.stopPropagation(); void copyToClipboard(rawJson); }}
          >
            {t('Copy')}
          </Button>
        )}
      </Space>
    );

    if (toolName === 'processors_list') {
      const processors = Array.isArray(data?.processors) ? data!.processors : [];
      return (
        <div className="fx-agent-tool-details">
          {header}
          <Divider style={{ margin: '10px 0' }} />
          <List
            size="small"
            dataSource={processors}
            locale={{ emptyText: t('No results') }}
            renderItem={(item: any) => (
              <List.Item>
                <Space size={10} wrap>
                  <Text code style={{ fontVariantNumeric: 'tabular-nums' }}>{String(item?.type || '')}</Text>
                  <Text>{String(item?.name || '')}</Text>
                </Space>
              </List.Item>
            )}
            style={{ background: 'transparent' }}
          />
          {showRaw && (
            <>
              <Divider style={{ margin: '10px 0' }} />
              <pre className="fx-agent-pre">{rawJson}</pre>
            </>
          )}
        </div>
      );
    }

    if (toolName === 'vfs_list_dir') {
      const path = typeof data?.path === 'string' ? data!.path : '/';
      const entries = Array.isArray(data?.entries) ? data!.entries : [];
      const pagination = data?.pagination && typeof data.pagination === 'object' ? data.pagination : null;
      return (
        <div className="fx-agent-tool-details">
          {header}
          <Divider style={{ margin: '10px 0' }} />
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>{t('Directory')}: {path}</Text>
            {pagination?.total != null ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t('Total')}: {String(pagination.total)}
              </Text>
            ) : null}
          </Space>
          <Divider style={{ margin: '10px 0' }} />
          <List
            size="small"
            dataSource={entries}
            locale={{ emptyText: t('No results') }}
            renderItem={(item: any) => {
              const name = String(item?.name || '');
              const type = String(item?.type || (item?.is_dir ? 'dir' : 'file'));
              return (
                <List.Item>
                  <Space size={10} wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                    <Space size={10} wrap>
                      <Text code style={{ fontVariantNumeric: 'tabular-nums' }}>{type}</Text>
                      <Text>{name}</Text>
                    </Space>
                    {!item?.is_dir && typeof item?.size === 'number' ? (
                      <Text type="secondary" style={{ fontSize: 12 }}>{item.size} bytes</Text>
                    ) : null}
                  </Space>
                </List.Item>
              );
            }}
            style={{ background: 'transparent' }}
          />
          {showRaw && (
            <>
              <Divider style={{ margin: '10px 0' }} />
              <pre className="fx-agent-pre">{rawJson}</pre>
            </>
          )}
        </div>
      );
    }

    if (toolName === 'vfs_search') {
      const query = typeof data?.query === 'string' ? data!.query : '';
      const mode = typeof data?.mode === 'string' ? data!.mode : '';
      const items = Array.isArray(data?.items) ? data!.items : [];
      const pagination = data?.pagination && typeof data.pagination === 'object' ? data.pagination : null;
      return (
        <div className="fx-agent-tool-details">
          {header}
          <Divider style={{ margin: '10px 0' }} />
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>{t('Search')}: {query || '-'}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>{t('Mode')}: {mode || '-'}</Text>
            {pagination?.has_more != null ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t('Page')}: {String(pagination.page)} · {t('Has more')}: {String(Boolean(pagination.has_more))}
              </Text>
            ) : null}
          </Space>
          <Divider style={{ margin: '10px 0' }} />
          <List
            size="small"
            dataSource={items}
            locale={{ emptyText: t('No results') }}
            renderItem={(item: any) => {
              const type = String(item?.source_type || item?.mime || '');
              const path = String(item?.path || '');
              const score = item?.score != null ? Number(item.score) : null;
              return (
                <List.Item>
                  <Space size={10} wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                    <Space size={10} wrap>
                      {type ? <Text code style={{ fontVariantNumeric: 'tabular-nums' }}>{type}</Text> : null}
                      <Text>{path}</Text>
                    </Space>
                    {score != null && !Number.isNaN(score) ? (
                      <Text type="secondary" style={{ fontSize: 12 }}>{score.toFixed(3)}</Text>
                    ) : null}
                  </Space>
                </List.Item>
              );
            }}
            style={{ background: 'transparent' }}
          />
          {showRaw && (
            <>
              <Divider style={{ margin: '10px 0' }} />
              <pre className="fx-agent-pre">{rawJson}</pre>
            </>
          )}
        </div>
      );
    }

    if (toolName === 'vfs_read_text') {
      const path = typeof data?.path === 'string' ? data!.path : '';
      const content = typeof data?.content === 'string' ? data!.content : '';
      return (
        <div className="fx-agent-tool-details">
          {header}
          <Divider style={{ margin: '10px 0' }} />
          <Text type="secondary" style={{ fontSize: 12 }}>{t('File')}: {path || '-'}</Text>
          <pre className="fx-agent-pre" style={{ marginTop: 10 }}>{content || ''}</pre>
          {showRaw && (
            <>
              <Divider style={{ margin: '10px 0' }} />
              <pre className="fx-agent-pre">{rawJson}</pre>
            </>
          )}
        </div>
      );
    }

    return (
      <div className="fx-agent-tool-details">
        {header}
        <Divider style={{ margin: '10px 0' }} />
        {showRaw ? (
          <pre className="fx-agent-pre">{rawJson}</pre>
        ) : (
          <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
            {extractTextContent(data ?? rawContent) || <Text type="secondary">{t('No content')}</Text>}
          </Paragraph>
        )}
      </div>
    );
  }, [copyToClipboard, expandedRaw, t]);

  const renderToolArgsSummary = useCallback((toolName: string, args?: Record<string, any> | null) => {
    const a = args || {};
    if (toolName === 'processors_run') {
      const path = typeof a.path === 'string' ? a.path : '';
      return path ? `${t('Path')}: ${path}` : '';
    }
    if (toolName === 'vfs_read_text' || toolName === 'vfs_list_dir' || toolName === 'vfs_stat' || toolName === 'vfs_delete' || toolName === 'vfs_mkdir') {
      const path = typeof a.path === 'string' ? a.path : '';
      return path ? `${t('Path')}: ${path}` : '';
    }
    if (toolName === 'vfs_search') {
      const query = typeof a.query === 'string' ? a.query : '';
      return query ? `${t('Search')}: ${query}` : '';
    }
    if (toolName === 'vfs_write_text') {
      const path = typeof a.path === 'string' ? a.path : '';
      return path ? `${t('Path')}: ${path}` : '';
    }
    if (toolName === 'vfs_move' || toolName === 'vfs_copy' || toolName === 'vfs_rename') {
      const src = typeof a.src === 'string' ? a.src : '';
      const dst = typeof a.dst === 'string' ? a.dst : '';
      if (src && dst) return `${src} → ${dst}`;
      if (src) return src;
      if (dst) return dst;
      return '';
    }
    return '';
  }, [t]);

  return (
    <>
      <Drawer
        title={t('AI Agent')}
        open={open}
        onClose={() => { streamControllerRef.current?.abort(); onOpenChange(false); }}
        width={520}
        mask={false}
        destroyOnHidden
        styles={{
          body: {
            padding: 8,
            background: token.colorBgLayout,
          },
        }}
        extra={
          <Space align="center">
            <Text type="secondary">{t('Auto execute')}</Text>
            <Switch size="small" checked={autoExecute} onChange={setAutoExecute} />
            <Button
              type="text"
              size="small"
              icon={<DeleteOutlined />}
              onClick={clearChat}
              disabled={loading || messageItems.length === 0}
            >
              {t('Clear')}
            </Button>
          </Space>
        }
      >
        <Flex vertical gap={8} style={{ height: '100%' }} className="fx-agent-container">
          <div
            ref={scrollRef}
            className="fx-agent-chat-scroll"
          >
            {messageItems.length === 0 ? (
              <div className="fx-agent-empty">
                <Avatar size={36} icon={<RobotOutlined />} style={{ background: token.colorPrimary }} />
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">{t('Start a conversation')}</Text>
                </div>
              </div>
            ) : (
              <div className="fx-agent-messages">
                {messageItems.map((m, idx) => {
                  const role = String((m as any).role);
                  const isUser = role === 'user';
                  const isTool = role === 'tool';
                  const toolCallId = typeof (m as any).tool_call_id === 'string' ? String((m as any).tool_call_id) : '';
                  const toolInfo = toolCallId ? toolCallsById.get(toolCallId) : null;
                  const toolName = toolInfo?.name || (toolCallId ? toolNameByIdRef.current[toolCallId] : '') || '';
                  const msgKey = toolCallId ? `tool:${toolCallId}` : `${role}:${idx}`;

                  if (isTool) {
                    const rawContent = extractTextContent((m as any).content);
                    const expanded = !!expandedTools[msgKey];
                    const summary = toolName ? renderToolResultSummary(toolName, rawContent, toolInfo?.args || null) : '';
                    return (
                      <div key={msgKey} className="fx-agent-msg fx-agent-msg-tool">
                        <div className="fx-agent-tool-block">
                          <div className="fx-agent-tool-bar">
                            <Space size={6} wrap className="fx-agent-tool-pills">
                              <Tag className="fx-agent-pill" bordered={false} icon={<ToolOutlined />}>
                                {t('MCP Tool')}
                              </Tag>
                              <Tag className="fx-agent-pill fx-agent-pill-strong" bordered={false} icon={<CodeOutlined />}>
                                {toolName || t('Tool')}
                              </Tag>
                            </Space>
                            <Button
                              type="text"
                              size="small"
                              icon={expanded ? <UpOutlined /> : <DownOutlined />}
                              onClick={() => setExpandedTools((prev) => ({ ...prev, [msgKey]: !prev[msgKey] }))}
                            >
                              {expanded ? t('Collapse') : t('Expand')}
                              </Button>
                          </div>
                          {summary ? (
                            <div className="fx-agent-tool-summary-line">
                              <Text type="secondary">{summary}</Text>
                            </div>
                          ) : null}
                          {expanded && (
                            <div className="fx-agent-tool-expanded">
                              {toolInfo?.args && Object.keys(toolInfo.args).length > 0 && (
                                <div style={{ marginBottom: 10 }}>
                                  <Text type="secondary" style={{ fontSize: 12 }}>{t('Arguments')}</Text>
                                  <pre className="fx-agent-pre fx-agent-pre-compact">
                                    {JSON.stringify(toolInfo.args, null, 2)}
                                  </pre>
                                </div>
                              )}
                              {renderToolDetails(msgKey, toolName || t('Tool'), rawContent)}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  }

                  const text = extractTextContent((m as any).content);
                  if (isUser) {
                    return (
                      <div key={msgKey} className="fx-agent-msg fx-agent-msg-user">
                        <div className="fx-agent-user-block fx-agent-content">
                          {text.trim() ? <div className="fx-agent-text">{text}</div> : <Text type="secondary">{t('No content')}</Text>}
                        </div>
                      </div>
                    );
                  }

                  return (
                    <div key={msgKey} className="fx-agent-msg fx-agent-msg-assistant">
                      <div className="fx-agent-assistant-block fx-agent-content">
                        {text.trim() ? (
                          <div className="fx-agent-md">
                            <ReactMarkdown>{text}</ReactMarkdown>
                          </div>
                        ) : (
                          <Text type="secondary">{t('No content')}</Text>
                        )}
                      </div>
                    </div>
                  );
                })}
                {runningToolCount > 0 && (
                  <div className="fx-agent-running">
                    <LoadingOutlined spin />
                    <Text type="secondary">{t('Calling tools')}</Text>
                    <Space size={6} wrap>
                      {runningToolEntries.slice(0, 2).map(([id, name]) => (
                        <Tag key={id} bordered={false} color="blue">
                          {(name || t('Tool'))} #{shortId(id, 4)}
                        </Tag>
                      ))}
                      {runningToolCount > 2 && (
                        <Text type="secondary">+{runningToolCount - 2}</Text>
                      )}
                    </Space>
                  </div>
                )}
                {pending.length > 0 && (
                  <div className="fx-agent-pending-group">
                    <div className="fx-agent-pending-head">
                      <Space size={8} wrap>
                        <Tag className="fx-agent-pill fx-agent-pill-warn" bordered={false}>
                          {t('Pending actions')}
                        </Tag>
                        <Text type="secondary">{pending.length}</Text>
                      </Space>
                      <Space size={6}>
                        <Button size="small" type="primary" onClick={approveAll} loading={loading}>
                          {t('Execute all')}
                        </Button>
                        <Button size="small" onClick={rejectAll} disabled={loading}>
                          {t('Cancel all')}
                        </Button>
                      </Space>
                    </div>

                    <div className="fx-agent-pending-list">
                      {pending.map((p) => {
                        const args = p.arguments || {};
                        const key = `pending:${p.id}`;
                        const expanded = !!expandedTools[key];
                        const running = Object.prototype.hasOwnProperty.call(runningTools, p.id);
                        const summary = renderToolArgsSummary(p.name, args);
                        return (
                          <div key={p.id} className="fx-agent-tool-block fx-agent-pending-item">
                            <div className="fx-agent-tool-bar">
                              <Space size={6} wrap className="fx-agent-tool-pills">
                                <Tag className="fx-agent-pill" bordered={false} icon={<ToolOutlined />}>
                                  {t('MCP Tool')}
                                </Tag>
                                <Tag className="fx-agent-pill fx-agent-pill-strong" bordered={false} icon={<CodeOutlined />}>
                                  {p.name}
                                </Tag>
                                {running ? <LoadingOutlined spin style={{ color: token.colorPrimary }} /> : null}
                              </Space>
                              <Space size={6}>
                                <Button
                                  size="small"
                                  type="primary"
                                  onClick={() => void approveOne(p.id)}
                                  loading={loading && running}
                                  disabled={loading && !running}
                                >
                                  {t('Execute')}
                                </Button>
                                <Button
                                  size="small"
                                  onClick={() => void rejectOne(p.id)}
                                  disabled={loading && !running}
                                >
                                  {t('Cancel')}
                                </Button>
                                <Button
                                  type="text"
                                  size="small"
                                  icon={expanded ? <UpOutlined /> : <DownOutlined />}
                                  onClick={() => setExpandedTools((prev) => ({ ...prev, [key]: !prev[key] }))}
                                />
                              </Space>
                            </div>
                            {summary ? (
                              <div className="fx-agent-tool-summary-line">
                                <Text type="secondary">{summary}</Text>
                              </div>
                            ) : null}
                            {expanded && (
                              <div className="fx-agent-tool-expanded">
                                <Text type="secondary" style={{ fontSize: 12 }}>{t('Arguments')}</Text>
                                <pre className="fx-agent-pre">
                                  {JSON.stringify(args, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="fx-agent-composer">
            <Flex vertical gap={8}>
              <Space wrap>
                <Button size="small" icon={<FolderOpenOutlined />} onClick={() => setPathModalOpen(true)} disabled={loading}>
                  {t('Select Path')}
                </Button>
                {effectivePath && (
                  <Tag bordered={false} color="blue">{t('Current')}: {effectivePath}</Tag>
                )}
              </Space>

              <Input.TextArea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={t('Type a message')}
                autoSize={{ minRows: 2, maxRows: 6 }}
                disabled={loading || pending.length > 0}
                variant="borderless"
                onPressEnter={(e) => {
                  if (e.shiftKey) return;
                  e.preventDefault();
                  void handleSend();
                }}
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <Button
                  type="primary"
                  size="small"
                  icon={<SendOutlined />}
                  onClick={handleSend}
                  loading={loading}
                  disabled={loading || pending.length > 0 || !input.trim()}
                >
                  {t('Send')}
                </Button>
              </div>
            </Flex>
          </div>
        </Flex>
      </Drawer>

      <PathSelectorModal
        open={pathModalOpen}
        mode="any"
        initialPath={effectivePath || '/'}
        onOk={handlePathSelected}
        onCancel={() => setPathModalOpen(false)}
      />
    </>
  );
});

export default AiAgentWidget;
