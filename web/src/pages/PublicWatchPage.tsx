import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router';
import { Alert, Button, Card, Empty, Input, Space, Spin, Typography, message } from 'antd';
import { videoRoomApi, type VideoRoomState } from '../api/videoRoom';

const { Title, Text } = Typography;

export default function PublicWatchPage() {
  const { token } = useParams();
  const [data, setData] = useState<VideoRoomState | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [wsConnected, setWsConnected] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const syncingRef = useRef(false);
  const wsRef = useRef<WebSocket | null>(null);

  const actorId = useMemo(() => {
    const key = 'watch_actor_id';
    const cached = localStorage.getItem(key);
    if (cached) return cached;
    const v = `guest:${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(key, v);
    return v;
  }, []);

  useEffect(() => {
    if (!token) return;
    const load = async () => {
      try {
        const res = await videoRoomApi.getState(token);
        setData(res);
        setErr('');
      } catch (e: any) {
        setErr(e.message || '加载视频间失败');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let closedByCleanup = false;
    let reconnectTimer: number | null = null;

    const connect = () => {
      const ws = videoRoomApi.connectWs(token, actorId);
      wsRef.current = ws;
      ws.onopen = () => setWsConnected(true);
      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === 'snapshot' || msg.type === 'playback') {
            setData((prev) => {
              if (!prev) return prev;
              return { ...prev, playback: msg.playback };
            });
          }
        } catch {
          void 0;
        }
      };
      ws.onclose = () => {
        setWsConnected(false);
        if (!closedByCleanup) {
          reconnectTimer = window.setTimeout(connect, 1500);
        }
      };
      ws.onerror = () => {
        setWsConnected(false);
      };
    };

    connect();

    return () => {
      closedByCleanup = true;
      setWsConnected(false);
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [token, actorId]);

  useEffect(() => {
    const video = videoRef.current;
    const pb = data?.playback;
    if (!video || !pb) return;

    syncingRef.current = true;
    const targetSec = (pb.position_ms || 0) / 1000;
    if (Math.abs(video.currentTime - targetSec) > 1.2) video.currentTime = targetSec;
    if (Math.abs(video.playbackRate - pb.playback_rate) > 0.01) video.playbackRate = pb.playback_rate;
    if (pb.is_paused && !video.paused) video.pause();
    if (!pb.is_paused && video.paused) void video.play().catch(() => void 0);
    setTimeout(() => { syncingRef.current = false; }, 120);
  }, [data?.playback?.updated_at]);

  const sendEvent = (payload: { event: 'play' | 'pause' | 'seek' | 'rate'; position_ms?: number; playback_rate?: number }) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(payload));
  };

  if (loading) return <div style={{ padding: 40, textAlign: 'center' }}><Spin /></div>;
  if (err || !data) return <div style={{ padding: 40 }}><Empty description={err || '房间不存在'} /></div>;

  return (
    <div style={{ maxWidth: 980, margin: '24px auto', padding: '0 16px' }}>
      <Card>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>{data.room.name}</Title>
          <Text type="secondary">同步状态：{data.playback.is_paused ? '暂停' : '播放中'} | 倍速 {data.playback.playback_rate}x</Text>
          <Text type={wsConnected ? 'success' : 'warning'}>{wsConnected ? '实时同步已连接' : '实时同步断开，正在重连…'}</Text>
          <Input readOnly value={`${window.location.origin}/watch/${data.room.token}`} addonBefore="分享链接" />
        </Space>
      </Card>

      <Card style={{ marginTop: 16 }}>
        <video
          ref={videoRef}
          src={videoRoomApi.streamUrl(data.room.token, data.room.path)}
          style={{ width: '100%', background: '#000', borderRadius: 8 }}
          controls
          onPlay={() => { if (!syncingRef.current) sendEvent({ event: 'play' }); }}
          onPause={() => { if (!syncingRef.current) sendEvent({ event: 'pause' }); }}
          onSeeked={() => {
            if (syncingRef.current) return;
            const ms = Math.floor((videoRef.current?.currentTime || 0) * 1000);
            sendEvent({ event: 'seek', position_ms: ms });
          }}
          onRateChange={() => {
            if (syncingRef.current) return;
            const rate = videoRef.current?.playbackRate || 1;
            sendEvent({ event: 'rate', playback_rate: rate });
          }}
        />
        <Alert type="info" showIcon style={{ marginTop: 12 }} message="已改为 WebSocket 实时同步，不再使用定时轮询。" />
        <Space style={{ marginTop: 12 }}>
          <Button onClick={() => { navigator.clipboard.writeText(`${window.location.origin}/watch/${data.room.token}`); message.success('已复制'); }}>复制链接</Button>
        </Space>
      </Card>
    </div>
  );
}
