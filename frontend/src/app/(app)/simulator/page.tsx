"use client";
import { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { StageCanvas3D } from "./equipment-3d";
import { getStagesByPathway, getInputBadgeStyle } from "./stages-data";
import AudioReaderButton from "@/components/AudioReaderButton";
import { useChatbotStore } from "@/stores/chatbot";
import ProcessSelector from "@/components/ProcessSelector";
import { PATHWAY_NAMES } from "./pathway-config";
import { ProcessStage } from "./types";
import { INDUSTRY_PAGE_BG } from "@/lib/industryTheme";

/* ── Industry / amber accent palette ── */
const C = {
  accent:      "#C2410C",
  accentSoft:  "#9A3412",
  accentDim:   "rgba(226,98,58,.45)",
  accentGlow:  "rgba(226,98,58,.25)",
  accentInner: "rgba(226,98,58,.06)",
  accentDrop:  "rgba(226,98,58,.45)",
  textBody:    "#431E12",
  gradTitle:   "linear-gradient(90deg,#431E12,#C2410C)",
  gradBtn:     "linear-gradient(90deg,#C2410C,#E2623A)",
  btnText:     "#1a0800",
  barA:        "#FB923C",
  barB:        "#F97316",
};

const FONT = '"Rubik",sans-serif';
const gb   = (c: string) => `1.5px solid ${c}`;
const card = (extra?: React.CSSProperties): React.CSSProperties => ({
  border: gb(C.accentDim),
  background: "rgba(255,255,255,0.57)",
  backdropFilter: "blur(12px)",
  WebkitBackdropFilter: "blur(12px)",
  boxShadow: `0 10px 40px rgba(120,53,15,0.16),inset 0 0 30px ${C.accentInner},0 0 36px ${C.accentGlow}`,
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
        background: "rgba(255,255,255,0.61)",
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

/* ── Daily yield from the physics model (POST /pathways/compare result) ── */
const OUTPUT_LABELS: Record<string, { unit: string; digits: number }> = {
  biogas_m3_d: { unit: "m³/day biogas", digits: 0 },
  syngas_mj_d: { unit: "MJ/day syngas", digits: 0 },
  heat_mj_d:   { unit: "MJ/day heat", digits: 0 },
  compost_t_d: { unit: "t/day compost", digits: 2 },
};

type ModelYield =
  | { kind: "estimate"; energyKwhD: number; products: string[] }
  | { kind: "none"; message: string };

function getModelYield(row: PathwayResult | undefined, fromModel: boolean): ModelYield {
  if (!fromModel) return { kind: "none", message: "No model estimate: live simulation unavailable" };
  if (!row || row.model_status === "infeasible") {
    return { kind: "none", message: "No model estimate for this feedstock" };
  }
  const products = Object.entries(row.outputs ?? {})
    .filter(([key, value]) => key in OUTPUT_LABELS && Number.isFinite(value))
    .map(([key, value]) => {
      const { unit, digits } = OUTPUT_LABELS[key];
      return `${value.toLocaleString(undefined, { maximumFractionDigits: digits })} ${unit}`;
    });
  return { kind: "estimate", energyKwhD: row.e_net_kwh_d, products };
}

/* ── Inner component (needs Suspense boundary for useSearchParams) ── */
function SimulatorInner() {
  const router      = useRouter();
  const params      = useSearchParams();
  const pincode     = params.get("pincode") ?? "";
  const massRaw     = params.get("mass") ?? "0";
  const initialMass = parseFloat(massRaw) || 0;
  const address     = params.get("address") ?? "";
  const category    = params.get("category") ?? "energy";
  const latParam    = params.get("lat") ? Number(params.get("lat")) : undefined;
  const lngParam    = params.get("lng") ? Number(params.get("lng")) : undefined;

  const [dailyVolumeInput, setDailyVolumeInput] = useState<string>(
    initialMass > 0 ? String(initialMass) : ""
  );
  const [activeMass, setActiveMass]             = useState<number>(initialMass);
  const [hasSimulated, setHasSimulated]         = useState<boolean>(false);

  const [activeView, setActiveView] = useState<"monte_carlo" | "gemini">("monte_carlo");

  const [results, setResults]     = useState<PathwayResult[] | null>(null);
  const [resultsFromModel, setResultsFromModel] = useState(false);
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

  /* ── Trigger backend API calls for Monte Carlo & simulation ── */
  const handleRunSimulation = async (specifiedMass?: number) => {
    const rawVal = specifiedMass !== undefined ? String(specifiedMass) : dailyVolumeInput;
    const parsedMass = parseFloat(rawVal);
    if (isNaN(parsedMass) || parsedMass <= 0) {
      setSimError("Please enter a valid daily waste volume greater than 0 kg/day.");
      return;
    }

    setActiveMass(parsedMass);
    setHasSimulated(true);
    setLoadPhase(1);
    setSimError(null);

    try {
      const data = await callCompare(pincode, parsedMass);
      setResults(data);
      setResultsFromModel(true);
      setLoadPhase(2);
      barAnimRef.current = true;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setResults(buildMockResults(parsedMass / 1000));
      setResultsFromModel(false);
      setLoadPhase(2);
      barAnimRef.current = true;
      if (!msg.includes("fetch") && !msg.includes("network")) {
        setSimError(`Live simulation unavailable (${msg}) — showing indicative results.`);
      }
    }
  };

  /* ── Route to Marketplace appending process and mass ── */
  const handleFinalizeProcess = () => {
    const chosenProcess = selectedPathwayId;
    const massVal = activeMass > 0 ? activeMass : (parseFloat(dailyVolumeInput) || 10000);
    const pinVal = pincode || "110001";

    try {
      sessionStorage.setItem("wp_audit_process", chosenProcess);
      sessionStorage.setItem("wp_audit_mass", String(massVal));
      sessionStorage.setItem("wp_audit_pincode", pinVal);
      sessionStorage.setItem("wp_audit_category", category);
    } catch (err) {
      console.warn("sessionStorage save failed:", err);
    }

    const searchParams = new URLSearchParams({
      pincode: pinVal,
      process: chosenProcess,
      mass: String(massVal),
      category: category,
    });
    router.push(`/market/energy?${searchParams.toString()}`);
  };

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

  /* Share live simulation state with the global chatbot (mounted in the root layout) */
  const setChatContext = useChatbotStore((s) => s.setContext);
  useEffect(() => {
    setChatContext({
      pincode,
      address,
      mass_kg_per_day: activeMass,
      selected_pathway: selectedPathwayId,
      results,
      simulation_status: loadPhase === 1 ? "running" : loadPhase === 2 ? "complete" : "idle",
      error: simError,
    });
  }, [setChatContext, pincode, address, activeMass, selectedPathwayId, results, loadPhase, simError]);
  useEffect(() => () => setChatContext(null), [setChatContext]);

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
  const modelYield = getModelYield(
    results?.find((r) => r.pathway === selectedPathwayId),
    resultsFromModel
  );

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
      minHeight: "100vh", ...INDUSTRY_PAGE_BG, fontFamily: FONT, color: "#27120A",
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
              background: "rgba(255,255,255,0.53)",
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
            See which process works best for your waste, location and weather.
          </p>
        </div>

        {/* ── Active parameter banner ── */}
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 10, marginTop: 4,
        }}>
          {[
            { icon: "📍", label: `PIN: ${pincode || "—"}` },
            { icon: "⚖️", label: activeMass > 0 ? `Mass: ${activeMass.toLocaleString()} kg/day` : "Awaiting Mass Input" },
            { icon: "⚡", label: `Category: ${category === "non-energy" ? "Non-Energy Recoverable" : "Energy Recoverable"}` },
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

        {/* ══ INPUT BLOCK: ENTER DAILY WASTE VOLUME (KG/DAY) ══ */}
        <section style={card({
          border: "1.5px solid #FB923C",
          background: "linear-gradient(135deg, rgba(251,146,60,0.1) 0%, rgba(255,250,245,0.85) 100%)",
          boxShadow: "0 8px 32px rgba(120,53,15,0.14), inset 0 0 20px rgba(226,98,58,.08)",
        })}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginBottom: 6 }}>
            <h2 style={{
              margin: 0,
              fontSize: "1.1rem",
              fontWeight: 800,
              letterSpacing: ".08em",
              color: "#C2410C",
              textTransform: "uppercase",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}>
              ⚖️ Enter Daily Waste Volume (kg/day)
            </h2>
            <span style={{ fontSize: ".76rem", color: "#C2410C" }}>
              Location: PIN {pincode || "110001"} · Pathway Feasibility Modeling
            </span>
          </div>
          <p style={{ margin: "0 0 18px", fontSize: ".85rem", color: C.textBody, letterSpacing: ".02em" }}>
            Enter how much waste you produce each day, then run the simulation.
          </p>

          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "stretch" }}>
            <div style={{ position: "relative", flex: "1 1 260px" }}>
              <input
                type="number"
                min="1"
                value={dailyVolumeInput}
                onChange={(e) => setDailyVolumeInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleRunSimulation()}
                placeholder="e.g. 10000"
                aria-label="Daily waste volume in kg per day"
                style={{
                  width: "100%",
                  padding: "14px 80px 14px 20px",
                  borderRadius: 14,
                  boxSizing: "border-box",
                  border: "1.5px solid rgba(251,146,60,0.4)",
                  background: "rgba(255,250,245,0.85)",
                  color: "#27120A",
                  fontFamily: FONT,
                  fontSize: "1.15rem",
                  fontWeight: 700,
                  letterSpacing: ".06em",
                  outline: "none",
                  boxShadow: "inset 0 0 12px rgba(120,53,15,0.17)",
                }}
              />
              <span style={{
                position: "absolute",
                right: 16,
                top: "50%",
                transform: "translateY(-50%)",
                fontSize: ".82rem",
                fontWeight: 700,
                color: "#C2410C",
                pointerEvents: "none",
              }}>
                kg/day
              </span>
            </div>

            <button
              onClick={() => handleRunSimulation()}
              disabled={loadPhase === 1}
              style={{
                flex: "0 0 auto",
                padding: "14px 32px",
                borderRadius: 14,
                background: loadPhase === 1
                  ? "rgba(226,98,58,0.2)"
                  : "linear-gradient(90deg, #C2410C 0%, #EA580C 50%, #FB923C 100%)",
                border: "none",
                color: loadPhase === 1 ? "#9A3412" : "#070a0f",
                fontFamily: FONT,
                fontWeight: 800,
                fontSize: "1rem",
                letterSpacing: ".1em",
                textTransform: "uppercase",
                cursor: loadPhase === 1 ? "not-allowed" : "pointer",
                boxShadow: "0 0 24px rgba(251,146,60,0.5)",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                transition: "all .2s ease",
              }}
            >
              {loadPhase === 1 ? (
                <>
                  <Spinner size={16} color="#FB923C" />
                  <span>Simulating...</span>
                </>
              ) : (
                <>
                  <span>⚡ Run Simulation</span>
                </>
              )}
            </button>
          </div>

          {/* Quick preset chips */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
            <span style={{ fontSize: ".72rem", color: "#7A4A38", letterSpacing: ".04em" }}>Quick Presets:</span>
            {[
              { label: "1,000 kg/day (Micro-plant)", val: 1000 },
              { label: "5,000 kg/day (Mid-scale)", val: 5000 },
              { label: "10,000 kg/day (Cluster standard)", val: 10000 },
              { label: "25,000 kg/day (Heavy industrial)", val: 25000 },
            ].map((preset) => (
              <button
                key={preset.val}
                type="button"
                onClick={() => {
                  setDailyVolumeInput(String(preset.val));
                  handleRunSimulation(preset.val);
                }}
                style={{
                  fontSize: ".72rem",
                  padding: "4px 12px",
                  borderRadius: 999,
                  background: "rgba(255,255,255,0.53)",
                  border: "1px solid rgba(226,98,58,0.25)",
                  color: "#C2410C",
                  cursor: "pointer",
                  transition: "all .15s",
                }}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </section>

        {/* ── Soft error notice ── */}
        {simError && (
          <div style={{ padding: "12px 18px", borderRadius: 12,
            border: gb("rgba(248,113,113,.35)"), background: "rgba(248,113,113,.07)" }}>
            <p style={{ margin: 0, color: "#b91c1c", fontSize: ".86rem" }}>ℹ {simError}</p>
          </div>
        )}

        {/* ══ INITIAL PLACEHOLDER (Hidden Monte Carlo & 3D visualizers before simulation) ══ */}
        {!hasSimulated && loadPhase === 0 && (
          <section style={card({
            textAlign: "center",
            padding: "50px 30px",
            border: "1px dashed rgba(251,146,60,0.35)",
            background: "rgba(255,255,255,0.49)",
          })}>
            <div style={{
              width: 60,
              height: 60,
              borderRadius: "50%",
              background: "rgba(251,146,60,0.12)",
              border: "1px solid rgba(251,146,60,0.3)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "1.8rem",
              marginBottom: 16,
            }}>
              📊
            </div>
            <h3 style={{ margin: "0 0 8px", fontSize: "1.2rem", fontWeight: 800, color: "#27120A" }}>
              Awaiting Feedstock Volume
            </h3>
            <p style={{ margin: 0, maxWidth: 540, marginInline: "auto", fontSize: ".88rem", color: "#C2410C", lineHeight: 1.5 }}>
              Enter your daily waste above and click <strong>&quot;Run Simulation&quot;</strong> to see the best processes.
            </p>
          </section>
        )}

        {/* ══ LOADING CARD ══ */}
        {loadPhase === 1 && (
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
                <p style={{ margin: 0, fontSize: ".8rem", color: "#7A4A38", letterSpacing: ".04em" }}>
                  Feedstock: {activeMass.toLocaleString()} kg/day · Location: {pincode || "—"}
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
                      ? <span style={{ color: "#15803d", fontSize: ".85rem" }}>✓</span>
                      : i === phaseIdx % 3
                      ? <Spinner size={14} />
                      : <span style={{ width: 14, height: 14 }} />}
                    <span style={{ fontSize: ".82rem", color: i < phaseIdx ? "#15803d" : "#8A5A48", letterSpacing: ".03em" }}>
                      {step}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* ══ TABBED MAIN CONTENT: MONTE CARLO vs GEMINI PROCESS SELECTOR ══ */}
        {hasSimulated && loadPhase === 2 && (
          activeView === "monte_carlo" ? (
            <>
              {/* ══ RESULTS CARD: 7-Pathway Feasibility Ranking ══ */}
              {results && (
                <section style={card()}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between",
              flexWrap: "wrap", gap: 10, marginBottom: 20 }}>
              <div>
                <h2 style={{ margin: "0 0 4px", fontSize: "1.05rem", letterSpacing: ".1em",
                  color: C.accentSoft, textTransform: "uppercase" }}>
                  ✦ 7-Pathway Feasibility Ranking
                </h2>
                <p style={{ margin: 0, fontSize: ".76rem", color: "#C2410C" }}>
                  Click a process to see how it works step by step.
                </p>
                {/* callCompare sends identical capex/opex for every pathway (no verified per-process costs yet). */}
                <p style={{ margin: "4px 0 0", fontSize: ".72rem", color: "#7A4A38", fontStyle: "italic" }}>
                  Costs are assumed equal for every process, so the ranking compares energy and product revenue only.
                </p>
              </div>
              <span style={{ fontSize: ".78rem", color: "#7A4A38", letterSpacing: ".06em" }}>
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
                  textTransform: "uppercase", color: "#7A4A38" }}>
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
                      background: isSelected ? "rgba(251,146,60,0.12)" : "rgba(255,255,255,0.47)",
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
                              color: isSelected ? "#C2410C" : isTop ? C.accentSoft : "#27120A",
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
                                <span style={{ width: 5, height: 5, borderRadius: "50%", background: "rgba(255,250,245,0.9)" }} />
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
                          <p style={{ margin: "2px 0 0", fontSize: ".72rem", color: "#7A4A38" }}>
                            {row.feasible ? row.status : `rejected — ${row.reasons[0] ?? "infeasible"}`}
                          </p>
                        </div>
                      </div>

                      {/* Col 2: Score Bar */}
                      <ScoreBar score={share} animated={idx < 4} />

                      {/* Col 3: Output Badge */}
                      <span style={{
                        fontSize: ".75rem", padding: "5px 10px", borderRadius: 999,
                        border: gb(row.feasible ? "rgba(226,98,58,.3)" : "rgba(194,65,12,0.2)"),
                        background: row.feasible ? "rgba(226,98,58,.1)" : "rgba(255,255,255,0.51)",
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
                          background: active ? "rgba(226,98,58,.15)" : "rgba(255,255,255,0.53)",
                          color: active ? C.accentSoft : "#8A5A48",
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
                              color: explainCache[row.pathway].source === "gemini" ? "#15803d" : C.accentSoft,
                            }}>
                              {explainCache[row.pathway].source === "gemini" ? "✦ Gemini AI" : "📋 Template"}
                            </span>
                            {!explainCache[row.pathway].grounded && (
                              <span style={{ fontSize: ".72rem", color: "#7A4A38" }}>
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
                              background: "rgba(255,255,255,0.53)", border: gb("rgba(226,98,58,.18)") }}>
                              <p style={{ margin: "0 0 2px", fontSize: ".67rem", letterSpacing: ".1em",
                                textTransform: "uppercase", color: "#7A4A38" }}>{label}</p>
                              <p style={{ margin: 0, fontSize: ".88rem", fontWeight: 600,
                                color: "#27120A" }}>{value}</p>
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
            // activeMass is kg/day; the recommender expects tonnes/day.
            weight={activeMass > 0 ? Math.round(activeMass) / 1000 : 25}
            category={category}
            pincode={pincode || undefined}
            lat={latParam}
            lng={lngParam}
            weather={params.get("weather") || undefined}
            duration={params.get("duration") || undefined}
            selectedProcessId={hasUserSelected ? selectedPathwayId : null}
            onSelectProcess={(id) => {
              setSelectedPathwayId(id);
              setHasUserSelected(true);
            }}
          />
        )
      )}

        {/* ══ STEP 2: INTERACTIVE 3D SUBPROCESS PIPELINE VIEW ══ */}
        {hasSimulated && loadPhase === 2 && (
          <section style={card({
            border: "1.5px solid #FB923C",
            boxShadow: "0 10px 40px rgba(120,53,15,0.16), inset 0 0 30px rgba(226,98,58,.06), 0 0 36px rgba(251,146,60,0.3)",
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
                    color: "#C2410C",
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
                    color: "#C2410C",
                    letterSpacing: ".08em",
                    boxShadow: "0 0 14px rgba(251,146,60,0.35)",
                  }}>
                    {currentStages.length} Subprocess Stages
                  </span>
                </div>
                <p style={{ margin: "6px 0 0", fontSize: ".82rem", color: C.textBody, letterSpacing: ".02em" }}>
                  Each step of the process. Click a stage to see its operating conditions.
                </p>
              </div>

              {/* Pathway quick switcher tags */}
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <span style={{ fontSize: ".72rem", color: "#7A4A38", letterSpacing: ".05em" }}>Switch:</span>
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
                        background: isCur ? "rgba(251,146,60,0.22)" : "rgba(255,255,255,0.49)",
                        color: isCur ? "#C2410C" : "#8A5A48",
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
              scrollbarColor: "#FB923C #F5E6DA",
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
                          background: isInspected ? "rgba(251,146,60,0.14)" : "rgba(255,250,245,0.8)",
                          border: isInspected ? "2px solid #FB923C" : "1px solid rgba(251,146,60,0.25)",
                          boxShadow: isInspected
                            ? "0 0 30px rgba(251,146,60,0.45), inset 0 0 20px rgba(251,146,60,0.12)"
                            : "0 8px 30px rgba(120,53,15,0.17), inset 0 0 20px rgba(251,146,60,0.02)",
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
                              <Spinner size={24} color="#C2410C" />
                            </div>
                          )}
                          <div style={{
                            position: "absolute",
                            top: 8,
                            right: 8,
                            padding: "3px 8px",
                            borderRadius: 999,
                            background: "rgba(255,250,245,0.81)",
                            border: "1px solid rgba(251,146,60,0.3)",
                            fontSize: ".65rem",
                            color: "#C2410C",
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
                            color: isInspected ? "#C2410C" : "#27120A",
                            letterSpacing: ".02em",
                            lineHeight: 1.35,
                          }}>
                            Stage {stage.code}: {stage.name}
                          </p>
                          <span style={{
                            fontSize: ".68rem",
                            color: "#7A4A38",
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
                            color: "#C2410C",
                          }}>
                            🌡️ {stage.operatingConditions?.temperature ?? "Ambient"}
                          </span>
                          <span style={{
                            fontSize: ".7rem",
                            padding: "3px 8px",
                            borderRadius: 6,
                            background: "rgba(56,189,248,0.1)",
                            border: "1px solid rgba(56,189,248,0.25)",
                            color: "#0369a1",
                          }}>
                            ⏱️ {stage.operatingConditions?.residenceTime ?? "Continuous"}
                          </span>
                        </div>

                        {/* Callout Prompt */}
                        <div style={{
                          padding: "6px 10px",
                          borderRadius: 8,
                          background: isInspected ? "rgba(251,146,60,0.2)" : "rgba(255,255,255,0.51)",
                          textAlign: "center",
                          fontSize: ".72rem",
                          fontWeight: 600,
                          color: isInspected ? "#C2410C" : "#8A5A48",
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
                          color: "#C2410C",
                          fontSize: "1.2rem",
                          fontWeight: "bold",
                        }}>
                          ➔
                        </div>
                        <span style={{
                          fontSize: ".65rem",
                          color: "#C2410C",
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
                            color: "#27120A",
                            fontSize: "1.35rem",
                            fontWeight: "bold",
                          }}>
                            ➔
                          </div>
                          <span style={{
                            fontSize: ".66rem",
                            color: "#C2410C",
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
                            background: "linear-gradient(145deg, rgba(251,146,60,0.18) 0%, rgba(255,250,245,0.87) 100%)",
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
                                color: "#27120A",
                                letterSpacing: ".02em",
                                lineHeight: 1.35,
                              }}>
                                ⚡ Output Produced: {primaryOutput}
                              </h4>
                            </div>

                            {/* Daily yield from the physics model */}
                            <div style={{
                              padding: "10px 14px",
                              borderRadius: 12,
                              background: "rgba(255,250,245,0.81)",
                              border: "1px solid rgba(251,146,60,0.3)",
                              display: "flex",
                              flexDirection: "column",
                              gap: 3,
                            }}>
                              <span style={{ fontSize: ".68rem", color: "#7A4A38", textTransform: "uppercase", letterSpacing: ".06em" }}>
                                Model estimate · Daily yield
                              </span>
                              {modelYield.kind === "estimate" ? (
                                <>
                                  <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                                    <span style={{ fontSize: "1.25rem", fontWeight: 800, color: "#C2410C" }}>
                                      {Math.round(modelYield.energyKwhD).toLocaleString()}
                                    </span>
                                    <span style={{ fontSize: ".78rem", color: "#C2410C", fontWeight: 600 }}>
                                      kWh/day net energy
                                    </span>
                                  </div>
                                  {modelYield.energyKwhD < 0 && (
                                    <span style={{ fontSize: ".72rem", color: "#9A3412" }}>
                                      Uses more energy than it produces
                                    </span>
                                  )}
                                  {modelYield.products.length > 0 && (
                                    <span style={{ fontSize: ".78rem", color: "#431E12", fontWeight: 600 }}>
                                      {modelYield.products.join(" · ")}
                                    </span>
                                  )}
                                  <span style={{ fontSize: ".7rem", color: "#15803d" }}>
                                    Physics model, from {activeMass.toLocaleString()} kg/day input
                                  </span>
                                </>
                              ) : (
                                <span style={{ fontSize: ".88rem", fontWeight: 700, color: "#7A4A38" }}>
                                  {modelYield.message}
                                </span>
                              )}
                            </div>

                            {/* Action Button: Finalize Process & Go to Marketplace */}
                            <button
                              id="finalize-process-stream-btn"
                              onClick={handleFinalizeProcess}
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
                              <span>Finalize this process</span>
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

        {/* ══ STEP 2.5: FINALIZATION & ROUTING TO MARKETPLACE DOCK ══ */}
        {hasSimulated && loadPhase === 2 && (
          <section style={card({
            border: "2px solid #FB923C",
            background: "linear-gradient(135deg, rgba(251,146,60,0.18) 0%, rgba(255,250,245,0.88) 100%)",
            boxShadow: "0 0 40px rgba(251,146,60,0.4), inset 0 0 25px rgba(251,146,60,0.1)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 18,
            padding: "26px 32px",
          })}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: "1.4rem" }}>🎯</span>
                <h3 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 800, color: "#27120A", letterSpacing: ".06em", textTransform: "uppercase" }}>
                  Selected Process: {selectedPathwayName}
                </h3>
              </div>
              <p style={{ margin: "6px 0 0", fontSize: ".88rem", color: "#C2410C" }}>
                Next: find buyers and get your carbon audit report.
              </p>
            </div>

            <button
              id="finalize-process-bottom-btn"
              onClick={handleFinalizeProcess}
              style={{
                padding: "16px 38px",
                borderRadius: 999,
                background: "linear-gradient(90deg, #C2410C 0%, #EA580C 50%, #FB923C 100%)",
                border: "none",
                color: "#070a0f",
                fontFamily: FONT,
                fontWeight: 800,
                fontSize: "1.05rem",
                letterSpacing: ".12em",
                textTransform: "uppercase",
                cursor: "pointer",
                boxShadow: "0 0 30px rgba(251,146,60,0.7)",
                display: "inline-flex",
                alignItems: "center",
                gap: 12,
                transition: "all .2s ease",
              }}
            >
              <span>Finalize this process</span>
              <span style={{ fontSize: "1.25rem" }}>→</span>
            </button>
          </section>
        )}

        {/* ══ STEP 3: STAGE INSPECTOR DRAWER / MODAL ══ */}
        {inspectedStage && (
          <div
            onClick={() => setInspectedStage(null)}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(255,250,245,0.85)",
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
                background: "rgba(255,250,245,0.9)",
                border: "2px solid #FB923C",
                borderRadius: 24,
                boxShadow: "0 0 60px rgba(251,146,60,0.4), 0 25px 70px rgba(120,53,15,0.18)",
                maxWidth: 760,
                width: "100%",
                maxHeight: "90vh",
                overflowY: "auto",
                padding: "28px 32px",
                display: "flex",
                flexDirection: "column",
                gap: 22,
                fontFamily: FONT,
                color: "#27120A",
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
                      color: "#C2410C",
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
                    color: "#27120A",
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
                    background: "rgba(255,255,255,0.57)",
                    border: "1px solid rgba(251,146,60,0.3)",
                    color: "#C2410C",
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
                background: "radial-gradient(ellipse at 50% 60%, rgba(251,146,60,0.12) 0%, rgba(255,250,245,0.9) 80%)",
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
                  color: "#C2410C",
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
                    <span style={{ fontSize: ".68rem", color: "#C2410C", textTransform: "uppercase", letterSpacing: ".06em" }}>
                      🌡️ Temperature
                    </span>
                    <p style={{ margin: "4px 0 0", fontSize: "1.05rem", fontWeight: 800, color: "#27120A" }}>
                      {inspectedStage.operatingConditions?.temperature ?? "Ambient (~25°C)"}
                    </p>
                  </div>

                  <div style={{
                    padding: "12px 14px",
                    borderRadius: 12,
                    background: "rgba(14,165,233,0.1)",
                    border: "1px solid rgba(14,165,233,0.3)",
                  }}>
                    <span style={{ fontSize: ".68rem", color: "#0369a1", textTransform: "uppercase", letterSpacing: ".06em" }}>
                      📊 Operating Pressure
                    </span>
                    <p style={{ margin: "4px 0 0", fontSize: "1.05rem", fontWeight: 800, color: "#27120A" }}>
                      {inspectedStage.operatingConditions?.pressure ?? "1.0 bar (atm)"}
                    </p>
                  </div>

                  <div style={{
                    padding: "12px 14px",
                    borderRadius: 12,
                    background: "rgba(168,85,247,0.1)",
                    border: "1px solid rgba(168,85,247,0.3)",
                  }}>
                    <span style={{ fontSize: ".68rem", color: "#7e22ce", textTransform: "uppercase", letterSpacing: ".06em" }}>
                      ⏱️ Residence Time
                    </span>
                    <p style={{ margin: "4px 0 0", fontSize: "1.05rem", fontWeight: 800, color: "#27120A" }}>
                      {inspectedStage.operatingConditions?.residenceTime ?? "Continuous"}
                    </p>
                  </div>

                  <div style={{
                    padding: "12px 14px",
                    borderRadius: 12,
                    background: "rgba(34,197,94,0.1)",
                    border: "1px solid rgba(34,197,94,0.3)",
                  }}>
                    <span style={{ fontSize: ".68rem", color: "#15803d", textTransform: "uppercase", letterSpacing: ".06em" }}>
                      📈 Conversion Yield
                    </span>
                    <p style={{ margin: "4px 0 0", fontSize: "1.05rem", fontWeight: 800, color: "#27120A" }}>
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
                <p style={{ margin: 0, fontSize: ".8rem", color: "#C2410C", fontStyle: "italic" }}>
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
                background: "rgba(255,255,255,0.51)",
                border: "1px solid rgba(251,146,60,0.2)",
              }}>
                <div>
                  <span style={{ fontSize: ".72rem", color: "#15803d", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>
                    Subprocess Ingestion Materials:
                  </span>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
                    {(inspectedStage.subprocessInputs ?? inspectedStage.inputs).map((inp) => (
                      <span key={inp} style={{ fontSize: ".8rem", color: "#27120A" }}>
                        • {inp}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: ".72rem", color: "#0369a1", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>
                    Stage Stream Outputs:
                  </span>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
                    {inspectedStage.outputs.map((out) => (
                      <span key={out} style={{ fontSize: ".8rem", color: "#27120A" }}>
                        ➔ {out}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Equipment Highlights */}
              {inspectedStage.equipmentHighlights?.length > 0 && (
                <div>
                  <span style={{ fontSize: ".72rem", color: "#a16207", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>
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
                          color: "#a16207",
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
                      background: currentStageIndex > 0 ? "rgba(251,146,60,0.15)" : "rgba(255,255,255,0.51)",
                      border: "1px solid rgba(251,146,60,0.3)",
                      color: currentStageIndex > 0 ? "#C2410C" : "#7A4A38",
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
                      background: currentStageIndex < currentStages.length - 1 ? "rgba(251,146,60,0.15)" : "rgba(255,255,255,0.51)",
                      border: "1px solid rgba(251,146,60,0.3)",
                      color: currentStageIndex < currentStages.length - 1 ? "#C2410C" : "#7A4A38",
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
            <p style={{ margin: 0, color: "#b91c1c", fontSize: ".9rem" }}>⚠ {simError}</p>
            <Link href="/explore/industry" style={{
              display: "inline-block", marginTop: 14, color: C.accentSoft,
              textDecoration: "none", fontSize: ".88rem",
            }}>
              ← Return to Industry Hub
            </Link>
          </section>
        )}

      </div>
    </main>
  );
}

/* ── Default export wraps in Suspense (required for useSearchParams) ── */
export default function SimulatorPage() {
  return (
    <Suspense fallback={
      <main style={{ minHeight: "100vh", background: "rgba(255,250,245,0.9)", display: "flex",
        alignItems: "center", justifyContent: "center", fontFamily: '"Rubik",sans-serif' }}>
        <span style={{ color: "#9A3412", fontSize: "1rem", letterSpacing: ".1em" }}>
          Loading simulator…
        </span>
      </main>
    }>
      <SimulatorInner />
    </Suspense>
  );
}
