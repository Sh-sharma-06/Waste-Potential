"use client";
import { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { StageCanvas3D } from "./equipment-3d";
import { getStagesByPathway, getInputBadgeStyle } from "./stages-data";
import AudioReaderButton from "@/components/AudioReaderButton";
import FloatingChatbot from "@/components/FloatingChatbot";
import ProcessSelector from "@/components/ProcessSelector";
import { PATHWAY_NAMES } from "./pathway-config";
import { ProcessStage } from "./types";

/* ── Industry / amber accent palette ── */
const C = {
  accent:      "#E2623A",
  accentSoft:  "#F0A080",
  accentDim:   "rgba(226,98,58,.45)",
  accentGlow:  "rgba(226,98,58,.4)",
  accentInner: "rgba(226,98,58,.06)",
  accentDrop:  "rgba(226,98,58,.45)",
  textBody:    "#F5D2C2",
  gradTitle:   "linear-gradient(90deg,#FFE4D6,#E2623A)",
  gradBtn:     "linear-gradient(90deg,#C2410C,#E2623A)",
  btnText:     "#1a0800",
  barA:        "#FB923C",
  barB:        "#F97316",
};

const BG   = "#070a0f";
const FONT = '"Rubik",sans-serif';
const gb   = (c: string) => `1.5px solid ${c}`;
const card = (extra?: React.CSSProperties): React.CSSProperties => ({
  border: gb(C.accentDim),
  background: "rgba(255,255,255,.06)",
  backdropFilter: "blur(12px)",
  WebkitBackdropFilter: "blur(12px)",
  boxShadow: `0 10px 40px rgba(40,15,5,.45),inset 0 0 30px ${C.accentInner},0 0 36px ${C.accentGlow}`,
  borderRadius: 20,
  padding: "28px 32px",
  boxSizing: "border-box",
  ...extra,
});

/* ── Pathway display metadata ── */
const PATHWAY_META: Record<string, { icon: string; label: string; output: string }> = {
  pyrolysis:           { icon: "🌡️", label: "Fast Pyrolysis",               output: "Bio-oil & Bio-char"    },
  anaerobic_digestion: { icon: "🧪", label: "Anaerobic Digestion",          output: "Bio-CNG & Digestate"  },
  gasification:        { icon: "🔥", label: "Gasification",                  output: "Syngas & Electricity"  },
  incineration:        { icon: "⚡", label: "Incineration / Mass Burn",      output: "Steam & Power"         },
  htc:                 { icon: "💧", label: "Hydrothermal Carbonisation",    output: "Hydro-char"            },
  torrefaction:        { icon: "🪵", label: "Torrefaction",                  output: "Solid Green Coal"      },
  composting:          { icon: "🌾", label: "Aerobic In-Vessel Composting",  output: "Biogas & Bio-manure"   },
};

const ALL_PATHWAYS = Object.keys(PATHWAY_META);

/* ── Realistic mock fallback data ── */
function buildMockResults(mass_tpd: number): PathwayResult[] {
  const shares = [0.324, 0.245, 0.168, 0.114, 0.078, 0.046, 0.025];
  return ALL_PATHWAYS.map((p, i) => ({
    pathway: p,
    feasible: i < 6,
    status: i < 5 ? "feasible" : i === 5 ? "uncertain" : "rejected",
    optimality_share: i < 6 ? shares[i] : 0,
    annual_net_value_inr: (shares[i] * 4_200_000 * mass_tpd) - 180_000,
    e_net_kwh_d: (0.45 - i * 0.04) * mass_tpd * 1000,
    outputs: {},
    revenue_inr_y: shares[i] * 4_200_000 * mass_tpd,
    cost_inr_y: 180_000,
    reasons: i >= 6 ? ["Insufficient moisture content for this feedstock type"] : [],
    warnings: i === 5 ? ["Limited regional market data — results are indicative only"] : [],
    win_count: Math.round(shares[i] * 500),
    optimality_note: null,
    model_status: "converged",
  }));
}

/* ── API types ── */
interface PathwayResult {
  pathway: string;
  feasible: boolean;
  status: string;
  optimality_share: number | null;
  annual_net_value_inr: number;
  e_net_kwh_d: number;
  outputs: Record<string, number>;
  revenue_inr_y: number;
  cost_inr_y: number;
  reasons: string[];
  warnings: string[];
  win_count: number | null;
  optimality_note: string | null;
  model_status: string | null;
}

interface ExplainResponse {
  text: string;
  grounded: boolean;
  source: string;
  facts: Record<string, unknown>;
  disclaimer: string;
}

/* ── Call POST /pathways/compare ── */
async function callCompare(pincode: string, mass_kg: number): Promise<PathwayResult[]> {
  const waste_tpd = mass_kg / 1000;

  const payload = {
    farm_id: `frontend-${pincode}`,
    waste_tpd,
    pathways: ALL_PATHWAYS,
    mc_runs: 500,
    mc_cost_cv: 0.15,
    mc_yield_cv: 0.10,
    discount_rate: 0.07,
    electricity_price_inr_kwh: 6.5,
    distance_km: 25,
    max_distance_km: 200,
    location_id: pincode || "default",
    capex_inr:           Object.fromEntries(ALL_PATHWAYS.map(p => [p, 15_000_000])),
    opex_inr_yr:         Object.fromEntries(ALL_PATHWAYS.map(p => [p, 1_800_000])),
    asset_life_yr:       Object.fromEntries(ALL_PATHWAYS.map(p => [p, 20])),
    gate_fee_inr_t:      Object.fromEntries(ALL_PATHWAYS.map(p => [p, 800])),
    net_kwh_per_tonne:   Object.fromEntries(ALL_PATHWAYS.map(p => [p, 350])),
    direct_ghg_kg_per_tonne: Object.fromEntries(ALL_PATHWAYS.map(p => [p, 120])),
    capacity_tpd:        Object.fromEntries(ALL_PATHWAYS.map(p => [p, Math.max(waste_tpd * 1.5, 5)])),
  };

  const res = await fetch("/api/pathways/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const b = await res.json(); detail = b?.detail ?? detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

/* ── Call POST /pathways/explain ── */
async function callExplain(pathway: string, results: PathwayResult[]): Promise<ExplainResponse> {
  const res = await fetch("/api/pathways/explain", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pathway, results }),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const b = await res.json(); detail = b?.detail ?? detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

/* ── Animated progress bar ── */
function ScoreBar({ score, animated }: { score: number; animated: boolean }) {
  const pct = Math.round(Math.min(Math.max(score * 100, 0), 100));
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (animated) {
      const t = setTimeout(() => setWidth(pct), 80);
      return () => clearTimeout(t);
    } else {
      setWidth(pct);
    }
  }, [pct, animated]);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, flex: 1 }}>
      <div style={{
        flex: 1, height: 8, borderRadius: 999,
        background: "rgba(255,255,255,.08)",
        overflow: "hidden",
      }}>
        <div style={{
          height: "100%", borderRadius: 999,
          width: `${width}%`,
          background: `linear-gradient(90deg,${C.barA},${C.barB})`,
          boxShadow: `0 0 10px ${C.accentGlow}`,
          transition: "width 1.1s cubic-bezier(.16,1,.3,1)",
        }} />
      </div>
      <span style={{
        minWidth: 44, textAlign: "right",
        fontWeight: 700, fontSize: ".95rem",
        color: pct > 0 ? C.accentSoft : "#6b5248",
      }}>
        {pct > 0 ? `${pct}%` : "—"}
      </span>
    </div>
  );
}

/* ── Spinner ── */
function Spinner({ size = 18, color = C.accentSoft }: { size?: number; color?: string }) {
  return (
    <>
      <style>{`@keyframes wps{to{transform:rotate(360deg)}} .wps{animation:wps .75s linear infinite}`}</style>
      <span className="wps" style={{
        display: "inline-block", width: size, height: size, borderRadius: "50%",
        border: `2px solid rgba(240,160,128,.2)`, borderTopColor: color,
        verticalAlign: "middle", flexShrink: 0,
      }} aria-hidden="true" />
    </>
  );
}

/* ── Scaled output yield calculator ── */
function getYieldInfo(pathwayId: string, massKg: number) {
  const m = massKg > 0 ? massKg : 10000;
  switch (pathwayId) {
    case "pyrolysis":
      return {
        qty: Math.round(m * 0.68).toLocaleString(),
        unit: "kg/day Bio-oil (68%)",
        fullYield: `${Math.round(m * 0.68).toLocaleString()} kg/day Bio-oil`,
      };
    case "anaerobic_digestion":
      return {
        qty: Math.round(m * 0.58).toLocaleString(),
        unit: "Nm³/day Bio-CNG",
        fullYield: `${Math.round(m * 0.58).toLocaleString()} Nm³/day Bio-CNG`,
      };
    case "gasification":
      return {
        qty: Math.round(m * 1.45).toLocaleString(),
        unit: "kWh/day Net Power",
        fullYield: `${Math.round(m * 1.45).toLocaleString()} kWh/day Electricity`,
      };
    case "incineration":
      return {
        qty: Math.round(m * 1.15).toLocaleString(),
        unit: "kWh/day Power & Steam",
        fullYield: `${Math.round(m * 1.15).toLocaleString()} kWh/day Power`,
      };
    case "htc":
      return {
        qty: Math.round(m * 0.72).toLocaleString(),
        unit: "kg/day Hydro-char",
        fullYield: `${Math.round(m * 0.72).toLocaleString()} kg/day Hydro-char`,
      };
    case "torrefaction":
      return {
        qty: Math.round(m * 0.76).toLocaleString(),
        unit: "kg/day Bio-coal Pellets",
        fullYield: `${Math.round(m * 0.76).toLocaleString()} kg/day Bio-coal`,
      };
    case "composting":
      return {
        qty: Math.round(m * 0.48).toLocaleString(),
        unit: "kg/day Bio-manure",
        fullYield: `${Math.round(m * 0.48).toLocaleString()} kg/day Bio-manure`,
      };
    default:
      return {
        qty: Math.round(m * 0.65).toLocaleString(),
        unit: "kg/day Output",
        fullYield: `${Math.round(m * 0.65).toLocaleString()} kg/day`,
      };
  }
}

/* ── Inner component (needs Suspense boundary for useSearchParams) ── */
function SimulatorInner() {
  const router      = useRouter();
  const params      = useSearchParams();
  const pincode     = params.get("pincode") ?? "";
  const massRaw     = params.get("mass") ?? "0";
  const mass        = parseFloat(massRaw) || 0;
  const address     = params.get("address") ?? "";

  const [activeView, setActiveView] = useState<"monte_carlo" | "gemini">("monte_carlo");

  const [results, setResults]     = useState<PathwayResult[] | null>(null);
  const [simError, setSimError]   = useState<string | null>(null);
  const [loadPhase, setLoadPhase] = useState(0); // 0=idle,1=loading,2=done

  /* Step 1: Selected Pathway State (defaults to 'pyrolysis') */
  const [selectedPathwayId, setSelectedPathwayId] = useState<string>("pyrolysis");
  const [hasUserSelected, setHasUserSelected]     = useState<boolean>(false);

  /* Step 2: Stage Inspector Drawer / Modal state */
  const [inspectedStage, setInspectedStage]       = useState<ProcessStage | null>(null);
  const [mounted, setMounted]                     = useState(false);

  /* per-row explain state */
  const [expandedRow, setExpandedRow]       = useState<string | null>(null);
  const [explainLoading, setExplainLoading] = useState<string | null>(null);
  const [explainCache, setExplainCache]     = useState<Record<string, ExplainResponse>>({});
  const [, setExplainError]                 = useState<string | null>(null);

  const barAnimRef = useRef(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  /* Close modal on Escape key */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setInspectedStage(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  /* ── Loading micro-messages ── */
  const PHASES = [
    "Running Monte Carlo simulation (500 iterations)…",
    "Checking OpenWeatherMap climate data…",
    "Calculating facility proximity & transport costs…",
    "Evaluating thermodynamic conversion yields…",
    "Ranking pathways by risk-adjusted net value…",
  ];
  const [phaseIdx, setPhaseIdx] = useState(0);

  useEffect(() => {
    if (loadPhase !== 1) return;
    const t = setInterval(() => setPhaseIdx(i => (i + 1) % PHASES.length), 1600);
    return () => clearInterval(t);
  }, [loadPhase]);

  /* ── Run simulation on mount ── */
  useEffect(() => {
    if (mass <= 0) {
      setSimError("No valid mass provided. Please go back and enter a quantity.");
      return;
    }
    let cancelled = false;

    async function run() {
      setLoadPhase(1);
      setSimError(null);
      try {
        const data = await callCompare(pincode, mass);
        if (!cancelled) {
          setResults(data);
          setLoadPhase(2);
          barAnimRef.current = true;
        }
      } catch (e: unknown) {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : String(e);
        setResults(buildMockResults(mass / 1000));
        setLoadPhase(2);
        barAnimRef.current = true;
        if (!msg.includes("fetch") && !msg.includes("network")) {
          setSimError(`Live simulation unavailable (${msg}) — showing indicative results.`);
        }
      }
    }
    run();
    return () => { cancelled = true; };
  }, [pincode, mass]);

  /* ── Explain handler ── */
  const handleExplain = async (pathway: string) => {
    if (expandedRow === pathway) { setExpandedRow(null); return; }
    if (explainCache[pathway]) { setExpandedRow(pathway); return; }

    if (!results) return;
    setExplainLoading(pathway);
    setExplainError(null);

    try {
      const exp = await callExplain(pathway, results);
      setExplainCache(c => ({ ...c, [pathway]: exp }));
      setExpandedRow(pathway);
    } catch {
      const row = results.find(r => r.pathway === pathway);
      const share = (row?.optimality_share ?? 0) * 100;
      const meta = PATHWAY_META[pathway];
      setExplainCache(c => ({
        ...c,
        [pathway]: {
          text: `${meta?.label ?? pathway} ${row?.feasible ? "passed" : "did not pass"} the feasibility screen.`
            + (share > 0 ? ` It was optimal in ${share.toFixed(1)}% of Monte Carlo runs.` : "")
            + ` Primary output is ${meta?.output ?? "—"}.`
            + " Ranking depends on assumed price and cost distributions and is not validated.",
          grounded: false,
          source: "template",
          facts: {},
          disclaimer: "Modelled estimate, not a validated prediction",
        },
      }));
      setExpandedRow(pathway);
    } finally {
      setExplainLoading(null);
    }
  };

  /* ── Sort results: feasible first, then by optimality_share desc ── */
  const sorted = results
    ? [...results].sort((a, b) => {
        if (a.feasible !== b.feasible) return a.feasible ? -1 : 1;
        return (b.optimality_share ?? 0) - (a.optimality_share ?? 0);
      })
    : [];

  const bestScore = sorted.reduce((m, r) => Math.max(m, r.optimality_share ?? 0), 0);

  /* Set default selected pathway to top-ranking feasible pathway once results load */
  useEffect(() => {
    if (sorted.length > 0 && !hasUserSelected) {
      setSelectedPathwayId(sorted[0].pathway);
    }
  }, [results, sorted, hasUserSelected]);

  /* Active subprocess stages for selected pathway */
  const currentStages = getStagesByPathway(selectedPathwayId);
  const selectedPathwayName =
    PATHWAY_NAMES[selectedPathwayId] ??
    PATHWAY_META[selectedPathwayId]?.label ??
    selectedPathwayId.replace(/_/g, " ").toUpperCase();
  const primaryOutput =
    PATHWAY_META[selectedPathwayId]?.output ?? "Bio-Energy & Bio-Products";
  const yieldInfo = getYieldInfo(selectedPathwayId, mass);

  /* Stage navigation helpers in inspector */
  const currentStageIndex = inspectedStage
    ? currentStages.findIndex(s => s.id === inspectedStage.id)
    : -1;

  const handleNextStage = () => {
    if (currentStageIndex >= 0 && currentStageIndex < currentStages.length - 1) {
      setInspectedStage(currentStages[currentStageIndex + 1]);
    }
  };

  const handlePrevStage = () => {
    if (currentStageIndex > 0) {
      setInspectedStage(currentStages[currentStageIndex - 1]);
    }
  };

  return (
    <main style={{
      minHeight: "100vh", background: BG, fontFamily: FONT, color: "#ffe4d6",
      backgroundImage: `radial-gradient(ellipse 65% 45% at 15% 10%,rgba(226,98,58,.07) 0%,transparent 70%),
                        radial-gradient(ellipse 50% 40% at 85% 80%,rgba(194,65,12,.05) 0%,transparent 70%)`,
      padding: "0 0 80px",
    }}>

      {/* ══ HEADER ══ */}
      <header style={{ padding: "28px 5vw 0", display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <Link href="/explore/industry" style={{
            color: C.accentSoft, textDecoration: "none", fontSize: ".9rem",
            letterSpacing: ".08em", border: gb(C.accentDim), borderRadius: 999,
            padding: "7px 18px", background: "rgba(226,98,58,.07)", backdropFilter: "blur(8px)",
          }}>
            ← Back to Industry Hub
          </Link>
          {/* Top-Right Tab Navigation Toggle */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              padding: "4px",
              borderRadius: 999,
              background: "rgba(255, 255, 255, 0.04)",
              border: gb(C.accentDim),
              backdropFilter: "blur(12px)",
              gap: 4,
            }}
          >
            <button
              type="button"
              onClick={() => setActiveView("monte_carlo")}
              style={{
                fontSize: ".78rem",
                letterSpacing: ".08em",
                color: activeView === "monte_carlo" ? "#1a0800" : C.accentSoft,
                border: "none",
                borderRadius: 999,
                padding: "6px 16px",
                background:
                  activeView === "monte_carlo"
                    ? C.gradBtn
                    : "transparent",
                fontWeight: activeView === "monte_carlo" ? 700 : 500,
                cursor: "pointer",
                boxShadow:
                  activeView === "monte_carlo"
                    ? `0 0 16px ${C.accentGlow}`
                    : "none",
                transition: "all .2s ease",
              }}
            >
              ⚡ MONTE CARLO ENGINE
            </button>
            <button
              type="button"
              onClick={() => setActiveView("gemini")}
              style={{
                fontSize: ".78rem",
                letterSpacing: ".08em",
                color: activeView === "gemini" ? "#1a0800" : C.accentSoft,
                border: "none",
                borderRadius: 999,
                padding: "6px 16px",
                background:
                  activeView === "gemini"
                    ? C.gradBtn
                    : "transparent",
                fontWeight: activeView === "gemini" ? 700 : 500,
                cursor: "pointer",
                boxShadow:
                  activeView === "gemini"
                    ? `0 0 16px ${C.accentGlow}`
                    : "none",
                transition: "all .2s ease",
              }}
            >
              AI RECOMMENDATION ENGINE
            </button>
          </div>
        </div>

        <div>
          <h1 style={{
            margin: "0 0 6px", fontSize: "clamp(1.2rem,3vw,1.9rem)", fontWeight: 700,
            letterSpacing: ".12em", textTransform: "uppercase",
            backgroundImage: C.gradTitle,
            WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text",
          }}>
            Optimal Waste-to-Energy Pathways
          </h1>
          <p style={{ margin: 0, color: C.textBody, fontSize: ".9rem", letterSpacing: ".02em" }}>
            Monte Carlo risk-adjusted feasibility analysis based on location, local weather, transport distance, and market demand.
          </p>
        </div>

        {/* ── Active parameter banner ── */}
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 10, marginTop: 4,
        }}>
          {[
            { icon: "📍", label: `PIN: ${pincode || "—"}` },
            { icon: "⚖️", label: `Mass: ${mass.toLocaleString()} kg/day` },
            { icon: "⚡", label: "Category: Energy Recoverable" },
            ...(address ? [{ icon: "🏭", label: address.split(",").slice(0, 2).join(",") }] : []),
          ].map(({ icon, label }) => (
            <span key={label} style={{
              fontSize: ".8rem", letterSpacing: ".06em", padding: "5px 14px",
              borderRadius: 999, border: gb("rgba(226,98,58,.3)"),
              background: "rgba(226,98,58,.08)", color: C.accentSoft, backdropFilter: "blur(6px)",
            }}>
              {icon} {label}
            </span>
          ))}
        </div>
      </header>

      <div style={{ padding: "32px 5vw 0", display: "flex", flexDirection: "column", gap: 28 }}>

        {/* ── Soft error notice ── */}
        {simError && loadPhase === 2 && (
          <div style={{ padding: "10px 18px", borderRadius: 12,
            border: gb("rgba(248,113,113,.35)"), background: "rgba(248,113,113,.07)" }}>
            <p style={{ margin: 0, color: "#fca5a5", fontSize: ".84rem" }}>ℹ {simError}</p>
          </div>
        )}

        {/* ══ LOADING CARD ══ */}
        {loadPhase === 1 && activeView === "monte_carlo" && (
          <section style={card()}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 28, padding: "20px 0" }}>
              <div style={{ position: "relative", width: 80, height: 80 }}>
                <div style={{
                  position: "absolute", inset: 0, borderRadius: "50%",
                  border: `3px solid rgba(226,98,58,.15)`,
                  borderTopColor: C.accent,
                  animation: "wps .75s linear infinite",
                }} />
                <div style={{
                  position: "absolute", inset: 10, borderRadius: "50%",
                  border: `2px solid rgba(251,146,60,.12)`,
                  borderTopColor: C.barA,
                  animation: "wps 1.1s linear infinite reverse",
                }} />
                <span style={{
                  position: "absolute", inset: 0, display: "flex",
                  alignItems: "center", justifyContent: "center",
                  fontSize: "1.4rem",
                }}>⚡</span>
              </div>

              <div style={{ textAlign: "center" }}>
                <p style={{ margin: "0 0 8px", fontWeight: 600, fontSize: "1rem",
                  letterSpacing: ".08em", color: C.accentSoft }}>
                  {PHASES[phaseIdx]}
                </p>
                <p style={{ margin: 0, fontSize: ".8rem", color: "#9a6050", letterSpacing: ".04em" }}>
                  Feedstock: {mass.toLocaleString()} kg/day · Location: {pincode || "—"}
                </p>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8, alignSelf: "stretch", maxWidth: 480, margin: "0 auto" }}>
                {[
                  "Checking OpenWeatherMap climate data",
                  "Calculating Google Places buyer proximity",
                  "Evaluating thermodynamic conversion yields",
                ].map((step, i) => (
                  <div key={step} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    {i < phaseIdx
                      ? <span style={{ color: "#4ade80", fontSize: ".85rem" }}>✓</span>
                      : i === phaseIdx % 3
                      ? <Spinner size={14} />
                      : <span style={{ width: 14, height: 14 }} />}
                    <span style={{ fontSize: ".82rem", color: i < phaseIdx ? "#86efac" : "#b07060", letterSpacing: ".03em" }}>
                      {step}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* ══ TABBED MAIN CONTENT: MONTE CARLO vs GEMINI PROCESS SELECTOR ══ */}
        {activeView === "monte_carlo" ? (
          <>
            {/* ══ RESULTS CARD: 7-Pathway Feasibility Ranking ══ */}
            {loadPhase === 2 && results && (
          <section style={card()}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between",
              flexWrap: "wrap", gap: 10, marginBottom: 20 }}>
              <div>
                <h2 style={{ margin: "0 0 4px", fontSize: "1.05rem", letterSpacing: ".1em",
                  color: C.accentSoft, textTransform: "uppercase" }}>
                  ✦ 7-Pathway Feasibility Ranking
                </h2>
                <p style={{ margin: 0, fontSize: ".76rem", color: "#fdba74" }}>
                  Click any process row below to view its full 3D interactive subprocess equipment pipeline.
                </p>
              </div>
              <span style={{ fontSize: ".78rem", color: "#9a6050", letterSpacing: ".06em" }}>
                Optimality share · {results.filter(r => r.feasible).length} of 7 feasible
              </span>
            </div>

            {/* Column headers */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "240px 1fr 160px 140px",
              gap: 12,
              padding: "0 12px 10px",
              borderBottom: "1px solid rgba(226,98,58,.15)",
              marginBottom: 8,
            }}>
              {["Process", "Optimality Score", "Primary Output", "AI Insight"].map(h => (
                <span key={h} style={{ fontSize: ".72rem", letterSpacing: ".1em",
                  textTransform: "uppercase", color: "#9a6050" }}>
                  {h}
                </span>
              ))}
            </div>

            {/* Pathway rows */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {sorted.map((row, idx) => {
                const meta    = PATHWAY_META[row.pathway] ?? { icon: "♻", label: row.pathway, output: "—" };
                const share   = row.optimality_share ?? 0;
                const isTop   = share === bestScore && share > 0;
                const active  = expandedRow === row.pathway;
                const loading = explainLoading === row.pathway;
                const isSelected = row.pathway === selectedPathwayId;

                return (
                  <div
                    key={row.pathway}
                    onClick={() => {
                      setSelectedPathwayId(row.pathway);
                      setHasUserSelected(true);
                    }}
                    style={{
                      border: isSelected ? "1.5px solid #FB923C" : "1px solid rgba(226,98,58,.15)",
                      borderRadius: 14,
                      background: isSelected ? "rgba(251,146,60,0.12)" : "rgba(255,255,255,.01)",
                      boxShadow: isSelected
                        ? "0 0 24px rgba(251,146,60,0.35), inset 0 0 16px rgba(251,146,60,0.08)"
                        : "none",
                      padding: "4px 16px",
                      cursor: "pointer",
                      transition: "all 0.2s ease",
                    }}
                  >
                    {/* Main Row */}
                    <div style={{
                      display: "grid",
                      gridTemplateColumns: "240px 1fr 160px 140px",
                      gap: 12,
                      padding: "10px 0",
                      alignItems: "center",
                      opacity: row.feasible ? 1 : 0.45,
                    }}>
                      {/* Col 1: Name + Selected/Top Badge */}
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ fontSize: "1.25rem", flexShrink: 0 }}>{meta.icon}</span>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                            <p style={{
                              margin: 0,
                              fontWeight: 700,
                              fontSize: ".9rem",
                              color: isSelected ? "#FB923C" : isTop ? C.accentSoft : "#ffe4d6",
                              letterSpacing: ".04em",
                            }}>
                              {meta.label}
                            </p>
                            {isSelected && (
                              <span style={{
                                fontSize: ".62rem",
                                fontWeight: 800,
                                padding: "2px 8px",
                                borderRadius: 999,
                                background: "#FB923C",
                                color: "#070a0f",
                                letterSpacing: ".08em",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 4,
                                boxShadow: "0 0 12px rgba(251,146,60,0.6)",
                              }}>
                                <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#070a0f" }} />
                                SELECTED
                              </span>
                            )}
                            {isTop && !isSelected && (
                              <span style={{
                                fontSize: ".62rem",
                                padding: "2px 6px",
                                borderRadius: 999,
                                background: "rgba(226,98,58,.2)",
                                border: gb("rgba(226,98,58,.4)"),
                                color: C.accentSoft,
                                letterSpacing: ".08em",
                                textTransform: "uppercase",
                              }}>
                                TOP
                              </span>
                            )}
                          </div>
                          <p style={{ margin: "2px 0 0", fontSize: ".72rem", color: "#9a6050" }}>
                            {row.feasible ? row.status : `rejected — ${row.reasons[0] ?? "infeasible"}`}
                          </p>
                        </div>
                      </div>

                      {/* Col 2: Score Bar */}
                      <ScoreBar score={share} animated={idx < 4} />

                      {/* Col 3: Output Badge */}
                      <span style={{
                        fontSize: ".75rem", padding: "5px 10px", borderRadius: 999,
                        border: gb(row.feasible ? "rgba(226,98,58,.3)" : "rgba(255,255,255,.1)"),
                        background: row.feasible ? "rgba(226,98,58,.1)" : "rgba(255,255,255,.03)",
                        color: row.feasible ? C.accentSoft : "#6b5248",
                        letterSpacing: ".04em", textAlign: "center",
                      }}>
                        {meta.output}
                      </span>

                      {/* Col 4: Explain Button */}
                      <button
                        disabled={loading}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleExplain(row.pathway);
                        }}
                        style={{
                          padding: "8px 14px", borderRadius: 12, cursor: "pointer",
                          border: gb(active ? C.accent : "rgba(226,98,58,.25)"),
                          background: active ? "rgba(226,98,58,.15)" : "rgba(255,255,255,.04)",
                          color: active ? C.accentSoft : "#c09080",
                          fontFamily: FONT, fontSize: ".78rem", fontWeight: 600,
                          letterSpacing: ".06em", display: "flex", alignItems: "center", gap: 6,
                          transition: "all .2s",
                          boxShadow: active ? `0 0 14px ${C.accentGlow}` : "none",
                        }}>
                        {loading ? <Spinner size={12} /> : "✨"}
                        {loading ? "Loading…" : "Why Choose This?"}
                      </button>
                    </div>

                    {/* AI explanation drawer */}
                    {active && explainCache[row.pathway] && (
                      <div
                        onClick={(e) => e.stopPropagation()}
                        style={{
                          margin: "0 0 14px", padding: "16px 20px", borderRadius: 14,
                          border: gb("rgba(226,98,58,.25)"),
                          background: "rgba(226,98,58,.06)", backdropFilter: "blur(6px)",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 10 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ fontSize: ".75rem", letterSpacing: ".1em",
                              textTransform: "uppercase", padding: "2px 10px", borderRadius: 999,
                              background: explainCache[row.pathway].source === "gemini"
                                ? "rgba(74,222,128,.12)" : "rgba(226,98,58,.1)",
                              border: gb(explainCache[row.pathway].source === "gemini"
                                ? "rgba(74,222,128,.3)" : "rgba(226,98,58,.2)"),
                              color: explainCache[row.pathway].source === "gemini" ? "#86efac" : C.accentSoft,
                            }}>
                              {explainCache[row.pathway].source === "gemini" ? "✦ Gemini AI" : "📋 Template"}
                            </span>
                            {!explainCache[row.pathway].grounded && (
                              <span style={{ fontSize: ".72rem", color: "#9a6050" }}>
                                (indicative — grounding check not passed)
                              </span>
                            )}
                          </div>
                          <AudioReaderButton text={explainCache[row.pathway].text} />
                        </div>
                        <p style={{ margin: "0 0 10px", color: C.textBody, fontSize: ".88rem",
                          lineHeight: 1.65, letterSpacing: ".02em" }}>
                          {explainCache[row.pathway].text}
                        </p>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 8 }}>
                          {[
                            { label: "Net kWh/day", value: row.e_net_kwh_d > 0 ? `${row.e_net_kwh_d.toFixed(0)} kWh` : "—" },
                            { label: "Annual Net", value: `₹${(row.annual_net_value_inr / 100_000).toFixed(1)}L` },
                            { label: "MC Wins", value: row.win_count != null ? `${row.win_count} / ${Math.round((row.win_count / (row.optimality_share ?? 0.01)) * 1)}` : "—" },
                          ].map(({ label, value }) => (
                            <div key={label} style={{ padding: "6px 14px", borderRadius: 10,
                              background: "rgba(255,255,255,.04)", border: gb("rgba(226,98,58,.18)") }}>
                              <p style={{ margin: "0 0 2px", fontSize: ".67rem", letterSpacing: ".1em",
                                textTransform: "uppercase", color: "#9a6050" }}>{label}</p>
                              <p style={{ margin: 0, fontSize: ".88rem", fontWeight: 600,
                                color: "#ffe4d6" }}>{value}</p>
                            </div>
                          ))}
                        </div>
                        <p style={{ margin: "12px 0 0", fontSize: ".72rem", color: "#6b5248", fontStyle: "italic" }}>
                          ⚠ {explainCache[row.pathway].disclaimer}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}
          </>
        ) : (
          <ProcessSelector
            location={address || (pincode ? `PIN ${pincode}, India` : "Industrial Zone")}
            weight={mass >= 1000 ? Math.round((mass / 1000) * 10) / 10 : mass || 25}
            weather={params.get("weather") || "Tropical, 28°C with moderate humidity"}
            duration={params.get("duration") || "< 24 hours (Continuous)"}
            onSelectProcess={(proc) => {
              const matched = ALL_PATHWAYS.find(
                (p) =>
                  PATHWAY_META[p]?.label.toLowerCase().includes(proc.toLowerCase()) ||
                  p.toLowerCase().includes(proc.toLowerCase())
              );
              if (matched) {
                setSelectedPathwayId(matched);
                setHasUserSelected(true);
              }
            }}
          />
        )}

        {/* ══ STEP 2: INTERACTIVE 3D SUBPROCESS PIPELINE VIEW ══ */}
        {loadPhase === 2 && (
          <section style={card({
            border: "1.5px solid #FB923C",
            boxShadow: "0 10px 40px rgba(40,15,5,.45), inset 0 0 30px rgba(226,98,58,.06), 0 0 36px rgba(251,146,60,0.3)",
            padding: "28px 32px",
          })}>
            {/* 1. Header Bar */}
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 12,
              paddingBottom: 20,
              borderBottom: "1px solid rgba(251,146,60,0.25)",
              marginBottom: 24,
            }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <h2 style={{
                    margin: 0,
                    fontSize: "clamp(1rem, 2.2vw, 1.25rem)",
                    letterSpacing: ".08em",
                    textTransform: "uppercase",
                    fontWeight: 800,
                    color: "#FB923C",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}>
                    ⚙️ INTERACTIVE SUBPROCESS PIPELINE: {selectedPathwayName.toUpperCase()}
                  </h2>
                  <span style={{
                    fontSize: ".72rem",
                    fontWeight: 700,
                    padding: "4px 12px",
                    borderRadius: 999,
                    background: "rgba(251,146,60,0.18)",
                    border: "1.5px solid #FB923C",
                    color: "#FB923C",
                    letterSpacing: ".08em",
                    boxShadow: "0 0 14px rgba(251,146,60,0.35)",
                  }}>
                    {currentStages.length} Subprocess Stages
                  </span>
                </div>
                <p style={{ margin: "6px 0 0", fontSize: ".82rem", color: C.textBody, letterSpacing: ".02em" }}>
                  Sequential thermochemical & biochemical unit operations. Click any 3D equipment stage to inspect real-time operating conditions.
                </p>
              </div>

              {/* Pathway quick switcher tags */}
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <span style={{ fontSize: ".72rem", color: "#9a6050", letterSpacing: ".05em" }}>Switch:</span>
                {ALL_PATHWAYS.map(p => {
                  const isCur = p === selectedPathwayId;
                  const meta = PATHWAY_META[p];
                  return (
                    <button
                      key={p}
                      onClick={() => {
                        setSelectedPathwayId(p);
                        setHasUserSelected(true);
                      }}
                      style={{
                        fontSize: ".7rem",
                        padding: "4px 10px",
                        borderRadius: 999,
                        border: isCur ? "1.5px solid #FB923C" : "1px solid rgba(226,98,58,.2)",
                        background: isCur ? "rgba(251,146,60,0.22)" : "rgba(255,255,255,.02)",
                        color: isCur ? "#FB923C" : "#b07060",
                        cursor: "pointer",
                        fontWeight: isCur ? 700 : 500,
                        transition: "all .15s",
                      }}
                    >
                      {meta?.icon} {meta?.label.split(" ")[0]}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 2. Sequential Stage Flowchart (Block Diagram) */}
            <div style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 14,
              overflowX: "auto",
              padding: "10px 4px 20px",
              scrollbarWidth: "thin",
              scrollbarColor: "#FB923C #0c111d",
            }}>
              {currentStages.map((stage, stageIdx) => {
                const isInspected = inspectedStage?.id === stage.id;
                const hasNext = stageIdx < currentStages.length - 1;

                return (
                  <div key={stage.id} style={{ display: "flex", alignItems: "flex-start", gap: 14, flexShrink: 0 }}>
                    {/* Stage Block Container */}
                    <div style={{ width: 280, display: "flex", flexDirection: "column" }}>

                      {/* Floating Input Badges (Showing exact raw materials with downward arrow) */}
                      <div style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                        minHeight: 52,
                        marginBottom: 10,
                        justifyContent: "flex-end",
                      }}>
                        {(stage.subprocessInputs ?? ["↓ Raw Feedstock"]).map((rawInput) => {
                          const badgeStyle = getInputBadgeStyle(rawInput);
                          return (
                            <span
                              key={rawInput}
                              style={{
                                fontSize: ".73rem",
                                fontWeight: 700,
                                letterSpacing: ".04em",
                                padding: "4px 10px",
                                borderRadius: 8,
                                background: badgeStyle.bg,
                                border: `1px solid ${badgeStyle.border}`,
                                color: badgeStyle.text,
                                boxShadow: `0 2px 10px ${badgeStyle.glow}`,
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 4,
                                backdropFilter: "blur(6px)",
                                alignSelf: "flex-start",
                              }}
                            >
                              {rawInput}
                            </span>
                          );
                        })}
                      </div>

                      {/* Interactive Stage Card */}
                      <div
                        onClick={() => setInspectedStage(stage)}
                        style={{
                          background: isInspected ? "rgba(251,146,60,0.14)" : "rgba(15,23,42,0.7)",
                          border: isInspected ? "2px solid #FB923C" : "1px solid rgba(251,146,60,0.25)",
                          boxShadow: isInspected
                            ? "0 0 30px rgba(251,146,60,0.45), inset 0 0 20px rgba(251,146,60,0.12)"
                            : "0 8px 30px rgba(0,0,0,0.5), inset 0 0 20px rgba(251,146,60,0.02)",
                          borderRadius: 18,
                          padding: "16px",
                          cursor: "pointer",
                          transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
                          display: "flex",
                          flexDirection: "column",
                          gap: 12,
                        }}
                      >
                        {/* 3D Canvas Viewport */}
                        <div style={{ position: "relative" }}>
                          {mounted ? (
                            <StageCanvas3D
                              equipmentType={stage.equipmentType}
                              stageName={stage.name}
                              accentColor="#FB923C"
                              selected={isInspected}
                              height={180}
                            />
                          ) : (
                            <div style={{ height: 180, display: "flex", alignItems: "center", justifyContent: "center" }}>
                              <Spinner size={24} color="#FB923C" />
                            </div>
                          )}
                          <div style={{
                            position: "absolute",
                            top: 8,
                            right: 8,
                            padding: "3px 8px",
                            borderRadius: 999,
                            background: "rgba(7,10,15,0.75)",
                            border: "1px solid rgba(251,146,60,0.3)",
                            fontSize: ".65rem",
                            color: "#fdba74",
                            letterSpacing: ".06em",
                            fontWeight: 600,
                          }}>
                            STAGE {stage.code}
                          </div>
                        </div>

                        {/* Stage Label (Number and Name) */}
                        <div>
                          <p style={{
                            margin: 0,
                            fontWeight: 700,
                            fontSize: ".9rem",
                            color: isInspected ? "#FB923C" : "#ffe4d6",
                            letterSpacing: ".02em",
                            lineHeight: 1.35,
                          }}>
                            Stage {stage.code}: {stage.name}
                          </p>
                          <span style={{
                            fontSize: ".68rem",
                            color: "#9a6050",
                            letterSpacing: ".04em",
                            textTransform: "uppercase",
                            marginTop: 2,
                            display: "inline-block",
                          }}>
                            {stage.category}
                          </span>
                        </div>

                        {/* Quick Operating Condition Preview Pills */}
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          <span style={{
                            fontSize: ".7rem",
                            padding: "3px 8px",
                            borderRadius: 6,
                            background: "rgba(251,146,60,0.1)",
                            border: "1px solid rgba(251,146,60,0.25)",
                            color: "#fdba74",
                          }}>
                            🌡️ {stage.operatingConditions?.temperature ?? "Ambient"}
                          </span>
                          <span style={{
                            fontSize: ".7rem",
                            padding: "3px 8px",
                            borderRadius: 6,
                            background: "rgba(56,189,248,0.1)",
                            border: "1px solid rgba(56,189,248,0.25)",
                            color: "#7dd3fc",
                          }}>
                            ⏱️ {stage.operatingConditions?.residenceTime ?? "Continuous"}
                          </span>
                        </div>

                        {/* Callout Prompt */}
                        <div style={{
                          padding: "6px 10px",
                          borderRadius: 8,
                          background: isInspected ? "rgba(251,146,60,0.2)" : "rgba(255,255,255,0.03)",
                          textAlign: "center",
                          fontSize: ".72rem",
                          fontWeight: 600,
                          color: isInspected ? "#FB923C" : "#b07060",
                          letterSpacing: ".04em",
                        }}>
                          {isInspected ? "✦ Currently Inspecting" : "Inspect Conditions 🔍"}
                        </div>
                      </div>
                    </div>

                    {/* Connecting Glowing Directional Flow Arrows linking Stage N -> Stage N+1 */}
                    {hasNext && (
                      <div style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        paddingTop: 150, // aligns vertically with the 3D canvas viewport center
                        flexShrink: 0,
                      }}>
                        <div style={{
                          width: 36,
                          height: 36,
                          borderRadius: "50%",
                          background: "rgba(251,146,60,0.14)",
                          border: "1.5px solid #FB923C",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          boxShadow: "0 0 16px rgba(251,146,60,0.5)",
                          color: "#FB923C",
                          fontSize: "1.2rem",
                          fontWeight: "bold",
                        }}>
                          ➔
                        </div>
                        <span style={{
                          fontSize: ".65rem",
                          color: "#FB923C",
                          letterSpacing: ".08em",
                          textTransform: "uppercase",
                          marginTop: 6,
                          fontWeight: 700,
                        }}>
                          Flow
                        </span>
                      </div>
                    )}

                    {/* Step 1 Requirement: Final Subprocess Stage Glowing Directional Output Arrow & Sell Button */}
                    {!hasNext && (
                      <div style={{ display: "flex", alignItems: "flex-start", gap: 14, flexShrink: 0 }}>
                        {/* Glowing Directional Output Connector */}
                        <div style={{
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center",
                          justifyContent: "center",
                          paddingTop: 145,
                          flexShrink: 0,
                        }}>
                          <div style={{
                            width: 44,
                            height: 44,
                            borderRadius: "50%",
                            background: "linear-gradient(135deg, rgba(251,146,60,0.3), rgba(234,88,12,0.65))",
                            border: "2px solid #FB923C",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            boxShadow: "0 0 24px rgba(251,146,60,0.85), inset 0 0 10px rgba(251,146,60,0.4)",
                            color: "#fff",
                            fontSize: "1.35rem",
                            fontWeight: "bold",
                          }}>
                            ➔
                          </div>
                          <span style={{
                            fontSize: ".66rem",
                            color: "#FB923C",
                            letterSpacing: ".08em",
                            textTransform: "uppercase",
                            marginTop: 6,
                            fontWeight: 800,
                          }}>
                            Output Stream
                          </span>
                        </div>

                        {/* Output Block Card with Yield Badge & Sell Button */}
                        <div style={{
                          width: 320,
                          display: "flex",
                          flexDirection: "column",
                          justifyContent: "flex-end",
                          marginTop: 62,
                        }}>
                          <div style={{
                            background: "linear-gradient(145deg, rgba(251,146,60,0.18) 0%, rgba(15,23,42,0.92) 100%)",
                            border: "2px solid #FB923C",
                            boxShadow: "0 0 35px rgba(251,146,60,0.4), inset 0 0 25px rgba(251,146,60,0.12)",
                            borderRadius: 18,
                            padding: "20px 22px",
                            display: "flex",
                            flexDirection: "column",
                            gap: 14,
                            position: "relative",
                            overflow: "hidden",
                          }}>
                            <div style={{
                              position: "absolute",
                              top: -24,
                              right: -24,
                              width: 90,
                              height: 90,
                              borderRadius: "50%",
                              background: "radial-gradient(circle, rgba(251,146,60,0.35) 0%, transparent 70%)",
                              pointerEvents: "none",
                            }} />

                            <div>
                              <span style={{
                                fontSize: ".65rem",
                                fontWeight: 800,
                                letterSpacing: ".1em",
                                textTransform: "uppercase",
                                color: "#070a0f",
                                background: "#FB923C",
                                padding: "2px 8px",
                                borderRadius: 999,
                                display: "inline-block",
                                marginBottom: 6,
                              }}>
                                READY TO MONETIZE
                              </span>
                              <h4 style={{
                                margin: 0,
                                fontSize: "1rem",
                                fontWeight: 800,
                                color: "#FFE4D6",
                                letterSpacing: ".02em",
                                lineHeight: 1.35,
                              }}>
                                ⚡ Output Produced: {primaryOutput}
                              </h4>
                            </div>

                            {/* Yield quantity badge scaled from user mass */}
                            <div style={{
                              padding: "10px 14px",
                              borderRadius: 12,
                              background: "rgba(7,10,15,0.75)",
                              border: "1px solid rgba(251,146,60,0.3)",
                              display: "flex",
                              flexDirection: "column",
                              gap: 3,
                            }}>
                              <span style={{ fontSize: ".68rem", color: "#9a6050", textTransform: "uppercase", letterSpacing: ".06em" }}>
                                Scaled Daily Yield
                              </span>
                              <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                                <span style={{ fontSize: "1.25rem", fontWeight: 800, color: "#FB923C" }}>
                                  {yieldInfo.qty}
                                </span>
                                <span style={{ fontSize: ".78rem", color: "#fdba74", fontWeight: 600 }}>
                                  {yieldInfo.unit}
                                </span>
                              </div>
                              <span style={{ fontSize: ".7rem", color: "#86efac" }}>
                                Direct recovery from {mass.toLocaleString()} kg/day input
                              </span>
                            </div>

                            {/* Action Button: SELL PRODUCED ENERGY → */}
                            <button
                              onClick={() => {
                                router.push(
                                  '/market/energy?pincode=' + encodeURIComponent(pincode || "110001") +
                                  '&output=' + encodeURIComponent(primaryOutput) +
                                  '&mass=' + (mass || 10000)
                                );
                              }}
                              style={{
                                padding: "14px 18px",
                                borderRadius: 12,
                                background: "linear-gradient(90deg, #C2410C 0%, #EA580C 50%, #FB923C 100%)",
                                border: "none",
                                color: "#070a0f",
                                fontFamily: FONT,
                                fontSize: ".88rem",
                                fontWeight: 800,
                                letterSpacing: ".06em",
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                gap: 8,
                                boxShadow: "0 0 24px rgba(251,146,60,0.6)",
                                transition: "all 0.2s ease",
                              }}
                            >
                              <span>SELL PRODUCED ENERGY</span>
                              <span style={{ fontSize: "1.1rem" }}>→</span>
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* ══ STEP 3: STAGE INSPECTOR DRAWER / MODAL ══ */}
        {inspectedStage && (
          <div
            onClick={() => setInspectedStage(null)}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(4,7,14,0.85)",
              backdropFilter: "blur(12px)",
              WebkitBackdropFilter: "blur(12px)",
              zIndex: 999,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "20px",
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: "#0c111d",
                border: "2px solid #FB923C",
                borderRadius: 24,
                boxShadow: "0 0 60px rgba(251,146,60,0.4), 0 25px 70px rgba(0,0,0,0.9)",
                maxWidth: 760,
                width: "100%",
                maxHeight: "90vh",
                overflowY: "auto",
                padding: "28px 32px",
                display: "flex",
                flexDirection: "column",
                gap: 22,
                fontFamily: FONT,
                color: "#ffe4d6",
              }}
            >
              {/* Header */}
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 14 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
                    <span style={{
                      fontSize: ".7rem",
                      fontWeight: 800,
                      padding: "3px 10px",
                      borderRadius: 999,
                      background: "#FB923C",
                      color: "#070a0f",
                      letterSpacing: ".08em",
                    }}>
                      STAGE {inspectedStage.code}
                    </span>
                    <span style={{
                      fontSize: ".72rem",
                      padding: "3px 10px",
                      borderRadius: 999,
                      background: "rgba(251,146,60,0.15)",
                      border: "1px solid rgba(251,146,60,0.35)",
                      color: "#fdba74",
                      letterSpacing: ".06em",
                      textTransform: "uppercase",
                    }}>
                      {inspectedStage.category}
                    </span>
                  </div>
                  <h3 style={{
                    margin: 0,
                    fontSize: "1.35rem",
                    fontWeight: 800,
                    color: "#ffe4d6",
                    letterSpacing: ".03em",
                  }}>
                    {inspectedStage.name}
                  </h3>
                </div>

                <button
                  onClick={() => setInspectedStage(null)}
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: "50%",
                    background: "rgba(255,255,255,0.06)",
                    border: "1px solid rgba(251,146,60,0.3)",
                    color: "#fdba74",
                    fontSize: "1.1rem",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    transition: "all .15s",
                  }}
                  title="Close Inspector"
                >
                  ✕
                </button>
              </div>

              {/* 3D Visual Preview inside Inspector */}
              <div style={{
                borderRadius: 16,
                overflow: "hidden",
                border: "1px solid rgba(251,146,60,0.3)",
                background: "radial-gradient(ellipse at 50% 60%, rgba(251,146,60,0.12) 0%, #070a0f 80%)",
              }}>
                {mounted && (
                  <StageCanvas3D
                    equipmentType={inspectedStage.equipmentType}
                    stageName={inspectedStage.name}
                    accentColor="#FB923C"
                    selected={true}
                    height={210}
                  />
                )}
              </div>

              {/* Operating Conditions Grid (Primary Prompt Requirement) */}
              <div>
                <h4 style={{
                  margin: "0 0 12px",
                  fontSize: ".8rem",
                  letterSpacing: ".1em",
                  textTransform: "uppercase",
                  color: "#FB923C",
                }}>
                  ⚙️ Real-Time Operating Conditions
                </h4>
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
                  gap: 12,
                }}>
                  <div style={{
                    padding: "12px 14px",
                    borderRadius: 12,
                    background: "rgba(249,115,22,0.1)",
                    border: "1px solid rgba(249,115,22,0.3)",
                  }}>
                    <span style={{ fontSize: ".68rem", color: "#fdba74", textTransform: "uppercase", letterSpacing: ".06em" }}>
                      🌡️ Temperature
                    </span>
                    <p style={{ margin: "4px 0 0", fontSize: "1.05rem", fontWeight: 800, color: "#fff" }}>
                      {inspectedStage.operatingConditions?.temperature ?? "Ambient (~25°C)"}
                    </p>
                  </div>

                  <div style={{
                    padding: "12px 14px",
                    borderRadius: 12,
                    background: "rgba(14,165,233,0.1)",
                    border: "1px solid rgba(14,165,233,0.3)",
                  }}>
                    <span style={{ fontSize: ".68rem", color: "#7dd3fc", textTransform: "uppercase", letterSpacing: ".06em" }}>
                      📊 Operating Pressure
                    </span>
                    <p style={{ margin: "4px 0 0", fontSize: "1.05rem", fontWeight: 800, color: "#fff" }}>
                      {inspectedStage.operatingConditions?.pressure ?? "1.0 bar (atm)"}
                    </p>
                  </div>

                  <div style={{
                    padding: "12px 14px",
                    borderRadius: 12,
                    background: "rgba(168,85,247,0.1)",
                    border: "1px solid rgba(168,85,247,0.3)",
                  }}>
                    <span style={{ fontSize: ".68rem", color: "#d8b4fe", textTransform: "uppercase", letterSpacing: ".06em" }}>
                      ⏱️ Residence Time
                    </span>
                    <p style={{ margin: "4px 0 0", fontSize: "1.05rem", fontWeight: 800, color: "#fff" }}>
                      {inspectedStage.operatingConditions?.residenceTime ?? "Continuous"}
                    </p>
                  </div>

                  <div style={{
                    padding: "12px 14px",
                    borderRadius: 12,
                    background: "rgba(34,197,94,0.1)",
                    border: "1px solid rgba(34,197,94,0.3)",
                  }}>
                    <span style={{ fontSize: ".68rem", color: "#86efac", textTransform: "uppercase", letterSpacing: ".06em" }}>
                      📈 Conversion Yield
                    </span>
                    <p style={{ margin: "4px 0 0", fontSize: "1.05rem", fontWeight: 800, color: "#fff" }}>
                      {inspectedStage.operatingConditions?.conversionYield ?? "95% throughput"}
                    </p>
                  </div>
                </div>
              </div>

              {/* Description & Role */}
              <div>
                <p style={{ margin: "0 0 8px", fontSize: ".88rem", lineHeight: 1.6, color: C.textBody }}>
                  {inspectedStage.description}
                </p>
                <p style={{ margin: 0, fontSize: ".8rem", color: "#fdba74", fontStyle: "italic" }}>
                  Role: {inspectedStage.role}
                </p>
              </div>

              {/* Raw Inputs & Process Outputs */}
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                gap: 16,
                padding: "14px 16px",
                borderRadius: 14,
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(251,146,60,0.2)",
              }}>
                <div>
                  <span style={{ fontSize: ".72rem", color: "#86efac", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>
                    Subprocess Ingestion Materials:
                  </span>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
                    {(inspectedStage.subprocessInputs ?? inspectedStage.inputs).map((inp) => (
                      <span key={inp} style={{ fontSize: ".8rem", color: "#ffe4d6" }}>
                        • {inp}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: ".72rem", color: "#38bdf8", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>
                    Stage Stream Outputs:
                  </span>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
                    {inspectedStage.outputs.map((out) => (
                      <span key={out} style={{ fontSize: ".8rem", color: "#ffe4d6" }}>
                        ➔ {out}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Equipment Highlights */}
              {inspectedStage.equipmentHighlights?.length > 0 && (
                <div>
                  <span style={{ fontSize: ".72rem", color: "#facc15", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>
                    Industrial Specifications:
                  </span>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
                    {inspectedStage.equipmentHighlights.map((eq) => (
                      <span
                        key={eq}
                        style={{
                          fontSize: ".74rem",
                          padding: "4px 10px",
                          borderRadius: 8,
                          background: "rgba(250,204,21,0.08)",
                          border: "1px solid rgba(250,204,21,0.25)",
                          color: "#fef08a",
                        }}
                      >
                        ✓ {eq}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Stage Navigation & Actions Footer */}
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                paddingTop: 14,
                borderTop: "1px solid rgba(251,146,60,0.2)",
                flexWrap: "wrap",
                gap: 10,
              }}>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    disabled={currentStageIndex <= 0}
                    onClick={handlePrevStage}
                    style={{
                      padding: "8px 16px",
                      borderRadius: 10,
                      background: currentStageIndex > 0 ? "rgba(251,146,60,0.15)" : "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(251,146,60,0.3)",
                      color: currentStageIndex > 0 ? "#FB923C" : "#64748b",
                      cursor: currentStageIndex > 0 ? "pointer" : "not-allowed",
                      fontFamily: FONT,
                      fontSize: ".8rem",
                      fontWeight: 600,
                    }}
                  >
                    ← Previous Stage
                  </button>
                  <button
                    disabled={currentStageIndex >= currentStages.length - 1}
                    onClick={handleNextStage}
                    style={{
                      padding: "8px 16px",
                      borderRadius: 10,
                      background: currentStageIndex < currentStages.length - 1 ? "rgba(251,146,60,0.15)" : "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(251,146,60,0.3)",
                      color: currentStageIndex < currentStages.length - 1 ? "#FB923C" : "#64748b",
                      cursor: currentStageIndex < currentStages.length - 1 ? "pointer" : "not-allowed",
                      fontFamily: FONT,
                      fontSize: ".8rem",
                      fontWeight: 600,
                    }}
                  >
                    Next Stage →
                  </button>
                </div>

                <button
                  onClick={() => setInspectedStage(null)}
                  style={{
                    padding: "8px 20px",
                    borderRadius: 10,
                    background: "linear-gradient(90deg, #C2410C, #FB923C)",
                    border: "none",
                    color: "#070a0f",
                    fontFamily: FONT,
                    fontSize: ".82rem",
                    fontWeight: 700,
                    cursor: "pointer",
                    boxShadow: "0 0 16px rgba(251,146,60,0.4)",
                  }}
                >
                  Done Inspecting
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Hard error (no results at all) ── */}
        {simError && loadPhase !== 2 && (
          <section style={card()}>
            <p style={{ margin: 0, color: "#f87171", fontSize: ".9rem" }}>⚠ {simError}</p>
            <Link href="/explore/industry" style={{
              display: "inline-block", marginTop: 14, color: C.accentSoft,
              textDecoration: "none", fontSize: ".88rem",
            }}>
              ← Return to Industry Hub
            </Link>
          </section>
        )}

      </div>
      <FloatingChatbot simulationContext={{ pincode, address, mass_kg_per_day: mass, selected_pathway: selectedPathwayId, results, simulation_status: loadPhase === 1 ? "running" : loadPhase === 2 ? "complete" : "idle", error: simError }} />
    </main>
  );
}

/* ── Default export wraps in Suspense (required for useSearchParams) ── */
export default function SimulatorPage() {
  return (
    <Suspense fallback={
      <main style={{ minHeight: "100vh", background: "#070a0f", display: "flex",
        alignItems: "center", justifyContent: "center", fontFamily: '"Rubik",sans-serif' }}>
        <span style={{ color: "#F0A080", fontSize: "1rem", letterSpacing: ".1em" }}>
          Loading simulator…
        </span>
      </main>
    }>
      <SimulatorInner />
    </Suspense>
  );
}
