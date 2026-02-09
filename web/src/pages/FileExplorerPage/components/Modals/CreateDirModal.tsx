import React, { useState, useEffect } from 'react';
import { Modal, Input } from 'antd';
import { useI18n } from '../../../../i18n';

interface CreateDirModalProps {
  open: boolean;
  onOk: (name: string) => void;
  onCancel: () => void;
}

export const CreateDirModal: React.FC<CreateDirModalProps> = ({ open, onOk, onCancel }) => {
  const [name, setName] = useState('');
  const { t } = useI18n();

  useEffect(() => {
    if (open) {
      setName('');
    }
  }, [open]);

  const handleOk = () => {
    onOk(name);
  };

  return (
    <Modal
      title={t('New Folder')}
      open={open}
      onOk={handleOk}
      onCancel={onCancel}
      okButtonProps={{ disabled: !name.trim() }}
      destroyOnHidden
    >
      <Input
        placeholder={t('Folder Name')}
        value={name}
        onChange={e => setName(e.target.value)}
        onPressEnter={handleOk}
        autoFocus
      />
    </Modal>
  );
};
