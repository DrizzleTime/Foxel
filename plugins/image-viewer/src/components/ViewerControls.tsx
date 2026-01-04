/**
 * 查看器控制按钮组件
 */
import React, { CSSProperties } from 'react';
import { Button, Tooltip } from 'antd';
import {
  LeftOutlined,
  RightOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  RotateRightOutlined,
  ReloadOutlined,
  CompressOutlined,
} from '@ant-design/icons';
import { useI18n } from '../i18n';

interface ViewerControlsProps {
  style?: CSSProperties;
  onPrev: () => void;
  onNext: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onRotate: () => void;
  onReset: () => void;
  onFit: () => void;
  disableSwitch: boolean;
}

export const ViewerControls: React.FC<ViewerControlsProps> = ({
  style,
  onPrev,
  onNext,
  onZoomIn,
  onZoomOut,
  onRotate,
  onReset,
  onFit,
  disableSwitch,
}) => {
  const { t } = useI18n();
  const btn = (
    title: string,
    icon: React.ComponentType,
    onClick: () => void,
    disabled = false
  ) => (
    <Tooltip title={title} key={title}>
      <Button
        shape="circle"
        type="text"
        icon={React.createElement(icon)}
        onClick={onClick}
        disabled={disabled}
        style={{ color: '#fff' }}
      />
    </Tooltip>
  );

  return (
    <div style={style}>
      {btn(t('Previous'), LeftOutlined, onPrev, disableSwitch)}
      {btn(t('Zoom out'), ZoomOutOutlined, onZoomOut)}
      {btn(t('Zoom in'), ZoomInOutlined, onZoomIn)}
      {btn(t('Rotate 90°'), RotateRightOutlined, onRotate)}
      {btn(t('Reset'), ReloadOutlined, onReset)}
      {btn(t('Fit to screen'), CompressOutlined, onFit)}
      {btn(t('Next'), RightOutlined, onNext, disableSwitch)}
    </div>
  );
};
