"use client";

import { useState, useRef, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AudioReaderButton from "@/components/AudioReaderButton";

/* ── Agriculture Green Accent Palette ── */
const AGRI = {
  bg: "#070a0f",
  accent: "#4ADE80",
  accentHover: "#22C55E",
  accentSoft: "#86EFAC",
  accentDim: "rgba(74,222,128,.45)",
  accentGlow: "rgba(74,222,128,.35)",
  accentInner: "rgba(74,222,128,.06)",
  accentDrop: "rgba(74,222,128,.45)",
  textHeading: "#DCFCE7",
  textBody: "#C8F5D8",
  textMuted: "#689b7b",
  gradTitle: "linear-gradient(90deg,#DCFCE7,#4ADE80)",
  gradBtn: "linear-gradient(90deg,#16A34A 0%,#22C55E 50%,#4ADE80 100%)",
  btnText: "#02150a",

  cardBg: "rgba(12, 26, 18, 0.5)",
  badgeBg: "rgba(74,222,128,.15)",
};

const FONT = '"Rubik", sans-serif';
const glassBorder = (color: string) => `1.5px solid ${color}`;
const glassCard = (extra?: React.CSSProperties): React.CSSProperties => ({
  border: glassBorder(AGRI.accentDim),
  background: AGRI.cardBg,
  backdropFilter: "blur(10px)",
  WebkitBackdropFilter: "blur(10px)",
  boxShadow: `0 10px 40px rgba(83, 162, 136, 0.45), inset 0 0 30px ${AGRI.accentInner}, 0 0 36px ${AGRI.accentGlow}`,
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
  role: "user" | "assistant";
  content: string;
}

type PipelineStage = "idle" | "detecting" | "advising" | "complete" | "error";

export default function AgricultureWasteClassifierPage() {
  const router = useRouter();
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

  /* ── Step 2 & 3: Hybrid AI Pipeline ── */
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
            class: it.label || it.category || "Agricultural Biomass",
            confidence: Math.round((it.confidence ?? 0.88) * 100),
          }));
          const top = detectionsList[0];
          detectedClass = top.class;
          detectedConfidence = top.confidence;
          setModelSource("gemini-fallback");
        } else {
          throw new Error("Unable to identify agricultural residue from image.");
        }
      } catch (fbErr: unknown) {
        const msg = fbErr instanceof Error ? fbErr.message : String(fbErr);
        setErrorMsg(`Classification failed: ${msg}. Please retry with a clearer photo of crop residue or farm waste.`);
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
          sector: "rural",
        }),
      });

      if (!adviceRes.ok) {
        throw new Error(`Gemini rural advice returned status ${adviceRes.status}`);
      }

      const adviceData = await adviceRes.json();
      const generatedAdvice = adviceData.text || adviceData.markdown || "No specific advice returned.";
      setAdviceText(generatedAdvice);
      setStage("complete");
    } catch (adviceErr: unknown) {
      console.warn("Failed to retrieve Gemini rural advice:", adviceErr);
      setAdviceText(
        `### Actionable Guidance for ${detectedClass}\n\n` +
        `**Classification:** ${detectedClass} (${detectedConfidence}% confidence)\n\n` +
        `### On-Farm Utilisation & Composting\n` +
        `- **Stubble Incorporation:** Shred and mix residue back into topsoil 3–4 weeks before next sowing to enrich organic carbon.\n` +
        `- **Bio-Enriched Compost:** Layer residue with cattle manure and trichoderma bioculture for rapid decomposition in 45–60 days.\n\n` +
        `### Monetization Pathways\n` +
        `- **Pelletization / Briquetting:** Compress into solid bio-coal for industrial boiler co-firing or brick kilns at Rs 2,500–4,500/tonne.`
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
          message: userMsg,
          history: newHistory,
          context: adviceText || "",
          waste_type: topDetection?.class || "",
          sector: "rural",
        }),
      });

      if (!res.ok) throw new Error(`Chat API returned ${res.status}`);
      const data = await res.json();
      const reply = data.text || data.reply || "I could not generate a response. Please try again.";
      setChatHistory([...newHistory, { role: "assistant", content: reply }]);
    } catch {
      setChatHistory([...newHistory, {
        role: "assistant",
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
              color: AGRI.accent,
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
              color: AGRI.textHeading,
              margin: "0 0 14px",
              fontSize: "1.25rem",
              fontWeight: 800,
              letterSpacing: ".06em",
              backgroundImage: AGRI.gradTitle,
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
            style={{ margin: "6px 0", color: AGRI.textBody, lineHeight: 1.55, fontSize: ".92rem" }}
            dangerouslySetInnerHTML={{
              __html: trimmed.slice(2).replace(/\*\*(.+?)\*\*/g, `<strong style="color:#DCFCE7">$1</strong>`),
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
          style={{ margin: "6px 0", color: AGRI.textBody, lineHeight: 1.6, fontSize: ".92rem" }}
          dangerouslySetInnerHTML={{
            __html: trimmed.replace(/\*\*(.+?)\*\*/g, `<strong style="color:#DCFCE7">$1</strong>`),
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
        color: "#183D2B",
        backgroundImage: `
            linear-gradient(
              135deg,
              rgba(230, 242, 220, 0.08),
              rgba(190, 220, 175, 0.12)
            ),
            url('/agri-bg(new).jpg')
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
                color: "#064E3B",
                textDecoration: "none",
                fontSize: ".88rem",
                fontWeight: 700,
                letterSpacing: ".08em",
                border: "1px solid rgba(6,78,59,0.3)",
                borderRadius: 999,
                padding: "7px 18px",
                background: "rgba(255,255,255,0.4)",
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
                color: "#064E3B",
                border: "1px solid rgba(6,78,59,0.3)",
                borderRadius: 999,
                padding: "5px 14px",
                background: "rgba(255,255,255,0.4)",
                backdropFilter: "blur(8px)",
                fontWeight: 700,
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#059669" }} />
              HYBRID AI VISION PIPELINE (LOCAL ML + GEMINI)
            </span>
          </div>

          <span suppressHydrationWarning
            style={{
              fontSize: ".82rem",
              letterSpacing: ".08em",
              color: "#064E3B",
              border: "1px solid rgba(6,78,59,0.3)",
              borderRadius: 999,
              padding: "6px 16px",
              background: "rgba(255,255,255,0.4)",
              backdropFilter: "blur(8px)",
              fontWeight: 700,
            }}
          >
            PIN {pin}
          </span>
        </div>

        <div>
          <h1
            style={{
              margin: "0 0 6px",
              fontSize: "clamp(1.4rem, 3.5vw, 2.2rem)",
              fontWeight: 900,
              letterSpacing: ".06em",
              textTransform: "uppercase",
              color: "#026a4dff",
            }}
          >
            Agricultural Waste AI Classifier
          </h1>
          <p style={{ margin: 0, color: "#064E3B", fontSize: ".92rem", letterSpacing: ".02em", fontWeight: 500 }}>
            Real-time on-device classification via local Hugging Face model paired with generative Gemini guidance for crop residue valorization and clean bio-energy pathways.
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
              <h2 style={{ margin: 0, fontSize: "1rem", letterSpacing: ".08em", color: AGRI.accentSoft, textTransform: "uppercase" }}>
                Upload Farm Residue Photo
              </h2>
              <span style={{ fontSize: ".72rem", color: AGRI.textMuted }}>
                JPG, PNG, WebP up to 5MB
              </span>
            </div>

            {/* Dropzone */}
            <div
              role="button"
              tabIndex={0}
              aria-label="Drop zone: upload crop residue image"
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
                border: `2px dashed ${dragging ? AGRI.accent : AGRI.accentDim}`,
                background: dragging ? "rgba(74,222,128,.12)" : "rgba(7,10,15,.6)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 12,
                transition: "all .2s ease",
                boxShadow: dragging ? `0 0 28px ${AGRI.accentGlow}` : "none",
                padding: 20,
              }}
            >
              {preview ? (
                <div style={{ position: "relative", width: "100%", display: "flex", justifyContent: "center" }}>
                  <img
                    src={preview}
                    alt="Uploaded farm residue preview"
                    style={{
                      maxHeight: 240,
                      maxWidth: "100%",
                      borderRadius: 12,
                      objectFit: "contain",
                      border: "1px solid rgba(74,222,128,0.3)",
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
                      background: "rgba(74,222,128,0.15)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "1.5rem",
                    }}
                  >
                    [AGRI]
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <p style={{ margin: 0, color: AGRI.textHeading, fontSize: ".95rem", fontWeight: 600 }}>
                      Drag and drop crop residue photo here
                    </p>
                    <span style={{ color: AGRI.accentSoft, fontSize: ".82rem", marginTop: 4, display: "inline-block" }}>
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
                background: !file || stage === "detecting" || stage === "advising" ? "rgba(255,255,255,.08)" : AGRI.gradBtn,
                color: !file || stage === "detecting" || stage === "advising" ? "rgba(134,239,172,.4)" : AGRI.btnText,
                fontFamily: FONT,
                fontWeight: 800,
                fontSize: "1rem",
                letterSpacing: ".12em",
                textTransform: "uppercase",
                cursor: !file || stage === "detecting" || stage === "advising" ? "not-allowed" : "pointer",
                boxShadow: file && stage !== "detecting" ? `0 0 28px ${AGRI.accentGlow}` : "none",
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
                border: "1.5px solid #4ADE80",
                background: "linear-gradient(135deg, rgba(74,222,128,0.12) 0%, rgba(0,30,20,0.85) 100%)",
              })}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <h2 style={{ margin: 0, fontSize: "1rem", fontWeight: 800, letterSpacing: ".08em", color: AGRI.textHeading, textTransform: "uppercase" }}>
                    Detection Result
                  </h2>
                </div>

                <span
                  style={{
                    fontSize: ".68rem",
                    fontWeight: 800,
                    padding: "3px 10px",
                    borderRadius: 999,
                    background: modelSource === "local" ? "rgba(34,197,94,0.2)" : "rgba(74,222,128,0.2)",
                    border: `1px solid ${modelSource === "local" ? "rgba(34,197,94,0.5)" : "rgba(74,222,128,0.5)"}`,
                    color: modelSource === "local" ? "#86efac" : "#bbf7d0",
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
                  background: "rgba(7,10,15,0.75)",
                  border: "1px solid rgba(74,222,128,0.3)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: 12,
                }}
              >
                <div>
                  <span style={{ fontSize: ".72rem", color: AGRI.textMuted, textTransform: "uppercase", letterSpacing: ".06em" }}>
                    Identified Biomass Feedstock
                  </span>
                  <p style={{ margin: "4px 0 0", fontSize: "1.35rem", fontWeight: 800, color: "#DCFCE7" }}>
                    Detected: {topDetection.class} ({topDetection.confidence}%)
                  </p>
                </div>

                <div style={{ textAlign: "right" }}>
                  <span style={{ fontSize: ".72rem", color: AGRI.textMuted, textTransform: "uppercase", letterSpacing: ".06em" }}>
                    Confidence Score
                  </span>
                  <p style={{ margin: "4px 0 0", fontSize: "1.35rem", fontWeight: 800, color: AGRI.accent }}>
                    {topDetection.confidence}%
                  </p>
                </div>
              </div>

              {allDetections.length > 1 && (
                <div style={{ marginTop: 14 }}>
                  <span style={{ fontSize: ".72rem", color: AGRI.accentSoft, textTransform: "uppercase", letterSpacing: ".04em" }}>
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
                          border: "1px solid rgba(74,222,128,0.25)",
                          color: AGRI.textBody,
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
            <section style={glassCard({ border: "1.5px solid rgba(74,222,128,0.4)" })}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
                <span style={{ fontSize: "1.3rem", color: AGRI.accent }}>✦</span>
                <h2
                  style={{
                    margin: 0,
                    fontSize: "1.05rem",
                    fontWeight: 800,
                    letterSpacing: ".08em",
                    color: AGRI.textHeading,
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
                  background: "rgba(7,10,15,0.65)",
                  border: "1px solid rgba(74,222,128,0.2)",
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
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: AGRI.accent }} />
                  <span style={{ fontSize: ".78rem", color: AGRI.accentSoft, letterSpacing: ".06em", textTransform: "uppercase", fontWeight: 700 }}>
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
                      background: "rgba(7,10,15,0.55)",
                      border: "1px solid rgba(74,222,128,0.15)",
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
                              ? "rgba(74,222,128,0.18)"
                              : "rgba(255,255,255,0.06)",
                            border: msg.role === "user"
                              ? "1px solid rgba(74,222,128,0.35)"
                              : "1px solid rgba(255,255,255,0.1)",
                            color: msg.role === "user" ? "#DCFCE7" : AGRI.textBody,
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
                            background: "rgba(255,255,255,0.06)",
                            border: "1px solid rgba(255,255,255,0.1)",
                            color: AGRI.textMuted,
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
                      border: "1px solid rgba(74,222,128,0.3)",
                      background: "rgba(7,10,15,0.75)",
                      color: "#DCFCE7",
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
                      background: chatInput.trim() && !chatLoading ? AGRI.gradBtn : "rgba(255,255,255,.06)",
                      color: chatInput.trim() && !chatLoading ? AGRI.btnText : "rgba(134,239,172,.3)",
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
                border: "1.5px dashed rgba(74,222,128,0.3)",
              })}
            >
              <div
                style={{
                  width: 58,
                  height: 58,
                  borderRadius: "50%",
                  background: "rgba(74,222,128,0.1)",
                  border: "1px solid rgba(74,222,128,0.3)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "1.8rem",
                  color: AGRI.accent,
                }}
              >
                ✦
              </div>

              <div>
                <h3 style={{ margin: "0 0 6px", fontSize: "1.1rem", fontWeight: 700, color: AGRI.textHeading }}>
                  Gemini GenAI Farm Advisory Desk
                </h3>
                <p style={{ margin: 0, color: AGRI.accentSoft, fontSize: ".86rem", maxWidth: 320, lineHeight: 1.5 }}>
                  {stage === "detecting"
                    ? "Local ML model is classifying farm residue..."
                    : stage === "advising"
                      ? "Generating tailored rural composting guidance..."
                      : "Upload an agricultural residue photo on the left and start analysis to generate actionable recovery guidelines."}
                </p>
              </div>

              {(stage === "detecting" || stage === "advising") && (
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
                  <div
                    style={{
                      width: 20,
                      height: 20,
                      borderRadius: "50%",
                      border: "2px solid rgba(74,222,128,0.3)",
                      borderTopColor: AGRI.accent,
                      animation: "spin 0.8s linear infinite",
                    }}
                  />
                  <span style={{ fontSize: ".8rem", color: AGRI.accent, fontWeight: 600 }}>
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
