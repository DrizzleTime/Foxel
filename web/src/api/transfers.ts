export const TRANSFER_CHUNK_SIZE = 8 * 1024 * 1024;
export const MAX_BLOB_DOWNLOAD_SIZE = 128 * 1024 * 1024;

export class TransferError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'TransferError';
    this.status = status;
  }
}

export const encodeFilePath = (path: string) => path.replace(/^\/+/, '').split('/').map(encodeURIComponent).join('/');

export function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

class RequestPool {
  private active = 0;
  private waiting: Array<() => void> = [];

  async run<T>(work: () => Promise<T>, signal?: AbortSignal): Promise<T> {
    signal?.throwIfAborted();
    if (this.active >= 6) {
      await new Promise<void>((resolve, reject) => {
        const ready = () => {
          signal?.removeEventListener('abort', aborted);
          resolve();
        };
        const aborted = () => {
          this.waiting = this.waiting.filter(item => item !== ready);
          reject(signal?.reason ?? new DOMException('Aborted', 'AbortError'));
        };
        this.waiting.push(ready);
        signal?.addEventListener('abort', aborted, { once: true });
      });
    } else {
      this.active += 1;
    }
    try {
      signal?.throwIfAborted();
      return await work();
    } finally {
      const next = this.waiting.shift();
      if (next) next();
      else this.active -= 1;
    }
  }
}

export const transferRequests = new RequestPool();

export async function transferJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...options, headers: { ...authHeaders(), 'Content-Type': 'application/json', ...options.headers },
  });
  const data = await response.json();
  if (!response.ok || data.code !== 0) {
    throw new TransferError(data.detail || data.msg || 'Transfer failed', response.status);
  }
  return data.data;
}

export async function retryTransfer<T>(work: () => Promise<T>, signal?: AbortSignal): Promise<T> {
  for (let attempt = 0; ; attempt += 1) {
    signal?.throwIfAborted();
    try {
      return await work();
    } catch (error) {
      signal?.throwIfAborted();
      if (attempt >= 2 || (error instanceof TransferError && error.status !== undefined
        && error.status < 500 && ![408, 429].includes(error.status))) throw error;
      await new Promise<void>((resolve, reject) => {
        const aborted = () => {
          clearTimeout(timer);
          reject(signal?.reason ?? new DOMException('Aborted', 'AbortError'));
        };
        const timer = setTimeout(() => {
          signal?.removeEventListener('abort', aborted);
          resolve();
        }, 400 * 2 ** attempt);
        signal?.addEventListener('abort', aborted, { once: true });
      });
    }
  }
}

export async function runTransferWorkers(count: number, concurrency: number,
  work: (index: number, signal: AbortSignal) => Promise<void>, signal?: AbortSignal) {
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  if (signal?.aborted) abort();
  else signal?.addEventListener('abort', abort, { once: true });
  let next = 0;
  let failure: unknown;
  const workers = Array.from({ length: Math.min(count, concurrency) }, async () => {
    while (next < count && !controller.signal.aborted) {
      const index = next++;
      try {
        await work(index, controller.signal);
      } catch (error) {
        if (failure === undefined) failure = error;
        controller.abort(error);
      }
    }
  });
  await Promise.all(workers);
  signal?.removeEventListener('abort', abort);
  if (failure !== undefined) throw failure;
  signal?.throwIfAborted();
}

export function sendUpload(url: string, body: Blob | FormData,
  onProgress?: (loaded: number, total: number) => void, signal?: AbortSignal,
  method: 'PUT' | 'POST' = 'PUT'): Promise<{ path: string; size: number }> {
  return transferRequests.run(() => new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    const finish = (error?: Error, result?: { path: string; size: number }) => {
      signal?.removeEventListener('abort', abort);
      if (error) reject(error);
      else resolve(result!);
    };
    xhr.open(method, url);
    xhr.timeout = 10 * 60 * 1000;
    Object.entries(authHeaders()).forEach(([key, value]) => xhr.setRequestHeader(key, value));
    if (body instanceof Blob) xhr.setRequestHeader('Content-Type', body.type || 'application/octet-stream');
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) onProgress?.(event.loaded, event.total);
    };
    xhr.onload = () => {
      let data;
      try { data = JSON.parse(xhr.responseText); } catch { /* Handled below. */ }
      if (xhr.status >= 200 && xhr.status < 300 && data?.code === 0) finish(undefined, data.data);
      else finish(new TransferError(data?.detail || data?.msg || 'Upload failed', xhr.status));
    };
    xhr.onerror = () => finish(new TransferError('Upload connection failed'));
    xhr.ontimeout = () => finish(new TransferError('Upload timed out', 408));
    xhr.onabort = () => finish(new DOMException('Aborted', 'AbortError'));
    signal?.addEventListener('abort', abort, { once: true });
    xhr.send(body);
  }), signal);
}

export interface DownloadTarget {
  write(data: { type: 'write'; position: number; data: Blob }): Promise<void>;
  close(): Promise<void>;
  abort(): Promise<void>;
}

interface SaveFileHandle {
  createWritable(): Promise<DownloadTarget>;
}

export function selectDownloadTarget(name: string): Promise<SaveFileHandle> | undefined {
  if (!window.isSecureContext) return undefined;
  const picker = (window as Window & { showSaveFilePicker?:
    (options: { suggestedName: string }) => Promise<SaveFileHandle> }).showSaveFilePicker;
  return picker?.call(window, { suggestedName: name });
}

export function saveDownloadUrl(url: string, name: string) {
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export async function downloadRanges(url: string, size: number,
  onProgress?: (loaded: number, total: number) => void, signal?: AbortSignal,
  target?: DownloadTarget): Promise<Blob | null> {
  const probe = await transferRequests.run(() => fetch(url, {
    headers: { ...authHeaders(), Range: 'bytes=0-0' }, signal,
  }), signal);
  const range = probe.headers.get('Content-Range');
  const supportsRanges = probe.status === 206 && range === `bytes 0-0/${size}`;
  const etag = probe.headers.get('ETag');
  await probe.body?.cancel();
  if (!supportsRanges) {
    if (!probe.ok) throw new TransferError('Download failed', probe.status);
    if (target) {
      await transferRequests.run(async () => {
        const response = await fetch(url, { headers: authHeaders(), signal });
        if (!response.ok) throw new TransferError('Download failed', response.status);
        if (!response.body) throw new TransferError('Empty download response');
        const reader = response.body.getReader();
        let position = 0;
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const data = new Blob([value]);
            await target.write({ type: 'write', position, data });
            position += data.size;
            onProgress?.(position, size);
          }
        } finally {
          await reader.cancel().catch(() => void 0);
        }
      }, signal);
      return new Blob();
    }
    return null;
  }
  const parts: Blob[] = [];
  const count = Math.ceil(size / TRANSFER_CHUNK_SIZE);
  let completed = 0;
  let writing = Promise.resolve();
  await runTransferWorkers(count, 4, async (index, workerSignal) => {
    const start = index * TRANSFER_CHUNK_SIZE;
    const end = Math.min(size - 1, start + TRANSFER_CHUNK_SIZE - 1);
    const blob = await retryTransfer(() => transferRequests.run(async () => {
      const headers: Record<string, string> = { ...authHeaders(), Range: `bytes=${start}-${end}` };
      if (etag) headers['If-Match'] = etag;
      const response = await fetch(url, { headers, signal: AbortSignal.any([workerSignal, AbortSignal.timeout(120_000)]) });
      if (!response.ok) throw new TransferError('Download failed', response.status);
      if (response.status !== 206 || response.headers.get('Content-Range') !== `bytes ${start}-${end}/${size}`) {
        await response.body?.cancel();
        throw new TransferError('Invalid download range', 400);
      }
      if (!response.body) throw new TransferError('Empty download segment');
      const reader = response.body.getReader();
      const chunks: Uint8Array<ArrayBuffer>[] = [];
      let received = 0;
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          received += value.byteLength;
          if (received > end - start + 1) throw new TransferError('Download segment exceeds requested size', 400);
          chunks.push(value);
        }
      } finally {
        await reader.cancel().catch(() => void 0);
      }
      if (received !== end - start + 1) throw new TransferError('Incomplete download segment');
      return new Blob(chunks);
    }, workerSignal), workerSignal);
    if (target) {
      // Serialize writes to one file stream while network requests stay parallel.
      const write = writing.then(() => target.write({ type: 'write', position: start, data: blob }));
      writing = write;
      await write;
    } else {
      parts[index] = blob;
    }
    completed += blob.size;
    onProgress?.(completed, size);
  }, signal).catch(async error => {
    await writing.catch(() => void 0);
    throw error;
  });
  return target ? new Blob() : new Blob(parts, { type: 'application/octet-stream' });
}
