import { memo, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router';
import { Button, Empty, Spin, Typography, message } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import Artplayer from 'artplayer';
import { videoRoomsApi, type VideoRoomInfo, type VideoRoomState } from '../api/videoRooms';
import { useI18n } from '../i18n';

const { Title, Text } = Typography;

const SYNC_THRESHOLD = 1.2;

const VideoRoomPage = memo(function VideoRoomPage() {
  const { token } = useParams<{ token: string }>();
  const { t } = useI18n();
  const artRef = useRef<HTMLDivElement | null>(null);
  const artInstance = useRef<Artplayer | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const applyingRemoteRef = useRef(false);
  const sendTimerRef = useRef<number | null>(null);
  const [room, setRoom] = useState<VideoRoomInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let mounted = true;
    if (!token) return;

    videoRoomsApi.get(token)
      .then((data) => {
        if (!mounted) return;
        setRoom(data);
      })
      .catch((e: any) => {
        if (!mounted) return;
        setError(e.message || t('Video room load failed'));
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [t, token]);

  useEffect(() => {
    if (!token || !room || !artRef.current) return;

    const sendState = () => {
      const art = artInstance.current;
      const ws = wsRef.current;
      if (!art || !ws || ws.readyState !== WebSocket.OPEN || applyingRemoteRef.current) return;
      const video = art.video;
      const payload = {
        type: 'state',
        current_time: video.currentTime || 0,
        paused: video.paused,
      };
      ws.send(JSON.stringify(payload));
    };

    const sendStateSoon = () => {
      if (sendTimerRef.current !== null) {
        window.clearTimeout(sendTimerRef.current);
      }
      sendTimerRef.current = window.setTimeout(() => {
        sendTimerRef.current = null;
        sendState();
      }, 120);
    };

    const applyState = (state: VideoRoomState) => {
      const art = artInstance.current;
      if (!art) return;
      const video = art.video;
      const targetTime = Math.max(0, Number(state.current_time) || 0);
      applyingRemoteRef.current = true;
      if (Math.abs((video.currentTime || 0) - targetTime) > SYNC_THRESHOLD) {
        video.currentTime = targetTime;
      }
      if (state.paused && !video.paused) {
        void video.pause();
      }
      if (!state.paused && video.paused) {
        void video.play().catch(() => undefined);
      }
      window.setTimeout(() => {
        applyingRemoteRef.current = false;
      }, 250);
    };

    const art = new Artplayer({
      container: artRef.current,
      url: videoRoomsApi.streamUrl(token),
      autoplay: false,
      fullscreen: true,
      fullscreenWeb: true,
      pip: true,
      setting: true,
      playbackRate: true,
    });
    artInstance.current = art;

    art.on('ready', () => applyState(room.state));
    art.on('play', sendStateSoon);
    art.on('pause', sendStateSoon);
    art.on('seek', sendStateSoon);

    const ws = new WebSocket(videoRoomsApi.wsUrl(token));
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data?.type === 'state' && data.state) {
          applyState(data.state);
        }
      } catch {
        void 0;
      }
    };

    return () => {
      if (sendTimerRef.current !== null) {
        window.clearTimeout(sendTimerRef.current);
        sendTimerRef.current = null;
      }
      ws.close();
      art.destroy();
      wsRef.current = null;
      artInstance.current = null;
    };
  }, [room, token]);

  const handleCopy = () => {
    navigator.clipboard.writeText(window.location.href);
    message.success(t('Copied to clipboard'));
  };

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 50 }}><Spin size="large" /></div>;
  }

  if (error || !room) {
    return <div style={{ textAlign: 'center', padding: 50 }}><Empty description={error || t('Video room not found')} /></div>;
  }

  return (
    <div style={{ minHeight: '100vh', background: '#111', color: '#fff', padding: 24 }}>
      <div style={{ maxWidth: 1120, margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', marginBottom: 16 }}>
          <div style={{ minWidth: 0 }}>
            <Title level={3} style={{ color: '#fff', margin: 0 }}>{room.name}</Title>
            <Text style={{ color: connected ? '#7dd3fc' : '#fca5a5' }}>
              {connected ? t('Room synced') : t('Room disconnected')}
            </Text>
          </div>
          <Button icon={<CopyOutlined />} onClick={handleCopy}>
            {t('Copy Link')}
          </Button>
        </div>
        <div
          ref={artRef}
          style={{
            width: '100%',
            height: 'min(70vh, 680px)',
            minHeight: 360,
            background: '#000',
          }}
        />
      </div>
    </div>
  );
});

export default VideoRoomPage;
