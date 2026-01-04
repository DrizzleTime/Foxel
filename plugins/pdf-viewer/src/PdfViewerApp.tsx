/**
 * PDF 查看器主组件
 */
import React, { useState, useEffect } from 'react';
import { Spin, Result, Button } from 'antd';
import type { PluginContext } from './foxel-types';
import { useI18n } from './i18n';

export const PdfViewerApp: React.FC<PluginContext> = ({ filePath, host }) => {
  const { foxelApi } = window.__FOXEL_EXTERNALS__;
  const { t } = useI18n();
  
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
        if (!cancelled) setErr(e.message || 'Failed to get temporary link');
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
        <Spin tip={t('Loading PDF...')} />
      </div>
    );
  }

  if (err) {
    return (
      <Result
        status="error"
        title={t('Unable to load PDF')}
        subTitle={t(err)}
        extra={
          <Button type="primary" onClick={host.close}>
            {t('Close')}
          </Button>
        }
      />
    );
  }

  if (!url) {
    return (
      <Result
        status="warning"
        title={t('No available link')}
        subTitle={t('Failed to generate a temporary access link for the PDF.')}
        extra={
          <Button type="primary" onClick={host.close}>
            {t('Close')}
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
