import React, { useEffect, useMemo } from 'react';
import { Modal, Button, List, Progress, Typography, message, Flex, Tag, Space } from 'antd';
import { CopyOutlined, CheckCircleFilled, CloseCircleFilled } from '@ant-design/icons';
import type { ConflictDecision, UploadConflict, UploadFile } from '../../hooks/useUploader';
import { useI18n } from '../../../../i18n';

interface UploadModalProps {
  visible: boolean;
  files: UploadFile[];
  isUploading: boolean;
  totalProgress: number;
  totalFileBytes: number;
  uploadedFileBytes: number;
  conflict: UploadConflict | null;
  onClose: () => void;
  onStartUpload: () => void;
  onResolveConflict: (decision: ConflictDecision) => void;
}

const formatBytes = (bytes: number) => {
  if (bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / (1024 ** index);
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
};

const UploadModal: React.FC<UploadModalProps> = ({
  visible,
  files,
  isUploading,
  totalProgress,
  totalFileBytes,
  uploadedFileBytes,
  conflict,
  onClose,
  onStartUpload,
  onResolveConflict,
}) => {
  const { t } = useI18n();

  const summary = useMemo(() => {
    const total = files.length;
    const completed = files.filter(f => ['success', 'skipped'].includes(f.status)).length;
    const failures = files.filter(f => f.status === 'error').length;
    const pending = files.filter(f => ['pending', 'waiting', 'uploading'].includes(f.status)).length;
    return { total, completed, failures, pending };
  }, [files]);

  const allFinished = files.length > 0 && files.every(f => ['success', 'error', 'skipped'].includes(f.status));

  useEffect(() => {
    if (visible && files.length > 0 && files.some(f => f.status === 'pending')) {
      onStartUpload();
    }
  }, [visible, files, onStartUpload]);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success(t('Copied to clipboard'));
  };

  const renderStatus = (file: UploadFile) => {
    if (file.type === 'directory') {
      if (file.status === 'uploading') {
        return <Typography.Text type="secondary">{t('Creating directory...')}</Typography.Text>;
      }
      if (file.status === 'success') {
        return (
          <Flex align="center" gap={8}>
            <CheckCircleFilled style={{ color: 'var(--ant-color-success, #52c41a)' }} />
            <Typography.Text type="secondary">{t('Directory ready')}</Typography.Text>
          </Flex>
        );
      }
      if (file.status === 'error') {
        return (
          <Flex align="center" gap={8}>
            <CloseCircleFilled style={{ color: 'var(--ant-color-error, #ff4d4f)' }} />
            <Typography.Text type="danger" title={file.error}>{t('Create directory failed')}</Typography.Text>
          </Flex>
        );
      }
      return <Typography.Text type="secondary">{t('Waiting to create')}</Typography.Text>;
    }

    switch (file.status) {
      case 'uploading':
        return <Progress percent={Math.round(file.progress)} size="small" />;
      case 'success':
        return (
          <Flex align="center" gap={8}>
            <CheckCircleFilled style={{ color: 'var(--ant-color-success, #52c41a)' }} />
            <Typography.Text type="secondary" style={{ verticalAlign: 'middle' }}>{t('Upload succeeded')}</Typography.Text>
            <Button icon={<CopyOutlined />} size="small" onClick={() => handleCopy(file.permanentLink!)} type="text" />
          </Flex>
        );
      case 'waiting':
        return <Typography.Text type="warning">{t('Waiting for overwrite decision')}</Typography.Text>;
      case 'skipped':
        return <Typography.Text type="secondary">{t('Skipped')}</Typography.Text>;
      case 'error':
        return (
            <Flex align="center" gap={8}>
                <CloseCircleFilled style={{ color: 'var(--ant-color-error, #ff4d4f)' }} />
                <Typography.Text type="danger" title={file.error}>{t('Upload failed')}</Typography.Text>
            </Flex>
        );
      default:
        return <Typography.Text type="secondary">{t('Waiting to upload')}</Typography.Text>;
    }
  };

  return (
    <Modal
      open={visible}
      title={t('Upload File')}
      width={600}
      closable={!isUploading}
      maskClosable={!isUploading}
      onCancel={onClose}
      footer={[
        <Button key="close" onClick={onClose} disabled={!allFinished || isUploading}>
          {allFinished ? t('Close') : t('Done')}
        </Button>,
      ]}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={16}>
        <div>
          <Flex justify="space-between" align="center">
            <Typography.Text strong>
              {t('Total progress')}:
            </Typography.Text>
            <Typography.Text type="secondary">
              {t('Upload bytes summary', {
                uploaded: formatBytes(uploadedFileBytes),
                total: formatBytes(totalFileBytes),
              })}
            </Typography.Text>
          </Flex>
          <Progress percent={Math.round(totalProgress)} showInfo />
          <Typography.Text type="secondary">
            {t('Upload task summary', {
              completed: summary.completed,
              total: summary.total,
              pending: summary.pending,
              failures: summary.failures,
            })}
          </Typography.Text>
        </div>

        {conflict && (
          <div
            style={{
              border: '1px solid var(--ant-color-warning-border, #faad14)',
              borderRadius: 8,
              padding: '12px 16px',
              background: 'var(--ant-color-warning-bg, rgba(250,173,20,0.1))',
            }}
          >
            <Typography.Text strong>
              {t('Overwrite confirmation required')}
            </Typography.Text>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
              {t('Target already exists: {path}', { path: conflict.relativePath })}
            </Typography.Paragraph>
            <Flex gap={8} wrap="wrap">
              <Button size="small" type="primary" onClick={() => onResolveConflict('overwrite')}>
                {t('Overwrite')}
              </Button>
              <Button size="small" onClick={() => onResolveConflict('skip')}>
                {t('Skip')}
              </Button>
              <Button size="small" type="primary" onClick={() => onResolveConflict('overwriteAll')}>
                {t('Overwrite All')}
              </Button>
              <Button size="small" onClick={() => onResolveConflict('skipAll')}>
                {t('Skip All')}
              </Button>
            </Flex>
          </div>
        )}
      </Space>

      <List
        dataSource={files}
        itemLayout="horizontal"
        renderItem={file => (
          <List.Item
            style={{
              padding: '12px 8px',
              borderRadius: 8,
              transition: 'background-color 0.2s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--ant-color-fill-tertiary, #f0f0f0)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
          >
            <Flex justify="space-between" align="center" style={{ width: '100%' }}>
              <Flex align="center" gap={8} style={{ maxWidth: '60%', overflow: 'hidden' }}>
                <Typography.Text ellipsis={{ tooltip: file.relativePath }} style={{ maxWidth: '100%' }}>
                  {file.relativePath}
                </Typography.Text>
                {file.type === 'directory' ? (
                  <Tag color="blue">{t('Directory')}</Tag>
                ) : (
                  <Tag color="geekblue">{formatBytes(file.size)}</Tag>
                )}
              </Flex>
              <div style={{ minWidth: 180, textAlign: 'right', flexShrink: 0 }}>
                {renderStatus(file)}
              </div>
            </Flex>
          </List.Item>
        )}
      />
    </Modal>
  );
};

export default UploadModal;
