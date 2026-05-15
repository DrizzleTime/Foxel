import request, { API_BASE_URL } from './client';

export interface VideoRoomInfo {
  id: number;
  name: string;
  token: string;
  path: string;
  control_mode: 'host_only' | 'everyone';
  created_at: string;
  expires_at?: string | null;
}

export interface VideoPlaybackState {
  position_ms: number;
  is_paused: boolean;
  playback_rate: number;
  updated_at: string;
  updated_by: string;
}

export interface VideoRoomState {
  room: VideoRoomInfo;
  playback: VideoPlaybackState;
}

export interface VideoRoomCreatePayload {
  path: string;
  name?: string;
  expires_in_days?: number;
  control_mode?: 'host_only' | 'everyone';
}

export const videoRoomApi = {
  create: (payload: VideoRoomCreatePayload) => request<VideoRoomInfo>('/video-rooms', { method: 'POST', json: payload }),
  getState: (token: string) => request<VideoRoomState>(`/watch/${token}`),
  pushEvent: (token: string, payload: { type: 'play' | 'pause' | 'seek' | 'rate'; position_ms?: number; playback_rate?: number }, actorId?: string) =>
    request<{ playback: VideoPlaybackState }>(`/watch/${token}/events`, {
      method: 'POST',
      json: payload,
      headers: actorId ? { 'X-Watch-Actor': actorId } : undefined,
    }),
  streamUrl: (token: string, path: string) => `${API_BASE_URL}/s/${token}/download?path=${encodeURIComponent(path)}`,
  connectWs: (token: string, actorId: string) => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return new WebSocket(`${proto}://${window.location.host}/api/watch/${token}/ws?actor=${encodeURIComponent(actorId)}`);
  },
};
