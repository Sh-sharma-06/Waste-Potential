"use client";

import React, { useState, useEffect } from "react";
import AudioReaderButton from "./AudioReaderButton";

// ============================================================================
// Types and Constants
// ============================================================================

/** The simulator's seven pathways; ids match the backend and the simulator page. */
export const PROCESSES = [
  { id: "pyrolysis", name: "Pyrolysis" },
  { id: "gasification", name: "Gasification" },
  { id: "anaerobic_digestion", name: "Anaerobic Digestion" },
  { id: "htc", name: "Hydrothermal Carbonisation (HTC)" },
  { id: "composting", name: "Composting" },
  { id: "incineration", name: "Incineration" },
  { id: "torrefaction", name: "Torrefaction" },
] as const;

export type ProcessId = (typeof PROCESSES)[number]["id"];

export const DURATION_OPTIONS = [
  "No preference",
  "Continuous, < 24 hours",
  "Days (1–7 days)",
  "Weeks (2–8 weeks)",
] as const;

// Checked in order: torrefaction before pyrolysis, since it is often described as "mild pyrolysis".
const PROCESS_KEYWORDS: [string, ProcessId][] = [
  ["torref", "torrefaction"],
  ["hydrothermal", "htc"],
  ["htc", "htc"],
  ["anaerobic", "anaerobic_digestion"],
  ["digest", "anaerobic_digestion"],
  ["biogas", "anaerobic_digestion"],
  ["gasif", "gasification"],
  ["pyro", "pyrolysis"],
  ["compost", "composting"],
  ["incinerat", "incineration"],
  ["mass burn", "incineration"],
];

/** Map any process id or display name ("HTC", "Hydrothermal Carbonization", "htc") to a canonical id. */
export function toProcessId(text: string | null | undefined): ProcessId | null {
  const s = (text || "").trim().toLowerCase().replace(/[-_]/g, " ");
  if (!s) return null;
  const exact = PROCESSES.find((p) => s === p.id.replace(/_/g, " ") || s === p.name.toLowerCase());
  if (exact) return exact.id;
  return PROCESS_KEYWORDS.find(([kw]) => s.includes(kw))?.[1] ?? null;
}

export interface ProcessSelectorProps {
  location: string;
  /** Tonnes per day. */
  weight: number;
  /** "energy" | "non-energy" */
  category?: string;
  pincode?: string;
  lat?: number;
  lng?: number;
  /** Optional override; when omitted the backend looks up live weather for the PIN / coordinates. */
  weather?: string;
  /** Initial duration preference. */
  duration?: string;
  /** Controlled selection (canonical id) from the parent, if it tracks one. */
  selectedProcessId?: string | null;
  onSelectProcess?: (processId: ProcessId) => void;
  className?: string;
}

interface ProcessInfo {
  icon: string;
  tagline: string;
  typicalProducts: string;
  idealMoisture: string;
}

const PROCESS_DATA: Record<ProcessId, ProcessInfo> = {
  pyrolysis: {
    icon: "🌡️",
    tagline: "Thermal cracking at 400–650°C in the absence of oxygen",
    typicalProducts: "Bio-oil, Biochar & Syngas",
    idealMoisture: "< 15%",
  },
  gasification: {
    icon: "🔥",
    tagline: "High-temperature partial oxidation producing energy-dense syngas",
    typicalProducts: "Syngas, Electricity & Hydrogen",
    idealMoisture: "< 20%",
  },
  anaerobic_digestion: {
    icon: "🧪",
    tagline: "Bacterial digestion of high-moisture organic feedstock",
    typicalProducts: "Bio-CNG, Digestate & Organic Fertilizer",
    idealMoisture: "> 60%",
  },
  htc: {
    icon: "💧",
    tagline: "Wet carbonisation at 180–250°C under subcritical water pressure",
    typicalProducts: "Hydro-char & Liquid Fertilizer",
    idealMoisture: "50% – 90%",
  },
  composting: {
    icon: "🌾",
    tagline: "Aerobic biological humification into stabilized compost",
    typicalProducts: "Soil Conditioner & Organic Humus",
    idealMoisture: "40% – 60%",
  },
  incineration: {
    icon: "⚡",
    tagline: "Direct thermal combustion with high-efficiency steam recovery",
    typicalProducts: "High-pressure Steam & Baseload Power",
    idealMoisture: "< 35%",
  },
  torrefaction: {
    icon: "🪵",
    tagline: "Mild roasting at 200–300°C that upgrades biomass into a coal-like solid fuel",
    typicalProducts: "Torrefied Bio-coal & Pellets",
    idealMoisture: "< 15%",
  },
};

// ============================================================================
// Markdown Renderer Component
// ============================================================================

function MarkdownRenderer({ content }: { content: string }) {
  const lines = content.split("\n");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px", lineHeight: 1.6 }}>
      {lines.map((rawLine, idx) => {
        const line = rawLine.trim();
        if (!line) {
          return <div key={idx} style={{ height: "4px" }} />;
        }

        if (line.startsWith("### ")) {
          return (
            <h4
              key={idx}
              style={{
                margin: "14px 0 4px",
                fontSize: "1rem",
                fontWeight: 700,
                color: "#C2410C",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              {line.replace(/^###\s+/, "")}
            </h4>
          );
        }

        if (line.startsWith("## ")) {
          return (
            <h3
              key={idx}
              style={{
                margin: "18px 0 6px",
                fontSize: "1.15rem",
                fontWeight: 800,
                color: "#C2410C",
                borderBottom: "1px solid rgba(226, 98, 58, 0.25)",
                paddingBottom: "6px",
                letterSpacing: "0.02em",
              }}
            >
              {line.replace(/^##\s+/, "")}
            </h3>
          );
        }

        if (line.startsWith("# ")) {
          return (
            <h2
              key={idx}
              style={{
                margin: "20px 0 8px",
                fontSize: "1.3rem",
                fontWeight: 800,
                color: "#27120A",
              }}
            >
              {line.replace(/^#\s+/, "")}
            </h2>
          );
        }

        if (line.startsWith("- ") || line.startsWith("* ")) {
          const itemText = line.replace(/^[-*]\s+/, "");
          const html = itemText.replace(
            /\*\*(.+?)\*\*/g,
            '<strong style="color: #9A3412; font-weight: 700;">$1</strong>'
          );
          return (
            <div
              key={idx}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "8px",
                paddingLeft: "6px",
                color: "#431E12",
                fontSize: "0.93rem",
              }}
            >
              <span style={{ color: "#C2410C", fontSize: "1.1rem", lineHeight: 1 }}>•</span>
              <span dangerouslySetInnerHTML={{ __html: html }} />
            </div>
          );
        }

        const formattedHtml = line.replace(
          /\*\*(.+?)\*\*/g,
          '<strong style="color: #9A3412; font-weight: 700;">$1</strong>'
        );

        return (
          <p
            key={idx}
            style={{ margin: 0, color: "#5B3A2E", fontSize: "0.93rem" }}
            dangerouslySetInnerHTML={{ __html: formattedHtml }}
          />
        );
      })}
    </div>
  );
}

// ============================================================================
// Main ProcessSelector Component
// ============================================================================

export default function ProcessSelector({
  location,
  weight,
  category,
  pincode,
  lat,
  lng,
  weather,
  duration,
  selectedProcessId,
  onSelectProcess,
  className,
}: ProcessSelectorProps) {
  const [suggestedId, setSuggestedId] = useState<ProcessId | null>(null);
  const [weatherUsed, setWeatherUsed] = useState<string | null>(weather || null);
  const [durationPref, setDurationPref] = useState<string>(duration || DURATION_OPTIONS[0]);
  const [isRecommending, setIsRecommending] = useState<boolean>(true);
  const [recommendError, setRecommendError] = useState<string | null>(null);

  // Briefing cache, keyed by process id
  const [detailsCache, setDetailsCache] = useState<Record<string, string>>({});
  const [loadingProcess, setLoadingProcess] = useState<string | null>(null);
  const [expandedProcess, setExpandedProcess] = useState<string | null>(null);
  const [localSelectedId, setLocalSelectedId] = useState<ProcessId | null>(null);
  const [fetchError, setFetchError] = useState<Record<string, string>>({});

  const selectedId = selectedProcessId !== undefined ? toProcessId(selectedProcessId) : localSelectedId;
  const nameOf = (id: string | null) => PROCESSES.find((p) => p.id === id)?.name ?? null;
  // Briefings compare against the current suggestion, so cache per (suggestion, process).
  const cacheKey = (processId: string) => `${suggestedId ?? "none"}:${processId}`;

  // --------------------------------------------------------------------------
  // Step 4: Fetch Suggested Process On Mount
  // --------------------------------------------------------------------------
  useEffect(() => {
    let isCancelled = false;

    async function fetchRecommendation() {
      setIsRecommending(true);
      setRecommendError(null);

      const payload = {
        location: location || "Unknown Region",
        weight: Number(weight) > 0 ? Number(weight) : 10,
        category: category || null,
        pincode: pincode || null,
        lat: lat ?? null,
        lng: lng ?? null,
        weather: weather || null,
        duration_pref: durationPref,
      };

      try {
        let res: Response;
        try {
          res = await fetch("/simulator/recommend", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          if (!res.ok && res.status === 404) {
            res = await fetch("/api/simulator/recommend", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
          }
        } catch {
          res = await fetch("/api/simulator/recommend", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
        }

        if (!res.ok) {
          let errDetail = `Server returned HTTP ${res.status}`;
          try {
            const errJson = await res.json();
            if (errJson?.detail) errDetail = errJson.detail;
          } catch {}
          throw new Error(errDetail);
        }

        const data = await res.json();
        const id = toProcessId(data?.process_id) ?? toProcessId(data?.suggested_process);
        if (!isCancelled) {
          if (!id) throw new Error(`Unrecognised recommendation: ${data?.suggested_process}`);
          setSuggestedId(id);
          if (data.weather_used) setWeatherUsed(data.weather_used);
        }
      } catch (err: any) {
        if (!isCancelled) {
          console.warn("Simulator recommendation error:", err);
          setRecommendError(err?.message || "Failed to retrieve AI process recommendation.");
        }
      } finally {
        if (!isCancelled) {
          setIsRecommending(false);
        }
      }
    }

    fetchRecommendation();

    return () => {
      isCancelled = true;
    };
  }, [location, weight, category, pincode, lat, lng, weather, durationPref]);

  // --------------------------------------------------------------------------
  // Step 5: On-Demand Fetching with Details Cache
  // --------------------------------------------------------------------------
  async function handleToggleDetails(processId: ProcessId) {
    // If accordion is already open for this process, close it
    if (expandedProcess === processId) {
      setExpandedProcess(null);
      return;
    }

    // If explanation is already in detailsCache, expand immediately without API call
    if (detailsCache[cacheKey(processId)]) {
      setExpandedProcess(processId);
      return;
    }

    // Otherwise show inline loading spinner and fetch from API
    setLoadingProcess(processId);
    setFetchError((prev) => ({ ...prev, [processId]: "" }));

    const payload = {
      location: location || "Unknown Region",
      weight: Number(weight) > 0 ? Number(weight) : 10,
      weather: weatherUsed || "unknown",
      target_process: nameOf(processId),
      suggested_process: nameOf(suggestedId) || "not yet determined",
    };

    try {
      let res: Response;
      try {
        res = await fetch("/simulator/process-details", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok && res.status === 404) {
          res = await fetch("/api/simulator/process-details", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
        }
      } catch {
        res = await fetch("/api/simulator/process-details", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }

      if (!res.ok) {
        let errDetail = `Server returned HTTP ${res.status}`;
        try {
          const errJson = await res.json();
          if (errJson?.detail) errDetail = errJson.detail;
        } catch {}
        throw new Error(errDetail);
      }

      const data = await res.json();
      const markdownResult =
        data.details ||
        data.explanation ||
        data.markdown ||
        (typeof data === "string" ? data : JSON.stringify(data));

      // Cache the fetched explanation so subsequent clicks don't hit the API
      setDetailsCache((prev) => ({
        ...prev,
        [cacheKey(processId)]: markdownResult,
        [processId]: markdownResult, // latest briefing, rendered in the panel
      }));
      setExpandedProcess(processId);
    } catch (err: any) {
      setFetchError((prev) => ({
        ...prev,
        [processId]: err?.message || "Could not retrieve details for this process.",
      }));
      setExpandedProcess(processId);
    } finally {
      setLoadingProcess(null);
    }
  }

  function handleSelect(processId: ProcessId) {
    setLocalSelectedId(processId);
    if (onSelectProcess) {
      onSelectProcess(processId);
    }
  }

  // --------------------------------------------------------------------------
  // Render
  // --------------------------------------------------------------------------
  return (
    <div
      className={className}
      style={{
        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        color: "#27120A",
        maxWidth: "1080px",
        margin: "0 auto",
        padding: "24px 16px",
      }}
    >
      {/* Header status bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          marginBottom: "24px",
          padding: "16px 20px",
          borderRadius: "16px",
          background: "rgba(255,250,245,0.8)",
          backdropFilter: "blur(14px)",
          border: "1px solid rgba(226, 98, 58, 0.25)",
          boxShadow: "0 8px 32px rgba(120,53,15,0.12)",
        }}
      >
        <div>
          <h2
            style={{
              margin: 0,
              fontSize: "1.35rem",
              fontWeight: 800,
              background: "linear-gradient(90deg, #431E12, #C2410C)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Waste-to-Energy Process Recommendation Engine
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: "0.88rem", color: "#7A4A38" }}>
            Operating for: <strong style={{ color: "#431E12" }}>{location || "All regions"}</strong> |{" "}
            <strong style={{ color: "#431E12" }}>{weight} tonnes/day</strong> |{" "}
            Weather: <strong style={{ color: "#431E12" }}>{weatherUsed || (isRecommending ? "fetching live…" : "unavailable")}</strong>
          </p>
          <label style={{ display: "inline-flex", alignItems: "center", gap: "8px", marginTop: "8px", fontSize: "0.82rem", color: "#7A4A38" }}>
            Preferred processing duration:
            <select
              value={durationPref}
              onChange={(e) => setDurationPref(e.target.value)}
              style={{
                background: "rgba(255,250,245,0.86)",
                color: "#27120A",
                border: "1px solid rgba(226, 98, 58, 0.4)",
                borderRadius: "8px",
                padding: "4px 8px",
                fontSize: "0.82rem",
              }}
            >
              {DURATION_OPTIONS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </label>
        </div>

        {/* AI Recommendation Badge / Spinner */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          {isRecommending ? (
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                padding: "6px 14px",
                borderRadius: "999px",
                background: "rgba(226, 98, 58, 0.15)",
                border: "1px solid rgba(226, 98, 58, 0.4)",
                color: "#C2410C",
                fontSize: "0.85rem",
                fontWeight: 600,
              }}
            >
              <span
                style={{
                  width: "12px",
                  height: "12px",
                  borderRadius: "50%",
                  border: "2px solid #ffaa80",
                  borderTopColor: "transparent",
                  animation: "spin 0.8s linear infinite",
                  display: "inline-block",
                }}
              />
              Evaluating {PROCESSES.length} Processes...
            </div>
          ) : suggestedId ? (
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "6px 16px",
                borderRadius: "999px",
                background: "linear-gradient(135deg, rgba(226, 98, 58, 0.3), rgba(249, 115, 22, 0.2))",
                border: "1px solid #e2623a",
                color: "#431E12",
                fontSize: "0.9rem",
                fontWeight: 700,
                boxShadow: "0 0 20px rgba(226, 98, 58, 0.35)",
              }}
            >
              <span>AI Choice:</span>
              <span style={{ color: "#C2410C" }}>{nameOf(suggestedId)}</span>
            </div>
          ) : recommendError ? (
            <div
              style={{
                padding: "6px 12px",
                borderRadius: "999px",
                background: "rgba(239, 68, 68, 0.15)",
                border: "1px solid rgba(239, 68, 68, 0.4)",
                color: "#b91c1c",
                fontSize: "0.82rem",
              }}
            >
              Recommendation offline
            </div>
          ) : null}
        </div>
      </div>

      {/* Grid of the 7 Waste Processing Methods */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
          gap: "18px",
        }}
      >
        {PROCESSES.map(({ id: proc, name }) => {
          const isSuggested = suggestedId === proc;
          const isSelected = selectedId === proc;
          const isExpanded = expandedProcess === proc;
          const isLoadingDetails = loadingProcess === proc;
          const meta = PROCESS_DATA[proc];

          return (
            <div
              key={proc}
              data-process-id={proc}
              data-suggested={isSuggested || undefined}
              data-selected={isSelected || undefined}
              style={{
                display: "flex",
                flexDirection: "column",
                borderRadius: "18px",
                background: isSelected
                  ? "linear-gradient(165deg, rgba(255,250,245,0.86) 0%, rgba(255,250,245,0.88) 100%)"
                  : isSuggested
                  ? "linear-gradient(165deg, rgba(255,250,245,0.85) 0%, rgba(255,250,245,0.88) 100%)"
                  : "rgba(255,250,245,0.81)",
                backdropFilter: "blur(14px)",
                border: isSelected
                  ? "2px solid #22c55e"
                  : isSuggested
                  ? "2px solid #e2623a"
                  : "1px solid rgba(194,65,12,0.2)",
                boxShadow: isSelected
                  ? "0 10px 30px rgba(34, 197, 94, 0.25), 0 0 24px rgba(34, 197, 94, 0.18)"
                  : isSuggested
                  ? "0 10px 30px rgba(226, 98, 58, 0.25), 0 0 24px rgba(226, 98, 58, 0.15)"
                  : "0 6px 20px rgba(120,53,15,0.1)",
                transition: "all 0.25s ease",
                overflow: "hidden",
              }}
            >
              {/* Process Card Top Bar */}
              <div style={{ padding: "20px 22px 14px" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: "10px",
                    marginBottom: "10px",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <span style={{ fontSize: "1.6rem" }}>{meta?.icon || "⚙️"}</span>
                    <div>
                      <h3
                        style={{
                          margin: 0,
                          fontSize: "1.18rem",
                          fontWeight: 700,
                          color: isSuggested || isSelected ? "#27120A" : "#27120A",
                        }}
                      >
                        {name}
                      </h3>
                      <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#7A4A38" }}>
                        Products: {meta?.typicalProducts}
                      </p>
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "6px" }}>
                  {isSelected && (
                    <span
                      style={{
                        padding: "4px 12px",
                        borderRadius: "999px",
                        background: "linear-gradient(90deg, #15803d, #22c55e)",
                        color: "#ffffff",
                        fontWeight: 800,
                        fontSize: "0.78rem",
                        whiteSpace: "nowrap",
                      }}
                    >
                      ✓ Selected
                    </span>
                  )}
                  {/* Step 4: Highly visible "✨ Suggested" badge */}
                  {isSuggested && (
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "4px",
                        padding: "4px 12px",
                        borderRadius: "999px",
                        background: "linear-gradient(135deg, #c2410c 0%, #ea580c 50%, #f97316 100%)",
                        color: "#ffffff",
                        fontWeight: 800,
                        fontSize: "0.78rem",
                        boxShadow: "0 0 16px rgba(234, 88, 12, 0.6)",
                        letterSpacing: "0.03em",
                        whiteSpace: "nowrap",
                        animation: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
                      }}
                    >
                      ✨ Suggested
                    </span>
                  )}
                  </div>
                </div>

                <p
                  style={{
                    margin: "4px 0 14px",
                    fontSize: "0.85rem",
                    color: "#5B3A2E",
                    lineHeight: 1.45,
                  }}
                >
                  {meta?.tagline}
                </p>

                {/* Sub-metrics */}
                <div
                  style={{
                    display: "flex",
                    gap: "12px",
                    fontSize: "0.78rem",
                    color: "#7A4A38",
                    marginBottom: "14px",
                  }}
                >
                  <span
                    style={{
                      background: "rgba(255,255,255,0.55)",
                      padding: "3px 8px",
                      borderRadius: "6px",
                    }}
                  >
                    Optimal Feed: <strong>{meta?.idealMoisture}</strong>
                  </span>
                </div>

                {/* Show Details Button */}
                <div style={{ display: "flex", gap: "10px" }}>
                  <button
                    type="button"
                    onClick={() => handleToggleDetails(proc)}
                    disabled={isLoadingDetails}
                    style={{
                      flex: 1,
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "8px",
                      padding: "9px 16px",
                      borderRadius: "10px",
                      fontSize: "0.88rem",
                      fontWeight: 600,
                      cursor: isLoadingDetails ? "not-allowed" : "pointer",
                      background: isExpanded
                        ? "rgba(226, 98, 58, 0.2)"
                        : "rgba(255,255,255,0.59)",
                      color: isExpanded ? "#C2410C" : "#27120A",
                      border: isExpanded
                        ? "1px solid #e2623a"
                        : "1px solid rgba(194,65,12,0.2)",
                      transition: "all 0.2s ease",
                    }}
                  >
                    {/* Step 5: Inline loading spinner */}
                    {isLoadingDetails ? (
                      <>
                        <span
                          style={{
                            width: "14px",
                            height: "14px",
                            borderRadius: "50%",
                            border: "2px solid #ffaa80",
                            borderTopColor: "transparent",
                            animation: "spin 0.7s linear infinite",
                            display: "inline-block",
                          }}
                        />
                        <span>Analyzing with AI...</span>
                      </>
                    ) : isExpanded ? (
                      <>
                        <span>Hide Details</span>
                        <span style={{ fontSize: "0.75rem" }}>▲</span>
                      </>
                    ) : (
                      <>
                        <span>Show Details</span>
                        <span style={{ fontSize: "0.75rem" }}>▼</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Step 5: Expandable Accordion / Glass-morphism Container */}
              {isExpanded && (
                <div
                  style={{
                    padding: "18px 22px 22px",
                    background: "rgba(255,250,245,0.85)",
                    borderTop: "1px solid rgba(226, 98, 58, 0.3)",
                    borderBottomLeftRadius: "18px",
                    borderBottomRightRadius: "18px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "18px",
                    animation: "fadeIn 0.25s ease-in-out",
                  }}
                >
                  {fetchError[proc] ? (
                    <div
                      style={{
                        padding: "12px 14px",
                        borderRadius: "10px",
                        background: "rgba(239, 68, 68, 0.12)",
                        border: "1px solid rgba(239, 68, 68, 0.35)",
                        color: "#b91c1c",
                        fontSize: "0.85rem",
                      }}
                    >
                      {fetchError[proc]}
                    </div>
                  ) : detailsCache[proc] ? (
                    <div
                      style={{
                        maxHeight: "360px",
                        overflowY: "auto",
                        paddingRight: "8px",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
                        <AudioReaderButton text={detailsCache[proc]} />
                      </div>
                      <MarkdownRenderer content={detailsCache[proc]} />
                    </div>
                  ) : (
                    <p style={{ color: "#7A4A38", fontSize: "0.88rem" }}>
                      Loading briefing...
                    </p>
                  )}

                  {/* Step 5: Primary "Select This Process" Button */}
                  <button
                    type="button"
                    onClick={() => handleSelect(proc)}
                    style={{
                      padding: "12px 20px",
                      borderRadius: "12px",
                      fontSize: "0.95rem",
                      fontWeight: 700,
                      cursor: "pointer",
                      border: "none",
                      color: isSelected ? "#ffffff" : "#1a0800",
                      background: isSelected
                        ? "linear-gradient(90deg, #15803d, #22c55e)"
                        : "linear-gradient(90deg, #c2410c, #e2623a)",
                      boxShadow: isSelected
                        ? "0 4px 20px rgba(34, 197, 94, 0.4)"
                        : "0 4px 20px rgba(226, 98, 58, 0.45)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "8px",
                      transition: "all 0.2s ease",
                    }}
                  >
                    {isSelected ? (
                      <>
                        <span>✓ Process Selected</span>
                      </>
                    ) : (
                      <>
                        <span>Select This Process</span>
                        <span>➔</span>
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Global micro-keyframes */}
      <style>{`
        @keyframes spin {
          from {
            transform: rotate(0deg);
          }
          to {
            transform: rotate(360deg);
          }
        }
        @keyframes pulse {
          0%,
          100% {
            opacity: 1;
            transform: scale(1);
          }
          50% {
            opacity: 0.9;
            transform: scale(1.03);
          }
        }
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(-6px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
}
