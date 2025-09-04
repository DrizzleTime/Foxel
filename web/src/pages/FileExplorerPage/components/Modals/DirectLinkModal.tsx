import { memo, useState, useEffect } from 'react';
import { Modal, Radio, message, Button, Typography, Input, Space } from 'antd';
import { CopyOutlined, FileMarkdownOutlined } from '@ant-design/icons';
import type { VfsEntry } from '../../../../api/client';
import { vfsApi } from '../../../../api/client';

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

  useEffect(() => {
    if (open && entry) {
      setLink('');
      generateLink();
    }
  }, [open, entry, expiresIn]);

  const generateLink = async () => {
    if (!entry) return;
    setLoading(true);
    try {
      const fullPath = (path === '/' ? '' : path) + '/' + entry.name;
      const res = await vfsApi.getTempLinkToken(fullPath, expiresIn);
      setLink(res.url);
    } catch (e: any) {
      message.error(e.message || '生成链接失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success('已复制到剪贴板');
  };

  const handleCopyMarkdown = () => {
    if (!entry || !link) return;
    const markdownText = generateMarkdownLink(entry.name, link);
    navigator.clipboard.writeText(markdownText);
    message.success('Markdown 格式已复制到剪贴板');
  };
  
  const handleExpiresChange = (e: any) => {
    setExpiresIn(e.target.value);
  };

  return (
    <Modal
      title="获取直链"
      open={open}
      onCancel={onCancel}
      footer={[
        <Button key="back" onClick={onCancel}>
          关闭
        </Button>,
      ]}
    >
      <Typography.Paragraph>
        为 <strong>{entry?.name}</strong> 生成一个直接访问链接。
      </Typography.Paragraph>
      <Radio.Group value={expiresIn} onChange={handleExpiresChange} style={{ marginBottom: 16 }}>
        <Radio.Button value={3600}>1 小时</Radio.Button>
        <Radio.Button value={86400}>1 天</Radio.Button>
        <Radio.Button value={604800}>7 天</Radio.Button>
        <Radio.Button value={0}>永久</Radio.Button>
      </Radio.Group>
      
      <div style={{ display: 'flex', gap: 8 }}>
        <Input readOnly value={link} disabled={loading} placeholder={loading ? "正在生成链接..." : "链接将显示在这里"} />
        <Space.Compact>
          <Button icon={<CopyOutlined />} onClick={() => handleCopy(link)} disabled={!link || loading}>
            复制
          </Button>
          <Button icon={<FileMarkdownOutlined />} onClick={handleCopyMarkdown} disabled={!link || loading}>
            复制 Markdown
          </Button>
        </Space.Compact>
      </div>
    </Modal>
  );
});