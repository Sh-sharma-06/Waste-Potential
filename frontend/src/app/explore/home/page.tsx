"use client";

import { useState, useRef, useCallback } from "react";
import Link from "next/link";
import AudioReaderButton from "../../../components/AudioReaderButton";

/* ── Home Purple Accent Palette ── */
const HOME = {
  bg: "#070a0f",
  accent: "#9D4EDD",
  accentHover: "#7B2CBF",
  accentSoft: "#C77DFF",
  accentDim: "rgba(157,78,221,.45)",
  accentGlow: "rgba(157,78,221,.35)",
  accentInner: "rgba(157,78,221,.06)",
  accentDrop: "rgba(157,78,221,.45)",
  textHeading: "#10002B",
  textBody: "#240046",
  textMuted: "#3C096C",
  gradTitle: "linear-gradient(90deg,#10002B,#5A189A)",
  gradBtn: "linear-gradient(90deg,#3C096C 0%,#5A189A 50%,#7B2CBF 100%)",
  btnText: "#FFFFFF",
  cardBg: "rgba(255, 252, 255, 0.35)",
  badgeBg: "rgba(255,255,255,.4)",
};

const FONT = '"Rubik", sans-serif';
const glassBorder = (color: string) => `1.5px solid ${color}`;
const glassCard = (extra?: React.CSSProperties): React.CSSProperties => ({
  border: glassBorder(HOME.accentDim),
  background: HOME.cardBg,
  backdropFilter: "blur(14px)",
  WebkitBackdropFilter: "blur(14px)",
  boxShadow: `0 8px 32px rgba(80, 30, 120, 0.18), inset 0 0 20px ${HOME.accentInner}`,
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

interface ChatMessage {
  role: "user" | "model";
  content: string;
}

type PipelineStage = "idle" | "detecting" | "advising" | "complete" | "error";

export default function HomeWasteClassifierPage() {
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

  // Chat state
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

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
    setChatHistory([]);
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("image/")) {
      acceptFile(f);
    }
  }, [acceptFile]);

  /* ── Hybrid AI Pipeline ── */
  const handleAnalyze = async () => {
    if (!file) return;

    setErrorMsg(null);
    setStage("detecting");

    let detectedClass = "";
    let detectedConfidence = 0;
    let detectionsList: Detection[] = [];

    try {
      const localForm = new FormData();
      localForm.append("file", file);

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

    const topResult: Detection = { class: detectedClass, confidence: detectedConfidence };
    setTopDetection(topResult);
    setAllDetections(detectionsList);

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
        `### Doorstep Scrap Offtake\n` +
        `- Sorted clean dry recyclables fetch Rs 5–30/kg at local buy-back counters.\n` +
        `- Request bulk pickup or explore regional recycling centers via the Marketplace.`
      );
      setStage("complete");
    }
  };

  /* ── Chat send handler ── */
  const handleChatSend = async () => {
    if (!chatInput.trim() || chatLoading) return;
    const userMsg = chatInput.trim();
    setChatInput("");
    setChatLoading(true);

    const newHistory: ChatMessage[] = [...chatHistory, { role: "user", content: userMsg }];
    setChatHistory(newHistory);

    try {
      const res = await fetch("http://localhost:8000/vision/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: newHistory,
          context: adviceText || "",
          waste_type: topDetection?.class || "",
          sector: "urban",
        }),
      });

      if (!res.ok) throw new Error(`Chat API returned ${res.status}`);
      const data = await res.json();
      const reply = data.text || data.reply || "I could not generate a response. Please try again.";
      setChatHistory([...newHistory, { role: "model", content: reply }]);
    } catch {
      setChatHistory([...newHistory, {
        role: "model",
        content: "Sorry, I could not connect to the AI service. Please check that the backend is running and try again.",
      }]);
    } finally {
      setChatLoading(false);
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
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
              __html: trimmed.slice(2).replace(/\*\*(.+?)\*\*/g, `<strong style="color:#3C096C">$1</strong>`),
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
            __html: trimmed.replace(/\*\*(.+?)\*\*/g, `<strong style="color:#3C096C">$1</strong>`),
          }}
        />
      );
    });
  };

  return (
    <main
      style={{
        minHeight: "100vh",
        fontFamily: FONT,
        color: "#2A1B4E",
        backgroundImage: `
            linear-gradient(
              135deg,
              rgba(255, 255, 255, 0.45),
              rgba(240, 230, 255, 0.55)
            ),
            url('/home-bg(new).jpg')
          `,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed",
        backgroundRepeat: "no-repeat",
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
                color: "#2A1B4E",
                textDecoration: "none",
                fontSize: ".88rem",
                fontWeight: 700,
                letterSpacing: ".08em",
                border: "1px solid rgba(42,27,78,0.3)",
                borderRadius: 999,
                padding: "7px 18px",
                background: "rgba(255,255,255,0.55)",
                backdropFilter: "blur(8px)",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                transition: "all .15s ease",
              }}
            >
              Back to Categories
            </Link>

            <span
              style={{
                fontSize: ".75rem",
                letterSpacing: ".08em",
                color: "#2A1B4E",
                border: "1px solid rgba(42,27,78,0.3)",
                borderRadius: 999,
                padding: "5px 14px",
                background: "rgba(255,255,255,0.55)",
                backdropFilter: "blur(8px)",
                fontWeight: 700,
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#7C3AED" }} />
              HYBRID AI VISION PIPELINE (LOCAL ML + GEMINI)
            </span>
          </div>

        </div>

        <div>
          <h1
            style={{
              margin: "0 0 6px",
              fontSize: "clamp(1.4rem, 3.5vw, 2.2rem)",
              fontWeight: 900,
              letterSpacing: ".06em",
              textTransform: "uppercase",
              color: "#3d0b6cff",
            }}
          >
            Household Waste AI Classifier
          </h1>
          <p style={{ margin: 0, color: "#3d0b6cff", fontSize: ".92rem", letterSpacing: ".02em", fontWeight: 500 }}>
            Upload a photo and AI tells you what the waste is and what to do with it.
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
              <h2 style={{ margin: 0, fontSize: "1.05rem", letterSpacing: ".08em", color: "#3C096C", textTransform: "uppercase" }}>
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
                background: dragging ? "rgba(167,139,250,.12)" : "rgba(255,255,255,0.3)",
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
                    [HOME]
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <p style={{ margin: 0, color: HOME.textHeading, fontSize: ".95rem", fontWeight: 600 }}>
                      Drag and drop household waste photo here
                    </p>
                    <span style={{ color: "#7643a6ff", fontSize: ".82rem", marginTop: 4, display: "inline-block" }}>
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
                ? "1/2 Running Local ML Detection..."
                : stage === "advising"
                  ? "2/2 Requesting Gemini Insights..."
                  : "ANALYZE WITH HYBRID AI VISION"}
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
                <span>[!]</span>
                <span>{errorMsg}</span>
              </div>
            )}
          </section>

          {/* Local ML Detection Result Card */}
          {topDetection && (
            <section
              style={glassCard({
                border: "1.5px solid #A78BFA",
                background: "rgba(240,235,255,0.55)",
              })}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
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
                    color: modelSource === "local" ? "#166534" : "#4C1D95",
                    letterSpacing: ".06em",
                  }}
                >
                  {modelSource === "local" ? "LOCAL ML PIPELINE" : "GEMINI CLOUD FALLBACK"}
                </span>
              </div>

              <div
                style={{
                  padding: "18px 20px",
                  borderRadius: 14,
                  background: "rgba(255,255,255,0.5)",
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
                  <p style={{ margin: "4px 0 0", fontSize: "1.35rem", fontWeight: 800, color: HOME.textHeading }}>
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

              {allDetections.length > 1 && (
                <div style={{ marginTop: 14 }}>
                  <span style={{ fontSize: ".72rem", color: HOME.textMuted, textTransform: "uppercase", letterSpacing: ".04em" }}>
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
                          background: "rgba(255,255,255,0.5)",
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

        {/* ══ RIGHT PANEL: Gemini AI Guidance & Chat ══ */}
        <div style={{ position: "sticky", top: 28, alignSelf: "start" }}>
          {adviceText ? (
            <section style={glassCard({ border: "1.5px solid rgba(167,139,250,0.4)" })}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
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

              <div
                style={{
                  padding: "16px 20px",
                  borderRadius: 14,
                  background: "rgba(255,255,255,0.45)",
                  border: "1px solid rgba(167,139,250,0.2)",
                  maxHeight: "40vh",
                  overflowY: "auto",
                }}
              >
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
                  <AudioReaderButton text={adviceText} />
                </div>
                {renderMarkdown(adviceText)}
              </div>

              {/* ── Gemini Chat Continuation ── */}
              <div style={{ marginTop: 20 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: HOME.accent }} />
                  <span style={{ fontSize: ".78rem", color: HOME.textMuted, letterSpacing: ".06em", textTransform: "uppercase", fontWeight: 700 }}>
                    Continue conversation with Gemini
                  </span>
                </div>

                {/* Chat messages */}
                {chatHistory.length > 0 && (
                  <div
                    style={{
                      maxHeight: "28vh",
                      overflowY: "auto",
                      display: "flex",
                      flexDirection: "column",
                      gap: 10,
                      marginBottom: 14,
                      padding: "12px 14px",
                      borderRadius: 12,
                      background: "rgba(255,255,255,0.35)",
                      border: "1px solid rgba(167,139,250,0.2)",
                    }}
                  >
                    {chatHistory.map((msg, i) => (
                      <div
                        key={i}
                        style={{
                          display: "flex",
                          justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                        }}
                      >
                        <div
                          style={{
                            maxWidth: "85%",
                            padding: "9px 14px",
                            borderRadius: msg.role === "user" ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                            background: msg.role === "user"
                              ? "rgba(157,78,221,0.15)"
                              : "rgba(255,255,255,0.5)",
                            border: msg.role === "user"
                              ? "1px solid rgba(157,78,221,0.35)"
                              : "1px solid rgba(167,139,250,0.2)",
                            color: HOME.textBody,
                            fontSize: ".87rem",
                            lineHeight: 1.5,
                          }}
                        >
                          {msg.content}
                        </div>
                      </div>
                    ))}
                    {chatLoading && (
                      <div style={{ display: "flex", justifyContent: "flex-start" }}>
                        <div
                          style={{
                            padding: "9px 14px",
                            borderRadius: "14px 14px 14px 4px",
                            background: "rgba(255,255,255,0.5)",
                            border: "1px solid rgba(167,139,250,0.2)",
                            color: HOME.textMuted,
                            fontSize: ".84rem",
                          }}
                        >
                          Gemini is thinking...
                        </div>
                      </div>
                    )}
                    <div ref={chatEndRef} />
                  </div>
                )}

                {/* Chat input row */}
                <div style={{ display: "flex", gap: 10 }}>
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleChatSend()}
                    placeholder="Ask a follow-up question about this waste..."
                    disabled={chatLoading}
                    style={{
                      flex: 1,
                      padding: "11px 16px",
                      borderRadius: 12,
                      border: "1px solid rgba(157,78,221,0.35)",
                      background: "rgba(255,255,255,0.6)",
                      color: HOME.textBody,
                      fontFamily: FONT,
                      fontSize: ".9rem",
                      outline: "none",
                      transition: "border-color .2s",
                    }}
                  />
                  <button
                    onClick={handleChatSend}
                    disabled={!chatInput.trim() || chatLoading}
                    style={{
                      padding: "11px 20px",
                      borderRadius: 12,
                      border: "none",
                      background: chatInput.trim() && !chatLoading ? HOME.gradBtn : "rgba(255,255,255,.3)",
                      color: chatInput.trim() && !chatLoading ? HOME.btnText : HOME.textMuted,
                      fontFamily: FONT,
                      fontWeight: 700,
                      fontSize: ".88rem",
                      letterSpacing: ".06em",
                      cursor: chatInput.trim() && !chatLoading ? "pointer" : "not-allowed",
                      transition: "all .2s ease",
                      whiteSpace: "nowrap",
                    }}
                  >
                    Send
                  </button>
                </div>
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
                  background: "rgba(167,139,250,0.15)",
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
                <p style={{ margin: 0, color: HOME.textMuted, fontSize: ".86rem", maxWidth: 320, lineHeight: 1.5 }}>
                  {stage === "detecting"
                    ? "Local ML model is classifying your image..."
                    : stage === "advising"
                      ? "Generating tailored recycling, composting, and upcycling advice..."
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
                    Processing AI Inference...
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
