import request, { API_BASE_URL } from './client';

export type AgentChatMessage = Record<string, any>;

export interface AgentChatContext {
  current_path?: string | null;
}

export interface AgentChatRequest {
  messages: AgentChatMessage[];
  auto_execute?: boolean;
  approved_tool_call_ids?: string[];
  rejected_tool_call_ids?: string[];
  context?: AgentChatContext;
}

export interface PendingToolCall {
  id: string;
  name: string;
  arguments: Record<string, any>;
  requires_confirmation: boolean;
}

export interface AgentChatResponse {
  messages: AgentChatMessage[];
  pending_tool_calls?: PendingToolCall[];
}

export type AgentSseEvent =
  | { event: 'assistant_start'; data: { id: string } }
  | { event: 'assistant_delta'; data: { id: string; delta: string } }
  | { event: 'assistant_end'; data: { id: string; message: AgentChatMessage } }
  | { event: 'tool_start'; data: { tool_call_id: string; name: string } }
  | { event: 'tool_end'; data: { tool_call_id: string; name: string; message: AgentChatMessage } }
  | { event: 'pending'; data: { pending_tool_calls: PendingToolCall[] } }
  | { event: 'done'; data: AgentChatResponse };

export const agentApi = {
  chat: (payload: AgentChatRequest) =>
    request<AgentChatResponse>('/agent/chat', {
      method: 'POST',
      json: payload,
    }),
  chatStream: async (
    payload: AgentChatRequest,
    onEvent: (evt: AgentSseEvent) => void,
    options?: { signal?: AbortSignal }
  ) => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    };
    const token = localStorage.getItem('token');
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const resp = await fetch(`${API_BASE_URL}/agent/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal: options?.signal,
    });

    if (!resp.ok) {
      let errMsg = resp.statusText;
      try {
        const data = await resp.json();
        if (Array.isArray((data as any)?.detail)) {
          errMsg = (data as any).detail.map((e: any) => e.msg || JSON.stringify(e)).join('; ');
        } else {
          errMsg = (typeof (data as any)?.detail === 'string') ? (data as any).detail : JSON.stringify(data);
        }
      } catch {
        try {
          errMsg = await resp.text();
        } catch { void 0; }
      }
      throw new Error(errMsg || `Request failed: ${resp.status}`);
    }

    const reader = resp.body?.getReader();
    if (!reader) throw new Error('Stream not supported');

    const decoder = new TextDecoder();
    let buffer = '';

    const flush = (raw: string) => {
      const lines = raw.split(/\r?\n/);
      let eventName = 'message';
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trimStart());
        }
      }
      const dataStr = dataLines.join('\n').trim();
      if (!eventName || !dataStr) return;
      try {
        const data = JSON.parse(dataStr);
        onEvent({ event: eventName as any, data } as any);
      } catch {
        // ignore parse error
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      while (true) {
        const idx = buffer.indexOf('\n\n');
        if (idx === -1) break;
        const chunk = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        if (chunk.trim()) flush(chunk);
      }
    }
    if (buffer.trim()) flush(buffer);
  },
};
