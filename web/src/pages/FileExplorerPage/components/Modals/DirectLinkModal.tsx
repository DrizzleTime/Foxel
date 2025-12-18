import { memo, useState, useEffect, useCallback } from 'react';
import { Modal, Radio, message, Button, Typography, Input, Space } from 'antd';
import { CopyOutlined, FileMarkdownOutlined } from '@ant-design/icons';
import type { VfsEntry } from '../../../../api/client';
import { vfsApi } from '../../../../api/client';
import { useI18n } from '../../../../i18n';

interface DirectLinkModalProps {
  entry: VfsEntry | null;
  path: string;
  open: boolean;
  onCancel: () => void;
}

// Helper function to check if a file is an image
const isImageFile = (fileName: string): boolean => {
  const ext = fileName.split('.').pop()?.toLowerCase() || '';
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'tiff'].includes(ext);
};

// Helper function to generate Markdown formatted link
const generateMarkdownLink = (fileName: string, url: string): string => {
  if (isImageFile(fileName)) {
    return `![${fileName}](${url})`;
  } else {
    return `[${fileName}](${url})`;
  }
};

export const DirectLinkModal = memo(function DirectLinkModal({ entry, path, open, onCancel }: DirectLinkModalProps) {
  const [loading, setLoading] = useState(false);
  const [expiresIn, setExpiresIn] = useState(3600);
  const [link, setLink] = useState('');
  const { t } = useI18n();

  const generateLink = useCallback(async () => {
    if (!entry) return;
    setLoading(true);
    try {
      const fullPath = (path === '/' ? '' : path) + '/' + entry.name;
      const res = await vfsApi.getTempLinkToken(fullPath, expiresIn);
      let url = res.url;
      if (url && !url.startsWith('http://') && !url.startsWith('https://')) {
        const origin = window.location.origin;
        url = url.startsWith('/') ? origin + url : origin + '/' + url;
      }
      setLink(url);
    } catch (e: any) {
      message.error(e.message || t('Failed to generate link'));
    } finally {
      setLoading(false);
    }
  }, [entry, expiresIn, path, t]);

  useEffect(() => {
    if (open && entry) {
      setLink('');
      void generateLink();
    }
  }, [open, entry, generateLink]);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success(t('Copied to clipboard'));
  };

  const handleCopyMarkdown = () => {
    if (!entry || !link) return;
    const markdownText = generateMarkdownLink(entry.name, link);
    navigator.clipboard.writeText(markdownText);
    message.success(t('Markdown copied to clipboard'));
  };

  const handleExpiresChange = (e: any) => {
    setExpiresIn(e.target.value);
  };

  return (
    <Modal
      title={t('Get Direct Link')}
      open={open}
      onCancel={onCancel}
      footer={[
        <Button key="back" onClick={onCancel}>
          {t('Close')}
        </Button>,
      ]}
    >
      <Typography.Paragraph>
        {t('Generate a direct link for {name}', { name: entry?.name || '' })}
      </Typography.Paragraph>
      <Radio.Group value={expiresIn} onChange={handleExpiresChange} style={{ marginBottom: 16 }}>
        <Radio.Button value={3600}>{t('1 hour')}</Radio.Button>
        <Radio.Button value={86400}>{t('1 day')}</Radio.Button>
        <Radio.Button value={604800}>{t('7 days')}</Radio.Button>
        <Radio.Button value={0}>{t('Forever')}</Radio.Button>
      </Radio.Group>

      <div style={{ display: 'flex', gap: 8 }}>
        <Input readOnly value={link} disabled={loading} placeholder={loading ? t('Generating link...') : t('Link will appear here')} />
        <Space.Compact>
          <Button icon={<CopyOutlined />} onClick={() => handleCopy(link)} disabled={!link || loading}>
            {t('Copy')}
          </Button>
          <Button icon={<FileMarkdownOutlined />} onClick={handleCopyMarkdown} disabled={!link || loading}>
            {t('Copy Markdown')}
          </Button>
        </Space.Compact>
      </div>
    </Modal>
  );
});
