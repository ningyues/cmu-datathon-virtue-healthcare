import { useEffect, useState } from 'react';

const emptyResults = new Map();

export default function useVerificationQueue(keys, verify, concurrency = 1) {
  const [run, setRun] = useState(null);

  useEffect(() => {
    if (!keys?.length) return;
    const controller = new AbortController();
    const { signal } = controller;
    let next = 0;

    async function checkNext() {
      while (!signal.aborted && next < keys.length) {
        const key = keys[next++];
        let result;
        try {
          result = await verify(key, { signal });
        } catch (error) {
          result = { status: 'unavailable', reason: error.message };
        }
        if (signal.aborted) return;

        setRun(previous => {
          const results = new Map(previous?.keys === keys ? previous.results : undefined);
          results.set(key, result);
          return { keys, results };
        });
      }
    }

    // Start after the effect's cleanup has a chance to cancel a Strict Mode replay.
    queueMicrotask(() => {
      for (let worker = 0; worker < Math.min(concurrency, keys.length); worker++) void checkNext();
    });
    return () => controller.abort();
  }, [keys, verify, concurrency]);

  return keys && run?.keys === keys ? run.results : emptyResults;
}
