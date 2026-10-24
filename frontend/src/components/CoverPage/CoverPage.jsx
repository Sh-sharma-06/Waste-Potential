"use client";
import { useEffect, useState } from "react";
import "./CoverPage.css";

// Put bg.mp4 and poster.jpg inside your /public folder.
export default function CoverPage({ onExplore }) {
  const [ready, setReady] = useState(false);

  // Start the sequence once the video can play (fallback after 2s).
  useEffect(() => {
    const t = setTimeout(() => setReady(true), 2000);
    return () => clearTimeout(t);
  }, []);

  const handleExplore = () => {
    if (onExplore) onExplore();          // e.g. navigate("/explore")
    else window.location.href = "/explore";
  };

  return (
    <main className={`cover ${ready ? "is-ready" : ""}`}>
      <video
        className="cover__video"
        src="/bg.mp4"
        poster="/poster.jpg"
        autoPlay
        muted
        loop
        playsInline
        onCanPlay={() => setReady(true)}
      />
      <div className="cover__shade" />

      <div className="cover__head">
        <h1 className="cover__title">WASTE-POTENTIAL</h1>
        <p className="cover__tagline">The Potential Was Always There. We Just Found It</p>
      </div>

      <button className="cover__btn" onClick={handleExplore}>
        EXPLORE <span aria-hidden="true">→</span>
      </button>
    </main>
  );
}
