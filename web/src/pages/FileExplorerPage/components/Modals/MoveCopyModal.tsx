import { useEffect, useMemo, useState } from 'react';
import { Button, Modal, Input, message, Space } from 'antd';
import { useI18n } from '../../../../i18n';
import type { VfsEntry } from '../../../../api/client';
import PathSelectorModal from '../../../../components/PathSelectorModal';

interface MoveCopyModalProps {
  mode: 'move' | 'copy';
  entries: VfsEntry[];
  open: boolean;
  defaultPath: string;
  onOk: (destination: string) => Promise<void> | void;
  onCancel: () => void;
}

export function MoveCopyModal({ mode, entries, open, defaultPath, onOk, onCancel }: MoveCopyModalProps) {
  const { t } = useI18n();
  const [value, setValue] = useState(defaultPath);
  const [loading, setLoading] = useState(false);
  const [selectorOpen, setSelectorOpen] = useState(false);

  const entryName = useMemo(() => entries.length === 1 ? entries[0]?.name ?? '' : '', [entries]);

  useEffect(() => {
    if (open) {
      setValue(defaultPath);
    } else {
      setValue('');
    }
    setLoading(false);
    setSelectorOpen(false);
  }, [open, defaultPath]);

  const handleOk = async () => {
    const trimmed = value.trim();
    if (!trimmed) {
      message.warning(t('Please input destination path'));
      return;
    }
    setLoading(true);
    try {
      await onOk(trimmed);
      onCancel();
    } catch (e) {
      // 上层已处理提示，这里只需保持对话框
    } finally {
      setLoading(false);
    }
  };

  const title = mode === 'move' ? t('Move to') : t('Copy to');
  const okText = mode === 'move' ? t('Move') : t('Copy');

  const normalizeSelectedPath = (dirPath: string) => {
    const collapse = (p: string) => p.replace(/\/+/g, '/');
    const ensureLeading = (p: string) => (p.startsWith('/') ? p : `/${p}`);
    const normalizeDir = (() => {
      if (!dirPath || dirPath === '/') return '/';
      const replaced = dirPath.replace(/\\/g, '/');
      const trimmed = replaced.endsWith('/') ? replaced.replace(/\/+$/, '') : replaced;
      return ensureLeading(collapse(trimmed));
    })();

    if (!entryName) {
      return normalizeDir || '/';
    }

    const base = normalizeDir === '/' ? '' : normalizeDir;
    const combined = `${base}/${entryName}`;
    return ensureLeading(collapse(combined));
  };

  const handleBrowse = (selectedPath: string) => {
    const finalPath = normalizeSelectedPath(selectedPath);
    setValue(finalPath);
    setSelectorOpen(false);
  };

  const selectorInitialPath = useMemo(() => {
    if (!value) return '/';
    const normalized = value.replace(/\\/g, '/');
    if (!normalized || normalized === '/') return '/';
    const trimmed = normalized.endsWith('/') ? normalized.replace(/\/+$/, '') : normalized;
    const parts = trimmed.split('/');
    if (parts.length <= 1) return '/';
    parts.pop();
    const parent = parts.join('/') || '/';
    return parent.startsWith('/') ? parent : `/${parent}`;
  }, [value]);

  return (
    <Modal
      title={title}
      open={open && entries.length > 0}
      onOk={handleOk}
      onCancel={onCancel}
      confirmLoading={loading}
      okText={okText}
      destroyOnClose
    >
      <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
        <Input
          autoFocus
          value={value}
          placeholder={t('Destination path')}
          onChange={(e) => setValue(e.target.value)}
          onPressEnter={handleOk}
        />
        <Button onClick={() => setSelectorOpen(true)}>{t('Select destination')}</Button>
      </Space.Compact>
      <PathSelectorModal
        open={selectorOpen}
        mode="directory"
        initialPath={selectorInitialPath}
        onOk={handleBrowse}
        onCancel={() => setSelectorOpen(false)}
      />
    </Modal>
  );
}
