import { Modal, Input } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { InputRef } from 'antd/es/input/Input';
import { useI18n } from '../i18n';
import { useLocation, useNavigate } from 'react-router';

interface SearchDialogProps {
  open: boolean;
  onClose: () => void;
}

const SearchDialog: React.FC<SearchDialogProps> = ({ open, onClose }) => {
  const [search, setSearch] = useState('');
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const isOnFiles = location.pathname.startsWith('/files');
  const inputRef = useRef<InputRef | null>(null);

  useEffect(() => {
    if (!open) return;
    if (!isOnFiles) {
      setSearch('');
      return;
    }
    const params = new URLSearchParams(location.search);
    setSearch(params.get('q') || '');
  }, [open, isOnFiles, location.search]);

  const handleClose = useCallback(() => {
    setSearch('');
    onClose();
  }, [onClose]);

  return (
    <Modal
      open={open}
      onCancel={handleClose}
      afterOpenChange={(nextOpen) => {
        if (!nextOpen) return;
        window.setTimeout(() => inputRef.current?.focus(), 0);
      }}
      footer={null}
      width={720}
      centered
      title={<span className="fx-sr-only">{t('Search files / tags / types')}</span>}
      closable={false}
      destroyOnHidden
      styles={{
        header: { height: 0, margin: 0, padding: 0 },
        container: {
          background: 'transparent',
          boxShadow: 'none',
          padding: 0,
        },
        body: {
          padding: 0,
          background: 'transparent',
        },
      }}
    >
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder={t('Search files / tags / types')}
          aria-label={t('Search files / tags / types')}
          value={search}
          onChange={e => setSearch(e.target.value)}
          size="large"
          style={{ width: '100%' }}
          styles={{
            root: {
              borderRadius: 20,
            },
          }}
          ref={inputRef}
          onPressEnter={() => {
            const trimmed = search.trim();
            if (!trimmed) {
              if (isOnFiles) {
                navigate(location.pathname);
              }
              handleClose();
              return;
            }
            const params = new URLSearchParams();
            params.set('q', trimmed);
            const targetPath = isOnFiles ? location.pathname : '/files';
            navigate(`${targetPath}?${params.toString()}`);
            handleClose();
          }}
        />
    </Modal>
  );
};

export default SearchDialog;
