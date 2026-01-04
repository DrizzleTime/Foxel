/**
 * API 接口
 */
import type { LibraryItem, LibraryItemDetail } from './type';

const { foxelApi } = window.__FOXEL_EXTERNALS__;

export async function fetchLibrary(): Promise<LibraryItem[]> {
  const resp = await foxelApi.request('/plugins/video-library/library');
  return resp || [];
}

export async function fetchLibraryItem(id: string): Promise<LibraryItemDetail> {
  const resp = await foxelApi.request(`/plugins/video-library/library/${id}`);
  return resp;
}
