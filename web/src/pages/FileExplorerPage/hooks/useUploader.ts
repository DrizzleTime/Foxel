import type { ChangeEvent, RefObject } from 'react';
import { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import { message } from 'antd';
import { vfsApi } from '../../../api/client';
import { useI18n } from '../../../i18n';

type UploadStatus = 'pending' | 'waiting' | 'uploading' | 'success' | 'error' | 'skipped';

export interface UploadFile {
  id: string;
  name: string;
  relativePath: string;
  targetPath: string;
  type: 'file' | 'directory';
  size: number;
  loadedBytes: number;
  status: UploadStatus;
  progress: number;
  error?: string;
  permanentLink?: string;
  file?: File;
}

export type ConflictDecision = 'overwrite' | 'skip' | 'overwriteAll' | 'skipAll';

export interface UploadConflict {
  taskId: string;
  relativePath: string;
  targetPath: string;
  type: 'file' | 'directory';
}

interface RawUploadFile {
  kind: 'file';
  relativePath: string;
  file: File;
}

interface RawUploadDirectory {
  kind: 'directory';
  relativePath: string;
}

type RawUploadItem = RawUploadFile | RawUploadDirectory;

const generateId = (() => {
  const cryptoApi = typeof crypto !== 'undefined' ? crypto : undefined;
  return () => {
    if (cryptoApi?.randomUUID) return cryptoApi.randomUUID();
    return `upload-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
  };
})();

const normalizeRelativePath = (path: string) => path.replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '');

const joinWithBasePath = (base: string, relative: string) => {
  const cleanedBase = base === '/' ? '' : base.replace(/\/+$/, '');
  const cleanedRelative = normalizeRelativePath(relative);
  const parts = [cleanedBase, cleanedRelative].filter(Boolean);
  const joined = parts.join('/');
  return joined.startsWith('/') ? joined : `/${joined}`;
};

const collectParentDirectories = (relativePath: string) => {
  const normalized = normalizeRelativePath(relativePath);
  if (!normalized) return [];
  const segments = normalized.split('/').slice(0, -1);
  const dirs: string[] = [];
  for (let i = 1; i <= segments.length; i += 1) {
    const dir = segments.slice(0, i).join('/');
    if (dir) dirs.push(dir);
  }
  return dirs;
};

const collectAllDirectories = (items: RawUploadItem[]) => {
  const directories = new Set<string>();
  items.forEach((item) => {
    if (item.kind === 'directory') {
      const normalized = normalizeRelativePath(item.relativePath);
      if (normalized) directories.add(normalized);
    } else {
      collectParentDirectories(item.relativePath).forEach((dir) => directories.add(dir));
    }
  });
  return Array.from(directories).sort((a, b) => a.localeCompare(b));
};

interface WebkitFileSystemFileEntry {
  isFile: true;
  isDirectory: false;
  name: string;
  fullPath: string;
  file: (
    successCallback: (file: File) => void,
    errorCallback?: (err: DOMException) => void,
  ) => void;
}

interface WebkitFileSystemDirectoryReader {
  readEntries: (
    successCallback: (entries: WebkitFileSystemEntry[]) => void,
    errorCallback?: (err: DOMException) => void,
  ) => void;
}

interface WebkitFileSystemDirectoryEntry {
  isFile: false;
  isDirectory: true;
  name: string;
  fullPath: string;
  createReader: () => WebkitFileSystemDirectoryReader;
}

type WebkitFileSystemEntry = WebkitFileSystemFileEntry | WebkitFileSystemDirectoryEntry;

const safeStat = async (fullPath: string): Promise<{ is_dir?: boolean } | null> => {
  try {
    return await vfsApi.stat(fullPath) as { is_dir?: boolean };
  } catch {
    return null;
  }
};

const readAllDirectoryEntries = (directoryEntry: WebkitFileSystemDirectoryEntry): Promise<WebkitFileSystemEntry[]> =>
  new Promise((resolve, reject) => {
    const reader = directoryEntry.createReader();
    const entries: WebkitFileSystemEntry[] = [];
    const readBatch = () => {
      reader.readEntries(
        (batch: WebkitFileSystemEntry[]) => {
          if (batch.length === 0) {
            resolve(entries);
          } else {
            entries.push(...batch);
            readBatch();
          }
        },
        (err: DOMException) => reject(err),
      );
    };
    readBatch();
  });

const traverseEntry = async (
  entry: WebkitFileSystemEntry,
  parentPath: string,
  bucket: RawUploadItem[],
) => {
  if (!entry) return;
  const currentPath = parentPath ? `${parentPath}/${entry.name}` : entry.name;
  if (entry.isFile) {
    const file: File = await new Promise((resolve, reject) => {
      entry.file(
        (f: File) => resolve(f),
        (err: DOMException) => reject(err),
      );
    });
    bucket.push({
      kind: 'file',
      relativePath: currentPath,
      file,
    });
  } else if (entry.isDirectory) {
    bucket.push({
      kind: 'directory',
      relativePath: currentPath,
    });
    const entries = await readAllDirectoryEntries(entry);
    for (const child of entries) {
      await traverseEntry(child, currentPath, bucket);
    }
  }
};

const collectFromFileList = async (list: FileList): Promise<RawUploadItem[]> => {
  const items: RawUploadItem[] = [];
  for (const file of Array.from(list)) {
    const fileWithPath = file as File & { webkitRelativePath?: string };
    const relativePath = fileWithPath.webkitRelativePath || file.name;
    items.push({
      kind: 'file',
      relativePath,
      file,
    });
  }
  return items;
};

const collectFromDataTransfer = async (dataTransfer: DataTransfer): Promise<RawUploadItem[]> => {
  const items: RawUploadItem[] = [];
  if (dataTransfer.items && dataTransfer.items.length > 0) {
    for (const item of Array.from(dataTransfer.items)) {
      const itemWithEntry = item as DataTransferItem & {
        webkitGetAsEntry?: () => FileSystemEntry | null;
      };
      const entry = itemWithEntry.webkitGetAsEntry ? (itemWithEntry.webkitGetAsEntry() as unknown as WebkitFileSystemEntry) : null;
      if (entry) {
        await traverseEntry(entry, '', items);
      } else if (item.kind === 'file') {
        const file = item.getAsFile();
        if (file) {
          items.push({
            kind: 'file',
            relativePath: file.name,
            file,
          });
        }
      }
    }
  } else if (dataTransfer.files && dataTransfer.files.length > 0) {
    return collectFromFileList(dataTransfer.files);
  }
  return items;
};

const createUploadTasks = (basePath: string, items: RawUploadItem[]): UploadFile[] => {
  const idGenerator = generateId;
  const directories = collectAllDirectories(items);
  const directoryTasks: UploadFile[] = directories.map((relativePath) => {
    const targetPath = joinWithBasePath(basePath, relativePath);
    const segments = normalizeRelativePath(relativePath).split('/');
    const name = segments[segments.length - 1] || targetPath;
    return {
      id: idGenerator(),
      name,
      relativePath,
      targetPath,
      type: 'directory',
      size: 0,
      loadedBytes: 0,
      status: 'pending',
      progress: 0,
    };
  });

  const fileTasks: UploadFile[] = items
    .filter((item): item is RawUploadFile => item.kind === 'file')
    .map((item) => {
      const relativePath = normalizeRelativePath(item.relativePath) || item.file.name;
      const targetPath = joinWithBasePath(basePath, relativePath);
      return {
        id: idGenerator(),
        name: item.file.name,
        relativePath,
        targetPath,
        type: 'file',
        size: item.file.size,
        loadedBytes: 0,
        status: 'pending',
        progress: 0,
        file: item.file,
      };
    });

  return [...directoryTasks, ...fileTasks];
};

export function useUploader(path: string, onUploadComplete: () => void) {
  const { t } = useI18n();
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [conflict, setConflict] = useState<UploadConflict | null>(null);
  const conflictResolverRef = useRef<((decision: ConflictDecision) => void) | null>(null);
  const overwriteAllRef = useRef(false);
  const skipAllRef = useRef(false);
  const createdDirsRef = useRef<Set<string>>(new Set());
  const filesRef = useRef<UploadFile[]>(files);
  const isUploadingRef = useRef(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const directoryInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const node = directoryInputRef.current;
    if (!node) return;
    node.setAttribute('webkitdirectory', '');
    node.setAttribute('directory', '');
  }, []);

  const mutateFiles = useCallback((updater: (prev: UploadFile[]) => UploadFile[]) => {
    setFiles((prev) => {
      const next = updater(prev);
      filesRef.current = next;
      return next;
    });
  }, []);

  const replaceFiles = useCallback((next: UploadFile[]) => {
    filesRef.current = next;
    setFiles(next);
  }, []);

  const updateFile = useCallback((id: string, patch: Partial<UploadFile>) => {
    mutateFiles((prev) => prev.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  }, [mutateFiles]);

  const resetOverwriteDecisions = useCallback(() => {
    overwriteAllRef.current = false;
    skipAllRef.current = false;
  }, []);

  const openFilePicker = useCallback(() => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  }, []);

  const openDirectoryPicker = useCallback(() => {
    if (directoryInputRef.current) {
      directoryInputRef.current.click();
    }
  }, []);

  const closeModal = useCallback(() => {
    if (isUploadingRef.current) {
      return;
    }
    setIsModalVisible(false);
    replaceFiles([]);
    resetOverwriteDecisions();
    setConflict(null);
    conflictResolverRef.current = null;
    createdDirsRef.current = new Set();
  }, [replaceFiles, resetOverwriteDecisions]);

  const prepareQueue = useCallback((items: RawUploadItem[]) => {
    if (!items.length) {
      message.info(t('No items selected for upload'));
      return;
    }
    const tasks = createUploadTasks(path, items);
    if (!tasks.length) {
      message.info(t('No uploadable files or directories found'));
      return;
    }
    replaceFiles(tasks);
    resetOverwriteDecisions();
    createdDirsRef.current = new Set();
    setIsModalVisible(true);
  }, [path, replaceFiles, resetOverwriteDecisions, t]);

  const handleInputChange = useCallback(async (event: ChangeEvent<HTMLInputElement>, ref: RefObject<HTMLInputElement | null>) => {
    const selectedFiles = event.target.files;
    if (!selectedFiles || selectedFiles.length === 0) {
      return;
    }
    const items = await collectFromFileList(selectedFiles);
    prepareQueue(items);
    if (ref.current) {
      ref.current.value = '';
    }
  }, [prepareQueue]);

  const handleFileInputChange = useCallback(async (event: ChangeEvent<HTMLInputElement>) => {
    await handleInputChange(event, fileInputRef);
  }, [handleInputChange]);

  const handleDirectoryInputChange = useCallback(async (event: ChangeEvent<HTMLInputElement>) => {
    await handleInputChange(event, directoryInputRef);
  }, [handleInputChange]);

  const handleFileDrop = useCallback(async (data: DataTransfer) => {
    const items = await collectFromDataTransfer(data);
    prepareQueue(items);
  }, [prepareQueue]);

  const awaitConflictDecision = useCallback(async (task: UploadFile): Promise<'overwrite' | 'skip'> => {
    if (overwriteAllRef.current) {
      return 'overwrite';
    }
    if (skipAllRef.current) {
      return 'skip';
    }
    return new Promise<'overwrite' | 'skip'>((resolve) => {
      updateFile(task.id, { status: 'waiting' });
      setConflict({
        taskId: task.id,
        relativePath: task.relativePath,
        targetPath: task.targetPath,
        type: task.type,
      });
      conflictResolverRef.current = (decision: ConflictDecision) => {
        if (decision === 'overwriteAll') {
          overwriteAllRef.current = true;
          resolve('overwrite');
        } else if (decision === 'skipAll') {
          skipAllRef.current = true;
          resolve('skip');
        } else if (decision === 'overwrite') {
          resolve('overwrite');
        } else {
          resolve('skip');
        }
      };
    });
  }, [updateFile]);

  const confirmConflict = useCallback((decision: ConflictDecision) => {
    if (!conflictResolverRef.current) {
      return;
    }
    const resolver = conflictResolverRef.current;
    conflictResolverRef.current = null;
    setConflict(null);
    resolver(decision);
  }, []);

  const ensureDirectory = useCallback(async (fullPath: string) => {
    const normalized = fullPath.replace(/\/+/g, '/');
    if (!normalized || normalized === '/') {
      return;
    }
    if (createdDirsRef.current.has(normalized)) {
      return;
    }
    try {
      await vfsApi.mkdir(normalized);
    } catch (err: unknown) {
      const messageText = err instanceof Error ? err.message : String(err);
      if (!/exist/i.test(messageText)) {
        throw err;
      }
    } finally {
      createdDirsRef.current.add(normalized);
    }
  }, []);

  const ensureDirectoryTree = useCallback(async (targetDir: string) => {
    if (!targetDir || targetDir === '/') return;
    const normalized = targetDir.replace(/\/+/g, '/');
    const segments = normalized.replace(/^\/+/, '').split('/').filter(Boolean);
    let current = '';
    for (const segment of segments) {
      current = `${current}/${segment}`;
      await ensureDirectory(current.startsWith('/') ? current : `/${current}`);
    }
  }, [ensureDirectory]);

  const processDirectoryTask = useCallback(async (task: UploadFile) => {
    updateFile(task.id, { status: 'uploading', progress: 10 });
    const stat = await safeStat(task.targetPath);
    if (stat && !stat.is_dir) {
      const error = t('Directory conflicts with existing file');
      updateFile(task.id, { status: 'error', progress: 0, error });
      message.error(`${task.relativePath}: ${error}`);
      return;
    }
    try {
      await ensureDirectory(task.targetPath);
      updateFile(task.id, { status: 'success', progress: 100 });
    } catch (err: unknown) {
      const error = err instanceof Error ? err.message : t('Create directory failed');
      updateFile(task.id, { status: 'error', progress: 0, error });
      message.error(`${task.relativePath}: ${error}`);
    }
  }, [ensureDirectory, updateFile, t]);

  const processFileTask = useCallback(async (task: UploadFile) => {
    if (!task.file) {
      updateFile(task.id, { status: 'error', error: t('Missing file content') });
      return;
    }

    if (skipAllRef.current) {
      updateFile(task.id, { status: 'skipped', progress: 0 });
      return;
    }

    let shouldOverwrite = overwriteAllRef.current;
    if (!shouldOverwrite) {
      const stat = await safeStat(task.targetPath);
      if (stat) {
        const decision = await awaitConflictDecision(task);
        if (decision === 'skip') {
          updateFile(task.id, { status: 'skipped', progress: 0 });
          return;
        }
        shouldOverwrite = true;
      }
    }

    setConflict(null);
    updateFile(task.id, { status: 'uploading', progress: 0, loadedBytes: 0 });

    const parentDir = task.targetPath.replace(/\/[^/]+$/, '') || '/';
    try {
      await ensureDirectoryTree(parentDir);
      await vfsApi.uploadStream(task.targetPath, task.file, shouldOverwrite, (loaded, total) => {
        mutateFiles((prev) => prev.map((f) => {
          if (f.id !== task.id) return f;
          const effectiveTotal = total > 0 ? total : f.size;
          const size = Math.max(f.size, effectiveTotal, loaded);
          const percent = size > 0 ? Math.min(100, Math.round((loaded / size) * 100)) : 0;
          return {
            ...f,
            size,
            loadedBytes: loaded,
            progress: percent,
          };
        }));
      });

      const link = await vfsApi.getTempLinkToken(task.targetPath, 60 * 60 * 24 * 365 * 10);
      const permanentLink = vfsApi.getTempPublicUrl(link.token);
      updateFile(task.id, { status: 'success', progress: 100, loadedBytes: task.size, permanentLink });
    } catch (err: unknown) {
      const error = err instanceof Error ? err.message : t('Upload failed');
      updateFile(task.id, { status: 'error', error, progress: 0 });
      message.error(`${task.relativePath}: ${error}`);
    }
  }, [ensureDirectoryTree, awaitConflictDecision, mutateFiles, updateFile, t]);

  const startUpload = useCallback(async () => {
    if (isUploadingRef.current) return;
    if (!filesRef.current.length) return;

    isUploadingRef.current = true;
    setIsUploading(true);
    try {
      for (const task of filesRef.current) {
        if (task.status !== 'pending' && task.status !== 'waiting') {
          continue;
        }
        if (task.type === 'directory') {
          await processDirectoryTask(task);
        } else {
          await processFileTask(task);
        }
      }
      onUploadComplete();
    } finally {
      isUploadingRef.current = false;
      setIsUploading(false);
    }
  }, [onUploadComplete, processDirectoryTask, processFileTask]);

  const totalFileBytes = useMemo(
    () => files.reduce((acc, f) => acc + (f.type === 'file' ? f.size : 0), 0),
    [files],
  );

  const uploadedFileBytes = useMemo(
    () => files.reduce((acc, f) => {
      if (f.type !== 'file') return acc;
      const loaded = Math.min(f.loadedBytes, f.size);
      if (f.status === 'success') {
        return acc + (f.size || loaded);
      }
      if (f.status === 'uploading' || f.status === 'waiting') {
        return acc + loaded;
      }
      return acc;
    }, 0),
    [files],
  );

  const directoryCounts = useMemo(() => {
    const directories = files.filter((f) => f.type === 'directory');
    const completed = directories.filter((f) => f.status === 'success').length;
    return {
      total: directories.length,
      completed,
    };
  }, [files]);

  const totalWeight = totalFileBytes + directoryCounts.total;
  const totalProgress = totalWeight === 0
    ? 0
    : ((uploadedFileBytes + directoryCounts.completed) / totalWeight) * 100;

  return {
    files,
    isModalVisible,
    isUploading,
    totalProgress: Math.min(100, Math.max(0, totalProgress)),
    totalFileBytes,
    uploadedFileBytes,
    conflict,
    confirmConflict,
    resetOverwriteDecisions,
    fileInputRef,
    directoryInputRef,
    openFilePicker,
    openDirectoryPicker,
    closeModal,
    handleFileInputChange,
    handleDirectoryInputChange,
    handleFileDrop,
    startUpload,
  };
}
