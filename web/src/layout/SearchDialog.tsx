import { Modal, Input, Flex, Segmented } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { InputRef } from 'antd/es/input/Input';
import { useI18n } from '../i18n';
import { useLocation, useNavigate } from 'react-router';

interface SearchDialogProps {
  open: boolean;
  onClose: () => void;
}

type SearchMode = 'vector' | 'filename';

const SearchDialog: React.FC<SearchDialogProps> = ({ open, onClose }) => {
  const [search, setSearch] = useState('');
  const [searchMode, setSearchMode] = useState<SearchMode>('vector');
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const isOnFiles = location.pathname.startsWith('/files');
  const inputRef = useRef<InputRef | null>(null);

  useEffect(() => {
    if (!open) return;
    if (!isOnFiles) {
      setSearch('');
      setSearchMode('vector');
      return;
    }
    const params = new URLSearchParams(location.search);
    setSearch(params.get('q') || '');
    setSearchMode(params.get('mode') === 'filename' ? 'filename' : 'vector');
  }, [open, isOnFiles, location.search]);

  const handleClose = useCallback(() => {
    setSearch('');
    setSearchMode('vector');
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
      title={null}
      closable={false}
      destroyOnHidden
      styles={{
        body: {
          padding: '12px 16px 16px',
          maxHeight: '70vh',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        },
      }}
    >
      <Flex vertical style={{ gap: 12, flex: 1, minHeight: 0 }}>
        <Flex align="center" style={{ width: '100%', gap: 12, flexWrap: 'wrap' }}>
          <Segmented
            options={[
              { label: t('Smart Search'), value: 'vector' },
              { label: t('Name Search'), value: 'filename' },
            ]}
            value={searchMode}
            onChange={(value) => setSearchMode(value as SearchMode)}
            style={{
              minWidth: 160,
              height: 40,
              borderRadius: 20,
              display: 'flex',
              alignItems: 'center',
            }}
            size="large"
          />
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder={t('Search files / tags / types')}
            value={search}
            onChange={e => setSearch(e.target.value)}
            size="large"
            style={{ flex: 1, minWidth: 240 }}
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
              params.set('mode', searchMode);
              if (searchMode === 'filename') {
                params.set('page', '1');
              }
              const targetPath = isOnFiles ? location.pathname : '/files';
              navigate(`${targetPath}?${params.toString()}`);
              handleClose();
            }}
          />
        </Flex>
      </Flex>
    </Modal>
  );
};

export default SearchDialog;
