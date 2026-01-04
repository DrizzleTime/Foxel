/**
 * PDF 查看器主组件
 */
import React, { useState, useEffect } from 'react';
import { Spin, Result, Button } from 'antd';
import type { PluginContext } from './foxel-types';

export const PdfViewerApp: React.FC<PluginContext> = ({ filePath, host }) => {
  const { foxelApi } = window.__FOXEL_EXTERNALS__;
  
  const [url, setUrl] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string>();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(undefined);
    setUrl(undefined);

    const cleaned = filePath.replace(/^\/+/, '');
    foxelApi.vfs
      .getTempLinkToken(cleaned)
      .then(res => {
        if (cancelled) return;
        const publicUrl = foxelApi.vfs.getTempPublicUrl(res.token);
        setUrl(publicUrl + '#toolbar=1&navpanes=1');
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message || '获取临时链接失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [filePath, foxelApi]);

  if (loading) {
    return (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Spin tip="正在加载 PDF..." />
      </div>
    );
  }

  if (err) {
    return (
      <Result
        status="error"
        title="无法加载 PDF"
        subTitle={err}
        extra={
          <Button type="primary" onClick={host.close}>
            关闭
          </Button>
        }
      />
    );
  }

  if (!url) {
    return (
      <Result
        status="warning"
        title="无可用链接"
        subTitle="未能生成 PDF 的临时访问链接"
        extra={
          <Button type="primary" onClick={host.close}>
            关闭
          </Button>
        }
      />
    );
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        background: 'var(--ant-color-bg-container, #fff)',
      }}
    >
      <iframe
        src={url}
        width="100%"
        height="100%"
        title="PDF Viewer"
        style={{ border: 'none' }}
      />
    </div>
  );
};

