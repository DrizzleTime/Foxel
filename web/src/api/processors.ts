import request from './client';

export interface ProcessorTypeField {
  key: string;
  label: string;
  type: 'string' | 'password' | 'number' | 'select';
  required?: boolean;
  placeholder?: string;
  default?: any;
  options?: { label: string; value: string | number }[];
}

export interface ProcessorTypeMeta {
  type: string;
  name: string;
  supported_exts: string[];
  config_schema: ProcessorTypeField[];
  produces_file: boolean;
  supports_directory?: boolean;
  module_path?: string | null;
}

export function processorSupportsEntry(processor: ProcessorTypeMeta, entry: { name: string; is_dir: boolean }): boolean {
  if (entry.is_dir) return !!processor.supports_directory;
  const ext = entry.name.split('.').pop()?.toLowerCase() || '';
  return !processor.supported_exts?.length || processor.supported_exts.includes(ext);
}

export const processorsApi = {
  list: () => request<ProcessorTypeMeta[]>('/processors', {
    method: 'GET'
  }),
  process: (params: {
    path: string;
    processor_type: string;
    config: any;
    save_to?: string;
    overwrite?: boolean;
  }) =>
    request<{ task_id: string }>('/processors/process', {
      method: 'POST',
      json: params,
    }),
  processDirectory: (params: {
    path: string;
    processor_type: string;
    config: any;
    overwrite: boolean;
    max_depth?: number | null;
    suffix?: string | null;
  }) =>
    request<{ task_id: string }>('/processors/process-directory', {
      method: 'POST',
      json: params,
    }),
  getSource: (type: string) =>
    request<{ source: string; module_path: string }>('/processors/source/' + encodeURIComponent(type), {
      method: 'GET',
    }),
  updateSource: (type: string, source: string) =>
    request<boolean>('/processors/source/' + encodeURIComponent(type), {
      method: 'PUT',
      json: { source },
    }),
  reload: () =>
    request<boolean>('/processors/reload', {
      method: 'POST',
    }),
};
