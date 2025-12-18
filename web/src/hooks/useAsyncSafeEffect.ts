import React, { useEffect } from 'react';

export interface AsyncEffectCtx {
  isDisposed: () => boolean;
  signal: AbortSignal;
}

export function useAsyncSafeEffect(
  effect: (ctx: AsyncEffectCtx) => void | Promise<void>,
  deps: React.DependencyList,
  cleanup?: (ctx: AsyncEffectCtx) => void,
) {
  useEffect(() => {
    let disposed = false;
    const ac = new AbortController();
    const ctx: AsyncEffectCtx = {
      isDisposed: () => disposed,
      signal: ac.signal,
    };

    Promise.resolve(effect(ctx)).catch(() => {
      // 故意忽略 effect 内部抛出的异常，交由调用方处理
    });

    return () => {
      disposed = true;
      try {
        cleanup?.(ctx);
      } finally {
        ac.abort();
      }
    };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}
