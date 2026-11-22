import { useCallback, useEffect, useRef, useState } from 'react';
import LandingPage from './components/LandingPage.jsx';
import ResultsPage from './components/ResultsPage.jsx';
import { searchFacilities, usesIllustrativeData } from './services/search.js';

export default function App() {
  const [page, setPage] = useState('landing');
  const [query, setQuery] = useState('');
  const [result, setResult] = useState({ facilities: [], illustrative: usesIllustrativeData });
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState('');
  const request = useRef(null);
  const lastSearch = useRef(null);
  useEffect(() => () => request.current?.abort(), []);

  const handleSearch = useCallback(async (nextQuery, preserveIntent = false) => {
    lastSearch.current = nextQuery;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setPage('results');
    setStatus('loading');
    setError('');
    setResult(current => preserveIntent
      ? { ...current, facilities: [] }
      : { facilities: [], illustrative: usesIllustrativeData });
    try {
      const data = await searchFacilities(nextQuery, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setResult(data);
      setStatus('success');
    } catch (cause) {
      if (controller.signal.aborted) return;
      setError(cause.message || 'Unable to load results.');
      setStatus('error');
      if (cause.clarification) setPage('landing');
    }
  }, []);
  const handleRangeChange = useCallback((range) => {
    if (result.intent) handleSearch({ ...result.intent, range }, true);
  }, [result.intent, handleSearch]);
  function goHome() { request.current?.abort(); setPage('landing'); }
  return page === 'landing'
    ? <LandingPage query={query} setQuery={(value) => { setQuery(value); setError(''); }} onSearch={handleSearch} feedback={error} />
    : <ResultsPage {...result} status={status} error={error} onHome={goHome} onRangeChange={handleRangeChange} onRetry={() => handleSearch(lastSearch.current ?? query.trim(), Boolean(result.intent))} />;
}
