"use client";

import { useEffect, useRef } from "react";
import styles from "./PreviewAtmosphere.module.css";

// Dust motes drifting through light: sage, lavender and amber, deliberately sparse.
const MOTE_COLORS = ["70, 99, 75", "104, 85, 143", "200, 135, 75"];

type Mote = { x: number; y: number; z: number; r: number; speed: number; phase: number; color: number };

/**
 * Shared living background for the preview: light shafts, drifting mist layers with
 * cursor parallax, and a lightweight 2D-canvas particle field.
 */
export default function PreviewAtmosphere() {
  const rootRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Cursor parallax: writes --px / --py (-1..1) which the mist layers scale by depth.
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (!window.matchMedia("(pointer: fine)").matches) return;

    let frame = 0;
    let px = 0;
    let py = 0;
    const onMove = (e: PointerEvent) => {
      px = (e.clientX / window.innerWidth) * 2 - 1;
      py = (e.clientY / window.innerHeight) * 2 - 1;
      if (!frame) {
        frame = requestAnimationFrame(() => {
          frame = 0;
          root.style.setProperty("--px", px.toFixed(3));
          root.style.setProperty("--py", py.toFixed(3));
        });
      }
    };
    window.addEventListener("pointermove", onMove);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  // Particle field.
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const lowPower = (navigator.hardwareConcurrency ?? 8) <= 4;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);

    // Pre-render one soft sprite per colour; drawImage is far cheaper than shadowBlur.
    const sprites = MOTE_COLORS.map((rgb) => {
      const s = document.createElement("canvas");
      s.width = s.height = 64;
      const g = s.getContext("2d")!;
      const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
      grad.addColorStop(0, `rgba(${rgb}, 0.55)`);
      grad.addColorStop(0.4, `rgba(${rgb}, 0.18)`);
      grad.addColorStop(1, `rgba(${rgb}, 0)`);
      g.fillStyle = grad;
      g.fillRect(0, 0, 64, 64);
      return s;
    });

    let width = 0;
    let height = 0;
    let motes: Mote[] = [];

    const seed = () => {
      const count = Math.round((width * height) / (lowPower ? 38000 : 24000));
      motes = Array.from({ length: Math.min(count, 70) }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        z: Math.random(), // 0 = far, 1 = near
        r: 0,
        speed: 0,
        phase: Math.random() * Math.PI * 2,
        color: Math.floor(Math.random() * sprites.length),
      })).map((m) => ({ ...m, r: 3 + m.z * 9, speed: 0.08 + m.z * 0.25 }));
    };

    const resize = () => {
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
    };

    const draw = (t: number) => {
      ctx.clearRect(0, 0, width, height);
      for (const m of motes) {
        const sway = Math.sin(t * 0.0004 + m.phase) * 14 * m.z;
        ctx.globalAlpha = 0.35 + m.z * 0.5;
        const size = m.r * 2;
        ctx.drawImage(sprites[m.color], m.x + sway - m.r, m.y - m.r, size, size);
      }
    };

    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(now - last, 50);
      last = now;
      for (const m of motes) {
        m.y -= m.speed * dt * 0.06;
        if (m.y < -20) {
          m.y = height + 20;
          m.x = Math.random() * width;
        }
      }
      draw(now);
      frame = requestAnimationFrame(tick);
    };

    resize();
    window.addEventListener("resize", resize);

    const start = () => {
      if (reduced || frame) return;
      last = performance.now();
      frame = requestAnimationFrame(tick);
    };
    const stop = () => {
      cancelAnimationFrame(frame);
      frame = 0;
    };
    // Pause when the tab is hidden.
    const onVisibility = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", onVisibility);

    if (reduced) draw(0); // a single still frame
    else start();

    return () => {
      stop();
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <div ref={rootRef} className={styles.atmosphere} aria-hidden="true">
      <span className={`${styles.mist} ${styles.mistSage}`} />
      <span className={`${styles.mist} ${styles.mistLavender}`} />
      <span className={`${styles.mist} ${styles.mistAmber}`} />
      <span className={styles.rays} />
      <canvas ref={canvasRef} className={styles.motes} />
      <span className={styles.vignette} />
      <span className={styles.grain} />
    </div>
  );
}
