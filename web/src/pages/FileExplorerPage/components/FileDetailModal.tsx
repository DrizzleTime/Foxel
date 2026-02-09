import React from 'react';
import { Modal, Typography, Spin, theme, Card, Descriptions, Divider, Badge, Space, message, Collapse, Tag } from 'antd';
import { FileOutlined, FolderOutlined, CameraOutlined, InfoCircleOutlined, DatabaseOutlined } from '@ant-design/icons';
import { useI18n } from '../../../i18n';
import type { VfsEntry } from '../../../api/client';

interface Props {
  entry: VfsEntry | null;
  loading: boolean;
  data: any;
  onClose: () => void;
}

function getExifFieldMap(t: (k: string)=>string): Record<string, { label: string; format?: (v: any) => string }> {
  return {
    '271': { label: t('Camera Make') },
    '272': { label: t('Camera Model') },
    '306': { label: t('Capture Time') },
    '282': { label: t('X Resolution'), format: v => `${v} dpi` },
    '283': { label: t('Y Resolution'), format: v => `${v} dpi` },
    '33434': { label: t('Exposure Time'), format: v => `${v} s` },
    '33437': { label: t('Aperture'), format: v => `f/${v}` },
    '34855': { label: 'ISO' },
    '37377': { label: t('Focal Length'), format: v => `${v} mm` },
    '40962': { label: t('Width'), format: v => `${v} px` },
    '40963': { label: t('Height'), format: v => `${v} px` },
  };
}

function renderExif(exif: Record<string, any>, t: (k: string)=>string) {
  const exifFieldMap = getExifFieldMap(t);
  const items = Object.entries(exifFieldMap)
    .filter(([key]) => exif[key] !== undefined)
    .map(([key, { label, format }]) => ({
      key,
      label,
      value: format ? format(exif[key]) : exif[key]
    }));

  if (items.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 24, color: 'var(--ant-color-text-tertiary, #999)' }}>
        <InfoCircleOutlined style={{ fontSize: 20, marginBottom: 8 }} />
        <div>{t('No common EXIF info')}</div>
      </div>
    );
  }

  return (
    <Descriptions
      size="small"
      column={1}
      bordered
      items={items.map(item => ({
        key: item.key,
        label: <span style={{ fontWeight: 500, color: 'var(--ant-color-text-secondary, #595959)' }}>{item.label}</span>,
        children: <span style={{ color: 'var(--ant-color-text, #262626)' }}>{item.value}</span>
      }))}
      contentStyle={{ padding: '8px 12px' }}
      labelStyle={{ padding: '8px 12px', backgroundColor: 'var(--ant-color-fill-tertiary, #fafafa)', width: '30%' }}
    />
  );
}

function formatFileSize(size: number | string, t: (k: string)=>string): string {
  if (typeof size !== 'number') return String(size);
  
  const units = [t('Bytes'), 'KB', 'MB', 'GB'];
  let index = 0;
  let fileSize = size;
  
  while (fileSize >= 1024 && index < units.length - 1) {
    fileSize /= 1024;
    index++;
  }
  
  return `${fileSize.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export const FileDetailModal: React.FC<Props> = ({ entry, loading, data, onClose }) => {
  const { token } = theme.useToken();
  const { t } = useI18n();
  const vectorIndex = data?.vector_index;
  const vectorEntries = Array.isArray(vectorIndex?.entries) ? vectorIndex.entries : [];
  const primaryIndexEntries = vectorEntries.slice(0, 3);
  const remainingIndexEntries = vectorEntries.slice(3);

  const renderIndexEntry = (entry: any, idx: number, total: number) => {
    const key = entry?.chunk_id ?? entry?.vector_id ?? idx;
    const hasOffsets = entry?.start_offset !== undefined || entry?.end_offset !== undefined;
    const previewText = entry?.preview;
    const previewTruncated = Boolean(entry?.preview_truncated && previewText);

    return (
      <div
        key={String(key)}
        style={{
          padding: '12px 0',
          borderBottom: idx === total - 1 ? 'none' : `1px solid ${token.colorSplit}`,
        }}
      >
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Space size={[4, 4]} wrap>
            {entry?.chunk_id && (
              <Tag color="blue">{t('Chunk ID')}: {entry.chunk_id}</Tag>
            )}
            {entry?.type && (
              <Tag>{entry.type}</Tag>
            )}
            {entry?.mime && (
              <Tag color="geekblue">{entry.mime}</Tag>
            )}
            {entry?.name && !previewText && (
              <Tag color="purple">{entry.name}</Tag>
            )}
          </Space>
          {hasOffsets && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('Offset Range')}: {entry?.start_offset ?? '-'} ~ {entry?.end_offset ?? '-'}
            </Typography.Text>
          )}
          {entry?.vector_id && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('Vector ID')}: {entry.vector_id}
            </Typography.Text>
          )}
          {previewText && (
            <Typography.Paragraph
              style={{ marginBottom: 0 }}
              ellipsis={{ rows: 3, expandable: previewTruncated }}
            >
              {previewText}
            </Typography.Paragraph>
          )}
        </Space>
      </div>
    );
  };

  return (
    <Modal
      title={
        <Space>
          <InfoCircleOutlined style={{ color: token.colorPrimary }} />
          <span>{t('File Properties')}</span>
          {entry && (
            <Typography.Text type="secondary" style={{ fontSize: 14 }}>
              - {entry.name}
            </Typography.Text>
          )}
        </Space>
      }
      open={!!entry}
      onCancel={onClose}
      footer={null}
      width={800}
      styles={{
        body: { padding: '20px 0px' }
      }}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" />
          <div style={{ marginTop: 16, color: token.colorTextSecondary }}>{t('Loading file info...')}</div>
        </div>
      ) : data ? (
        data.error ? (
          <div style={{ textAlign: 'center', padding: 32 }}>
            <Typography.Text type="danger" style={{ fontSize: 16 }}>
              {data.error}
            </Typography.Text>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
            {/* 左侧：基本信息 */}
            <div style={{ flex: 1 }}>
              <Card 
                size="small"
                title={
                  <Space>
                    {data.is_dir ? <FolderOutlined /> : <FileOutlined />}
                    {t('Basic Info')}
                  </Space>
                }
                style={{ borderRadius: 8, height: 'fit-content' }}
              >
                <Descriptions
                  column={1}
                  size="small"
                  items={[
                    {
                      key: 'name',
                      label: t('Name'),
                      children: <Typography.Text strong>{data.name}</Typography.Text>
                    },
                    {
                      key: 'type',
                      label: t('Type'),
                      children: (
                        <Badge 
                          status={data.is_dir ? 'processing' : 'default'} 
                          text={data.type || (data.is_dir ? t('Folder') : t('File'))}
                        />
                      )
                    },
                    {
                      key: 'size',
                      label: t('Size'),
                      children: formatFileSize(data.size, t)
                    },
                    {
                      key: 'mtime',
                      label: t('Modified Time'),
                      children: data.mtime ? (
                        typeof data.mtime === 'number' 
                          ? new Date(data.mtime * 1000).toLocaleString()
                          : data.mtime
                      ) : '-'
                    },
                    {
                      key: 'path',
                      label: t('Path'),
                      children: (
                        <Typography.Text style={{ display: 'block', marginTop: 4 }}>
                          <a
                            href="#"
                            onClick={(e) => {
                              e.preventDefault();
                              try {
                                if (navigator.clipboard) {
                                  navigator.clipboard.writeText(data.path).then(() => {
                                    message.success(t('Path copied to clipboard'));
                                  }).catch(() => {
                                    message.error(t('Copy failed'));
                                  });
                                } else {
                                  const textarea = document.createElement('textarea');
                                  textarea.value = data.path;
                                  document.body.appendChild(textarea);
                                  textarea.select();
                                  const ok = document.execCommand('copy');
                                  document.body.removeChild(textarea);
                                  message[ok ? 'success' : 'error'](ok ? t('Path copied to clipboard') : t('Copy failed'));
                                }
                              } catch {
                                message.error(t('Copy failed'));
                              }
                            }}
                            style={{
                              fontSize: 12,
                              wordBreak: 'break-all',
                              backgroundColor: token.colorFillAlter,
                              padding: '4px 8px',
                              borderRadius: 4,
                              display: 'inline-block'
                            }}
                          >
                            {data.path}
                          </a>
                        </Typography.Text>
                      )
                    }
                  ]}
                  contentStyle={{ 
                    fontSize: 14,
                    color: token.colorText
                  }}
                  labelStyle={{ 
                    fontWeight: 500,
                    color: token.colorTextSecondary,
                    width: '30%'
                  }}
                />
                {data.mode !== undefined && (
                  <>
                    <Divider style={{ margin: '12px 0' }} />
                    <div>
                      <span style={{ fontWeight: 500, color: token.colorTextSecondary }}>{t('Permissions')}：</span>
                      <Typography.Text code>{data.mode.toString(8)}</Typography.Text>
                    </div>
                  </>
                )}
              </Card>

              {!data.is_dir && vectorIndex && (
                <Card
                  size="small"
                  style={{ borderRadius: 8, marginTop: 16 }}
                  title={
                    <Space>
                      <DatabaseOutlined />
                      {t('Index Info')}
                    </Space>
                  }
                >
                  <Descriptions
                    column={1}
                    size="small"
                    items={[
                      {
                        key: 'total',
                        label: t('Indexed Items'),
                        children: vectorIndex.total ?? 0,
                      },
                      {
                        key: 'types',
                        label: t('Indexed Types'),
                        children: Object.keys(vectorIndex.by_type || {}).length > 0 ? (
                          <Space size={[4, 4]} wrap>
                            {Object.entries(vectorIndex.by_type || {}).map(([type, count]) => (
                              <Tag key={type}>{type} ({count as number})</Tag>
                            ))}
                          </Space>
                        ) : (
                          <Typography.Text type="secondary">{t('No index data')}</Typography.Text>
                        ),
                      },
                    ]}
                    contentStyle={{ fontSize: 14 }}
                    labelStyle={{ fontWeight: 500, color: token.colorTextSecondary, width: '30%' }}
                  />

                  {vectorIndex.total ? (
                    <div style={{ marginTop: 12 }}>
                      <Typography.Text strong style={{ marginBottom: 8, display: 'block' }}>
                        {t('Indexed Chunks')}
                      </Typography.Text>
                      <div style={{ maxHeight: '40vh', overflowY: 'auto', paddingRight: 8 }}>
                        {primaryIndexEntries.map((entry: any, idx: number) => renderIndexEntry(entry, idx, primaryIndexEntries.length))}
                        {remainingIndexEntries.length > 0 && (
                          <Collapse
                            bordered={false}
                            size="small"
                            items={[{
                              key: 'more',
                              label: t('More Indexed Chunks'),
                              children: (
                                <div>
                                  {remainingIndexEntries.map((entry: any, idx: number) => renderIndexEntry(entry, idx, remainingIndexEntries.length))}
                                </div>
                              ),
                            }]}
                            style={{ background: 'transparent' }}
                          />
                        )}
                      </div>
                      {vectorIndex.has_more && (
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {t('Showing first {count} entries', { count: vectorEntries.length })}
                        </Typography.Text>
                      )}
                    </div>
                  ) : (
                    <div style={{ marginTop: 12 }}>
                      <Typography.Text type="secondary">{t('No index data')}</Typography.Text>
                    </div>
                  )}
                </Card>
              )}
            </div>

            {/* 右侧：EXIF 信息 */}
            {data.exif && (
              <div style={{ flex: 1 }}>
                <Card 
                  size="small"
                  title={
                    <Space>
                      <CameraOutlined />
                      {t('EXIF Info')}
                    </Space>
                  }
                  style={{ borderRadius: 8, height: 'fit-content' }}
                >
                  {renderExif(data.exif, t)}
                </Card>
              </div>
            )}
          </div>
        )
      ) : null}
    </Modal>
  );
};

export default FileDetailModal;
