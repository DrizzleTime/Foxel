/**
 * Office 文档查看器主组件
 */
import React, { useState, useEffect } from 'react';
import { Spin, Result, Button } from 'antd';
import type { PluginContext } from './foxel-types';
import { useI18n } from './i18n';

export const OfficeViewerApp: React.FC<PluginContext> = ({ filePath, host }) => {
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
        // 获取系统状态中的 file_domain
        const fileDomain = window.__FOXEL_SYSTEM_STATUS__?.file_domain;
        const baseUrl = fileDomain || window.location.origin;
        const fullUrl = new URL(res.url, baseUrl).href;
        const officeUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(fullUrl)}`;
        setUrl(officeUrl);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setErr(e.message || 'Failed to load document link');
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
        <Spin tip={t('Preparing document...')} />
      </div>
    );
  }

  if (err) {
    return (
      <Result
        status="error"
        title={t('Unable to load document')}
        subTitle={t(err)}
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
      {url ? (
        <iframe
          src={url}
          width="100%"
          height="100%"
          style={{ border: 'none' }}
          title="Office Document Viewer"
        />
      ) : (
        <Result
          status="warning"
          title={t('Invalid document link')}
          subTitle={t('Failed to generate an online preview link for the document.')}
          extra={
            <Button type="primary" onClick={host.close}>
              {t('Close')}
            </Button>
          }
        />
      )}
    </div>
  );
};
