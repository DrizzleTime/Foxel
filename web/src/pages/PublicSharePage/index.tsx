import { memo, useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router';
import { Card, message, Spin, Button, Empty, Input, Form } from 'antd';
import { shareApi, type ShareInfo } from '../../api/share';
import { type VfsEntry } from '../../api/vfs';
import { DirectoryViewer } from './DirectoryViewer';
import { FileViewer } from './FileViewer';
import { useI18n } from '../../i18n';

const PublicSharePage = memo(function PublicSharePage() {
  const { token } = useParams<{ token: string }>();
  const [loading, setLoading] = useState(true);
  const [shareInfo, setShareInfo] = useState<ShareInfo | null>(null);
  const [previewFile, setPreviewFile] = useState<{ entry: VfsEntry, path: string } | null>(null);
  const [error, setError] = useState('');
  const [password, setPassword] = useState('');
  const [verified, setVerified] = useState(false);
  const { t } = useI18n();

	  const loadData = useCallback(async (pwd?: string) => {
	    if (!token) return;
	    setLoading(true);
	    setError('');
    try {
      let info = shareInfo;
      if (!info) {
        info = await shareApi.get(token);
        setShareInfo(info);
      }

      if (info?.access_type === 'password' && !verified) {
        setLoading(false);
        return;
      }

      const currentPassword = pwd || password;

      if (info.paths.length === 1) {
        const listing = await shareApi.listDir(token, '/', currentPassword);
        if (listing.entries.length === 1) {
          const singleEntry = listing.entries[0];
          if (!singleEntry.is_dir) {
            setPreviewFile({ entry: singleEntry, path: '/' + singleEntry.name });
          }
        }
      }

    } catch (e: any) {
      setError(e.message || t('Share load failed'));
      if (e.message === '需要密码') {
        setVerified(false);
      }
	    } finally {
	      setLoading(false);
	    }
	  }, [password, shareInfo, t, token, verified]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handlePasswordSubmit = async (values: { password_input: string }) => {
    if (!token) return;
    try {
      await shareApi.verifyPassword(token, values.password_input);
      setPassword(values.password_input);
      setVerified(true);
      setError('');
      loadData(values.password_input);
    } catch (e: any) {
      message.error(e.message || t('Wrong password'));
    }
  };

  if (loading && !shareInfo) {
    return <div style={{ textAlign: 'center', padding: 50 }}><Spin size="large" /></div>;
  }

  if (error && !error.includes('需要密码')) {
    return <div style={{ textAlign: 'center', padding: 50 }}><Empty description={error} /></div>;
  }

  if (shareInfo?.access_type === 'password' && !verified) {
    return (
      <div style={{ padding: '24px', maxWidth: 400, margin: '100px auto' }}>
        <Card title={t('Password Required')}>
          <Form onFinish={handlePasswordSubmit}>
            <Form.Item name="password_input" rules={[{ required: true, message: t('Please enter password') }]}>
              <Input.Password placeholder={t('Please enter password')} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" block>
                {t('Confirm')}
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </div>
    );
  }

  if (!shareInfo) {
    return <div style={{ textAlign: 'center', padding: 50 }}><Empty description={t('Unable to load share info')} /></div>;
  }

  const handleFileClick = (entry: VfsEntry, path: string) => {
    setPreviewFile({ entry, path });
  };

  const handleBack = () => {
    setPreviewFile(null);
  };

  if (previewFile) {
    return (
      <FileViewer
        token={token!}
        shareInfo={shareInfo}
        entry={previewFile.entry}
        password={password}
        onBack={handleBack}
        path={previewFile.path}
      />
    );
  }
  return <DirectoryViewer token={token!} shareInfo={shareInfo} password={password} onFileClick={handleFileClick} />;
});

export default PublicSharePage;
