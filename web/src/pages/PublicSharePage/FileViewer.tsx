import { memo, useState, useEffect } from 'react';
import { Card, Spin, Button, Typography, Empty } from 'antd';
import { DownloadOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { shareApi, type ShareInfo } from '../../api/share';
import { type VfsEntry } from '../../api/vfs';
import { format, parseISO } from 'date-fns';
import ReactMarkdown from 'react-markdown';
import { VideoViewer } from './VideoViewer';
import { useI18n } from '../../i18n';

const { Title, Text } = Typography;

const isImageViewer = (name: string) => /\.(jpg|jpeg|png|gif|bmp|webp|svg)$/i.test(name);
const isVideoViewable = (name: string) => /\.(mp4|webm|ogg|m4v|mov)$/i.test(name);

interface FileViewerProps {
  token: string;
  shareInfo: ShareInfo;
  entry: VfsEntry;
  password?: string;
  onBack: () => void;
  path: string;
}

export const FileViewer = memo(function FileViewer({ token, shareInfo, entry, password, onBack, path }: FileViewerProps) {
  const [loading, setLoading] = useState(true);
  const [content, setContent] = useState<string>('');
  const [error, setError] = useState('');
  const { t } = useI18n();

  useEffect(() => {
    const loadFileContent = async () => {
      setLoading(true);
      setError('');
      try {
        const url = shareApi.downloadUrl(token, path, password);
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error('Unable to load file');
        }
        const text = await response.text();
        setContent(text);
      } catch (e: any) {
        setError(e.message || 'Failed to load file');
      } finally {
        setLoading(false);
      }
    };

    if (entry.name.endsWith('.md')) {
      loadFileContent();
    } else {
      setLoading(false);
    }
  }, [token, entry.name, password, path]);

  const renderContent = () => {
    if (loading) {
      return <div style={{ textAlign: 'center', padding: 50 }}><Spin /></div>;
    }
    if (error) {
      return <Empty description={error} />;
    }

    const downloadUrl = shareApi.downloadUrl(token, path, password);

    if (isImageViewer(entry.name)) {
      return <img src={downloadUrl} alt={entry.name} style={{ maxWidth: '100%' }} />;
    }

    if (isVideoViewable(entry.name)) {
      return <VideoViewer token={token} entry={entry} password={password} path={path} />;
    }

    if (entry.name.endsWith('.md')) {
      return <ReactMarkdown>{content}</ReactMarkdown>;
    }

      return (
      <Empty
        description={
          <div>
            <p>{t('Preview not supported for this file type')}</p>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              href={downloadUrl}
              download
            >
              {t('Download File')}
            </Button>
          </div>
        }
      />
    );
  };

  return (
    <div style={{ padding: '24px', maxWidth: 960, margin: 'auto' }}>
      <Card>
        <Title level={4}>{entry.name}</Title>
        <Text type="secondary">
          {t('Created on {date}', { date: format(parseISO(shareInfo.created_at), 'yyyy-MM-dd') })}
          {shareInfo?.expires_at ? (
            <>
              {' '}
              {t('Expires on {date}', { date: format(parseISO(shareInfo.expires_at), 'yyyy-MM-dd') })}
            </>
          ) : null}
        </Text>
        <div style={{ marginTop: 16 }}>
          <Button
            style={{ marginBottom: 16, marginRight: 8 }}
            icon={<ArrowLeftOutlined />}
            onClick={onBack}
          >
            {t('Back')}
          </Button>
          <Button
            style={{ marginBottom: 16 }}
            icon={<DownloadOutlined />}
            href={shareApi.downloadUrl(token, path, password)}
            download
          >
            {t('Download')}
          </Button>
        </div>
        <Card>
          {renderContent()}
        </Card>
      </Card>
    </div>
  );
});
