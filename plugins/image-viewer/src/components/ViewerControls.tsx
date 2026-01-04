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
      {btn('上一张', LeftOutlined, onPrev, disableSwitch)}
      {btn('缩小', ZoomOutOutlined, onZoomOut)}
      {btn('放大', ZoomInOutlined, onZoomIn)}
      {btn('旋转 90°', RotateRightOutlined, onRotate)}
      {btn('重置', ReloadOutlined, onReset)}
      {btn('适应窗口', CompressOutlined, onFit)}
      {btn('下一张', RightOutlined, onNext, disableSwitch)}
    </div>
  );
};

