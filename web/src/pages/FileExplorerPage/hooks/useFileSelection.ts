import { useState, useCallback } from 'react';
import type { VfsEntry } from '../../../api/client';

export function useFileSelection() {
  const [selectedEntries, setSelectedEntries] = useState<string[]>([]);

  const handleSelect = useCallback((entry: VfsEntry, additive: boolean = false) => {
    const name = entry.name;
    if (additive) {
      // Toggle selection
      setSelectedEntries(prev => {
        const exists = prev.includes(name);
        return exists ? prev.filter(n => n !== name) : [...prev, name];
      });
    } else {
      // Replace selection
      setSelectedEntries([name]);
    }
  }, []);

  const handleSelectRange = useCallback((names: string[]) => {
    setSelectedEntries(names);
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedEntries([]);
  }, []);

  return {
    selectedEntries,
    setSelectedEntries,
    handleSelect,
    handleSelectRange,
    clearSelection,
  };
}