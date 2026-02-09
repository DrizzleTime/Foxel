import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import 'antd/dist/reset.css';
import './global.css';
import { BrowserRouter } from 'react-router';

// 初始化插件依赖注入
import { initExternals } from './plugins/externals';
initExternals();

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
);
