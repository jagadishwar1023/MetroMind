import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * usePolling - Generic hook that polls an async function at a given interval.
 * Returns { data, loading, error, refetch }.
 */
export function usePolling(fetchFn, { interval = 30000, enabled = true, immediate = true } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);
  const mountedRef = useRef(true);

  const doFetch = useCallback(async () => {
    if (!enabled) return;
    setLoading(prev => !prev ? true : prev);  // only set true on first load
    try {
      const result = await fetchFn();
      if (mountedRef.current) {
        setData(result);
        setError(null);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message || 'Fetch failed');
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [fetchFn, enabled]);

  useEffect(() => {
    mountedRef.current = true;
    if (immediate && enabled) doFetch();
    if (interval > 0 && enabled) {
      intervalRef.current = setInterval(doFetch, interval);
    }
    return () => {
      mountedRef.current = false;
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [doFetch, interval, enabled, immediate]);

  return { data, loading, error, refetch: doFetch };
}
