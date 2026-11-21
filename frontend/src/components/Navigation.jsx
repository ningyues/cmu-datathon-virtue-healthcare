export default function Navigation({ light = false, onHome }) {
  return (
    <header className={`navigation ${light ? 'navigation-light' : ''}`}>
      <button type="button" className="brand" onClick={onHome} aria-label="CareLens — start a new search">
        <img src={`${import.meta.env.BASE_URL}assets/logo-${light ? 'light' : 'dark'}.svg`} alt="" width="36" height="36" />
        <span>CareLens</span>
      </button>
      <p>Healthcare, with clarity</p>
    </header>
  );
}
