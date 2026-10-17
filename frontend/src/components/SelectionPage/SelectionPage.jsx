import { useState } from "react";
import "./SelectionPage.css";

// Put bg.mp4 and poster.jpg inside your /public folder.
const MODES = [
    {
      id: "agriculture", title: "Agriculture", text: "Turn crop residue and farm waste into clean bio-energy.",
      icon: <svg viewBox="0 0 24 24"><path d="M12 22v-9"/><path d="M12 13c0-4 3-6 7-6 0 4-3 6-7 6z"/><path d="M12 16c0-3-2.5-5-6-5 0 3 2.5 5 6 5z"/></svg>,
    },
    {
      id: "home", title: "Home", text: "Convert everyday household waste into usable power.",
      icon: <svg viewBox="0 0 24 24"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/></svg>,
    },
    {
      id: "industry", title: "Industry", text: "Unlock energy from factory and industrial waste streams.",
      icon: <svg viewBox="0 0 24 24"><path d="M3 21h18"/><path d="M5 21V11l5 3v-3l5 3V4h4v17"/></svg>,
    },
];

export default function SelectionPage({ onSelect }) {
  const [place, setPlace] = useState(() => {
    try { return localStorage.getItem("wp_location") || ""; } catch { return ""; }
  });
  const [saved, setSaved] = useState(false);

  const save = (e) => {
    e.preventDefault();
    try { localStorage.setItem("wp_location", place.trim()); } catch {}
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  };

  const choose = (mode) => {
    if (onSelect) onSelect(mode, place.trim());   // e.g. navigate(`/${mode}?loc=${place}`)
    else window.location.href = `/${mode}?loc=${encodeURIComponent(place.trim())}`;
  };

  return (
    <main className="select">
      <video className="select__video" src="/bg.mp4" poster="/poster.jpg"
        autoPlay muted loop playsInline />
      <div className="select__shade" />

      <div className="select__content">
        <form className="search" onSubmit={save}>
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
          <input value={place} onChange={(e) => setPlace(e.target.value)}
            placeholder="Enter pincode or city name" aria-label="Pincode or city name" />
          <button type="submit" className={saved ? "is-saved" : ""}>{saved ? "SAVED ✓" : "SAVE"}</button>
        </form>

        <section className="cards">
          {MODES.map((m, i) => (
            <article className={`card card--${m.id}`} key={m.id} style={{ "--i": i }}>
              <div className="card__icon">{m.icon}</div>
              <h2 className="card__title">{m.title}</h2>
              <p className="card__text">{m.text}</p>
              <button className="card__btn" onClick={() => choose(m.id)}>ENTER →</button>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
