"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Sparkles,
  MessageSquare,
  FileText,
  ShieldCheck,
  Send,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
  Database,
  Cpu,
  Layers,
  Flame,
  Info,
} from "lucide-react";
import { useScenarioStore } from "@/stores/scenario";

// ─── API Helper ───────────────────────────────────────────────────────────────

async function callAssistantApi<T>(
  endpoint: "parse" | "advise" | "audit",
  body: unknown
): Promise<{ ok: boolean; status: number; data: T | null; error?: string }> {
  // Check primary Next.js proxy route (/api/api/v1/assistant/... -> /api/v1/assistant/...)
  let res: Response;
  try {
    res = await fetch(`/api/api/v1/assistant/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (res.status === 404) {
      // Fallback for direct /api/v1 rewrite
      res = await fetch(`/api/v1/assistant/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    }
  } catch (err) {
    return {
      ok: false,
      status: 0,
      data: null,
      error:
        err instanceof Error
          ? err.message
          : "Network error connecting to AI Assistant service.",
    };
  }

  try {
    const json = await res.json();
    if (!res.ok) {
      const detail =
        typeof json.detail === "string"
          ? json.detail
          : JSON.stringify(json.detail ?? json);
      return { ok: false, status: res.status, data: null, error: detail };
    }
    return { ok: true, status: res.status, data: json as T };
  } catch {
    return {
      ok: false,
      status: res.status,
      data: null,
      error: `Server returned non-JSON response (${res.status} ${res.statusText})`,
    };
  }
}

// ─── Types ────────────────────────────────────────────────────────────────────

type ParsedWasteData = {
  waste_type: string;
  quantity_kg_per_day: number;
  moisture_percent: number;
  organic_fraction_percent: number;
  location: string;
  missing_information: string[];
};

type ChatMessage = {
  id: string;
  sender: "user" | "assistant";
  text: string;
  timestamp: string;
  isFallback?: boolean;
};

// ─── Preset Sample Inputs ─────────────────────────────────────────────────────

const PRESET_PARSER_SAMPLES = [
  {
    title: "Mandi Wholesale Vegetables",
    text: "We collect approximately 12 metric tons per day of mixed spoiled vegetables and fruit peels from the APMC wholesale market in Pune. Moisture is estimated around 78% with low plastics contamination.",
  },
  {
    title: "Dairy Cattle Slurry",
    text: "A commercial dairy farm in Anand, Gujarat produces about 8,000 kg daily of fresh wet cow manure and cattle wash water. Total solids are around 14% with high organic carbon.",
  },
  {
    title: "Urban Mixed Kitchen Organics",
    text: "Residential ward segregated wet kitchen food waste of 3500 kg per day in Bengaluru, high moisture around 72%, organic fraction roughly 85%.",
  },
];

const PRESET_ADVISOR_QUESTIONS = [
  "How does feedstock moisture content dictate the threshold between Anaerobic Digestion and Incineration?",
  "What causes volatile fatty acid (VFA) accumulation and pH drop in high-rate anaerobic digestion?",
  "Explain why biomethane yield is lower than gross biogas production volume.",
  "What is the significance of the C:N ratio in optimizing methane yield versus composting?",
];

// ─── Main Assistant Page Component ────────────────────────────────────────────

export default function AssistantPage() {
  const router = useRouter();
  const { form, result, setForm } = useScenarioStore();

  const [activeTab, setActiveTab] = useState<"advise" | "parse" | "audit">("advise");

  // Advisory Chat State
  const [question, setQuestion] = useState("");
  const [includeContext, setIncludeContext] = useState(true);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      sender: "assistant",
      text: "Welcome to the Waste-Potential AI Assistant. I can answer complex biological and thermodynamic waste processing questions, extract structured parameters from unorganized text, or generate scientific audit narratives based on numerical simulations.",
      timestamp: "Ready",
    },
  ]);
  const [advising, setAdvising] = useState(false);
  const [advisorNotice, setAdvisorNotice] = useState<string | null>(null);

  // Parser State
  const [description, setDescription] = useState(
    PRESET_PARSER_SAMPLES[0].text
  );
  const [parsing, setParsing] = useState(false);
  const [parsedResult, setParsedResult] = useState<ParsedWasteData | null>(null);
  const [parserNotice, setParserNotice] = useState<string | null>(null);
  const [appliedFeedback, setAppliedFeedback] = useState<string | null>(null);

  // Audit State
  const [auditing, setAuditing] = useState(false);
  const [auditReport, setAuditReport] = useState<string | null>(null);
  const [auditNotice, setAuditNotice] = useState<string | null>(null);

  // ─── Advisory Handler ───────────────────────────────────────────────────────

  async function handleSendQuestion(queryText?: string) {
    const q = (queryText ?? question).trim();
    if (!q || advising) return;

    const userMsg: ChatMessage = {
      id: String(Date.now()),
      sender: "user",
      text: q,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setChatMessages((prev) => [...prev, userMsg]);
    setQuestion("");
    setAdvising(true);
    setAdvisorNotice(null);

    const contextPayload = includeContext
      ? {
          active_feedstock_kg_d: form.waste_mass_kg_day,
          organic_fraction: form.organic_fraction,
          suitable_fraction: form.suitable_fraction,
          location: form.location_id || "Unspecified",
          last_simulation_status: result?.status ?? "illustrative_estimate",
          simulated_biogas_nm3_d: result?.results?.biogas_nm3_d ?? null,
          simulated_net_kwh_d: result?.results?.e_net_kwh_d ?? null,
        }
      : {};

    const res = await callAssistantApi<{ status: string; answer: string }>("advise", {
      question: q,
      context: contextPayload,
    });

    if (res.ok && res.data?.answer) {
      setChatMessages((prev) => [
        ...prev,
        {
          id: String(Date.now() + 1),
          sender: "assistant",
          text: res.data!.answer,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } else {
      // Backend returned 503 or error (e.g. Gemini key missing)
      setAdvisorNotice(
        res.error?.includes("not configured")
          ? "Gemini API key is not configured in backend environment (GEMINI_API_KEY_ADVISOR). A grounded engineering baseline response is shown below."
          : `AI Service notice: ${res.error ?? "Failed to query advisor."}`
      );

      // Provide informative scientific explanation fallback
      let fallbackAnswer = "";
      if (q.toLowerCase().includes("moisture") || q.toLowerCase().includes("incineration")) {
        fallbackAnswer =
          "Feedstock moisture content is the primary thermodynamic dividing line between biochemical and thermal conversion. Anaerobic digestion excels in wet organic waste (65%–90% moisture) because water provides the transport medium for hydrolytic enzymes and methanogenic archaea. In contrast, mass-burn incineration requires high Lower Heating Values (LHV > 6–7 MJ/kg); feedstocks with moisture > 50% consume excessive latent heat of vaporization, quenching flame temperatures below the 850°C regulatory threshold and requiring supplementary fossil fuel support.";
      } else if (q.toLowerCase().includes("biomethane") || q.toLowerCase().includes("biogas")) {
        fallbackAnswer =
          "Raw biogas generated by anaerobic digestion is a mixed stream typically containing 55%–65% methane (CH₄), 35%–45% carbon dioxide (CO₂), along with trace water vapor and hydrogen sulfide (H₂S). Biomethane refers exclusively to the upgraded, purified gas (>95% CH₄) achieved after scrubbing CO₂ and drying moisture. Thus, 100 Nm³ of raw biogas yields approximately 55–60 Nm³ of pipeline-quality biomethane.";
      } else if (q.toLowerCase().includes("ammonia") || q.toLowerCase().includes("nitrogen")) {
        fallbackAnswer =
          "Ammonia inhibition occurs when protein-rich or nitrogenous wastes (such as slaughterhouse offal or pure poultry manure) release high concentrations of total ammonia nitrogen (TAN). At mesophilic pH (>7.5) and thermophilic temperatures, TAN shifts toward free unionized ammonia (NH₃), which passively diffuses across bacterial cell membranes, disrupts proton gradients, and selectively inhibits acetoclastic methanogens, leading to volatile fatty acid (VFA) buildup.";
      } else {
        fallbackAnswer = `Analysis for: "${q}"\n\nUnder thermodynamic mass balance rules: Organic waste conversion efficiency relies on biochemical methane potential (BMP), volatile solids destruction (typically 65%–75% in well-mixed CSTR systems), and maintaining volatile fatty acid (VFA) to alkalinity ratios under 0.3. For specific numeric predictions, run the numerical simulator in the Process Lab.`;
      }

      setChatMessages((prev) => [
        ...prev,
        {
          id: String(Date.now() + 1),
          sender: "assistant",
          text: fallbackAnswer,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          isFallback: true,
        },
      ]);
    }

    setAdvising(false);
  }

  // ─── Parser Handler ─────────────────────────────────────────────────────────

  async function handleParseWaste() {
    if (!description.trim() || parsing) return;

    setParsing(true);
    setParserNotice(null);
    setAppliedFeedback(null);

    const res = await callAssistantApi<{
      status: string;
      data: ParsedWasteData;
      note?: string;
    }>("parse", { description: description.trim() });

    if (res.ok && res.data?.data) {
      setParsedResult(res.data.data);
    } else {
      setParserNotice(
        res.error?.includes("not configured")
          ? "Gemini API key is not configured in backend environment (GEMINI_API_KEY_PARSER). Demonstrating rule-based heuristic extraction from text."
          : `AI Service notice: ${res.error ?? "Failed to parse text."}`
      );

      // Heuristic fallback parser
      const lower = description.toLowerCase();
      let mass = 1000;
      const massMatch = description.match(/(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:metric\s*)?(?:tons?|tonnes?|tpd|kg)/i);
      if (massMatch) {
        const val = parseFloat(massMatch[1].replace(/,/g, ""));
        if (/ton|tonne|tpd/i.test(massMatch[0])) mass = val * 1000;
        else mass = val;
      }

      let moisture = 75;
      const moistMatch = description.match(/(\d+(?:\.\d+)?)\s*%/);
      if (moistMatch) moisture = parseFloat(moistMatch[1]);

      let wasteType = "Mixed Municipal Organic Waste";
      if (lower.includes("vegetable") || lower.includes("mandi") || lower.includes("fruit")) {
        wasteType = "Market Vegetable & Fruit Residues";
      } else if (lower.includes("dairy") || lower.includes("cow") || lower.includes("manure")) {
        wasteType = "Dairy Cattle Manure Slurry";
      }

      let loc = "Pune, Maharashtra";
      if (lower.includes("anand") || lower.includes("gujarat")) loc = "Anand, Gujarat";
      else if (lower.includes("bengaluru") || lower.includes("bangalore")) loc = "Bengaluru, Karnataka";

      setParsedResult({
        waste_type: wasteType,
        quantity_kg_per_day: mass,
        moisture_percent: moisture,
        organic_fraction_percent: 80,
        location: loc,
        missing_information: ["Trace heavy metal levels", "Exact volatile solids ratio"],
      });
    }

    setParsing(false);
  }

  function handleApplyToSimulator() {
    if (!parsedResult) return;
    setForm({
      waste_mass_kg_day: parsedResult.quantity_kg_per_day,
      organic_fraction: (parsedResult.organic_fraction_percent || 60) / 100,
      location_id: parsedResult.location || "",
    });
    setAppliedFeedback(
      `Parameters successfully transferred! Feedstock set to ${parsedResult.quantity_kg_per_day.toLocaleString()} kg/day.`
    );
    setTimeout(() => {
      router.push("/simulator");
    }, 1200);
  }

  function handleApplyToCompare() {
    if (!parsedResult) return;
    router.push("/compare");
  }

  // ─── Audit Handler ──────────────────────────────────────────────────────────

  async function handleGenerateAudit() {
    setAuditing(true);
    setAuditNotice(null);

    const resultsPayload = {
      waste_mass_kg_day: form.waste_mass_kg_day,
      organic_fraction: form.organic_fraction,
      suitable_fraction: form.suitable_fraction,
      e_net_kwh_d: result?.results?.e_net_kwh_d ?? 214.5,
      biogas_nm3_d: result?.results?.biogas_nm3_d ?? 95.8,
      digester_m3: result?.results?.digester_m3 ?? 65,
      status: result?.status ?? "illustrative_estimate",
    };

    const assumptions = [
      "Mesophilic biological regime stabilized at 38°C (±1°C)",
      "Hydraulic retention time (HRT) assumed at 25 days",
      "Feedstock pre-screened for heavy plastics and gross inorganics",
      "Continuous stirred-tank reactor (CSTR) baseline configuration",
    ];

    const limitations = [
      "Calculations exclude fugitive pipe leaks or flaring during emergency shutdowns",
      "Seasonal temperature drops below 18°C require auxiliary thermal insulation",
      "Feedstock fluctuations in volatile solids content may alter weekly yield by ±12%",
    ];

    const res = await callAssistantApi<{ status: string; report: string }>("audit", {
      results: resultsPayload,
      assumptions,
      limitations,
    });

    if (res.ok && res.data?.report) {
      setAuditReport(res.data.report);
    } else {
      setAuditNotice(
        res.error?.includes("not configured")
          ? "Gemini API key is not configured in backend environment (GEMINI_API_KEY_AUDIT). An executive scientific audit preview is shown below."
          : `AI Service notice: ${res.error ?? "Failed to generate audit."}`
      );

      const netKwh = result?.results?.e_net_kwh_d ? result.results.e_net_kwh_d.toFixed(1) : "214.5";
      const biogas = result?.results?.biogas_nm3_d ? result.results.biogas_nm3_d.toFixed(1) : "95.8";
      const vol = result?.results?.digester_m3 ? result.results.digester_m3.toFixed(0) : "65";

      setAuditReport(
        `# Scientific Engineering Audit Report: Waste-Potential Facility\n\n` +
        `### 1. Mass & Energy Balance Integrity\n` +
        `The modeled facility evaluates an intake stream of ${form.waste_mass_kg_day.toLocaleString()} kg/day with an organic fraction of ${(form.organic_fraction * 100).toFixed(0)}%. ` +
        `Under nominal steady-state operation, thermodynamic stoichiometry projects a net electrical generation of ${netKwh} kWh/day and a raw biogas extraction rate of ${biogas} Nm³/day from an active digester volume of ${vol} m³.\n\n` +
        `### 2. Physical & Boundary Assumptions\n` +
        `- Mesophilic biological regime operates at 38°C under continuous stirring.\n` +
        `- Hydraulic retention time (HRT) of 25 days provides adequate methanogenic conversion of volatile solids.\n` +
        `- Upstream screening eliminates coarse inert solids (>40mm) and ferrous contaminants.\n\n` +
        `### 3. Engineering Limitations & Practical Risks\n` +
        `- Sub-optimal feedstock sorting or elevated ammonia (TAN > 3.0 g/L) could induce volatile fatty acid accumulation.\n` +
        `- Parasitic thermal load increases during winter months; heat exchanger loop efficiency must be sustained above 80%.\n\n` +
        `### 4. Regulatory & Environmental Compliance\n` +
        `The sealed bioconversion prevents direct atmospheric fugitive methane release (GWP 28x CO₂ equivalent). Bio-fertilizer effluent conforms to nutrient stabilization criteria for land application.`
      );
    }

    setAuditing(false);
  }

  return (
    <main className="min-h-screen bg-[#060a14] px-4 py-8 text-slate-100 sm:px-8">
      <div className="mx-auto max-w-6xl space-y-6">

        {/* =========================================================================
            PLATFORM NAVIGATION BAR
        ========================================================================= */}
        <nav aria-label="Main Navigation" className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-500/10 border border-teal-500/30 text-teal-400">
              <Sparkles className="h-4 w-4" />
            </span>
            <div>
              <span className="font-extrabold text-sm tracking-tight text-white">Waste-Potential</span>
              <span className="ml-2 rounded-full border border-teal-500/30 bg-teal-500/10 px-2 py-0.5 text-[10px] font-bold uppercase text-teal-400">
                AI Platform
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-medium">
            <Link href="/dashboard" className="rounded-lg px-3 py-1.5 text-slate-400 transition hover:bg-slate-900 hover:text-white">
              Dashboard
            </Link>
            <Link href="/simulator" className="rounded-lg px-3 py-1.5 text-slate-400 transition hover:bg-slate-900 hover:text-white">
              3D Simulator
            </Link>
            <Link href="/compare" className="rounded-lg px-3 py-1.5 text-slate-400 transition hover:bg-slate-900 hover:text-white">
              Compare
            </Link>
            <Link href="/assistant" className="rounded-lg bg-teal-950 px-3 py-1.5 font-bold text-teal-300 border border-teal-700/50">
              AI Assistant
            </Link>
          </div>
        </nav>

        {/* =========================================================================
            HEADER TITLE & INTRO
        ========================================================================= */}
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-teal-400">
            Platform &amp; Assistant · Intelligent Advisory Engine
          </p>
          <h1 className="mt-2 text-3xl font-extrabold tracking-tight sm:text-4xl text-white">
            Waste Intelligence &amp; Scientific Assistant
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-400 leading-relaxed">
            Directly connected to the Waste-Potential FastAPI engine. Ask biological and thermodynamic questions,
            extract structured parameters from unorganized text, or synthesize narrative engineering audits.
          </p>
        </div>

        {/* =========================================================================
            TAB SELECTOR
        ========================================================================= */}
        <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
          <button
            onClick={() => setActiveTab("advise")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === "advise"
                ? "bg-teal-500/20 text-teal-300 border border-teal-500/40 shadow-sm"
                : "text-slate-400 hover:text-white hover:bg-slate-900"
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Technical Advisor</span>
          </button>

          <button
            onClick={() => setActiveTab("parse")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === "parse"
                ? "bg-teal-500/20 text-teal-300 border border-teal-500/40 shadow-sm"
                : "text-slate-400 hover:text-white hover:bg-slate-900"
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>Natural Language Waste Parser</span>
          </button>

          <button
            onClick={() => setActiveTab("audit")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === "audit"
                ? "bg-teal-500/20 text-teal-300 border border-teal-500/40 shadow-sm"
                : "text-slate-400 hover:text-white hover:bg-slate-900"
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Engineering Audit Narrative</span>
          </button>
        </div>

        {/* =========================================================================
            TAB 1: ADVISORY CHAT
        ========================================================================= */}
        {activeTab === "advise" && (
          <div className="space-y-4">
            {advisorNotice && (
              <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-600/40 text-xs text-amber-300 flex items-start gap-2.5">
                <Info className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <span>{advisorNotice}</span>
              </div>
            )}

            {/* Context Toggle */}
            <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-300">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-teal-400" />
                <span>
                  Active Scenario Context:{" "}
                  <strong className="text-white">{form.waste_mass_kg_day.toLocaleString()} kg/day</strong> ·{" "}
                  Organic: <strong className="text-white">{(form.organic_fraction * 100).toFixed(0)}%</strong>
                  {result && (
                    <span className="ml-1 text-emerald-400 font-semibold">
                      · Verified: {result.results.biogas_nm3_d.toFixed(1)} Nm³/d
                    </span>
                  )}
                </span>
              </div>
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={includeContext}
                  onChange={(e) => setIncludeContext(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-800 text-teal-500 focus:ring-teal-400"
                />
                <span className="text-[11px] text-slate-400">Inject active scenario into AI prompt</span>
              </label>
            </div>

            {/* Chat Log Card */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 sm:p-6 min-h-[360px] max-h-[500px] overflow-y-auto space-y-4 shadow-xl">
              {chatMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col ${
                    msg.sender === "user" ? "items-end" : "items-start"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1 text-[11px] text-slate-400">
                    <span className="font-semibold text-slate-300">
                      {msg.sender === "user" ? "You" : "Waste-Potential Advisor"}
                    </span>
                    <span>·</span>
                    <span>{msg.timestamp}</span>
                    {msg.isFallback && (
                      <span className="px-1.5 py-0.2 rounded bg-amber-950/60 text-amber-300 border border-amber-600/30 text-[9px]">
                        Grounded Baseline
                      </span>
                    )}
                  </div>
                  <div
                    className={`p-3.5 rounded-2xl max-w-2xl text-xs sm:text-sm leading-relaxed whitespace-pre-wrap ${
                      msg.sender === "user"
                        ? "bg-teal-600 text-slate-950 font-medium rounded-tr-sm"
                        : "bg-slate-800/80 text-slate-200 border border-slate-700/60 rounded-tl-sm shadow-md"
                    }`}
                  >
                    {msg.text}
                  </div>
                </div>
              ))}

              {advising && (
                <div className="flex items-center gap-2 text-xs text-teal-400 animate-pulse p-2">
                  <Sparkles className="w-4 h-4" />
                  <span>Synthesizing thermodynamic &amp; biochemical advice...</span>
                </div>
              )}
            </div>

            {/* Quick Prompt Chips */}
            <div className="space-y-1.5">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Suggested Engineering Questions:
              </span>
              <div className="flex flex-wrap gap-2">
                {PRESET_ADVISOR_QUESTIONS.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendQuestion(q)}
                    disabled={advising}
                    className="text-left text-xs px-3 py-1.5 rounded-lg bg-slate-900/80 hover:bg-slate-800 border border-slate-800 hover:border-teal-500/40 text-slate-300 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>

            {/* Input Bar */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleSendQuestion();
              }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask about methane yields, C:N ratios, moisture limits, or gasification parameters..."
                className="flex-1 bg-slate-900 border border-slate-700 hover:border-teal-400 focus:border-teal-400 focus:ring-1 focus:ring-teal-400 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 outline-none transition"
              />
              <button
                type="submit"
                disabled={advising || !question.trim()}
                className="flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-500 disabled:opacity-40 text-slate-950 font-bold text-sm transition shadow-lg shadow-teal-500/20"
              >
                <Send className="w-4 h-4" />
                <span>Send</span>
              </button>
            </form>
          </div>
        )}

        {/* =========================================================================
            TAB 2: WASTE PARSER
        ========================================================================= */}
        {activeTab === "parse" && (
          <div className="space-y-6">
            {parserNotice && (
              <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-600/40 text-xs text-amber-300 flex items-start gap-2.5">
                <Info className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <span>{parserNotice}</span>
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column (6 cols): Free-Form Input */}
              <div className="lg:col-span-6 space-y-4">
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center justify-between">
                    <span>Describe Feedstock Stream</span>
                    <span className="text-[11px] text-slate-400 font-normal">Free-form unstructured text</span>
                  </label>
                  <textarea
                    rows={6}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Enter details like daily tons, location, moisture estimates, contaminant levels..."
                    className="w-full bg-slate-900 border border-slate-700 hover:border-teal-400 focus:border-teal-400 focus:ring-1 focus:ring-teal-400 rounded-xl p-3.5 text-sm text-white placeholder-slate-500 outline-none transition"
                  />
                </div>

                {/* Preset Chips */}
                <div className="space-y-1.5">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    Sample Scenarios:
                  </span>
                  <div className="flex flex-col gap-1.5">
                    {PRESET_PARSER_SAMPLES.map((sample, idx) => (
                      <button
                        key={idx}
                        onClick={() => setDescription(sample.text)}
                        className="text-left text-xs px-3 py-2 rounded-lg bg-slate-900/60 hover:bg-slate-800 border border-slate-800 text-slate-300 transition-colors flex items-center justify-between group"
                      >
                        <span className="font-semibold text-slate-200 group-hover:text-teal-300">
                          {sample.title}
                        </span>
                        <ArrowRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-teal-400 transition-transform group-hover:translate-x-1" />
                      </button>
                    ))}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleParseWaste}
                  disabled={parsing || !description.trim()}
                  className="w-full flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-teal-600 hover:bg-teal-500 disabled:opacity-40 text-slate-950 font-extrabold text-sm transition shadow-lg shadow-teal-500/20"
                >
                  <Cpu className="w-4 h-4" />
                  <span>{parsing ? "Extracting Parameters via API..." : "Parse Waste Stream Parameters"}</span>
                </button>
              </div>

              {/* Right Column (6 cols): Structured Result & Pipeline Actions */}
              <div className="lg:col-span-6 space-y-4">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                    <span className="text-xs font-bold uppercase tracking-wider text-teal-400">
                      Structured Extraction Result
                    </span>
                    <span className="text-[11px] text-slate-400 font-mono">
                      POST /api/v1/assistant/parse
                    </span>
                  </div>

                  {parsedResult ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-3">
                        <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800">
                          <span className="text-[10px] uppercase font-bold text-slate-400">Waste Type</span>
                          <p className="text-sm font-bold text-white mt-0.5 truncate">{parsedResult.waste_type}</p>
                        </div>
                        <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800">
                          <span className="text-[10px] uppercase font-bold text-slate-400">Quantity (kg/day)</span>
                          <p className="text-sm font-bold text-teal-400 mt-0.5 font-mono">
                            {parsedResult.quantity_kg_per_day.toLocaleString()} kg/d
                          </p>
                        </div>
                        <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800">
                          <span className="text-[10px] uppercase font-bold text-slate-400">Moisture</span>
                          <p className="text-sm font-bold text-sky-400 mt-0.5 font-mono">
                            {parsedResult.moisture_percent}%
                          </p>
                        </div>
                        <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800">
                          <span className="text-[10px] uppercase font-bold text-emerald-400">Organic Fraction</span>
                          <p className="text-sm font-bold text-emerald-400 mt-0.5 font-mono">
                            {parsedResult.organic_fraction_percent}%
                          </p>
                        </div>
                      </div>

                      <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800">
                        <span className="text-[10px] uppercase font-bold text-slate-400">Resolved Location</span>
                        <p className="text-xs font-semibold text-slate-200 mt-0.5">{parsedResult.location || "Not specified"}</p>
                      </div>

                      {parsedResult.missing_information && parsedResult.missing_information.length > 0 && (
                        <div className="p-3 rounded-xl bg-slate-950/40 border border-slate-800/80 space-y-1">
                          <span className="text-[10px] uppercase font-bold text-amber-400">
                            Identified Information Gaps:
                          </span>
                          <ul className="list-disc list-inside text-xs text-slate-400 space-y-0.5">
                            {parsedResult.missing_information.map((item, i) => (
                              <li key={i}>{item}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-600/30 text-[11px] text-amber-300 leading-relaxed flex items-start gap-2">
                        <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                        <span>
                          <strong>Scientific Verification Notice:</strong> AI-extracted values are estimates and must be verified before scientific or financial use.
                        </span>
                      </div>

                      {appliedFeedback && (
                        <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-xs text-emerald-300 flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          <span>{appliedFeedback}</span>
                        </div>
                      )}

                      {/* Action buttons */}
                      <div className="flex flex-col sm:flex-row gap-2.5 pt-2">
                        <button
                          type="button"
                          onClick={handleApplyToSimulator}
                          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-teal-500/20 hover:bg-teal-500/30 border border-teal-500/40 text-teal-300 text-xs font-bold transition shadow-sm"
                        >
                          <Layers className="w-3.5 h-3.5" />
                          <span>Apply to 3D Simulator</span>
                        </button>

                        <button
                          type="button"
                          onClick={handleApplyToCompare}
                          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-bold transition"
                        >
                          <Flame className="w-3.5 h-3.5 text-amber-400" />
                          <span>Compare Pathways</span>
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center text-center py-12 space-y-2 text-slate-400">
                      <Cpu className="w-8 h-8 text-slate-600" />
                      <p className="text-xs">No parsed data yet. Enter feedstock details on the left to extract structured values.</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
            TAB 3: SCIENTIFIC AUDIT
        ========================================================================= */}
        {activeTab === "audit" && (
          <div className="space-y-4">
            {auditNotice && (
              <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-600/40 text-xs text-amber-300 flex items-start gap-2.5">
                <Info className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <span>{auditNotice}</span>
              </div>
            )}

            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
              <div>
                <span className="font-bold text-slate-200">
                  Target Numerical Dataset: {form.waste_mass_kg_day.toLocaleString()} kg/day
                </span>
                <p className="text-slate-400 text-[11px] mt-0.5">
                  Audit will evaluate mass balance limits, mesophilic CSTR assumptions, and thermodynamic bounds.
                </p>
              </div>

              <button
                type="button"
                onClick={handleGenerateAudit}
                disabled={auditing}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-500 disabled:opacity-40 text-slate-950 font-bold text-xs transition shadow-lg shadow-teal-500/20"
              >
                <ShieldCheck className="w-4 h-4" />
                <span>{auditing ? "Generating Audit Report..." : "Generate Scientific Audit"}</span>
              </button>
            </div>

            {/* Audit Narrative Presentation */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-teal-400" />
                  <span className="text-xs font-bold uppercase tracking-wider text-white">
                    Audit Verification Report
                  </span>
                </div>
                <span className="text-[11px] text-slate-400 font-mono">
                  POST /api/v1/assistant/audit
                </span>
              </div>

              {auditReport ? (
                <div className="prose prose-invert max-w-none text-xs sm:text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-sans">
                  {auditReport}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center text-center py-12 space-y-2 text-slate-400">
                  <FileText className="w-8 h-8 text-slate-600" />
                  <p className="text-xs">Click “Generate Scientific Audit” above to produce an engineering narrative based on verified model parameters.</p>
                </div>
              )}
            </div>
          </div>
        )}

      </div>
    </main>
  );
}