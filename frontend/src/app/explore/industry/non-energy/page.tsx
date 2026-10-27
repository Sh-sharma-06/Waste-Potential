"use client";
import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { INDUSTRY_PAGE_BG } from "@/lib/industryTheme";

/* ── Industry accent tokens (same as /explore/industry) ── */
const IND = {
  accent: "#C2410C",
  accentSoft: "#EA580C",
  accentDim: "rgba(194,65,12,.45)",
  accentGlow: "rgba(194,65,12,.35)",
  textHeading: "#27120A",
  textBody: "#431E12",
  textMuted: "#6C321E",
  gradBtn: "linear-gradient(90deg,#9A3412 0%,#C2410C 50%,#EA580C 100%)",
  cardBg: "rgba(255, 248, 242, 0.55)",
};
const FONT = '"Rubik",sans-serif';

/* Keys must match CATEGORY_METAS in /market/non-energy, which reads them from the `breakdown` param. */
const MATERIALS = [
  { key: "plastics", label: "Plastics", icon: "🧴", examples: "PET bottles, HDPE drums, films, packaging" },
  { key: "metals", label: "Metals", icon: "🔩", examples: "Steel, aluminium, copper and brass scrap" },
  { key: "electronics", label: "Electronics / E-Waste", icon: "💻", examples: "Circuit boards, cables, devices, batteries" },
  { key: "paper", label: "Paper / Cardboard", icon: "📦", examples: "OCC cartons, office paper, kraft" },
  { key: "glass", label: "Glass", icon: "🍾", examples: "Container glass, cullet, flat glass" },
] as const;

type MaterialKey = (typeof MATERIALS)[number]["key"];

function NonEnergyEntryInner() {
  const router = useRouter();
  const params = useSearchParams();
  const pincode = params.get("pincode") ?? "";
  const address = params.get("address") ?? "";

  const [quantities, setQuantities] = useState<Record<MaterialKey, string>>(
    () => Object.fromEntries(MATERIALS.map((m) => [m.key, ""])) as Record<MaterialKey, string>
  );

  const parsed = useMemo(() => {
    const out: Partial<Record<MaterialKey, number>> = {};
    for (const m of MATERIALS) {
      const v = parseFloat(quantities[m.key]);
      if (Number.isFinite(v) && v > 0) out[m.key] = v;
    }
    return out;
  }, [quantities]);

  const total = Object.values(parsed).reduce((s, v) => s + (v ?? 0), 0);
  const canProceed = total > 0;

  const proceed = () => {
    if (!canProceed) return;
    const q = new URLSearchParams({
      pincode: pincode || "110001",
      mass: String(total),
      breakdown: JSON.stringify(parsed),
    });
    router.push(`/market/non-energy?${q.toString()}`);
  };

  return (
    <main style={{ minHeight: "100vh", fontFamily: FONT, color: IND.textBody, ...INDUSTRY_PAGE_BG, padding: "0 0 80px" }}>
      <header style={{ padding: "28px 5vw 0", display: "flex", flexDirection: "column", gap: 14 }}>
        <Link href="/explore/industry" style={{
          alignSelf: "flex-start", color: IND.textHeading, textDecoration: "none", fontSize: ".95rem", fontWeight: 700,
          letterSpacing: ".08em", border: "1px solid rgba(39,18,10,0.3)", borderRadius: 999, padding: "7px 18px",
          background: "rgba(255,255,255,.55)", backdropFilter: "blur(8px)",
        }}>
          ← Back to Industry Hub
        </Link>
        <h1 style={{
          margin: 0, fontSize: "clamp(1.4rem, 3.5vw, 2.2rem)", fontWeight: 900, letterSpacing: ".12em",
          textTransform: "uppercase", color: IND.textHeading,
        }}>
          Non-Energy Waste Breakdown
        </h1>
        <p style={{ margin: 0, fontSize: ".95rem", color: IND.textBody }}>
          Enter how much of each recyclable material you generate per day
          {pincode ? <> near <strong>PIN {pincode}</strong></> : null}. We&apos;ll match each stream with recyclers and scrap buyers.
        </p>
        {address && <p style={{ margin: 0, fontSize: ".82rem", color: IND.textMuted }}>{address}</p>}
      </header>

      <div style={{ padding: "28px 5vw 0" }}>
        <section style={{
          border: `1.5px solid ${IND.accentDim}`, background: IND.cardBg, backdropFilter: "blur(14px)",
          WebkitBackdropFilter: "blur(14px)", boxShadow: "0 8px 32px rgba(100, 40, 10, 0.18)",
          borderRadius: 20, padding: "28px 32px", boxSizing: "border-box",
        }}>
          <h2 style={{ margin: "0 0 18px", fontSize: "1rem", letterSpacing: ".1em", color: IND.accentSoft, textTransform: "uppercase" }}>
            Daily Quantity by Material (kg/day)
          </h2>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {MATERIALS.map((m) => (
              <label key={m.key} htmlFor={`qty-${m.key}`} style={{
                display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
                padding: "14px 18px", borderRadius: 14, background: "rgba(255,255,255,.6)",
                border: `1px solid ${parsed[m.key] ? IND.accent : "rgba(194,65,12,.18)"}`,
              }}>
                <span style={{ fontSize: "1.6rem" }} aria-hidden="true">{m.icon}</span>
                <span style={{ flex: "1 1 220px", minWidth: 0 }}>
                  <span style={{ display: "block", fontWeight: 700, color: IND.textHeading }}>{m.label}</span>
                  <span style={{ display: "block", fontSize: ".8rem", color: IND.textMuted }}>{m.examples}</span>
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input
                    id={`qty-${m.key}`}
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step="any"
                    placeholder="0"
                    value={quantities[m.key]}
                    onChange={(e) => setQuantities((q) => ({ ...q, [m.key]: e.target.value }))}
                    onKeyDown={(e) => { if (e.key === "Enter") proceed(); }}
                    style={{
                      width: 140, padding: "10px 14px", borderRadius: 10, fontFamily: FONT, fontSize: "1rem",
                      color: IND.textHeading, background: "rgba(255,255,255,.9)",
                      border: "1px solid rgba(194,65,12,.3)", outline: "none", textAlign: "right",
                    }}
                  />
                  <span style={{ fontSize: ".85rem", color: IND.textMuted }}>kg/day</span>
                </span>
              </label>
            ))}
          </div>

          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 16,
            marginTop: 22, paddingTop: 18, borderTop: "1px solid rgba(194,65,12,.18)",
          }}>
            <div>
              <div style={{ fontSize: ".75rem", letterSpacing: ".1em", textTransform: "uppercase", color: IND.textMuted }}>
                Total non-energy volume
              </div>
              <div style={{ fontSize: "1.5rem", fontWeight: 800, color: IND.textHeading }}>
                {total.toLocaleString()} kg/day
                <span style={{ fontSize: ".85rem", fontWeight: 500, color: IND.textMuted }}>
                  {" "}· {Object.keys(parsed).length} of {MATERIALS.length} streams
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={proceed}
              disabled={!canProceed}
              style={{
                padding: "14px 30px", borderRadius: 14, border: "none", fontFamily: FONT, fontWeight: 800,
                fontSize: "1rem", letterSpacing: ".1em", textTransform: "uppercase",
                color: canProceed ? "#FFFFFF" : "rgba(108,50,30,.5)",
                background: canProceed ? IND.gradBtn : "rgba(255,255,255,.4)",
                boxShadow: canProceed ? `0 0 30px ${IND.accentGlow}` : "none",
                cursor: canProceed ? "pointer" : "not-allowed",
              }}
            >
              {canProceed ? "Proceed to Non-Energy Marketplace →" : "Enter at least one quantity"}
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}

export default function NonEnergyEntryPage() {
  return (
    <Suspense fallback={null}>
      <NonEnergyEntryInner />
    </Suspense>
  );
}
