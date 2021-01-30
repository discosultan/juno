import { useEffect, useState } from 'react';
import { fetchJson } from 'fetch';

let optimizeInfoCache = null;

export default function useOptimizeInfo() {
  const [optimizeInfo, setOptimizeInfo] = useState({});

  useEffect(() => {
    const abortController = new AbortController();
    (async () => setOptimizeInfo(await fetchOptimizeInfo(abortController.signal)))();
    return () => abortController.abort();
  }, []);

  return optimizeInfo;
}

async function fetchOptimizeInfo(signal) {
  if (optimizeInfoCache === null) {
    optimizeInfoCache = await fetchJson('GET', '/optimize', null, signal);
  }
  return optimizeInfoCache;
}
