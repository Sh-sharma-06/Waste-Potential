"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

/* ── Industry accent tokens (from SelectionPage.css .card--industry) ── */
const IND = {
  accent: "#E2623A",
  accentSoft: "#F0A080",
  accentDim: "rgba(226,98,58,.45)",
  accentGlow: "rgba(226,98,58,.4)",
  accentInner: "rgba(226,98,58,.06)",
  accentDrop: "rgba(226,98,58,.45)",
  textBody: "#F5D2C2",
  gradTitle: "linear-gradient(90deg,#FFE4D6,#E2623A)",
  gradBtn: "linear-gradient(90deg,#C2410C,#E2623A)",
  btnText: "#1a0800",
  badgeBg: "rgba(226,98,58,.15)",
};

const BG = "#070a0f";
const FONT = '"Rubik",sans-serif';

const glassBorder = (color: string) => `1.5px solid ${color}`;
const glassCard = (
  border: string,
  glow: string,
  inner: string,
  extra?: React.CSSProperties
): React.CSSProperties => ({
  border: glassBorder(border),
  background: "rgba(255,255,255,.06)",
  backdropFilter: "blur(12px)",
  WebkitBackdropFilter: "blur(12px)",
  boxShadow: `0 10px 40px rgba(40,15,5,.45),inset 0 0 30px ${inner},0 0 36px ${glow}`,
  borderRadius: 20,
  padding: "28px 32px",
  boxSizing: "border-box",
  ...extra,
});

/* ── Real API response shape (GET /api/geocode?pincode=...) ── */
interface GeoResponse {
  lat: number;
  lng: number;
  display_name: string;
  precision: string;
  source: string;
  cached: boolean;
}

type WasteTab = "energy" | "non-energy";

/* ── Non-Energy Recoverable Itemized Categories ── */
interface ItemizedCategoryConfig {
  key: string;
  label: string;
  icon: string;
  desc: string;
  placeholder: string;
}

const NON_ENERGY_CATEGORIES: ItemizedCategoryConfig[] = [
  { key: "plastics", label: "Plastics", icon: "🧴", desc: "PET, HDPE, LDPE, PP, multilayer plastics", placeholder: "e.g. 500" },
  { key: "metals", label: "Metals", icon: "🔩", desc: "Ferrous scrap, steel, aluminum, copper", placeholder: "e.g. 300" },
  { key: "glass", label: "Glass", icon: "🍾", desc: "Clear flint, amber, green cullet & jars", placeholder: "e.g. 200" },
  { key: "electronics", label: "Electronics / E-Waste", icon: "💻", desc: "PCBs, consumer appliances, IT hardware", placeholder: "e.g. 150" },
  { key: "paper", label: "Paper / Cardboard", icon: "📦", desc: "OCC corrugated boxes, kraft, office pulp", placeholder: "e.g. 400" },
];

/* ── Geocode fetcher — hits the live backend via Next.js proxy ── */
async function fetchGeocode(pincode: string): Promise<GeoResponse> {
  const res = await fetch(
    `/api/geocode?pincode=${encodeURIComponent(pincode)}&country=India`
  );
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const body = await res.json(); detail = body?.detail ?? detail; } catch { }
    throw new Error(detail);
  }
  return res.json();
}

/* ── Inline animated spinner ── */
function Spinner() {
  return (
    <>
      <style>{`
        @keyframes wp-spin { to { transform: rotate(360deg); } }
        .wp-spinner {
          display: inline-block; width: 16px; height: 16px; border-radius: 50%;
          border: 2px solid rgba(240,160,128,.3); border-top-color: #F0A080;
          animation: wp-spin .7s linear infinite; vertical-align: middle;
          margin-right: 8px;
        }
      `}</style>
      <span className="wp-spinner" aria-hidden="true" />
    </>
  );
}

export default function IndustryPage() {
  const router = useRouter();

  const [pin, setPin] = useState("");
  const [geo, setGeo] = useState<GeoResponse | null>(null);
  const [geoLoading, setGeoLoading] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);

  const [tab, setTab] = useState<WasteTab>("energy");

  /* Energy Recoverable single input */
  const [weight, setWeight] = useState("");

  /* Step 1: Itemized quantities for Non-Energy Recoverable categories */
  const [itemizedQuantities, setItemizedQuantities] = useState<Record<string, string>>({
    plastics: "",
    metals: "",
    glass: "",
    electronics: "",
    paper: "",
  });

  /* Calculate total Non-Energy Recoverable quantity */
  const totalNonEnergyQuantity = Object.values(itemizedQuantities).reduce((acc, val) => {
    const num = parseFloat(val);
    return acc + (isNaN(num) || num < 0 ? 0 : num);
  }, 0);

  /* Proceed button enables based on active tab */
  const proceedEnabled = tab === "energy"
    ? parseFloat(weight) > 0
    : totalNonEnergyQuantity > 0;

  /* ── Geocode handler ── */
  const findLocation = async () => {
    const trimmed = pin.trim();
    if (!/^[1-9]\d{5}$/.test(trimmed)) {
      setGeoError("Enter a valid Indian 6-digit PIN code (must not start with 0).");
      return;
    }
    setGeoLoading(true);
    setGeoError(null);
    setGeo(null);
    try {
      const result = await fetchGeocode(trimmed);
      setGeo(result);
      try { localStorage.setItem("wp_location", trimmed); } catch { }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("404") || msg.toLowerCase().includes("no geocoding")) {
        setGeoError(`No location found for PIN ${trimmed}. Check the code and try again.`);
      } else if (msg.includes("422")) {
        setGeoError("Invalid PIN code format.");
      } else if (msg.includes("503")) {
        setGeoError("Location service is temporarily unavailable. Please try again shortly.");
      } else {
        setGeoError(`Could not resolve location: ${msg}`);
      }
    } finally {
      setGeoLoading(false);
    }
  };

  /* ── Proceed handler ── */
  const proceed = () => {
    if (!proceedEnabled) return;
    const resolvedPin = pin.trim() || "110001";

    if (tab === "energy") {
      const params = new URLSearchParams({
        pincode: resolvedPin,
        mass: weight,
        ...(geo ? { address: geo.display_name, lat: String(geo.lat), lng: String(geo.lng) } : {}),
      });
      router.push(`/simulator?${params.toString()}`);
    } else {
      /* Filter out 0 or empty inputs to build clean itemized breakdown */
      const breakdownObj: Record<string, number> = {};
      Object.entries(itemizedQuantities).forEach(([k, v]) => {
        const num = parseFloat(v);
        if (!isNaN(num) && num > 0) {
          breakdownObj[k] = num;
        }
      });

      const params = new URLSearchParams({
        pincode: resolvedPin,
        breakdown: JSON.stringify(breakdownObj),
        mass: String(totalNonEnergyQuantity),
        ...(geo ? { address: geo.display_name, lat: String(geo.lat), lng: String(geo.lng) } : {}),
      });

      /* Step 1 Requirement: Route to /market/non-energy?pincode={pincode}&breakdown={JSON_STRINGIFIED_QUANTITIES} */
      router.push(`/market/non-energy?${params.toString()}`);
    }
  };

  return (
    <main style={{
      minHeight: "100vh", background: BG, fontFamily: FONT, color: "#ffe4d6",
      backgroundImage: `radial-gradient(ellipse 65% 45% at 20% 15%,rgba(226,98,58,.07) 0%,transparent 70%),
                        radial-gradient(ellipse 50% 40% at 85% 75%,rgba(194,65,12,.05) 0%,transparent 70%)`,
      padding: "0 0 80px",
    }}>

      {/* ══ HEADER ══ */}
      <header style={{ padding: "28px 5vw 0", display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <Link href="/explore" style={{
            color: IND.accentSoft, textDecoration: "none", fontSize: ".95rem",
            letterSpacing: ".08em", display: "flex", alignItems: "center", gap: 6,
            border: glassBorder(IND.accentDim), borderRadius: 999, padding: "7px 18px",
            background: "rgba(226,98,58,.07)", backdropFilter: "blur(8px)",
          }}>
            ← Back to Categories
          </Link>
          <span style={{
            fontSize: ".8rem", letterSpacing: ".1em", color: IND.accentSoft,
            border: glassBorder(IND.accentDim), borderRadius: 999, padding: "5px 14px",
            background: IND.badgeBg, backdropFilter: "blur(8px)",
          }}>
            ⚙ INDUSTRY MODULE
          </span>
        </div>

        <div>
          <h1 style={{
            margin: "0 0 6px", fontSize: "clamp(1.3rem,3.2vw,2rem)", fontWeight: 700,
            letterSpacing: ".12em", textTransform: "uppercase",
            backgroundImage: IND.gradTitle,
            WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text",
          }}>
            Industrial Waste Intelligence Hub
          </h1>
          <p style={{ margin: 0, color: IND.textBody, fontSize: ".95rem", letterSpacing: ".03em" }}>
            Configure facility location and feedstock volume to simulate energy pathways and buyer markets.
          </p>
        </div>
      </header>

      {/* ══ FULL-WIDTH VERTICAL STACK ══ */}
      <div style={{ padding: "36px 5vw 0", display: "flex", flexDirection: "column", gap: 28, boxSizing: "border-box" }}>

        {/* ── 1. LOCATION CARD ── */}
        <section style={glassCard(IND.accentDim, IND.accentGlow, IND.accentInner)}>
          <h2 style={{ margin: "0 0 20px", fontSize: "1rem", letterSpacing: ".1em", color: IND.accentSoft, textTransform: "uppercase" }}>
            📍 Regional Location (Indian 6-Digit PIN Code)
          </h2>

          {/* PIN input row */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <input
              value={pin}
              onChange={(e) => {
                setPin(e.target.value.replace(/\D/g, "").slice(0, 6));
                setGeo(null);
                setGeoError(null);
              }}
              onKeyDown={(e) => e.key === "Enter" && !geoLoading && findLocation()}
              placeholder="e.g. 400001"
              maxLength={6}
              inputMode="numeric"
              aria-label="6-digit Indian PIN code"
              style={{
                flex: "1 1 180px", padding: "13px 20px", borderRadius: 12,
                border: glassBorder(geoError ? "#f87171" : pin.length === 6 && !geoError ? IND.accent : IND.accentDim),
                background: "rgba(255,255,255,.05)", backdropFilter: "blur(8px)",
                color: "#ffe4d6", fontFamily: FONT, fontSize: "1.05rem", letterSpacing: ".1em",
                outline: "none", transition: "border-color .2s",
              }}
            />
            <button
              onClick={findLocation}
              disabled={geoLoading}
              style={{
                flex: "0 0 auto", padding: "13px 28px", borderRadius: 12,
                border: glassBorder(IND.accent),
                background: geoLoading ? "rgba(255,255,255,.05)" : IND.gradBtn,
                color: geoLoading ? IND.accentSoft : IND.btnText,
                fontFamily: FONT, fontWeight: 600, fontSize: ".95rem", letterSpacing: ".12em",
                textTransform: "uppercase", cursor: geoLoading ? "not-allowed" : "pointer",
                boxShadow: geoLoading ? "none" : `0 0 18px ${IND.accentGlow}`,
                transition: "all .25s", whiteSpace: "nowrap",
              }}>
              {geoLoading ? <><Spinner />Fetching…</> : "Find Location"}
            </button>
          </div>

          {/* ── Loading state ── */}
          {geoLoading && (
            <p style={{ margin: "14px 0 0", color: IND.accentSoft, fontSize: ".88rem", letterSpacing: ".04em" }}>
              <Spinner />Fetching location data from OpenStreetMap Nominatim…
            </p>
          )}

          {/* ── Error state ── */}
          {geoError && (
            <div style={{
              marginTop: 14, padding: "12px 16px", borderRadius: 12,
              border: glassBorder("rgba(248,113,113,.4)"), background: "rgba(248,113,113,.08)",
            }}>
              <p style={{ margin: 0, color: "#f87171", fontSize: ".88rem" }}>⚠ {geoError}</p>
            </div>
          )}

          {/* ── Success state ── */}
          {geo && (
            <div style={{
              marginTop: 18, borderRadius: 14,
              border: glassBorder("rgba(226,98,58,.3)"),
              background: "rgba(226,98,58,.07)", backdropFilter: "blur(6px)",
              overflow: "hidden",
            }}>
              <div style={{ padding: "14px 20px", borderBottom: "1px solid rgba(226,98,58,.15)" }}>
                <p style={{ margin: "0 0 3px", color: "#c09080", fontSize: ".72rem", letterSpacing: ".12em", textTransform: "uppercase" }}>
                  Resolved Address
                </p>
                <p style={{ margin: 0, color: "#ffe4d6", fontSize: ".97rem", fontWeight: 500, lineHeight: 1.5 }}>
                  {geo.display_name}
                </p>
              </div>

              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                gap: 0,
              }}>
                {[
                  { label: "Latitude", value: `${geo.lat.toFixed(6)}° N` },
                  { label: "Longitude", value: `${geo.lng.toFixed(6)}° E` },
                  { label: "Precision", value: geo.precision || "Postal-code area centroid, approximate" },
                  { label: "Source", value: geo.source || "OpenStreetMap Nominatim (ODbL)" },
                ].map(({ label, value }, idx) => (
                  <div key={label} style={{
                    padding: "12px 20px",
                    borderRight: idx % 2 === 0 ? "1px solid rgba(226,98,58,.12)" : "none",
                    borderTop: idx >= 2 ? "1px solid rgba(226,98,58,.12)" : "none",
                  }}>
                    <p style={{ margin: "0 0 3px", color: "#c09080", fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>{label}</p>
                    <p style={{ margin: 0, color: "#ffe4d6", fontSize: ".88rem", fontWeight: 500 }}>{value}</p>
                  </div>
                ))}
              </div>

              <div style={{ padding: "8px 20px 12px", display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{
                  fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase",
                  padding: "3px 10px", borderRadius: 999,
                  background: geo.cached ? "rgba(74,222,128,.12)" : "rgba(226,98,58,.1)",
                  border: `1px solid ${geo.cached ? "rgba(74,222,128,.35)" : "rgba(226,98,58,.25)"}`,
                  color: geo.cached ? "#86EFAC" : IND.accentSoft,
                }}>
                  {geo.cached ? "⚡ Cached result" : "🌐 Live result"}
                </span>
              </div>
            </div>
          )}
        </section>

        {/* ── 2. WASTE CATEGORY TABS (Key Constraint: Non-Energy Recoverable) ── */}
        <section style={glassCard(IND.accentDim, IND.accentGlow, IND.accentInner)}>
          <h2 style={{ margin: "0 0 20px", fontSize: "1rem", letterSpacing: ".1em", color: IND.accentSoft, textTransform: "uppercase" }}>
            ⚡ Waste Category
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            {(
              [
                { id: "energy" as WasteTab, icon: "⚡", label: "Energy Recoverable", sub: "Thermal / Bio-conversion Streams" },
                { id: "non-energy" as WasteTab, icon: "♻️", label: "Non-Energy Recoverable", sub: "Recyclable / Material Recovery" },
              ] as { id: WasteTab; icon: string; label: string; sub: string }[]
            ).map(({ id, icon, label, sub }) => {
              const active = tab === id;
              return (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  style={{
                    padding: "18px 20px", borderRadius: 16, textAlign: "left",
                    border: active ? glassBorder(IND.accent) : glassBorder("rgba(226,98,58,.22)"),
                    background: active ? "rgba(226,98,58,.14)" : "rgba(255,255,255,.03)",
                    cursor: "pointer",
                    boxShadow: active ? `0 0 22px ${IND.accentGlow}, inset 0 0 20px rgba(226,98,58,.08)` : "none",
                    transition: "all .25s",
                  }}>
                  <p style={{ margin: "0 0 4px", fontSize: "1.15rem" }}>{icon}</p>
                  <p style={{
                    margin: "0 0 4px", fontFamily: FONT, fontWeight: 700,
                    fontSize: ".95rem", letterSpacing: ".08em", textTransform: "uppercase",
                    color: active ? "#FB923C" : "#c09080",
                  }}>
                    {label}
                  </p>
                  <p style={{ margin: 0, fontFamily: FONT, fontSize: ".8rem", color: active ? IND.textBody : "#7a5545" }}>
                    {sub}
                  </p>
                </button>
              );
            })}
          </div>
          <p style={{ margin: "16px 0 0", fontSize: ".82rem", color: "#b07060", letterSpacing: ".03em" }}>
            {tab === "energy"
              ? "Energy Recoverable waste streams will be routed through the Energy Simulator for thermodynamic conversion pathway modelling."
              : "Non-Energy Recoverable waste streams will be routed to the Non-Energy Recoverable Marketplace for itemized industrial recycling offtake pricing."}
          </p>
        </section>

        {/* ── 3. FEEDSTOCK QUANTITY & PROCEED ── */}
        <section style={glassCard(IND.accentDim, IND.accentGlow, IND.accentInner)}>
          {tab === "energy" ? (
            /* Energy Recoverable single input view */
            <>
              <h2 style={{ margin: "0 0 6px", fontSize: "1rem", letterSpacing: ".1em", color: IND.accentSoft, textTransform: "uppercase" }}>
                ⚖ Total Waste Quantity (Energy Recoverable)
              </h2>
              <p style={{ margin: "0 0 18px", fontSize: ".82rem", color: "#b07060", letterSpacing: ".04em" }}>
                kg / day — The entered quantity will be converted for simulation models and energy yield analysis.
              </p>

              <input
                type="number"
                min="0"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                placeholder="e.g. 10000"
                aria-label="Total waste quantity in kg per day"
                style={{
                  width: "100%", padding: "15px 22px", borderRadius: 14, boxSizing: "border-box",
                  border: glassBorder(
                    weight !== "" && parseFloat(weight) <= 0 ? "#f87171"
                      : proceedEnabled ? IND.accent
                        : IND.accentDim
                  ),
                  background: "rgba(255,255,255,.05)", backdropFilter: "blur(8px)",
                  color: "#ffe4d6", fontFamily: FONT, fontSize: "1.2rem", letterSpacing: ".06em",
                  outline: "none", transition: "border-color .2s",
                }}
              />

              {weight !== "" && parseFloat(weight) <= 0 && (
                <p style={{ margin: "10px 0 0", color: "#f87171", fontSize: ".84rem" }}>
                  ⚠ Quantity must be greater than 0.
                </p>
              )}
            </>
          ) : (
            /* Step 1 Requirement: Itemized Input Fields for Non-Energy Recoverable Categories */
            <>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginBottom: 6 }}>
                <h2 style={{ margin: 0, fontSize: "1.05rem", letterSpacing: ".08em", color: "#FB923C", textTransform: "uppercase", fontWeight: 800 }}>
                  ⚖ Itemized Feedstock Quantities (Non-Energy Recoverable)
                </h2>
                <span style={{ fontSize: ".76rem", color: "#fdba74" }}>
                  Unit: kg / day
                </span>
              </div>
              <p style={{ margin: "0 0 20px", fontSize: ".84rem", color: "#b07060", letterSpacing: ".02em" }}>
                Enter estimated daily volumes for each non-energy recoverable material category. Live industrial buyers and pricing tables will be fetched per stream.
              </p>

              {/* Itemized Category Input Grid */}
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                gap: 16,
              }}>
                {NON_ENERGY_CATEGORIES.map((cat) => {
                  const val = itemizedQuantities[cat.key] || "";
                  const num = parseFloat(val);
                  const isEntered = !isNaN(num) && num > 0;

                  return (
                    <div
                      key={cat.key}
                      style={{
                        padding: "18px 20px",
                        borderRadius: 16,
                        background: isEntered ? "rgba(251,146,60,0.12)" : "rgba(15,23,42,0.6)",
                        border: isEntered ? "1.5px solid #FB923C" : "1px solid rgba(226,98,58,.22)",
                        boxShadow: isEntered ? "0 0 18px rgba(251,146,60,0.25)" : "none",
                        transition: "all .2s ease",
                        display: "flex",
                        flexDirection: "column",
                        gap: 10,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontSize: "1.4rem" }}>{cat.icon}</span>
                          <span style={{
                            fontFamily: FONT,
                            fontWeight: 700,
                            fontSize: ".94rem",
                            color: isEntered ? "#FB923C" : "#FFE4D6",
                            letterSpacing: ".02em",
                          }}>
                            {cat.label}
                          </span>
                        </div>
                        {isEntered && (
                          <span style={{
                            fontSize: ".65rem",
                            fontWeight: 800,
                            padding: "2px 8px",
                            borderRadius: 999,
                            background: "rgba(34,197,94,0.2)",
                            border: "1px solid rgba(34,197,94,0.5)",
                            color: "#86efac",
                          }}>
                            ACTIVE
                          </span>
                        )}
                      </div>

                      <p style={{ margin: 0, fontSize: ".74rem", color: "#9a6050", lineHeight: 1.35 }}>
                        {cat.desc}
                      </p>

                      <div style={{ position: "relative", marginTop: 2 }}>
                        <input
                          type="number"
                          min="0"
                          value={val}
                          onChange={(e) => {
                            const v = e.target.value;
                            setItemizedQuantities((prev) => ({
                              ...prev,
                              [cat.key]: v,
                            }));
                          }}
                          placeholder={cat.placeholder}
                          aria-label={`${cat.label} quantity in kg per day`}
                          style={{
                            width: "100%",
                            padding: "12px 64px 12px 16px",
                            borderRadius: 10,
                            boxSizing: "border-box",
                            border: "1px solid rgba(251,146,60,0.3)",
                            background: "rgba(7,10,15,0.85)",
                            color: "#ffe4d6",
                            fontFamily: FONT,
                            fontSize: "1.05rem",
                            fontWeight: 600,
                            outline: "none",
                          }}
                        />
                        <span style={{
                          position: "absolute",
                          right: 14,
                          top: 13,
                          fontSize: ".75rem",
                          color: "#fdba74",
                          fontWeight: 600,
                          pointerEvents: "none",
                        }}>
                          kg/day
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Total Aggregate Summary Strip */}
              <div style={{
                marginTop: 20,
                padding: "14px 20px",
                borderRadius: 14,
                background: "rgba(251,146,60,0.12)",
                border: "1px solid rgba(251,146,60,0.35)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: 10,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontSize: "1.3rem" }}>📦</span>
                  <div>
                    <span style={{ fontSize: ".7rem", color: "#fdba74", textTransform: "uppercase", letterSpacing: ".06em" }}>
                      Total Non-Energy Recoverable Volume
                    </span>
                    <p style={{ margin: 0, fontSize: "1.1rem", fontWeight: 800, color: "#FFE4D6" }}>
                      {totalNonEnergyQuantity.toLocaleString()} kg / day
                    </p>
                  </div>
                </div>

                <span style={{
                  fontSize: ".74rem",
                  color: totalNonEnergyQuantity > 0 ? "#86efac" : "#9a6050",
                  fontWeight: 600,
                }}>
                  {totalNonEnergyQuantity > 0
                    ? `✓ Ready for marketplace routing (${Object.values(itemizedQuantities).filter(v => parseFloat(v) > 0).length} streams active)`
                    : "Enter quantity in at least one category to proceed"}
                </span>
              </div>
            </>
          )}

          {/* ── Proceed Button (Step 1 Requirement: PROCEED TO MARKETPLACE → activates only when totalQuantity > 0) ── */}
          <button
            disabled={!proceedEnabled}
            onClick={proceed}
            style={{
              marginTop: 26, width: "100%", padding: "16px 0", borderRadius: 999,
              border: glassBorder(proceedEnabled ? IND.accent : "rgba(226,98,58,.2)"),
              background: proceedEnabled ? IND.gradBtn : "rgba(255,255,255,.04)",
              color: proceedEnabled ? IND.btnText : "rgba(240,160,128,.3)",
              fontFamily: FONT, fontWeight: 800, fontSize: "1.05rem", letterSpacing: ".16em",
              textTransform: "uppercase", cursor: proceedEnabled ? "pointer" : "not-allowed",
              boxShadow: proceedEnabled ? `0 0 30px ${IND.accentGlow}` : "none",
              filter: proceedEnabled ? `drop-shadow(0 0 8px ${IND.accentDrop})` : "none",
              transition: "all .3s",
              opacity: proceedEnabled ? 1 : 0.45,
            }}>
            {proceedEnabled
              ? tab === "energy"
                ? "PROCEED TO SIMULATOR →"
                : "PROCEED TO MARKETPLACE →"
              : tab === "energy"
                ? "PROCEED TO SIMULATOR  (enter quantity to unlock)"
                : "PROCEED TO MARKETPLACE  (enter category quantity to unlock)"}
          </button>
        </section>

      </div>
    </main>
  );
}
