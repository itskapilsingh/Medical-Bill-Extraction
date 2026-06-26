"use client";

import { useEffect, useState } from "react";

/**
 * Returns `value` delayed by `delayMs`: the result only updates once the input
 * has stopped changing for that long. Used to keep expensive derived work — e.g.
 * filtering a large flattened record set — off the keystroke path, so the input
 * stays responsive while the heavy recompute waits for a pause in typing.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
