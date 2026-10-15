import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import 'antd/dist/reset.css';
import './global.css';
import { BrowserRouter } from 'react-router';
import { ConfigProvider } from 'antd';
import FoxelLoadingIndicator from './components/FoxelLoadingIndicator';

createRoot(document.getElementById('root')!).render(
  <ConfigProvider spin={{ indicator: <FoxelLoadingIndicator /> }}>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </ConfigProvider>
);
