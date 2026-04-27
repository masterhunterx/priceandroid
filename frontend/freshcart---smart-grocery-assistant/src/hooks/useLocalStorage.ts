import { useState, useCallback } from 'react';

/**
 * Mantiene un valor sincronizado con localStorage.
 * setValue(null) elimina la clave; setValue(value) serializa a JSON.
 */
export function useLocalStorage<T>(
  key: string,
  initialValue: T,
): [T, (value: T | null) => void] {
  const [storedValue, setStoredValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initialValue;
    } catch {
      localStorage.removeItem(key);
      return initialValue;
    }
  });

  const setValue = useCallback(
    (value: T | null) => {
      try {
        if (value === null) {
          localStorage.removeItem(key);
          setStoredValue(initialValue);
        } else {
          localStorage.setItem(key, JSON.stringify(value));
          setStoredValue(value);
        }
      } catch {
        // localStorage lleno o deshabilitado — ignorar
      }
    },
    [key, initialValue],
  );

  return [storedValue, setValue];
}
