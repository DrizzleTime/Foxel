import { createContext, useContext } from 'react';
import type { SystemStatus } from '../api/config';

export const SystemContext = createContext<SystemStatus | null>(null);

export const useSystemStatus = () => {
  const context = useContext(SystemContext);
  if (context === undefined) {
    throw new Error('useSystemStatus must be used within a SystemProvider');
  }
  return context;
};