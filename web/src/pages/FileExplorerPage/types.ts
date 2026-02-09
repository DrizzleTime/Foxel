import type { VfsEntry } from '../../api/client';
import type { AppDescriptor } from '../../apps/registry';

export type ViewMode = 'list' | 'grid';

export interface AppWindow {
  id: string;
  app: AppDescriptor;
  entry: VfsEntry;
  filePath: string;
  maximized: boolean;
  x: number;
  y: number;
  width: number;
  height: number;
}
