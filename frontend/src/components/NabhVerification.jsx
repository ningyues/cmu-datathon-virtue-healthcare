import CertificatePreview from './CertificatePreview.jsx';

export default function NabhVerification({ illustrative, result }) {
  if (illustrative) return <p className="detail-note">Verification is available for live facility results.</p>;
  const verified = result?.status === 'verified';

  return <div className="nabh-verification">
    {result ? <div className={`verification-feedback ${verified ? 'verified' : 'unverified'}`}>
      <div role="status" aria-atomic="true">
        <strong>{verified ? 'Verified' : 'Unable to verify'}</strong>
        {result.reason && <p>{result.reason}</p>}
      </div>
      {verified && result.certificateUrls.map((url, index) => <div className="certificate-evidence" key={url}>
        <p><a href={url} target="_blank" rel="noopener noreferrer">View certificate PDF{result.certificateUrls.length > 1 ? ` ${index + 1}` : ''} ↗</a></p>
        <CertificatePreview url={url} />
      </div>)}
    </div> : <p className="verification-feedback pending" role="status">Checking official NABH records and certificate evidence…</p>}
  </div>;
}
