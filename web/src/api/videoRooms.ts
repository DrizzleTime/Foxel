import request, { API_BASE_URL } from './client';

export interface VideoRoomState {
  current_time: number;
  paused: boolean;
  updated_at?: string | null;
}

export interface VideoRoomInfo {
  id: number;
  token: string;
  name: string;
  path: string;
  created_at: string;
  state: VideoRoomState;
}

export interface VideoRoomCreatePayload {
  name: string;
  path: string;
}

export const videoRoomsApi = {
  create: (payload: VideoRoomCreatePayload) => request<VideoRoomInfo>('/video-rooms', { method: 'POST', json: payload }),
  get: (token: string) => request<VideoRoomInfo>(`/video-rooms/${token}`),
  streamUrl: (token: string) => `${API_BASE_URL}/video-rooms/${token}/stream`,
  wsUrl: (token: string) => {
    const base = API_BASE_URL.startsWith('http')
      ? API_BASE_URL
      : `${window.location.origin}${API_BASE_URL}`;
    const url = new URL(`${base}/video-rooms/${token}/ws`);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.href;
  },
};
