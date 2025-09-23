import React from 'react';
import { Spin, Typography, Tooltip, Button } from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import type { VfsEntry } from '../../../api/client';
import { viewerStyles } from '../styles';

interface ImageCanvasProps {
  containerRef: React.RefObject<HTMLDivElement | null>;
  imageRef: React.RefObject<HTMLImageElement | null>;
  viewerStyle: React.CSSProperties;
  controls: React.ReactNode;
  scaleLabel: string;
  imageStyle: React.CSSProperties;
  loading: boolean;
  error?: string;
  imageUrl?: string;
  activeEntry: VfsEntry;
  onRequestClose: () => void;
  onImageLoad: () => void;
  onWheel: React.WheelEventHandler<HTMLDivElement>;
  onMouseDown: React.MouseEventHandler<HTMLDivElement>;
  onMouseMove: React.MouseEventHandler<HTMLDivElement>;
  onMouseLeave: React.MouseEventHandler<HTMLDivElement>;
  onMouseUp: React.MouseEventHandler<HTMLDivElement>;
  onDoubleClick: React.MouseEventHandler<HTMLDivElement>;
  onTouchStart: React.TouchEventHandler<HTMLDivElement>;
  onTouchMove: React.TouchEventHandler<HTMLDivElement>;
  onTouchEnd: React.TouchEventHandler<HTMLDivElement>;
}

export const ImageCanvas: React.FC<ImageCanvasProps> = ({
  containerRef,
  imageRef,
  viewerStyle,
  controls,
  scaleLabel,
  imageStyle,
  loading,
  error,
  imageUrl,
  activeEntry,
  onRequestClose,
  onImageLoad,
  onWheel,
  onMouseDown,
  onMouseMove,
  onMouseLeave,
  onMouseUp,
  onDoubleClick,
  onTouchStart,
  onTouchMove,
  onTouchEnd,
}) => (
  <div
    ref={containerRef}
    style={viewerStyle}
    onWheel={onWheel}
    onMouseDown={onMouseDown}
    onMouseMove={onMouseMove}
    onMouseLeave={onMouseLeave}
    onMouseUp={onMouseUp}
    onDoubleClick={onDoubleClick}
    onTouchStart={onTouchStart}
    onTouchMove={onTouchMove}
    onTouchEnd={onTouchEnd}
  >
    <div style={viewerStyles.viewerCloseWrap}>
      <Tooltip title="关闭">
        <Button
          type="text"
          icon={<CloseOutlined />}
          onClick={onRequestClose}
          style={viewerStyles.viewerClose}
        />
      </Tooltip>
    </div>
    {loading ? (
      <Spin tip="加载中" />
    ) : error ? (
      <Typography.Text type="danger">{error}</Typography.Text>
    ) : imageUrl ? (
      <img
        ref={imageRef}
        src={imageUrl}
        alt={activeEntry.name}
        onLoad={onImageLoad}
        draggable={false}
        crossOrigin="anonymous"
        style={imageStyle}
      />
    ) : (
      <Typography.Text>无可用内容</Typography.Text>
    )}

    <div style={viewerStyles.scaleBadge}>{scaleLabel}</div>

    {controls}
  </div>
);
