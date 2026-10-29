import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';

interface ImageQueue {
  observer: IntersectionObserver;
  pending: Map<HTMLImageElement, () => void>;
}

const queues = new Map<Element | null, ImageQueue>();

function observeImage(image: HTMLImageElement, load: () => void) {
  if (typeof IntersectionObserver === 'undefined') {
    load();
    return;
  }

  const root = image.closest('[data-file-scroll]');
  let queue = queues.get(root);
  if (!queue) {
    const pending = new Map<HTMLImageElement, () => void>();
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const image = entry.target as HTMLImageElement;
        const load = pending.get(image);
        pending.delete(image);
        observer.unobserve(image);
        load?.();
      }
      if (pending.size === 0) {
        observer.disconnect();
        if (queues.get(root)?.observer === observer) queues.delete(root);
      }
    }, { root, rootMargin: '300px 0px' });
    queue = { observer, pending };
    queues.set(root, queue);
  }

  const { observer, pending } = queue;

  pending.set(image, load);
  observer.observe(image);

  return () => {
    pending.delete(image);
    observer.unobserve(image);
    if (pending.size === 0) {
      observer.disconnect();
      if (queues.get(root)?.observer === observer) queues.delete(root);
    }
  };
}

interface FileThumbnailProps {
  src: string;
  alt: string;
  eager?: boolean;
  style: CSSProperties;
  fallback?: ReactNode;
}

export default function FileThumbnail({ src, alt, eager = false, style, fallback = null }: FileThumbnailProps) {
  const imageRef = useRef<HTMLImageElement>(null);
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);

  useEffect(() => {
    const image = imageRef.current;
    if (!image || eager || loadedSrc === src) return;
    return observeImage(image, () => setLoadedSrc(src));
  }, [eager, loadedSrc, src]);

  if (failedSrc === src) return fallback;

  return (
    <img
      ref={imageRef}
      src={eager || loadedSrc === src ? src : undefined}
      alt={alt}
      decoding="async"
      onError={() => setFailedSrc(src)}
      style={style}
    />
  );
}
