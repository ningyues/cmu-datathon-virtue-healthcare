import { useEffect, useRef, useState } from 'react';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

export default function CertificatePreview({ url }) {
  const canvas = useRef(null);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    if (typeof Worker === 'undefined') {
      setStatus('unavailable');
      return;
    }
    let active = true;
    let loadingTask;

    async function renderFirstPage() {
      try {
        const { getDocument, GlobalWorkerOptions } = await import('pdfjs-dist');
        if (!active) return;
        GlobalWorkerOptions.workerSrc = workerUrl;
        loadingTask = getDocument({ url });
        const pdf = await loadingTask.promise;
        if (!active) return;
        const page = await pdf.getPage(1);
        if (!active) return;

        const { width, height } = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({ scale: 1600 / Math.max(width, height) });
        const preview = canvas.current;
        preview.width = Math.ceil(viewport.width);
        preview.height = Math.ceil(viewport.height);
        await page.render({ canvas: preview, viewport }).promise;
        if (active) setStatus('ready');
      } catch {
        if (active) setStatus('unavailable');
      }
    }

    void renderFirstPage();
    return () => {
      active = false;
      void loadingTask?.destroy().catch(() => {});
    };
  }, [url]);

  return <>
    <canvas ref={canvas} className="certificate-preview" role="img"
      aria-label="First page of the NABH certificate" hidden={status !== 'ready'} />
    {status === 'loading' && <p className="detail-note" role="status">Loading certificate preview…</p>}
    {status === 'unavailable' && <p className="detail-note">Certificate preview unavailable.</p>}
  </>;
}
