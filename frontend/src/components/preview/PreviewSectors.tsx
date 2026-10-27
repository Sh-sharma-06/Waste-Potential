"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties, type MouseEvent } from "react";
import PreviewAtmosphere from "./PreviewAtmosphere";
import { cormorant, rubik, syne } from "./fonts";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";
import styles from "./PreviewSectors.module.css";

type SectorId = "agriculture" | "home" | "industry";

// Destinations are the existing sector experiences (same routes as the main /explore page).
const SECTORS: { id: SectorId; title: string; text: string }[] = [
  { id: "agriculture", title: "Agriculture", text: "Turn crop residue and farm waste into clean bio-energy" },
  { id: "home", title: "Home", text: "Convert everyday household waste into usable power" },
  { id: "industry", title: "Industry", text: "Unlock energy from factory and industrial waste streams" },
];

// Distance (px) at which an object starts reacting to the cursor.
const PROXIMITY_RADIUS = 460;
const LAUNCH_MS = 900;

type Launch = { id: SectorId; x: number; y: number; failed?: boolean };

/** Checks that a destination route actually exists before navigating to it. */
async function routeExists(href: string): Promise<boolean> {
  try {
    const res = await fetch(href, { method: "HEAD", cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

type Props = {
  /** Where the top-left brand link goes. */
  homeHref?: string;
  /** Shows the "Design preview" label (on in the preview, off on the main site). */
  showPreviewChip?: boolean;
  /** "display" = the preview's Syne headlines; "classic" = the main site's Cormorant Garamond. */
  typeface?: "display" | "classic";
};

export default function PreviewSectors({ homeHref = "/preview", showPreviewChip = true, typeface = "display" }: Props) {
  const headFont = typeface === "classic" ? cormorant : syne;
  const router = useRouter();
  const reduced = usePrefersReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const objectRefs = useRef<(HTMLElement | null)[]>([]);
  const [launch, setLaunch] = useState<Launch | null>(null);
  const [unavailable, setUnavailable] = useState<SectorId | null>(null);

  // Cursor response: each object tilts toward the pointer, its light follows it,
  // and it grows more prominent the closer the pointer gets. The whole stage parallaxes.
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || reduced !== false) return;
    if (!window.matchMedia("(pointer: fine)").matches) return;

    let frame = 0;
    let pointer: { x: number; y: number } | null = null;

    const render = () => {
      frame = 0;
      const wide = window.innerWidth > 900;
      if (pointer && wide) {
        const px = (pointer.x / window.innerWidth) * 2 - 1;
        const py = (pointer.y / window.innerHeight) * 2 - 1;
        stage.style.setProperty("--wy", `${(px * 5).toFixed(2)}deg`);
        stage.style.setProperty("--wx", `${(-py * 4).toFixed(2)}deg`);
      } else {
        stage.style.setProperty("--wy", "0deg");
        stage.style.setProperty("--wx", "0deg");
      }

      objectRefs.current.forEach((el) => {
        if (!el) return;
        const r = el.getBoundingClientRect();
        const cx = r.left + r.width / 2;
        const cy = r.top + r.height / 2;
        let p = 0;
        let tx = 0;
        let ty = 0;
        let lx = 50;
        let ly = 0;
        if (pointer) {
          const dx = pointer.x - cx;
          const dy = pointer.y - cy;
          p = Math.max(0, 1 - Math.hypot(dx, dy) / PROXIMITY_RADIUS);
          ty = Math.max(-1, Math.min(1, dx / (r.width / 2))) * 16 * p;
          tx = -Math.max(-1, Math.min(1, dy / (r.height / 2))) * 11 * p;
          lx = ((pointer.x - r.left) / r.width) * 100;
          ly = ((pointer.y - r.top) / r.height) * 100;
        }
        el.style.setProperty("--p", p.toFixed(3));
        el.style.setProperty("--tx", `${tx.toFixed(2)}deg`);
        el.style.setProperty("--ty", `${ty.toFixed(2)}deg`);
        el.style.setProperty("--lx", `${lx.toFixed(1)}%`);
        el.style.setProperty("--ly", `${ly.toFixed(1)}%`);
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

    window.addEventListener("pointermove", onMove);
    document.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
    };
  }, [reduced]);

  // ENTER: the object expands into its colour while we confirm the route exists, then navigate.
  // If the sector experience isn't available in this build, the animation reverses and we say so.
  const onEnter = (e: MouseEvent<HTMLAnchorElement>, id: SectorId, index: number) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    if (launch) return;

    const href = e.currentTarget.getAttribute("href")!;
    const r = objectRefs.current[index]?.getBoundingClientRect();
    setUnavailable(null);
    setLaunch({ id, x: r ? r.left + r.width / 2 : window.innerWidth / 2, y: r ? r.top + r.height / 2 : window.innerHeight / 2 });

    const wait = new Promise((resolve) => window.setTimeout(resolve, reduced ? 0 : LAUNCH_MS));
    Promise.all([routeExists(href), wait]).then(([ok]) => {
      if (ok) {
        router.push(href);
        return;
      }
      // Retract the veil, then explain.
      setLaunch((l) => (l ? { ...l, failed: true } : l));
      window.setTimeout(
        () => {
          setLaunch(null);
          setUnavailable(id);
        },
        reduced ? 0 : 450,
      );
    });
  };

  return (
    <main className={`${styles.page} ${rubik.className} ${typeface === "classic" ? styles.classic : ""}`}>
      <PreviewAtmosphere />

      {/* Continues the light "iris" from the landing page, then fades away. */}
      <div className={styles.arrive} aria-hidden="true" />

      <header className={styles.topbar}>
        <Link href={homeHref} className={`${styles.brand} ${headFont.className}`}>
          ← WASTE-POTENTIAL
        </Link>
        {showPreviewChip && <span className={styles.chip}>Design preview</span>}
      </header>

      <section className={styles.intro}>
        <p className={styles.eyebrow}>Choose your sector</p>
        <h1 className={`${styles.heading} ${headFont.className}`}>
          Where does your
          <br />
          waste begin?
        </h1>
        <p className={styles.hint}>Move closer to a structure to bring it into focus.</p>
      </section>

      <div ref={stageRef} className={styles.stage}>
        <div className={styles.world}>
          {SECTORS.map((s, i) => (
            <article
              key={s.id}
              ref={(el) => {
                objectRefs.current[i] = el;
              }}
              className={`${styles.object} ${styles[s.id]} ${launch?.id === s.id ? styles.launching : ""} ${
                launch && launch.id !== s.id ? styles.receding : ""
              }`}
              style={{ "--n": i } as CSSProperties}
            >
              <div className={styles.float}>
                <div className={styles.box}>
                  {/* The five hidden faces give the glass block real thickness. */}
                  <span className={`${styles.face} ${styles.back}`} aria-hidden="true" />
                  <span className={`${styles.face} ${styles.left}`} aria-hidden="true" />
                  <span className={`${styles.face} ${styles.right}`} aria-hidden="true" />
                  <span className={`${styles.face} ${styles.top}`} aria-hidden="true" />
                  <span className={`${styles.face} ${styles.bottom}`} aria-hidden="true" />

                  <div className={`${styles.face} ${styles.front}`}>
                    {/* Sector-specific light inside the glass (organic / warm / engineered). */}
                    <span className={styles.aura} aria-hidden="true" />
                    <span className={styles.texture} aria-hidden="true" />
                    <span className={styles.specular} aria-hidden="true" />

                    <span className={styles.index}>0{i + 1}</span>
                    <h2 className={`${styles.title} ${headFont.className}`}>{s.title}</h2>
                    <p className={styles.text}>{s.text}</p>
                    <a
                      href={`/explore/${s.id}`}
                      className={styles.enter}
                      onClick={(e) => onEnter(e, s.id, i)}
                      aria-label={`Enter ${s.title}`}
                    >
                      ENTER <span aria-hidden="true">→</span>
                    </a>
                  </div>
                </div>
              </div>
              <span className={styles.shadow} aria-hidden="true" />

              {unavailable === s.id && (
                <p className={styles.notice} role="status">
                  The {s.title} experience isn&apos;t available in this build yet.
                </p>
              )}
            </article>
          ))}
        </div>
      </div>

      {launch && (
        <div
          className={`${styles.launchVeil} ${styles[launch.id]} ${launch.failed ? styles.retract : ""}`}
          style={{ "--ox": `${launch.x}px`, "--oy": `${launch.y}px` } as CSSProperties}
          aria-hidden="true"
        >
          <span className={`${styles.launchTitle} ${headFont.className}`}>
            {SECTORS.find((s) => s.id === launch.id)?.title}
          </span>
        </div>
      )}
    </main>
  );
}
