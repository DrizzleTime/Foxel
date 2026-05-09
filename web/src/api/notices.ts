import request from './client';

export interface NoticeItem {
  id: number;
  title: string;
  contentMd: string;
  isPopup: boolean;
  createdAt: number;
}

export interface GetNoticesResponse {
  items: NoticeItem[];
  page: number;
  pageSize: number;
  total: number;
}

export interface GetNoticesParams {
  page?: number;
}

export const noticesApi = {
  list: async (params: GetNoticesParams): Promise<GetNoticesResponse> => {
    return await request<GetNoticesResponse>(`/notices?page=${params.page ?? 1}`);
  },
  getPopup: async (): Promise<NoticeItem | null> => {
    return await request<NoticeItem | null>('/notices/popup');
  },
  dismiss: async (id: number): Promise<void> => {
    await request(`/notices/${id}/dismiss`, { method: 'POST' });
  },
};
