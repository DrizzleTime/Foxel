import React, { useEffect, useState } from 'react';
import { vfsApi } from '../../api/client';
import type { AppComponentProps } from '../types';
import { Spin, Result, Button } from 'antd';
import { useSystemStatus } from '../../contexts/SystemContext';

export const OfficeViewerApp: React.FC<AppComponentProps> = ({ filePath, onRequestClose }) => {
  const systemStatus = useSystemStatus();
  const fileDomain = systemStatus?.file_domain;
  const [url, setUrl] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string>();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(undefined);
    setUrl(undefined);

    vfsApi.getTempLinkToken(filePath.replace(/^\/+/, ''))
      .then(res => {
        if (cancelled) return;
        const baseUrl = fileDomain || window.location.origin;
        const fullUrl = new URL(res.url, baseUrl).href;
        const officeUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(fullUrl)}`;
        setUrl(officeUrl);
      })
      .catch(e => {
        if (!cancelled) {
          setErr(e.message || '加载文档链接失败');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [filePath, fileDomain]);

  if (loading) {
    return (
      <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin tip="正在准备文档..." />
      </div>
    );
  }

  if (err) {
    return (
      <Result
        status="error"
        title="无法加载文档"
        subTitle={err}
        extra={<Button type="primary" onClick={onRequestClose}>关闭</Button>}
      />
    );
  }

  return (
    <div style={{ width: '100%', height: '100%', background: 'var(--ant-color-bg-container, #fff)' }}>
      {url ? (
        <iframe
          src={url}
          width="100%"
          height="100%"
          frameBorder="0"
          title="Office Document Viewer"
        />
      ) : (
        <Result
          status="warning"
          title="文档链接无效"
          subTitle="未能成功生成文档的在线查看链接。"
          extra={<Button type="primary" onClick={onRequestClose}>关闭</Button>}
        />
      )}
    </div>
  );
};
