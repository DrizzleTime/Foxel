/**
 * 视频库插件私有类型定义
 */

export type LibraryItemType = 'movie' | 'tv';

export interface LibraryItem {
  id: string;
  type: LibraryItemType;
  title?: string;
  overview?: string;
  year?: string | number;
  genres?: string[];
  poster_path?: string;
  backdrop_path?: string;
  episodes_count?: number;
}

export interface LibraryItemDetail {
  id?: string;
  type?: LibraryItemType;
  tmdb?: {
    detail?: {
      title?: string;
      name?: string;
      overview?: string;
    };
  };
}
