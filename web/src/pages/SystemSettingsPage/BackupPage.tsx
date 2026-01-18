import { memo, useState } from 'react';
import { Button, Typography, Upload, message, Modal, Card, Checkbox, Space, Radio } from 'antd';
import PageCard from '../../components/PageCard';
import { UploadOutlined, DownloadOutlined } from '@ant-design/icons';
import { backupApi } from '../../api/backup';
import { useI18n } from '../../i18n';

const { Paragraph, Text } = Typography;

const BACKUP_SECTIONS = [
  { key: 'user_accounts', labelKey: 'User Accounts' },
  { key: 'storage_adapters', labelKey: 'Storage Adapters' },
  { key: 'automation_tasks', labelKey: 'Automation Tasks' },
  { key: 'share_links', labelKey: 'Share Links' },
  { key: 'configurations', labelKey: 'Configurations' },
  { key: 'ai_providers', labelKey: 'AI Providers' },
  { key: 'ai_models', labelKey: 'AI Models' },
  { key: 'ai_default_models', labelKey: 'AI Default Models' },
  { key: 'plugins', labelKey: 'Plugin Data' },
] as const;

type BackupSection = typeof BACKUP_SECTIONS[number]['key'];
const ALL_SECTION_KEYS = BACKUP_SECTIONS.map((section) => section.key) as BackupSection[];

const BackupPage = memo(function BackupPage() {
  const [loading, setLoading] = useState(false);
  const [selectedSections, setSelectedSections] = useState<BackupSection[]>(ALL_SECTION_KEYS);
  const [importMode, setImportMode] = useState<'replace' | 'merge'>('replace');
  const { t } = useI18n();
  const importWarning = importMode === 'replace'
    ? t('Warning: This will clear data in the backup sections before importing.')
    : t('Warning: This will merge data in the backup sections and overwrite existing records with the same ID.');
  const importWarningType = importMode === 'replace' ? 'danger' : 'warning';
  const exportOptions = BACKUP_SECTIONS.map((section) => ({
    label: t(section.labelKey),
    value: section.key,
  }));
  const canExport = selectedSections.length > 0;

  const handleExport = async () => {
    setLoading(true);
    try {
      await backupApi.export(selectedSections);
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
          <Paragraph>
            <Text strong type={importWarningType}>{importWarning}</Text>
          </Paragraph>
        </Typography>
      ),
      okText: t('Confirm Import'),
      okType: 'danger',
      cancelText: t('Cancel'),
      onOk: async () => {
        setLoading(true);
        try {
          const response = await backupApi.import(file, importMode);
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
            {t('Export selected data into a JSON file.')}
            <Text strong>{t('Keep your backup file safe.')}</Text>
          </Paragraph>
          <Space direction="vertical" size={8} style={{ width: '100%', marginBottom: 12 }}>
            <Text>{t('Select backup sections')}</Text>
            <Checkbox.Group
              options={exportOptions}
              value={selectedSections}
              onChange={(values) => setSelectedSections(values as BackupSection[])}
            />
          </Space>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleExport}
            loading={loading}
            disabled={!canExport}
          >
            {t('Export Backup')}
          </Button>
        </Card>
        <Card title={t('Import')} style={{ flex: 1 }}>
          <Paragraph>
            {t('Restore data from a previously exported JSON file.')}
          </Paragraph>
          <Space direction="vertical" size={8} style={{ width: '100%', marginBottom: 12 }}>
            <Text>{t('Import mode')}</Text>
            <Radio.Group
              optionType="button"
              buttonStyle="solid"
              value={importMode}
              onChange={(event) => setImportMode(event.target.value)}
            >
              <Radio.Button value="merge">{t('Merge (upsert by ID)')}</Radio.Button>
              <Radio.Button value="replace">{t('Replace (clear before import)')}</Radio.Button>
            </Radio.Group>
            <Text type={importWarningType}>
              {importWarning}
            </Text>
          </Space>
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
