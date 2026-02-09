import { theme } from 'antd';
import type { ThemeConfig } from 'antd/es/config-provider/context';

export const foxelTheme: ThemeConfig = {
  algorithm: [theme.defaultAlgorithm, theme.compactAlgorithm],
  token: {
    colorInfoBg: '#efefef',
    colorPrimary: '#111',
    colorInfo: '#111',
    colorText: '#111',
    colorTextSecondary: '#444',
    colorTextTertiary: '#666',
    colorBgBase: '#fff',
    colorBgLayout: '#f9f9f9',
    colorBgContainer: '#fff',
    colorBorder: '#e5e5e5',
    colorBorderSecondary: '#efefef',
    borderRadius: 10,
    fontSize: 16,
    controlHeight: 34,
    boxShadow: '0 2px 4px -2px rgba(0,0,0,0.06),0 4px 12px -2px rgba(0,0,0,0.04)'
  },
  components: {
    Layout: { headerHeight: 56, headerPadding: '0 20px' },
    Menu: {
      itemBorderRadius: 8,
      itemHeight: 40,
      horizontalItemBorderRadius: 8,
      itemHoverColor: '#111',
      itemHoverBg: '#f2f2f2',
      itemSelectedBg: '#111',
      itemSelectedColor: '#fff'
    },
    Button: {
      borderRadius: 8,
      controlHeight: 36,
      fontWeight: 500
    },
    Card: {
      borderRadiusLG: 16,
      padding: 16
    },
    Input: { borderRadius: 8 },
    Dropdown: { controlItemBgHover: '#f2f2f2' },
    Table: {
      cellPaddingBlock: 14,
      cellPaddingInline: 18,
      headerBg: '#fafafa',
      rowHoverBg: '#f5f5f5'
    },
  }
};

export default foxelTheme;
