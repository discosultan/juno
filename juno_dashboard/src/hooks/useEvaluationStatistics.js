import { useEffect, useState } from 'react';
import { fetchJson } from '../fetch';

let evaluationStatisticsCache = null;

export default function useEvaluationStatistics() {
  const [evaluationStatistics, setEvaluationStatistics] = useState([]);

  useEffect(() => {
    (async () => setEvaluationStatistics(await fetchEvaluationStatistics()))();
  }, []);

  return evaluationStatistics;
}

async function fetchEvaluationStatistics() {
  if (evaluationStatisticsCache === null) {
    evaluationStatisticsCache = await fetchJson('GET', '/optimize');
  }
  return evaluationStatisticsCache;
}
