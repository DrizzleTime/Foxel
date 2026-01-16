import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Avatar, Button, Divider, Flex, Input, List, Modal, Space, Switch, Tag, Typography, message, theme } from 'antd';
import { RobotOutlined, SendOutlined, DeleteOutlined, ToolOutlined, DownOutlined, UpOutlined, CodeOutlined, CopyOutlined, LoadingOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import type { TextAreaRef } from 'antd/es/input/TextArea';
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

function clampText(value: string, maxLen: number): string {
  if (value.length <= maxLen) return value;
  return `${value.slice(0, maxLen)}…`;
}

function formatDisplayValue(value: any, maxLen: number = 120): string {
  if (value == null) return '';
  if (typeof value === 'string') return clampText(value, maxLen);
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return clampText(JSON.stringify(value), maxLen);
  } catch {
    return clampText(String(value), maxLen);
  }
}

function isPlainObject(value: any): value is Record<string, any> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

type ToolPayload = {
  ok?: boolean;
  summary?: string;
  view?: {
    type?: string;
    title?: string;
    meta?: Record<string, any>;
    items?: any[];
    text?: string;
    message?: string;
  };
  data?: any;
  error?: any;
};

function parseToolPayload(raw: string): ToolPayload | null {
  const parsed = tryParseJson<ToolPayload>(raw);
  if (!parsed || typeof parsed !== 'object') return null;
  return parsed;
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
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({});
  const [expandedRaw, setExpandedRaw] = useState<Record<string, boolean>>({});
  const [runningTools, setRunningTools] = useState<Record<string, string>>({});
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<TextAreaRef | null>(null);
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
    if (!open || loading || pending.length > 0) return;
    const t = window.setTimeout(() => {
      inputRef.current?.focus();
    }, 0);
    return () => window.clearTimeout(t);
  }, [open, loading, messages.length, pending.length]);

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

  const renderToolResultSummary = useCallback((rawContent: string) => {
    const payload = parseToolPayload(rawContent);
    if (!payload) return '';
    const summary = typeof payload.summary === 'string' ? payload.summary.trim() : '';
    if (summary) return summary;

    if (payload.ok === false) {
      const message = typeof payload.error?.message === 'string' ? payload.error.message : '';
      return message ? `${t('Error')}: ${message}` : t('Error');
    }

    const view = payload.view || {};
    const viewType = typeof view.type === 'string' ? view.type : '';
    if (viewType === 'text') {
      const text = typeof view.text === 'string' ? view.text : '';
      return text ? `${text.length} ${t('chars')}` : '';
    }
    if (viewType === 'list') {
      const items = Array.isArray(view.items) ? view.items : [];
      return `${items.length} ${t('items')}`;
    }
    if (viewType === 'kv') {
      const items = Array.isArray(view.items) ? view.items : [];
      return `${items.length} ${t('items')}`;
    }
    return '';
  }, [t]);

  const renderToolDetails = useCallback((toolKey: string, rawContent: string) => {
    const payload = parseToolPayload(rawContent);
    const view = payload?.view;
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

    const viewType = typeof view?.type === 'string' ? view.type : '';
    const title = typeof view?.title === 'string' ? view.title : '';
    const metaEntries = isPlainObject(view?.meta) ? Object.entries(view!.meta) : [];

    const renderMeta = () => {
      if (metaEntries.length === 0 && !title) return null;
      return (
        <>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            {title ? (
              <Text type="secondary" style={{ fontSize: 12 }}>{title}</Text>
            ) : null}
            {metaEntries.slice(0, 6).map(([key, value]) => (
              <Text key={key} type="secondary" style={{ fontSize: 12 }}>
                {key}: {formatDisplayValue(value, 180) || '-'}
              </Text>
            ))}
          </Space>
          <Divider style={{ margin: '10px 0' }} />
        </>
      );
    };

    if (viewType === 'error') {
      const message = typeof view?.message === 'string'
        ? view.message
        : (typeof payload?.error?.message === 'string' ? payload.error.message : t('Error'));
      return (
        <div className="fx-agent-tool-details">
          {header}
          <Divider style={{ margin: '10px 0' }} />
          <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
            {message || t('Error')}
          </Paragraph>
          {showRaw && (
            <>
              <Divider style={{ margin: '10px 0' }} />
              <pre className="fx-agent-pre">{rawJson}</pre>
            </>
          )}
        </div>
      );
    }

    if (viewType === 'text') {
      const text = typeof view?.text === 'string' ? view.text : '';
      return (
        <div className="fx-agent-tool-details">
          {header}
          <Divider style={{ margin: '10px 0' }} />
          {renderMeta()}
          <pre className="fx-agent-pre" style={{ marginTop: metaEntries.length || title ? 0 : 10 }}>{text || ''}</pre>
          {showRaw && (
            <>
              <Divider style={{ margin: '10px 0' }} />
              <pre className="fx-agent-pre">{rawJson}</pre>
            </>
          )}
        </div>
      );
    }

    if (viewType === 'kv') {
      const items = Array.isArray(view?.items) ? view!.items : [];
      return (
        <div className="fx-agent-tool-details">
          {header}
          <Divider style={{ margin: '10px 0' }} />
          {renderMeta()}
          <List
            size="small"
            dataSource={items}
            locale={{ emptyText: t('No results') }}
            renderItem={(item: any, idx) => {
              const key = typeof item?.key === 'string' ? item.key : (typeof item?.label === 'string' ? item.label : String(idx));
              const value = typeof item?.value === 'string' ? item.value : formatDisplayValue(item?.value, 200);
              return (
                <List.Item>
                  <Space size={10} wrap>
                    <Text code style={{ fontVariantNumeric: 'tabular-nums' }}>{key || '-'}</Text>
                    <Text>{value || '-'}</Text>
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

    if (viewType === 'list') {
      const items = Array.isArray(view?.items) ? view!.items : [];
      return (
        <div className="fx-agent-tool-details">
          {header}
          <Divider style={{ margin: '10px 0' }} />
          {renderMeta()}
          <List
            size="small"
            dataSource={items}
            locale={{ emptyText: t('No results') }}
            renderItem={(item: any) => {
              if (isPlainObject(item)) {
                const entries = Object.entries(item);
                const shown = entries.slice(0, 4);
                const extra = entries.length - shown.length;
                return (
                  <List.Item>
                    <Space size={10} wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                      <Space size={10} wrap>
                        {shown.map(([key, value]) => (
                          <Text key={key}>
                            <Text type="secondary">{key}</Text>: {formatDisplayValue(value, 160) || '-'}
                          </Text>
                        ))}
                        {extra > 0 ? <Text type="secondary">+{extra}</Text> : null}
                      </Space>
                    </Space>
                  </List.Item>
                );
              }
              return (
                <List.Item>
                  <Text>{formatDisplayValue(item, 200) || '-'}</Text>
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

    return (
      <div className="fx-agent-tool-details">
        {header}
        <Divider style={{ margin: '10px 0' }} />
        {showRaw ? (
          <pre className="fx-agent-pre">{rawJson}</pre>
        ) : (
          <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
            {extractTextContent(payload ?? rawContent) || <Text type="secondary">{t('No content')}</Text>}
          </Paragraph>
        )}
      </div>
    );
  }, [copyToClipboard, expandedRaw, t]);

  const renderToolArgsSummary = useCallback((args?: Record<string, any> | null) => {
    const entries = Object.entries(args || {})
      .filter(([, value]) => value != null && String(value).trim() !== '');
    if (entries.length === 0) return '';
    return entries.slice(0, 2)
      .map(([key, value]) => `${key}: ${formatDisplayValue(value, 60)}`)
      .join(' · ');
  }, []);

  return (
    <>
      <Modal
        title={(
          <Flex align="center" justify="space-between" gap={12} wrap>
            <Text strong>{t('AI Agent')}</Text>
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
          </Flex>
        )}
        open={open}
        onCancel={() => { streamControllerRef.current?.abort(); onOpenChange(false); }}
        width={720}
        centered
        closable={false}
        destroyOnHidden
        footer={null}
        styles={{
          body: {
            padding: 8,
            background: token.colorBgContainer,
            height: '70vh',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          },
        }}
      >
        <Flex vertical gap={0} style={{ flex: 1, minHeight: 0 }} className="fx-agent-container">
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
                    const summary = rawContent ? renderToolResultSummary(rawContent) : '';
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
                              {renderToolDetails(msgKey, rawContent)}
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
                        const summary = renderToolArgsSummary(args);
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
                {effectivePath && (
                  <Tag bordered={false} color="blue">{t('Current')}: {effectivePath}</Tag>
                )}
              </Space>

              <Input.TextArea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={t('Type a message')}
                autoSize={{ minRows: 2, maxRows: 6 }}
                autoFocus
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
      </Modal>
    </>
  );
});

export default AiAgentWidget;
