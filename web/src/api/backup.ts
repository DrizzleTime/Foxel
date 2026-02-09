import request from './client';

export const backupApi = {
  export: async (sections?: string[]) => {
    const params = new URLSearchParams();
    (sections || []).forEach((section) => params.append('sections', section));
    const query = params.toString();
    const response = await request(`/backup/export${query ? `?${query}` : ''}`, {
      method: 'GET',
      rawResponse: true,
    }) as Response;

    const contentDisposition = response.headers.get('content-disposition');
    let filename = 'backup.json';
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
      if (filenameMatch && filenameMatch.length > 1) {
        filename = filenameMatch[1];
      }
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },

  import: async (file: File, mode: 'replace' | 'merge' = 'replace') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', mode);
    return request('/backup/import', {
      method: 'POST',
      body: formData,
    });
  },
};
