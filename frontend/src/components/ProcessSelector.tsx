"use client";

import React, { useState, useEffect } from "react";
import AudioReaderButton from "./AudioReaderButton";

// ============================================================================
// Types and Constants
// ============================================================================

export const PROCESSES = [
  "Pyrolysis",
  "Gasification",
  "Anaerobic Digestion",
  "HTC",
  "Composting",
  "Incineration",
  "Pelletization",
] as const;

export type ProcessType = (typeof PROCESSES)[number];

export interface ProcessSelectorProps {
  location: string;
  weight: number;
  weather: string;
  duration: string;
  onSelectProcess?: (process: string) => void;
  className?: string;
}

interface ProcessInfo {
  icon: string;
  tagline: string;
  typicalProducts: string;
  idealMoisture: string;
}

const PROCESS_DATA: Record<ProcessType, ProcessInfo> = {
  "Pyrolysis": {
    icon: "🌡️",
    tagline: "Thermal cracking at 400–650°C in the absence of oxygen",
    typicalProducts: "Bio-oil, Biochar & Syngas",
    idealMoisture: "< 15%",
  },
  "Gasification": {
    icon: "🔥",
    tagline: "High-temperature partial oxidation producing energy-dense syngas",
    typicalProducts: "Syngas, Electricity & Hydrogen",
    idealMoisture: "< 20%",
  },
  "Anaerobic Digestion": {
    icon: "🧪",
    tagline: "Bacterial digestion of high-moisture organic feedstock",
    typicalProducts: "Bio-CNG, Digestate & Organic Fertilizer",
    idealMoisture: "> 60%",
  },
  "HTC": {
    icon: "💧",
    tagline: "Hydrothermal Carbonisation under subcritical liquid pressure",
    typicalProducts: "Hydro-char & Liquid Fertilizer",
    idealMoisture: "50% – 90%",
  },
  "Composting": {
    icon: "🌾",
    tagline: "Aerobic biological humification into stabilized compost",
    typicalProducts: "Soil Conditioner & Organic Humus",
    idealMoisture: "40% – 60%",
  },
  "Incineration": {
    icon: "⚡",
    tagline: "Direct thermal combustion with high-efficiency steam recovery",
    typicalProducts: "High-pressure Steam & Baseload Power",
    idealMoisture: "< 35%",
  },
  "Pelletization": {
    icon: "🪵",
    tagline: "Mechanical shredding and high-density extrusion into solid fuel",
    typicalProducts: "Refuse Derived Fuel (RDF) Pellets",
    idealMoisture: "< 12%",
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
                color: "#ffaa77",
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
                color: "#ff7a45",
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
                color: "#ffe4d6",
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
            '<strong style="color: #ffc4ad; font-weight: 700;">$1</strong>'
          );
          return (
            <div
              key={idx}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "8px",
                paddingLeft: "6px",
                color: "#e2e8f0",
                fontSize: "0.93rem",
              }}
            >
              <span style={{ color: "#e2623a", fontSize: "1.1rem", lineHeight: 1 }}>•</span>
              <span dangerouslySetInnerHTML={{ __html: html }} />
            </div>
          );
        }

        const formattedHtml = line.replace(
          /\*\*(.+?)\*\*/g,
          '<strong style="color: #ffc4ad; font-weight: 700;">$1</strong>'
        );

        return (
          <p
            key={idx}
            style={{ margin: 0, color: "#cbd5e1", fontSize: "0.93rem" }}
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
  weather,
  duration,
  onSelectProcess,
  className,
}: ProcessSelectorProps) {
  const [suggestedProcess, setSuggestedProcess] = useState<string | null>(null);
  const [isRecommending, setIsRecommending] = useState<boolean>(true);
  const [recommendError, setRecommendError] = useState<string | null>(null);

  // Cache for fetched process briefings (Record<string, string>)
  const [detailsCache, setDetailsCache] = useState<Record<string, string>>({});
  const [loadingProcess, setLoadingProcess] = useState<string | null>(null);
  const [expandedProcess, setExpandedProcess] = useState<string | null>(null);
  const [selectedProcess, setSelectedProcess] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<Record<string, string>>({});

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
        weight: Number(weight) || 10,
        weather: weather || "Moderate",
        duration_pref: duration || "Standard",
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
        if (!isCancelled && data?.suggested_process) {
          setSuggestedProcess(data.suggested_process);
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
  }, [location, weight, weather, duration]);

  // --------------------------------------------------------------------------
  // Step 5: On-Demand Fetching with Details Cache
  // --------------------------------------------------------------------------
  async function handleToggleDetails(processName: string) {
    // If accordion is already open for this process, close it
    if (expandedProcess === processName) {
      setExpandedProcess(null);
      return;
    }

    // If explanation is already in detailsCache, expand immediately without API call
    if (detailsCache[processName]) {
      setExpandedProcess(processName);
      return;
    }

    // Otherwise show inline loading spinner and fetch from API
    setLoadingProcess(processName);
    setFetchError((prev) => ({ ...prev, [processName]: "" }));

    const payload = {
      location: location || "Unknown Region",
      weight: Number(weight) || 10,
      weather: weather || "Moderate",
      target_process: processName,
      suggested_process: suggestedProcess || "Pyrolysis",
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
        [processName]: markdownResult,
      }));
      setExpandedProcess(processName);
    } catch (err: any) {
      setFetchError((prev) => ({
        ...prev,
        [processName]: err?.message || "Could not retrieve details for this process.",
      }));
      setExpandedProcess(processName);
    } finally {
      setLoadingProcess(null);
    }
  }

  function handleSelect(processName: string) {
    setSelectedProcess(processName);
    if (onSelectProcess) {
      onSelectProcess(processName);
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
        color: "#f8fafc",
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
          background: "rgba(18, 24, 38, 0.7)",
          backdropFilter: "blur(14px)",
          border: "1px solid rgba(226, 98, 58, 0.25)",
          boxShadow: "0 8px 32px rgba(0, 0, 0, 0.35)",
        }}
      >
        <div>
          <h2
            style={{
              margin: 0,
              fontSize: "1.35rem",
              fontWeight: 800,
              background: "linear-gradient(90deg, #ffe4d6, #e2623a)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Waste-to-Energy Process Recommendation Engine
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: "0.88rem", color: "#94a3b8" }}>
            Operating for: <strong style={{ color: "#e2e8f0" }}>{location || "All regions"}</strong> |{" "}
            <strong style={{ color: "#e2e8f0" }}>{weight} tonnes/day</strong> |{" "}
            Weather: <strong style={{ color: "#e2e8f0" }}>{weather}</strong>
          </p>
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
                color: "#ffaa80",
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
              Evaluating 7 Processes...
            </div>
          ) : suggestedProcess ? (
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "6px 16px",
                borderRadius: "999px",
                background: "linear-gradient(135deg, rgba(226, 98, 58, 0.3), rgba(249, 115, 22, 0.2))",
                border: "1px solid #e2623a",
                color: "#ffebd8",
                fontSize: "0.9rem",
                fontWeight: 700,
                boxShadow: "0 0 20px rgba(226, 98, 58, 0.35)",
              }}
            >
              <span>AI Choice:</span>
              <span style={{ color: "#ff8c5a" }}>{suggestedProcess}</span>
            </div>
          ) : recommendError ? (
            <div
              style={{
                padding: "6px 12px",
                borderRadius: "999px",
                background: "rgba(239, 68, 68, 0.15)",
                border: "1px solid rgba(239, 68, 68, 0.4)",
                color: "#fca5a5",
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
        {PROCESSES.map((proc) => {
          const isSuggested = suggestedProcess?.trim().toLowerCase() === proc.toLowerCase();
          const isSelected = selectedProcess === proc;
          const isExpanded = expandedProcess === proc;
          const isLoadingDetails = loadingProcess === proc;
          const meta = PROCESS_DATA[proc];

          return (
            <div
              key={proc}
              style={{
                display: "flex",
                flexDirection: "column",
                borderRadius: "18px",
                background: isSuggested
                  ? "linear-gradient(165deg, rgba(30, 24, 20, 0.85) 0%, rgba(14, 18, 28, 0.95) 100%)"
                  : "rgba(15, 20, 32, 0.75)",
                backdropFilter: "blur(14px)",
                border: isSelected
                  ? "2px solid #22c55e"
                  : isSuggested
                  ? "2px solid #e2623a"
                  : "1px solid rgba(255, 255, 255, 0.08)",
                boxShadow: isSuggested
                  ? "0 10px 30px rgba(226, 98, 58, 0.25), 0 0 24px rgba(226, 98, 58, 0.15)"
                  : "0 6px 20px rgba(0, 0, 0, 0.3)",
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
                          color: isSuggested ? "#ffffff" : "#f1f5f9",
                        }}
                      >
                        {proc}
                      </h3>
                      <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#94a3b8" }}>
                        Products: {meta?.typicalProducts}
                      </p>
                    </div>
                  </div>

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

                <p
                  style={{
                    margin: "4px 0 14px",
                    fontSize: "0.85rem",
                    color: "#cbd5e1",
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
                    color: "#94a3b8",
                    marginBottom: "14px",
                  }}
                >
                  <span
                    style={{
                      background: "rgba(255, 255, 255, 0.05)",
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
                        : "rgba(255, 255, 255, 0.07)",
                      color: isExpanded ? "#ffaa80" : "#f1f5f9",
                      border: isExpanded
                        ? "1px solid #e2623a"
                        : "1px solid rgba(255, 255, 255, 0.15)",
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
                    background: "rgba(9, 13, 21, 0.85)",
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
                        color: "#fca5a5",
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
                    <p style={{ color: "#94a3b8", fontSize: "0.88rem" }}>
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
