/**
 * API 接口
 */
import type { LibraryItem, LibraryItemDetail } from './type';

const { foxelApi } = window.__FOXEL_EXTERNALS__;

function unwrapResponse<T>(resp: any): T {
  if (resp && typeof resp === 'object' && 'code' in resp) {
    const { code, data, detail, message: msg } = resp as any;
    if (code !== 0) {
      throw new Error(detail || msg || '请求失败');
    }
    return data as T;
  }
  return resp as T;
}

export async function fetchLibrary(): Promise<LibraryItem[]> {
  const resp = await foxelApi.request('/plugins/video-library/library');
  const data = unwrapResponse<LibraryItem[] | undefined>(resp);
  return Array.isArray(data) ? data : [];
}

export async function fetchLibraryItem(id: string): Promise<LibraryItemDetail> {
  const resp = await foxelApi.request(`/plugins/video-library/library/${id}`);
  return unwrapResponse<LibraryItemDetail>(resp);
}
