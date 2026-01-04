/**
 * Office 文档查看器插件前端入口
 */
(function () {
  'use strict';

  const externals = window.__FOXEL_EXTERNALS__;
  if (!externals) {
    console.error('[office-viewer] Foxel externals not found');
    return;
  }

  const { React, ReactDOM, antd, foxelApi } = externals;
  const { useState, useEffect } = React;
  const { Spin, Result, Button } = antd;

  function OfficeViewerApp({ filePath, entry, urls, host }) {
    const [url, setUrl] = useState();
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState();

    useEffect(() => {
      let cancelled = false;
      setLoading(true);
      setErr(undefined);
      setUrl(undefined);

      const cleaned = filePath.replace(/^\/+/, '');
      foxelApi.request(`/fs/temp-link/${encodeURI(cleaned)}`)
        .then(res => {
          if (cancelled) return;
          // 获取系统状态中的 file_domain
          const fileDomain = window.__FOXEL_SYSTEM_STATUS__?.file_domain;
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
    }, [filePath]);

    if (loading) {
      return React.createElement('div', {
        style: { width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }
      }, React.createElement(Spin, { tip: '正在准备文档...' }));
    }

    if (err) {
      return React.createElement(Result, {
        status: 'error',
        title: '无法加载文档',
        subTitle: err,
        extra: React.createElement(Button, { type: 'primary', onClick: host.close }, '关闭')
      });
    }

    return React.createElement('div', {
      style: { width: '100%', height: '100%', background: 'var(--ant-color-bg-container, #fff)' }
    },
      url
        ? React.createElement('iframe', {
            src: url,
            width: '100%',
            height: '100%',
            frameBorder: '0',
            title: 'Office Document Viewer'
          })
        : React.createElement(Result, {
            status: 'warning',
            title: '文档链接无效',
            subTitle: '未能成功生成文档的在线查看链接。',
            extra: React.createElement(Button, { type: 'primary', onClick: host.close }, '关闭')
          })
    );
  }

  // 注册插件
  window.FoxelRegister({
    mount: (container, ctx) => {
      const root = ReactDOM.createRoot(container);
      root.render(React.createElement(OfficeViewerApp, ctx));
      return () => root.unmount();
    },
  });
})();

