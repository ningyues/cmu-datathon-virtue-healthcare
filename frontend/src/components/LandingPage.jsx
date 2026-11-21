import { useRef, useState } from 'react';
import Navigation from './Navigation.jsx';

export default function LandingPage({ query, setQuery, onSearch }) {
  const [error, setError] = useState('');
  const input = useRef(null);
  function submit(event) {
    event.preventDefault();
    if (!query.trim()) {
      setError('Enter the care you need and your location.');
      input.current?.focus();
      return;
    }
    setError('');
    onSearch(query.trim());
  }
  return (
    <div className="landing-page">
      <div className="landing-layout">
        <div className="atmosphere" aria-hidden="true"><img src={`${import.meta.env.BASE_URL}assets/atmosphere.svg`} alt="" /></div>
        <div className="orbital" aria-hidden="true"><img src={`${import.meta.env.BASE_URL}assets/orbital.png`} alt="" width="660" height="495" /></div>
        <Navigation light onHome={() => input.current?.focus()} />
        <main className="landing-main">
          <div className="hero-message">
            <h1>Find care you<span>can trust.</span></h1>
            <p>Search hospitals and healthcare services near you.</p>
          </div>
          <form className="search-form" onSubmit={submit} noValidate>
            <label htmlFor="care-query">How can I help you?</label>
            <textarea id="care-query" ref={input} value={query} onChange={(event) => { setQuery(event.target.value); setError(''); }} placeholder="I need to find a nursing service in 800001" aria-invalid={Boolean(error)} aria-describedby={error ? 'query-error' : undefined} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(event); } }} />
            <div className="search-form-bottom">
              <p id="query-error" className="form-error" role="alert">{error}</p>
              <button className="primary-button" type="submit">Send ↑</button>
            </div>
          </form>
          <div className="landing-footer">
            <ol className="steps"><li>01&nbsp; SEARCH BY NEED</li><li>02&nbsp; COMPARE OPTIONS</li><li>03&nbsp; INSPECT EVIDENCE</li></ol>
            <p>A clearer path to your next care decision.</p>
          </div>
        </main>
      </div>
    </div>
  );
}
