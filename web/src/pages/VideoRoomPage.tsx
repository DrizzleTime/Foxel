import { memo, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router';
import { Button, Empty, Space, Spin, Tag, Tooltip, Typography, message } from 'antd';
import {
  CheckCircleFilled,
  DisconnectOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import Artplayer from 'artplayer';
import { videoRoomsApi, type VideoRoomInfo, type VideoRoomState } from '../api/videoRooms';
import { useI18n } from '../i18n';
import './VideoRoomPage.css';

const { Text, Title } = Typography;

const SYNC_THRESHOLD = 1.2;

function getSyncedTime(state: VideoRoomState) {
  const baseTime = Math.max(0, Number(state.current_time) || 0);
  if (state.paused || !state.updated_at) return baseTime;

  const updatedAt = Date.parse(state.updated_at);
  if (Number.isNaN(updatedAt)) return baseTime;

  return baseTime + Math.max(0, (Date.now() - updatedAt) / 1000);
}

function formatTime(seconds: number) {
  const safeSeconds = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const secs = safeSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }
  return `${minutes}:${String(secs).padStart(2, '0')}`;
}

function getFileName(path: string) {
  return path.split('/').filter(Boolean).pop() || path;
}

const VideoRoomPage = memo(function VideoRoomPage() {
  const { token } = useParams<{ token: string }>();
  const { t } = useI18n();
  const artRef = useRef<HTMLDivElement | null>(null);
  const artInstance = useRef<Artplayer | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const applyingRemoteRef = useRef(false);
  const sendTimerRef = useRef<number | null>(null);
  const liveStateRef = useRef<VideoRoomState | null>(null);
  const [room, setRoom] = useState<VideoRoomInfo | null>(null);
  const [liveState, setLiveState] = useState<VideoRoomState | null>(null);
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
        setLiveState(data.state);
        liveStateRef.current = data.state;
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
      liveStateRef.current = state;
      setLiveState(state);
      if (!art) return;
      const video = art.video;
      const targetTime = getSyncedTime(state);
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

    const applyLatestState = () => {
      applyState(liveStateRef.current || room.state);
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

    art.on('ready', applyLatestState);
    art.video.addEventListener('loadedmetadata', applyLatestState);
    art.video.addEventListener('canplay', applyLatestState);
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
      art.video.removeEventListener('loadedmetadata', applyLatestState);
      art.video.removeEventListener('canplay', applyLatestState);
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
    return (
      <div className="video-room-page video-room-page--center">
        <Spin size="large" />
      </div>
    );
  }

  if (error || !room) {
    return (
      <div className="video-room-page video-room-page--center">
        <Empty description={error || t('Video room not found')} />
      </div>
    );
  }

  const fileName = getFileName(room.path);
  const state = liveState || room.state;

  return (
    <div className="video-room-page">
      <header className="video-room-header">
        <div className="video-room-header__left">
          <div className="video-room-title-block">
            <Title level={3} className="video-room-title">{room.name}</Title>
            <Space size={8} wrap>
              <Text type="secondary" ellipsis className="video-room-file-name">{fileName}</Text>
              <Text type="secondary">{formatTime(state.current_time)}</Text>
            </Space>
          </div>
        </div>
        <div className="video-room-header__right">
          <Tag
            className="video-room-status-tag"
            color={connected ? 'success' : 'error'}
            icon={connected ? <CheckCircleFilled /> : <DisconnectOutlined />}
          >
            {connected ? t('Room synced') : t('Room disconnected')}
          </Tag>
          <Tooltip title={t('Copy Link')}>
            <Button icon={<LinkOutlined />} onClick={handleCopy}>
              {t('Share room')}
            </Button>
          </Tooltip>
        </div>
      </header>

      <main className="video-room-shell">
        <section className="video-room-main">
          <div className="video-room-stage">
            <div ref={artRef} className="video-room-player" />
          </div>
          <div className="video-room-note">
            <CheckCircleFilled />
            <span>{t('Playback state is shared in this room')}</span>
          </div>
        </section>
      </main>
    </div>
  );
});

export default VideoRoomPage;
