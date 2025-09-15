import { memo, useEffect, useMemo, useState } from 'react';
import { Modal, Button, List, Typography, Space, Input, message } from 'antd';
import { FolderOutlined, ArrowUpOutlined } from '@ant-design/icons';
import { useI18n } from '../i18n';
import { vfsApi, type VfsEntry } from '../api/client';
import { getFileIcon } from '../pages/FileExplorerPage/components/FileIcons';

export type PathSelectorMode = 'directory' | 'file' | 'any';

interface PathSelectorModalProps {
  open: boolean;
  mode?: PathSelectorMode;
  initialPath?: string;
  onOk: (path: string) => void;
  onCancel: () => void;
}

function normalizePath(p: string): string {
  if (!p) return '/';
  const s = ('/' + p).replace(/\/+/, '/');
  return s.replace(/\\/g, '/').replace(/\/+$/, '') || '/';
}

function joinPath(dir: string, name: string): string {
  const base = normalizePath(dir);
  if (base === '/') return `/${name}`;
  return `${base}/${name}`.replace(/\/+/, '/');
}

const PathSelectorModal = memo(function PathSelectorModal({ open, mode = 'directory', initialPath = '/', onOk, onCancel }: PathSelectorModalProps) {
  const { t } = useI18n();
  const [path, setPath] = useState<string>(normalizePath(initialPath));
  const [entries, setEntries] = useState<VfsEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null); // selected file name within current folder

  const title = useMemo(() => {
    if (mode === 'file') return t('Select File');
    if (mode === 'any') return t('Select Path');
    return t('Select Folder');
  }, [mode, t]);

  const load = async (p: string) => {
    setLoading(true);
    try {
      const listing = await vfsApi.list(p, 1, 500, 'name', 'asc');
      setEntries(listing.entries);
      setPath(listing.path || p);
      setSelected(null);
    } catch (e: any) {
      message.error(e.message || t('Load failed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      load(normalizePath(initialPath));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialPath]);

  const canOk = useMemo(() => {
    if (mode === 'file') return !!selected;
    return true;
  }, [mode, selected]);

  const handleOk = () => {
    if (mode === 'directory') {
      onOk(normalizePath(path));
      return;
    }
    if (mode === 'file') {
      if (!selected) {
        message.warning(t('Please select a file'));
        return;
      }
      onOk(joinPath(path, selected));
      return;
    }
    // any
    if (selected) onOk(joinPath(path, selected));
    else onOk(normalizePath(path));
  };

  const goUp = () => {
    const cur = normalizePath(path);
    if (cur === '/') return;
    const parent = cur.replace(/\/+$/, '').split('/').slice(0, -1).join('/') || '/';
    load(parent);
  };

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      okButtonProps={{ disabled: !canOk }}
      width={720}
    >
      <Space style={{ width: '100%', marginBottom: 12 }} align="center">
        <Typography.Text type="secondary">{t('Current')}</Typography.Text>
        <Input value={path} readOnly />
        <Button onClick={goUp} icon={<ArrowUpOutlined />} disabled={path === '/'}>{t('Up')}</Button>
        {mode !== 'file' && (
          <Button type="primary" onClick={() => onOk(normalizePath(path))}>{t('Select Current Folder')}</Button>
        )}
      </Space>

      <List
        bordered
        loading={loading}
        dataSource={entries}
        style={{ maxHeight: 420, overflow: 'auto' }}
        renderItem={(item) => {
          const isSelected = selected === item.name && !item.is_dir;
          return (
            <List.Item
              onClick={() => {
                if (item.is_dir) {
                  load(joinPath(path, item.name));
                } else {
                  setSelected((prev) => (prev === item.name ? null : item.name));
                }
              }}
              style={{ cursor: 'pointer', background: isSelected ? 'rgba(22,119,255,0.08)' : undefined }}
            >
              <Space>
                {item.is_dir ? <FolderOutlined /> : getFileIcon(item.name)}
                <Typography.Text strong={item.is_dir}>{item.name}</Typography.Text>
              </Space>
            </List.Item>
          );
        }}
      />
    </Modal>
  );
});

export default PathSelectorModal;

