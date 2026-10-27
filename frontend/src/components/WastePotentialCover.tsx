"use client";

import Link from "next/link";
import { Cormorant_Garamond, Rubik } from "next/font/google";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties, type MouseEvent } from "react";
import PreviewAtmosphere from "./preview/PreviewAtmosphere";
import styles from "./WastePotentialCover.module.css";

const display = Cormorant_Garamond({ subsets: ["latin"], weight: ["300", "500"] });
// Rubik matches the /explore page and the sector experiences.
const sans = Rubik({ subsets: ["latin"], weight: ["300", "400", "500"] });

const EXPLORE_HREF = "/explore";

// The title is split into two words so it can wrap after the hyphen on narrow screens.
const TITLE_WORDS = ["WASTE-", "POTENTIAL"];
const TAGLINE = "The Potential Was Always There. We Just Found It";

// How far (in px) from the cursor a letter still reacts.
const INFLUENCE_RADIUS = 220;

// Highlight colours cycled across the title letters: one per sector (Agriculture, Home, Industry).
const LETTER_HIGHLIGHTS = ["#46634B", "#68558F", "#A9692F"];

// Builds an SVG <animate> that morphs a path through the given shapes and back again.
// Every shape must use the same commands (M, C, S) so the browser can blend between them.
function morph(shapes: string[], seconds: number) {
  const values = [...shapes, shapes[0]];
  const steps = values.length - 1;
  return (
    <animate
      attributeName="d"
      dur={`${seconds}s`}
      repeatCount="indefinite"
      values={values.join(";")}
      keyTimes={values.map((_, i) => (i / steps).toFixed(3)).join(";")}
      calcMode="spline"
      keySplines={Array(steps).fill("0.45 0 0.55 1").join(";")}
    />
  );
}

// Ribbon curves in a 1440×900 canvas. Each ribbon morphs between three shapes.
const RIBBONS = {
  lower: morph(
    [
      "M-200 620 C 200 460, 560 820, 900 600 S 1500 380, 1700 520",
      "M-200 540 C 240 740, 620 470, 940 650 S 1480 580, 1700 410",
      "M-200 680 C 160 520, 520 700, 880 520 S 1520 470, 1700 600",
    ],
    14,
  ),
  upper: morph(
    [
      "M-200 250 C 260 110, 620 420, 1000 240 S 1520 110, 1700 300",
      "M-200 330 C 300 400, 660 140, 1020 310 S 1500 270, 1700 180",
      "M-200 200 C 220 210, 600 360, 980 190 S 1540 190, 1700 350",
    ],
    18,
  ),
  lowerLine: morph(
    [
      "M-200 700 C 200 540, 560 900, 900 680 S 1500 460, 1700 600",
      "M-200 610 C 240 820, 620 550, 940 730 S 1480 660, 1700 490",
      "M-200 760 C 160 600, 520 780, 880 600 S 1520 550, 1700 680",
    ],
    14,
  ),
  upperLine: morph(
    [
      "M-200 180 C 260 40, 620 350, 1000 170 S 1520 40, 1700 230",
      "M-200 260 C 300 330, 660 70, 1020 240 S 1500 200, 1700 110",
      "M-200 130 C 220 140, 600 290, 980 120 S 1540 120, 1700 280",
    ],
    18,
  ),
};

export default function WastePotentialCover() {
  const router = useRouter();
  const titleRef = useRef<HTMLHeadingElement>(null);
  const ribbonsRef = useRef<SVGSVGElement>(null);
  const [iris, setIris] = useState<{ x: number; y: number } | null>(null);

  useEffect(() => {
    router.prefetch(EXPLORE_HREF);
  }, [router]);

  // Cursor-responsive lettering: each letter lifts and warms as the pointer nears it.
  useEffect(() => {
    const title = titleRef.current;
    if (!title) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const finePointer = window.matchMedia("(pointer: fine)").matches;
    if (reduceMotion || !finePointer) return;

    const letters = Array.from(title.querySelectorAll<HTMLElement>("[data-letter]"));
    let centers: { x: number; y: number }[] = [];
    let frame = 0;
    let pointer: { x: number; y: number } | null = null;

    const measure = () => {
      centers = letters.map((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      });
    };

    const render = () => {
      frame = 0;
      letters.forEach((el, i) => {
        let influence = 0;
        if (pointer && centers[i]) {
          const d = Math.hypot(pointer.x - centers[i].x, pointer.y - centers[i].y);
          influence = Math.max(0, 1 - d / INFLUENCE_RADIUS);
        }
        el.style.setProperty("--i", influence.toFixed(3));
      });
    };

    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(render);
    };

    const onMove = (e: PointerEvent) => {
      pointer = { x: e.clientX, y: e.clientY };
      schedule();
    };
    const onLeave = () => {
      pointer = null;
      schedule();
    };

    // Measure after the entrance animation has settled, and again on resize.
    const settle = window.setTimeout(measure, 1800);
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("pointermove", onMove);
    document.addEventListener("pointerleave", onLeave);

    return () => {
      window.clearTimeout(settle);
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", measure);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  // CSS can't stop the SVG ribbon morphing, so pause it here for reduced-motion users.
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      ribbonsRef.current?.pauseAnimations();
    }
  }, []);

  // Explore: an iris of light opens from the button, then the sector page takes over.
  const onExplore = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      router.push(EXPLORE_HREF);
      return;
    }
    const r = e.currentTarget.getBoundingClientRect();
    setIris({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
    window.setTimeout(() => router.push(EXPLORE_HREF), 820);
  };

  let letterIndex = 0;

  return (
    <main className={`${styles.cover} ${sans.className}`}>
      {/* Light, mist, drifting particles: the same atmosphere as the design preview. */}
      <PreviewAtmosphere />

      {/* Flowing ribbon waves, layered over the atmosphere: curves slowly reshape themselves. */}
      <div className={styles.waves} aria-hidden="true">
        <svg
          ref={ribbonsRef}
          className={styles.ribbons}
          viewBox="0 0 1440 900"
          preserveAspectRatio="xMidYMid slice"
        >
          <defs>
            {/* Sage flowing into lavender. */}
            <linearGradient id="wp-ribbon-a" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#A8C3A0" stopOpacity="0.55" />
              <stop offset="50%" stopColor="#DDE9D8" stopOpacity="0.5" />
              <stop offset="100%" stopColor="#B9A7D9" stopOpacity="0.45" />
            </linearGradient>
            {/* Lavender flowing into warm sand. */}
            <linearGradient id="wp-ribbon-b" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#E8E0F5" stopOpacity="0.2" />
              <stop offset="45%" stopColor="#B9A7D9" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#E7C9A3" stopOpacity="0.65" />
            </linearGradient>
          </defs>

          <g className={styles.ribbonSoft}>
            <path className={styles.ribbonWide} stroke="url(#wp-ribbon-a)" strokeWidth="170">
              {RIBBONS.lower}
            </path>
            <path className={styles.ribbonWide} stroke="url(#wp-ribbon-b)" strokeWidth="110">
              {RIBBONS.upper}
            </path>
          </g>

          <g className={styles.ribbonLines}>
            <path stroke="#FFFFFF" strokeWidth="1.5" strokeOpacity="0.9" fill="none">
              {RIBBONS.lowerLine}
            </path>
            <path stroke="#68558F" strokeWidth="1" strokeOpacity="0.18" fill="none">
              {RIBBONS.upperLine}
            </path>
          </g>
        </svg>
      </div>

      <div className={styles.content}>
        <p className={styles.eyebrow}>Rethink · Recover · Reimagine</p>

        <h1 ref={titleRef} className={`${styles.title} ${display.className}`} aria-label="WASTE-POTENTIAL">
          {TITLE_WORDS.map((word) => (
            <span key={word} className={styles.word} aria-hidden="true">
              {word.split("").map((char) => {
                const index = letterIndex++;
                return (
                  <span
                    key={index}
                    className={styles.letterIn}
                    style={{ animationDelay: `${300 + index * 55}ms` }}
                  >
                    <span
                      data-letter
                      className={styles.letter}
                      style={{ "--hl": LETTER_HIGHLIGHTS[index % LETTER_HIGHLIGHTS.length] } as CSSProperties}
                    >
                      {char}
                    </span>
                  </span>
                );
              })}
            </span>
          ))}
        </h1>

        <span className={styles.rule} aria-hidden="true" />

        <p className={`${styles.tagline} ${display.className}`}>{TAGLINE}</p>

        {/* Wrapper layers: entrance, then a gentle float, so hover can lift the link itself. */}
        <div className={styles.ctaWrap}>
          <div className={styles.ctaFloat}>
            <Link href={EXPLORE_HREF} className={styles.cta} onClick={onExplore}>
              <span className={styles.ctaLabel}>EXPLORE</span>
              <span className={styles.ctaArrow} aria-hidden="true">
                →
              </span>
            </Link>
          </div>
        </div>
      </div>

      {iris && (
        <div
          className={styles.iris}
          style={{ "--ix": `${iris.x}px`, "--iy": `${iris.y}px` } as CSSProperties}
          aria-hidden="true"
        />
      )}
    </main>
  );
}
