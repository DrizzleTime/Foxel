import { Grid } from 'antd';

export function useResponsive() {
  const screens = Grid.useBreakpoint();

  return {
    screens,
    isMobile: !screens.md,
    isTablet: !!screens.md && !screens.xl,
    isDesktop: !!screens.md,
  };
}

export default useResponsive;
