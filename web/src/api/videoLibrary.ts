import request from './client';

export type VideoLibraryMediaType = 'tv' | 'movie';

export interface VideoLibraryItem {
  id: string;
  type: VideoLibraryMediaType;
  title: string;
  year?: string | null;
  overview?: string | null;
  poster_path?: string | null;
  backdrop_path?: string | null;
  genres?: string[];
  tmdb_id?: number | null;
  source_path?: string | null;
  scraped_at?: string | null;
  updated_at?: string | null;
  episodes_count?: number;
  seasons_count?: number;
  vote_average?: number | null;
  vote_count?: number | null;
}

export const videoLibraryApi = {
  list: (params?: { q?: string; type?: VideoLibraryMediaType }) => {
    const search = new URLSearchParams();
    if (params?.q) search.set('q', params.q);
    if (params?.type) search.set('type', params.type);
    const suffix = search.toString();
    return request<VideoLibraryItem[]>(`/plugins/video-player/library${suffix ? `?${suffix}` : ''}`, { method: 'GET' });
  },
  get: (id: string) =>
    request<any>(`/plugins/video-player/library/${encodeURIComponent(id)}`, { method: 'GET' }),
};

