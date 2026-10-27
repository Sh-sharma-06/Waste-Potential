"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
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

export default function SelectionPage({ onSelect = undefined } = {}) {
  const router = useRouter();

  // The PIN code is asked for on the next page; clear any value saved by older versions.
  useEffect(() => {
    try { localStorage.removeItem("wp_location"); } catch {}
  }, []);

  const choose = (mode) => {
    if (onSelect) { onSelect(mode); return; }
    const routeMap = { agriculture: "/explore/agriculture", home: "/explore/home", industry: "/explore/industry" };
    router.push(routeMap[mode] ?? `/${mode}`);
  };

  return (
    <main className="select">
      <video className="select__video" src="/bg.mp4" poster="/poster.jpg"
        autoPlay muted loop playsInline />
      <div className="select__shade" />

      <div className="select__content">
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
