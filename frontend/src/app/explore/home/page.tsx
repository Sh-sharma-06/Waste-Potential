"use client";

import { useState, useRef, useCallback } from "react";
import Link from "next/link";

/* ── Home Purple Accent Palette (Reverted from Orange) ── */
const HOME = {
  bg:          "#070a0f",
  accent:      "#A78BFA",
  accentHover: "#8B5CF6",
  accentSoft:  "#C4B5FD",
  accentDim:   "rgba(167,139,250,.45)",
  accentGlow:  "rgba(167,139,250,.35)",
  accentInner: "rgba(167,139,250,.06)",
  accentDrop:  "rgba(167,139,250,.45)",
  textHeading: "#EDE9FE",
  textBody:    "#E0D8FB",
  textMuted:   "#9383b8",
  gradTitle:   "linear-gradient(90deg,#EDE9FE,#A78BFA)",
  gradBtn:     "linear-gradient(90deg,#7C3AED 0%,#8B5CF6 50%,#A78BFA 100%)",
  btnText:     "#0d0520",
  cardBg:      "rgba(255,255,255,.05)",
  badgeBg:     "rgba(167,139,250,.15)",
};

const FONT = '"Rubik", sans-serif';
const glassBorder = (color: string) => `1.5px solid ${color}`;
const glassCard = (extra?: React.CSSProperties): React.CSSProperties => ({
  border: glassBorder(HOME.accentDim),
  background: HOME.cardBg,
  backdropFilter: "blur(14px)",
  WebkitBackdropFilter: "blur(14px)",
  boxShadow: `0 10px 40px rgba(15,8,40,.45), inset 0 0 30px ${HOME.accentInner}, 0 0 36px ${HOME.accentGlow}`,
  borderRadius: 20,
  padding: "26px 30px",
  boxSizing: "border-box",
  ...extra,
});

/* ── Type Definitions ── */
interface Detection {
  class: string;
  confidence: number;
}

type PipelineStage = "idle" | "detecting" | "advising" | "complete" | "error";

export default function HomeWasteClassifierPage() {
  const [pin] = useState<string>(() => {
    try {
      return localStorage.getItem("wp_location") || "110001";
    } catch {
      return "110001";
    }
  });

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [stage, setStage] = useState<PipelineStage>("idle");
  const [modelSource, setModelSource] = useState<"local" | "gemini-fallback" | null>(null);

  // Results
  const [topDetection, setTopDetection] = useState<Detection | null>(null);
  const [allDetections, setAllDetections] = useState<Detection[]>([]);
  const [adviceText, setAdviceText] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  /* ── Accept File Helper ── */
  const acceptFile = useCallback((f: File) => {
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setStage("idle");
    setTopDetection(null);
    setAllDetections([]);
    setAdviceText(null);
    setErrorMsg(null);
    setModelSource(null);
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("image/")) {
      acceptFile(f);
    }
  }, [acceptFile]);

  /* ── Step 1: Hybrid AI Pipeline (Local ML -> Gemini Advice) ── */
  const handleAnalyze = async () => {
    if (!file) return;

    setErrorMsg(null);
    setStage("detecting");

    let detectedClass = "";
    let detectedConfidence = 0;
    let detectionsList: Detection[] = [];

    // 1. Detection (Local ML) with Fallback to Cloud Gemini
    try {
      const localForm = new FormData();
      localForm.append("file", file);

      // Primary: POST http://localhost:8000/vision/classify-local
      const localRes = await fetch("http://localhost:8000/vision/classify-local", {
        method: "POST",
        body: localForm,
      });

      if (!localRes.ok) {
        throw new Error(`Local model returned HTTP ${localRes.status}`);
      }

      const localData = await localRes.json();

      if (localData?.detections && localData.detections.length > 0) {
        detectionsList = localData.detections;
        const top = detectionsList[0];
        detectedClass = top.class;
        detectedConfidence = top.confidence;
        setModelSource("local");
      } else {
        throw new Error("No detections returned by local model.");
      }
    } catch (localErr) {
      console.warn("Local model detection failed, engaging Gemini fallback...", localErr);

      // Fallback: POST http://localhost:8000/vision/classify
      try {
        const fallbackForm = new FormData();
        fallbackForm.append("image", file);

        const fbRes = await fetch("http://localhost:8000/vision/classify", {
          method: "POST",
          body: fallbackForm,
        });

        if (!fbRes.ok) {
          throw new Error(`Fallback classification failed with status ${fbRes.status}`);
        }

        const fbData = await fbRes.json();
        if (fbData?.items && fbData.items.length > 0) {
          detectionsList = fbData.items.map((it: { label?: string; category?: string; confidence?: number }) => ({
            class: it.label || it.category || "General Household Waste",
            confidence: Math.round((it.confidence ?? 0.85) * 100),
          }));
          const top = detectionsList[0];
          detectedClass = top.class;
          detectedConfidence = top.confidence;
          setModelSource("gemini-fallback");
        } else {
          throw new Error("Unable to identify waste items.");
        }
      } catch (fbErr: unknown) {
        const msg = fbErr instanceof Error ? fbErr.message : String(fbErr);
        setErrorMsg(`Classification failed: ${msg}. Please retry with a clearer photo.`);
        setStage("error");
        return;
      }
    }

    // Set detection state in UI
    const topResult: Detection = { class: detectedClass, confidence: detectedConfidence };
    setTopDetection(topResult);
    setAllDetections(detectionsList);

    // 2. Insights (Gemini GenAI): POST http://localhost:8000/vision/advice
    setStage("advising");
    try {
      const adviceRes = await fetch("http://localhost:8000/vision/advice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          waste_type: detectedClass,
          items: [detectedClass],
          sector: "urban",
        }),
      });

      if (!adviceRes.ok) {
        throw new Error(`Gemini advice returned status ${adviceRes.status}`);
      }

      const adviceData = await adviceRes.json();
      const generatedAdvice = adviceData.text || adviceData.markdown || "No specific advice returned.";
      setAdviceText(generatedAdvice);
      setStage("complete");
    } catch (adviceErr: unknown) {
      console.warn("Failed to retrieve Gemini advice:", adviceErr);
      setAdviceText(
        `### Actionable Guidance for ${detectedClass}\n\n` +
        `**Classification:** ${detectedClass} (${detectedConfidence}% confidence)\n\n` +
        `### Home Composting & Segregation\n` +
        `- Keep the ${detectedClass.toLowerCase()} stream segregated from organic wet food waste.\n` +
        `- Rinse clean any packaging films, bottles, or food trays before recycling.\n\n` +
        `### DIY Upcycling & Doorstep Scrap Offtake\n` +
        `- Sorted clean dry recyclables fetch ₹5–30/kg at local buy-back counters and kabadiwalas.\n` +
        `- Request bulk pickup or explore regional recycling centers via the Marketplace.`
      );
      setStage("complete");
    }
  };

  /* ── Markdown to Formatted JSX Renderer ── */
  const renderMarkdown = (content: string) => {
    return content.split("\n").map((line, idx) => {
      const trimmed = line.trim();
      if (trimmed.startsWith("### ")) {
        return (
          <h3
            key={idx}
            style={{
              color: HOME.accent,
              margin: "18px 0 8px",
              fontSize: "1.05rem",
              fontWeight: 700,
              letterSpacing: ".04em",
              textTransform: "uppercase",
            }}
          >
            {trimmed.slice(4)}
          </h3>
        );
      }
      if (trimmed.startsWith("## ")) {
        return (
          <h2
            key={idx}
            style={{
              color: HOME.textHeading,
              margin: "0 0 14px",
              fontSize: "1.25rem",
              fontWeight: 800,
              letterSpacing: ".06em",
              backgroundImage: HOME.gradTitle,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            {trimmed.slice(3)}
          </h2>
        );
      }
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        return (
          <li
            key={idx}
            style={{ margin: "6px 0", color: HOME.textBody, lineHeight: 1.55, fontSize: ".92rem" }}
            dangerouslySetInnerHTML={{
              __html: trimmed.slice(2).replace(/\*\*(.+?)\*\*/g, `<strong style="color:#EDE9FE">$1</strong>`),
            }}
          />
        );
      }
      if (trimmed === "") {
        return <div key={idx} style={{ height: 8 }} />;
      }
      return (
        <p
          key={idx}
          style={{ margin: "6px 0", color: HOME.textBody, lineHeight: 1.6, fontSize: ".92rem" }}
          dangerouslySetInnerHTML={{
            __html: trimmed.replace(/\*\*(.+?)\*\*/g, `<strong style="color:#EDE9FE">$1</strong>`),
          }}
        />
      );
    });
  };

  return (
    <main
      style={{
        minHeight: "100vh",
        background: HOME.bg,
        fontFamily: FONT,
        color: HOME.textHeading,
        backgroundImage: `radial-gradient(ellipse 70% 50% at 70% 20%, rgba(167,139,250,.07) 0%, transparent 70%),
                          radial-gradient(ellipse 50% 40% at 20% 80%, rgba(124,58,237,.05) 0%, transparent 70%)`,
        padding: "0 0 80px",
      }}
    >
      {/* ══ HEADER ══ */}
      <header style={{ padding: "28px 5vw 0", display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Link
              href="/explore"
              style={{
                color: HOME.accentSoft,
                textDecoration: "none",
                fontSize: ".88rem",
                letterSpacing: ".08em",
                border: glassBorder(HOME.accentDim),
                borderRadius: 999,
                padding: "7px 18px",
                background: "rgba(167,139,250,.08)",
                backdropFilter: "blur(8px)",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                transition: "all .15s ease",
              }}
            >
              ← Back to Categories
            </Link>

            <span
              style={{
                fontSize: ".75rem",
                letterSpacing: ".08em",
                color: "#c4b5fd",
                border: "1px solid rgba(167,139,250,0.4)",
                borderRadius: 999,
                padding: "5px 14px",
                background: "rgba(167,139,250,0.1)",
                backdropFilter: "blur(8px)",
                fontWeight: 600,
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#a78bfa" }} />
              HYBRID AI VISION PIPELINE (LOCAL ML + GEMINI)
            </span>
          </div>

          <span
            style={{
              fontSize: ".82rem",
              letterSpacing: ".08em",
              color: HOME.accentSoft,
              border: glassBorder(HOME.accentDim),
              borderRadius: 999,
              padding: "6px 16px",
              background: HOME.badgeBg,
              backdropFilter: "blur(8px)",
              fontWeight: 600,
            }}
          >
            📍 PIN {pin}
          </span>
        </div>

        <div>
          <h1
            style={{
              margin: "0 0 6px",
              fontSize: "clamp(1.4rem, 3.5vw, 2.2rem)",
              fontWeight: 800,
              letterSpacing: ".06em",
              textTransform: "uppercase",
              backgroundImage: HOME.gradTitle,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            Household Waste AI Classifier
          </h1>
          <p style={{ margin: 0, color: HOME.textBody, fontSize: ".92rem", letterSpacing: ".02em" }}>
            Real-time on-device classification via local Hugging Face model paired with generative Gemini guidance for domestic upcycling and disposal.
          </p>
        </div>
      </header>

      {/* ══ TWO-COLUMN GRID ══ */}
      <div
        style={{
          padding: "32px 5vw 0",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 460px), 1fr))",
          gap: 28,
          alignItems: "start",
          boxSizing: "border-box",
        }}
      >
        {/* ══ LEFT PANEL: Image Upload & Detection Result ══ */}
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {/* Upload Card */}
          <section style={glassCard()}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: "1rem", letterSpacing: ".08em", color: HOME.accentSoft, textTransform: "uppercase" }}>
                Upload Waste Image
              </h2>
              <span style={{ fontSize: ".72rem", color: HOME.textMuted }}>
                JPG, PNG, WebP up to 5MB
              </span>
            </div>

            {/* Dropzone */}
            <div
              role="button"
              tabIndex={0}
              aria-label="Drop zone: upload waste image"
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
              style={{
                cursor: "pointer",
                borderRadius: 16,
                minHeight: 180,
                border: `2px dashed ${dragging ? HOME.accent : HOME.accentDim}`,
                background: dragging ? "rgba(167,139,250,.12)" : "rgba(7,10,15,.6)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 12,
                transition: "all .2s ease",
                boxShadow: dragging ? `0 0 28px ${HOME.accentGlow}` : "none",
                padding: 20,
              }}
            >
              {preview ? (
                <div style={{ position: "relative", width: "100%", display: "flex", justifyContent: "center" }}>
                  <img
                    src={preview}
                    alt="Uploaded waste preview"
                    style={{
                      maxHeight: 240,
                      maxWidth: "100%",
                      borderRadius: 12,
                      objectFit: "contain",
                      border: "1px solid rgba(167,139,250,0.3)",
                    }}
                  />
                </div>
              ) : (
                <>
                  <div
                    style={{
                      width: 52,
                      height: 52,
                      borderRadius: "50%",
                      background: "rgba(167,139,250,0.15)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "1.5rem",
                    }}
                  >
                    🏠
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <p style={{ margin: 0, color: HOME.textHeading, fontSize: ".95rem", fontWeight: 600 }}>
                      Drag and drop household waste photo here
                    </p>
                    <span style={{ color: HOME.accentSoft, fontSize: ".82rem", marginTop: 4, display: "inline-block" }}>
                      or click to browse from device
                    </span>
                  </div>
                </>
              )}
            </div>

            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) acceptFile(f);
              }}
            />

            {/* Analyze Action Button */}
            <button
              disabled={!file || stage === "detecting" || stage === "advising"}
              onClick={handleAnalyze}
              style={{
                marginTop: 20,
                width: "100%",
                padding: "15px 0",
                borderRadius: 12,
                border: "none",
                background: !file || stage === "detecting" || stage === "advising" ? "rgba(255,255,255,.08)" : HOME.gradBtn,
                color: !file || stage === "detecting" || stage === "advising" ? "rgba(196,181,253,.4)" : HOME.btnText,
                fontFamily: FONT,
                fontWeight: 800,
                fontSize: "1rem",
                letterSpacing: ".12em",
                textTransform: "uppercase",
                cursor: !file || stage === "detecting" || stage === "advising" ? "not-allowed" : "pointer",
                boxShadow: file && stage !== "detecting" ? `0 0 28px ${HOME.accentGlow}` : "none",
                transition: "all .2s ease",
              }}
            >
              {stage === "detecting"
                ? "⚡ 1/2 Running Local ML Detection…"
                : stage === "advising"
                ? "✦ 2/2 Requesting Gemini Insights…"
                : "🚀 ANALYZE WITH HYBRID AI VISION"}
            </button>

            {/* Error Banner */}
            {errorMsg && (
              <div
                style={{
                  marginTop: 14,
                  padding: "10px 14px",
                  borderRadius: 10,
                  background: "rgba(239,68,68,0.15)",
                  border: "1px solid rgba(239,68,68,0.4)",
                  color: "#fca5a5",
                  fontSize: ".84rem",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <span>⚠</span>
                <span>{errorMsg}</span>
              </div>
            )}
          </section>

          {/* Local ML Detection Result Card */}
          {topDetection && (
            <section
              style={glassCard({
                border: "1.5px solid #A78BFA",
                background: "linear-gradient(135deg, rgba(167,139,250,0.12) 0%, rgba(15,8,40,0.85) 100%)",
              })}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: "1.3rem" }}>🎯</span>
                  <h2 style={{ margin: 0, fontSize: "1rem", fontWeight: 800, letterSpacing: ".08em", color: HOME.textHeading, textTransform: "uppercase" }}>
                    Detection Result
                  </h2>
                </div>

                <span
                  style={{
                    fontSize: ".68rem",
                    fontWeight: 800,
                    padding: "3px 10px",
                    borderRadius: 999,
                    background: modelSource === "local" ? "rgba(34,197,94,0.2)" : "rgba(167,139,250,0.2)",
                    border: `1px solid ${modelSource === "local" ? "rgba(34,197,94,0.5)" : "rgba(167,139,250,0.5)"}`,
                    color: modelSource === "local" ? "#86efac" : "#c4b5fd",
                    letterSpacing: ".06em",
                  }}
                >
                  {modelSource === "local" ? "✓ LOCAL ML PIPELINE" : "✦ GEMINI CLOUD FALLBACK"}
                </span>
              </div>

              {/* Exact format: "Detected: Plastic (95%)" */}
              <div
                style={{
                  padding: "18px 20px",
                  borderRadius: 14,
                  background: "rgba(7,10,15,0.75)",
                  border: "1px solid rgba(167,139,250,0.3)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: 12,
                }}
              >
                <div>
                  <span style={{ fontSize: ".72rem", color: HOME.textMuted, textTransform: "uppercase", letterSpacing: ".06em" }}>
                    Identified Household Item
                  </span>
                  <p style={{ margin: "4px 0 0", fontSize: "1.35rem", fontWeight: 800, color: "#EDE9FE" }}>
                    Detected: {topDetection.class} ({topDetection.confidence}%)
                  </p>
                </div>

                <div style={{ textAlign: "right" }}>
                  <span style={{ fontSize: ".72rem", color: HOME.textMuted, textTransform: "uppercase", letterSpacing: ".06em" }}>
                    Confidence Score
                  </span>
                  <p style={{ margin: "4px 0 0", fontSize: "1.35rem", fontWeight: 800, color: HOME.accent }}>
                    {topDetection.confidence}%
                  </p>
                </div>
              </div>

              {/* Multi-class Detections Strip */}
              {allDetections.length > 1 && (
                <div style={{ marginTop: 14 }}>
                  <span style={{ fontSize: ".72rem", color: HOME.accentSoft, textTransform: "uppercase", letterSpacing: ".04em" }}>
                    Secondary Candidate Matches:
                  </span>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                    {allDetections.slice(1, 4).map((d, i) => (
                      <span
                        key={i}
                        style={{
                          fontSize: ".74rem",
                          padding: "3px 10px",
                          borderRadius: 8,
                          background: "rgba(255,255,255,0.05)",
                          border: "1px solid rgba(167,139,250,0.25)",
                          color: HOME.textBody,
                        }}
                      >
                        {d.class}: <strong>{d.confidence}%</strong>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}
        </div>

        {/* ══ RIGHT PANEL: Gemini AI Guidance & Insights ══ */}
        <div style={{ position: "sticky", top: 28, alignSelf: "start" }}>
          {adviceText ? (
            <section style={glassCard({ border: "1.5px solid rgba(167,139,250,0.4)" })}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontSize: "1.3rem", color: HOME.accent }}>✦</span>
                  <h2
                    style={{
                      margin: 0,
                      fontSize: "1.05rem",
                      fontWeight: 800,
                      letterSpacing: ".08em",
                      color: HOME.textHeading,
                      textTransform: "uppercase",
                    }}
                  >
                    Gemini AI Insights &amp; Guidance
                  </h2>
                </div>

                <span
                  style={{
                    fontSize: ".68rem",
                    fontWeight: 700,
                    padding: "3px 10px",
                    borderRadius: 999,
                    background: "rgba(167,139,250,0.15)",
                    border: "1px solid rgba(167,139,250,0.35)",
                    color: HOME.accentSoft,
                  }}
                >
                  DISPOSAL &amp; UPCYCLING
                </span>
              </div>

              <div
                style={{
                  padding: "16px 20px",
                  borderRadius: 14,
                  background: "rgba(7,10,15,0.65)",
                  border: "1px solid rgba(167,139,250,0.2)",
                  maxHeight: "68vh",
                  overflowY: "auto",
                }}
              >
                {renderMarkdown(adviceText)}
              </div>

              <div style={{ marginTop: 18, display: "flex", justifyContent: "flex-end" }}>
                <Link
                  href={`/market/non-energy?pincode=${encodeURIComponent(pin)}`}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "10px 18px",
                    borderRadius: 10,
                    background: "rgba(167,139,250,0.15)",
                    border: "1px solid #A78BFA",
                    color: "#EDE9FE",
                    fontSize: ".82rem",
                    fontWeight: 700,
                    letterSpacing: ".04em",
                    textDecoration: "none",
                    transition: "all .15s ease",
                  }}
                >
                  <span>Explore Recyclables Offtake</span>
                  <span>→</span>
                </Link>
              </div>
            </section>
          ) : (
            /* Placeholder Panel before analysis */
            <section
              style={glassCard({
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                minHeight: 340,
                textAlign: "center",
                gap: 16,
                border: "1.5px dashed rgba(167,139,250,0.3)",
              })}
            >
              <div
                style={{
                  width: 58,
                  height: 58,
                  borderRadius: "50%",
                  background: "rgba(167,139,250,0.1)",
                  border: "1px solid rgba(167,139,250,0.3)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "1.8rem",
                  color: HOME.accent,
                }}
              >
                ✦
              </div>

              <div>
                <h3 style={{ margin: "0 0 6px", fontSize: "1.1rem", fontWeight: 700, color: HOME.textHeading }}>
                  Gemini GenAI Advisory Desk
                </h3>
                <p style={{ margin: 0, color: HOME.accentSoft, fontSize: ".86rem", maxWidth: 320, lineHeight: 1.5 }}>
                  {stage === "detecting"
                    ? "Local ML model is classifying your image…"
                    : stage === "advising"
                    ? "Generating tailored recycling, composting, and upcycling advice…"
                    : "Upload an image on the left and start analysis to generate actionable recovery guidelines."}
                </p>
              </div>

              {(stage === "detecting" || stage === "advising") && (
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
                  <div
                    style={{
                      width: 20,
                      height: 20,
                      borderRadius: "50%",
                      border: "2px solid rgba(167,139,250,0.3)",
                      borderTopColor: HOME.accent,
                      animation: "spin 0.8s linear infinite",
                    }}
                  />
                  <span style={{ fontSize: ".8rem", color: HOME.accent, fontWeight: 600 }}>
                    Processing AI Inference…
                  </span>
                </div>
              )}
            </section>
          )}
        </div>
      </div>
    </main>
  );
}
