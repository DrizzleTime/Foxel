import { memo, useState } from 'react';
import { Button, Typography, Upload, message, Modal, Card } from 'antd';
import PageCard from '../../components/PageCard';
import { UploadOutlined, DownloadOutlined } from '@ant-design/icons';
import { backupApi } from '../../api/backup';
import { useI18n } from '../../i18n';

const { Paragraph, Text } = Typography;

const BackupPage = memo(function BackupPage() {
  const [loading, setLoading] = useState(false);
  const { t } = useI18n();

  const handleExport = async () => {
    setLoading(true);
    try {
      await backupApi.export();
      message.success(t('Export started, check your downloads.'));
    } catch (e: any) {
      message.error(e.message || t('Export failed'));
    } finally {
      setLoading(false);
    }
  };

  const handleImport = (file: File) => {
    Modal.confirm({
      title: t('Confirm import backup?'),
      content: (
        <Typography>
          <Paragraph>{t('Are you sure to import from this file?')}</Paragraph>
          <Paragraph strong>{t('Warning: This will overwrite all data including users (with passwords), settings, storages and tasks. Irreversible!')}</Paragraph>
        </Typography>
      ),
      okText: t('Confirm Import'),
      okType: 'danger',
      cancelText: t('Cancel'),
      onOk: async () => {
        setLoading(true);
        try {
          const response = await backupApi.import(file);
          message.success(response.message || t('Import succeeded! The page will refresh.'));
          setTimeout(() => window.location.reload(), 2000);
        } catch (e: any) {
          message.error(e.message || t('Import failed'));
        } finally {
          setLoading(false);
        }
      },
    });
    return false; // 阻止 antd 的 Upload 组件自动上传
  };

  return (
    <PageCard title={t('Backup & Restore')}>

      <div style={{ display: 'flex', gap: '16px' }}>
        <Card title={t('Export')} style={{ flex: 1 }}>
          <Paragraph>
            {t('Export all data (adapters, users, tasks, shares) into a JSON file.')}
            <Text strong>{t('Keep your backup file safe.')}</Text>
          </Paragraph>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleExport}
            loading={loading}
          >
            {t('Export Backup')}
          </Button>
        </Card>
        <Card title={t('Import')} style={{ flex: 1 }}>
          <Paragraph>
            {t('Restore data from a previously exported JSON file.')}
            <Text strong type="danger">{t('Warning: This will clear and overwrite existing data.')}</Text>
          </Paragraph>
          <Upload
            beforeUpload={handleImport}
            showUploadList={false}
          >
            <Button icon={<UploadOutlined />} loading={loading}>
              {t('Choose File and Restore')}
            </Button>
          </Upload>
        </Card>
      </div>
    </PageCard>
  );
});

export default BackupPage;
