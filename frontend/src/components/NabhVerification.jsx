import { useEffect, useRef, useState } from 'react';
import { verifyCertification } from '../services/verification.js';

export default function NabhVerification({ facility, illustrative }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const request = useRef(null);
  useEffect(() => () => request.current?.abort(), []);

  async function verify() {
    if (request.current && !request.current.signal.aborted && loading) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setResult(null);
    try {
      const data = await verifyCertification(facility.id, { signal: controller.signal });
      if (!controller.signal.aborted) setResult(data);
    } catch (error) {
      if (!controller.signal.aborted) setResult({ status: 'unavailable', certificateUrls: [], reason: error.message });
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  return <div className="nabh-verification">
    <button type="button" className="primary-button" onClick={verify} disabled={loading || illustrative}>
      {loading ? 'Verifying NABH certification…' : 'NABH certification verify'}
    </button>
    {illustrative && <p>Verification is available for live facility results.</p>}
    <div role="status" aria-live="polite" aria-atomic="true">
      {loading && <p>Checking official records and certificate evidence. This may take a few minutes.</p>}
      {result && <>
        <p className={result.status === 'verified' ? 'nabh-success' : 'nabh-unverified'}>
          {result.status === 'verified' ? 'successfully verified!' : "can't be verified"}
        </p>
        <p>{result.reason}</p>
        {result.certificateUrls.map((url, index) => <p key={url}><a href={url} target="_blank" rel="noopener noreferrer">View certificate PDF{result.certificateUrls.length > 1 ? ` ${index + 1}` : ''} ↗</a></p>)}
      </>}
    </div>
  </div>;
}
