import { useEffect, useState } from 'react';
import { fetchJson } from '../fetch';

let optimizeInfoCache = null;

export default function useOptimizeInfo() {
  const [optimizeInfo, setOptimizeInfo] = useState({});

  useEffect(() => {
    (async () => setOptimizeInfo(await fetchOptimizeInfo()))();
  }, []);

  return optimizeInfo;
}

async function fetchOptimizeInfo() {
  if (optimizeInfoCache === null) {
    optimizeInfoCache = await fetchJson('GET', '/optimize');
  }
  return optimizeInfoCache;
}
