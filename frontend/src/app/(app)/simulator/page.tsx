"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { Canvas } from "@react-three/fiber";
import {
  Layers,
  Filter,
  RotateCw,
  Flame,
  Wind,
  Zap,
  Sprout,
  Play,
  Pause,
  RotateCcw,
  Compass,
  ChevronRight,
  ChevronLeft,
  Recycle,
  Sparkles,
  AlertCircle,
  CheckCircle2,
  Activity,
  ArrowRight,
  Maximize2,
  ShieldAlert
} from "lucide-react";
import PlantScene from "./equipment-3d";
import { STAGES } from "./stages-data";

// Stage icon selector helper
function getStageIcon(code: string) {
  switch (code) {
    case "01":
      return <Layers className="w-4 h-4" />;
    case "02":
      return <Filter className="w-4 h-4" />;
    case "03":
      return <RotateCw className="w-4 h-4" />;
    case "04":
      return <Flame className="w-4 h-4 text-emerald-400" />;
    case "05":
      return <Wind className="w-4 h-4 text-purple-400" />;
    case "06":
      return <Zap className="w-4 h-4 text-rose-400" />;
    case "07":
      return <Sprout className="w-4 h-4 text-lime-400" />;
    default:
      return <Activity className="w-4 h-4" />;
  }
}

export default function SimulatorPage() {
  const [selected, setSelected] = useState(3); // Default to Anaerobic Digester (core hero stage)
  const [tourRunning, setTourRunning] = useState(false);
  const [tourCompleted, setTourCompleted] = useState(false);
  const [canvasKey, setCanvasKey] = useState(0); // For resetting camera view
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // Stop tour cleanly
  const stopTour = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setTourRunning(false);
  }, []);

  // Guided tour automation: advances every 3.5 seconds
  useEffect(() => {
    if (tourRunning) {
      setTourCompleted(false);
      timerRef.current = setInterval(() => {
        setSelected((prev) => {
          if (prev < STAGES.length - 1) {
            return prev + 1;
          } else {
            // Reached final stage
            stopTour();
            setTourCompleted(true);
            return prev;
          }
        });
      }, 3500);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [tourRunning, stopTour]);

  function handleSelectStage(index: number) {
    setSelected(index);
    if (tourCompleted && index < STAGES.length - 1) {
      setTourCompleted(false);
    }
  }

  function handleNextStage() {
    setSelected((prev) => Math.min(STAGES.length - 1, prev + 1));
  }

  function handlePrevStage() {
    setSelected((prev) => Math.max(0, prev - 1));
  }

  function handleRestartTour() {
    stopTour();
    setSelected(0);
    setTourCompleted(false);
  }

  function handleToggleTour() {
    if (tourRunning) {
      stopTour();
    } else {
      if (selected >= STAGES.length - 1) {
        setSelected(0);
      }
      setTourRunning(true);
      setTourCompleted(false);
    }
  }

  function handleResetCamera() {
    setCanvasKey((prev) => prev + 1);
  }

  const activeStage = STAGES[selected];

  return (
    <main className="min-h-screen bg-[#060a14] text-slate-100 p-4 sm:p-6 lg:p-8">
      <div className="max-w-[1720px] mx-auto space-y-6">

        {/* =========================================================================
            A. TOP NAVIGATION / HEADER
        ========================================================================= */}
        <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-teal-500/20 to-emerald-500/10 border border-teal-500/40 shadow-lg shadow-teal-500/10">
              <Sparkles className="w-5 h-5 text-teal-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-base tracking-tight text-white">
                  Waste-Potential
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase bg-teal-500/10 text-teal-400 border border-teal-500/30">
                  PROCESS LAB
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Interactive Biological & Mechanical Plant Simulation
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-900/80 border border-slate-800 text-xs text-slate-300">
              <span className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
              <span>3D R3F Viewport</span>
              <span className="text-slate-600">|</span>
              <span className="text-slate-400">7 Equipment Units</span>
            </div>

            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-amber-950/40 border border-amber-600/40 text-xs text-amber-300 shadow-sm">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
              <span>Illustrative · Not calculated</span>
            </div>
          </div>
        </header>

        {/* =========================================================================
            B. MAIN HEADING & VALUE INDICATORS AREA
        ========================================================================= */}
        <section className="space-y-4">
          <div className="space-y-1">
            <p className="text-xs font-bold tracking-[0.25em] uppercase text-teal-400">
              ORGANIC WASTE PROCESSING & BIOGAS CONVERSION
            </p>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold tracking-tight text-white">
              Anaerobic{" "}
              <span className="bg-gradient-to-r from-teal-300 via-emerald-400 to-cyan-300 bg-clip-text text-transparent">
                Digestion
              </span>{" "}
              Simulator
            </h1>
            <p className="text-sm sm:text-base text-slate-400 max-w-4xl leading-relaxed">
              Explore the continuous 7-stage pathway converting municipal and agricultural organic waste
              into renewable biomethane, electrical cogeneration, and circular bio-fertilizer.
            </p>
          </div>

          {/* 3 Compact Benefit Indicators */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="flex items-start gap-3 p-3.5 rounded-xl bg-slate-900/50 border border-slate-800/80 hover:border-slate-700 transition-colors">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-400 mt-0.5">
                <Recycle className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-xs font-bold text-slate-200">1. Divert Organic Waste</h2>
                <p className="text-xs text-slate-400 leading-normal mt-0.5">
                  Eliminates uncontrolled landfill methane emissions through sealed bioconversion.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3 p-3.5 rounded-xl bg-slate-900/50 border border-slate-800/80 hover:border-slate-700 transition-colors">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 mt-0.5">
                <Zap className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-xs font-bold text-slate-200">2. Generate Clean Energy</h2>
                <p className="text-xs text-slate-400 leading-normal mt-0.5">
                  Yields high-calorific biogas for combined electrical and thermal cogeneration.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3 p-3.5 rounded-xl bg-slate-900/50 border border-slate-800/80 hover:border-slate-700 transition-colors">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 mt-0.5">
                <Sprout className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-xs font-bold text-slate-200">3. Create Nutrient Digestate</h2>
                <p className="text-xs text-slate-400 leading-normal mt-0.5">
                  Supplies stabilized organic bio-fertilizer rich in nitrogen and organic carbon.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* =========================================================================
            C. MAIN WORKSPACE: 3D HERO VIEWPORT + SIDEBAR INSPECTOR
        ========================================================================= */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">

          {/* Left Column (8 cols): 3D Viewport & Guided Walkthrough */}
          <div className="lg:col-span-8 flex flex-col gap-5">

            {/* 3D Process Viewport Card */}
            <div className="glass-panel overflow-hidden relative rounded-2xl border border-slate-800 shadow-2xl flex flex-col">

              {/* Viewport Floating Top Controls Overlay */}
              <div className="absolute top-3.5 left-4 right-4 z-10 flex items-center justify-between pointer-events-none gap-2">
                <div>
                  <span className="text-[10px] font-bold tracking-[0.2em] text-teal-400 uppercase">
                    PROCESS FLOW / 3D VIEWPORT
                  </span>
                  <p className="text-xs font-semibold text-slate-200">
                    Miniature Industrial Facility · Stage {activeStage.code} Active
                  </p>
                </div>

                <div className="flex items-center gap-2 pointer-events-auto">
                  <button
                    onClick={handleResetCamera}
                    title="Reset camera view to default framing"
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-900/85 hover:bg-slate-800 border border-slate-700/80 text-xs text-slate-300 transition-colors shadow-md"
                  >
                    <Maximize2 className="w-3 h-3 text-teal-400" />
                    <span className="hidden sm:inline">Reset View</span>
                  </button>

                  <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-lg bg-slate-950/80 border border-slate-800 text-[11px] text-slate-400">
                    <span>Drag to orbit · Scroll to zoom</span>
                  </div>
                </div>
              </div>

              {/* 3D Canvas Container */}
              <div className="h-[460px] sm:h-[520px] md:h-[580px] w-full relative bg-[#060a14]">
                <Canvas
                  key={canvasKey}
                  camera={{ position: [0, 8.5, 23], fov: 40 }}
                  dpr={[1, 1.5]}
                  gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
                >
                  <PlantScene
                    stages={STAGES}
                    selectedStage={selected}
                    onSelectStage={handleSelectStage}
                  />
                </Canvas>
              </div>

              {/* Viewport Floating Bottom Bar Overlay */}
              <div className="absolute bottom-3 left-4 right-4 z-10 flex items-center justify-between pointer-events-none gap-2 text-[11px]">
                <div className="text-slate-400 font-mono tracking-wider">
                  SCHEMATIC EQUIPMENT · NOT TO SCALE
                </div>

                {/* Quick Stage Mini Pills */}
                <div className="flex items-center gap-1 pointer-events-auto bg-slate-950/85 px-2 py-1 rounded-full border border-slate-800/80">
                  {STAGES.map((s, idx) => (
                    <button
                      key={s.id}
                      onClick={() => handleSelectStage(idx)}
                      title={`Jump to ${s.code}: ${s.name}`}
                      className={`w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center transition-all ${
                        selected === idx
                          ? "bg-teal-400 text-slate-950 scale-110 shadow-sm shadow-teal-400/50"
                          : "text-slate-400 hover:text-white hover:bg-slate-800"
                      }`}
                    >
                      {s.code}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* =========================================================================
                F. GUIDED WALKTHROUGH PANEL (BELOW 3D SCENE)
            ========================================================================= */}
            <div className="glass-panel p-4 sm:p-5 rounded-2xl border border-slate-800 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-teal-500/10 border border-teal-500/30 flex items-center justify-center text-teal-400">
                    <Compass className={`w-4 h-4 ${tourRunning ? "animate-spin" : ""}`} />
                  </div>
                  <div>
                    <h2 className="text-xs font-bold tracking-wider uppercase text-teal-400">
                      GUIDED WALKTHROUGH
                    </h2>
                    <p className="text-xs text-slate-400">
                      Step-by-step automated inspection across the 7 digestion stages.
                    </p>
                  </div>
                </div>

                {/* Status Indicator */}
                <div className="flex items-center gap-2">
                  {tourRunning && (
                    <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-teal-500/10 text-teal-300 border border-teal-500/30 text-xs font-medium animate-pulse">
                      <span className="w-1.5 h-1.5 rounded-full bg-teal-400" />
                      Auto-Advancing (3.5s)
                    </span>
                  )}
                  {tourCompleted && (
                    <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 text-xs font-medium">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      Tour Complete
                    </span>
                  )}
                  <span className="text-xs font-semibold text-slate-300 bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-800">
                    Stage {selected + 1} of {STAGES.length}
                  </span>
                </div>
              </div>

              {/* 7-Step Interactive Stepper Bar */}
              <div className="grid grid-cols-7 gap-1.5 sm:gap-2">
                {STAGES.map((stage, idx) => {
                  const isCurrent = selected === idx;
                  const isPast = selected > idx;
                  return (
                    <button
                      key={stage.id}
                      onClick={() => handleSelectStage(idx)}
                      className={`flex flex-col items-center p-2 rounded-xl border text-center transition-all ${
                        isCurrent
                          ? "bg-teal-950/60 border-teal-400 shadow-md shadow-teal-500/20 scale-102"
                          : isPast
                          ? "bg-slate-900/60 border-emerald-500/30 text-slate-300 hover:bg-slate-800/80"
                          : "bg-slate-950/40 border-slate-800 text-slate-400 hover:bg-slate-900/60"
                      }`}
                    >
                      <span
                        className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold mb-1 transition-colors ${
                          isCurrent
                            ? "bg-teal-400 text-slate-950 shadow-sm"
                            : isPast
                            ? "bg-emerald-950 text-emerald-400 border border-emerald-500/40"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {stage.code}
                      </span>
                      <span className="text-[11px] font-semibold truncate w-full hidden sm:block">
                        {stage.shortName}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Controls bar */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <button
                    onClick={handlePrevStage}
                    disabled={selected === 0}
                    aria-label="Previous process stage"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-40 disabled:hover:bg-slate-900 border border-slate-700 text-xs font-semibold text-slate-200 transition-colors"
                  >
                    <ChevronLeft className="w-3.5 h-3.5" />
                    <span>Previous</span>
                  </button>

                  <button
                    onClick={handleNextStage}
                    disabled={selected === STAGES.length - 1}
                    aria-label="Next process stage"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-40 disabled:hover:bg-slate-900 border border-slate-700 text-xs font-semibold text-slate-200 transition-colors"
                  >
                    <span>Next</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleToggleTour}
                    aria-pressed={tourRunning}
                    className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-bold transition-all shadow-md ${
                      tourRunning
                        ? "bg-rose-950/80 hover:bg-rose-900 border border-rose-500/50 text-rose-200"
                        : "bg-teal-600 hover:bg-teal-500 border border-teal-400 text-slate-950 font-extrabold"
                    }`}
                  >
                    {tourRunning ? (
                      <>
                        <Pause className="w-3.5 h-3.5" />
                        <span>Pause Tour</span>
                      </>
                    ) : (
                      <>
                        <Play className="w-3.5 h-3.5 fill-current" />
                        <span>{tourCompleted ? "Replay Tour" : selected > 0 ? "Resume Tour" : "Start Tour"}</span>
                      </>
                    )}
                  </button>

                  <button
                    onClick={handleRestartTour}
                    title="Restart walkthrough from Stage 01"
                    aria-label="Restart tour from first stage"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-semibold text-slate-300 transition-colors"
                  >
                    <RotateCcw className="w-3 h-3 text-slate-400" />
                    <span>Restart</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Environmental Mission Card */}
            <div className="flex items-center justify-between p-3.5 rounded-xl bg-gradient-to-r from-teal-950/20 via-slate-900/40 to-emerald-950/20 border border-teal-500/20 text-xs text-slate-300">
              <div className="flex items-center gap-2.5">
                <Recycle className="w-4 h-4 text-teal-400 flex-shrink-0" />
                <span className="font-semibold text-slate-200">
                  “Turning Waste into a Cleaner Tomorrow”
                </span>
                <span className="hidden md:inline text-slate-400">
                  — Circular anaerobic digestion captures fugitive emissions and returns organic nutrients to regenerative agriculture.
                </span>
              </div>
            </div>
          </div>

          {/* Right Column (4 cols): Stage Selector & Selected-Stage Inspector */}
          <aside className="lg:col-span-4 flex flex-col gap-4">

            {/* Process Stages List Panel */}
            <div className="glass-panel p-4 rounded-2xl border border-slate-800 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <span className="text-[11px] font-bold tracking-[0.2em] uppercase text-teal-400">
                  PROCESS STAGES
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-800 text-slate-300">
                  7 SEQUENTIAL UNITS
                </span>
              </div>

              {/* 7 Stage Buttons */}
              <div className="grid gap-1.5">
                {STAGES.map((stage, idx) => {
                  const isActive = selected === idx;
                  return (
                    <button
                      key={stage.id}
                      onClick={() => handleSelectStage(idx)}
                      className={`stage-button flex items-center justify-between group ${
                        isActive ? "active" : ""
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div
                          className="flex items-center justify-center w-7 h-7 rounded-lg border text-xs font-bold transition-transform group-hover:scale-105"
                          style={{
                            backgroundColor: isActive ? stage.accentColor : "rgba(30, 41, 59, 0.5)",
                            borderColor: isActive ? stage.accentColor : "rgba(71, 85, 105, 0.4)",
                            color: isActive ? "#020617" : stage.color,
                          }}
                        >
                          {stage.code}
                        </div>

                        <div className="text-left min-w-0">
                          <p className="text-xs font-bold text-slate-200 group-hover:text-white truncate">
                            {stage.name}
                          </p>
                          <p className="text-[10px] text-slate-400 truncate">
                            {stage.category}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        <div className="text-slate-400 group-hover:text-slate-200">
                          {getStageIcon(stage.code)}
                        </div>
                        <ChevronRight
                          className={`w-3.5 h-3.5 transition-transform ${
                            isActive ? "text-teal-400 translate-x-0.5" : "text-slate-600"
                          }`}
                        />
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Selected-Stage Inspector Card */}
            <div className="glass-panel p-5 rounded-2xl border border-teal-500/30 shadow-lg shadow-teal-500/5 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <div
                    className="w-2.5 h-2.5 rounded-full animate-pulse"
                    style={{ backgroundColor: activeStage.accentColor }}
                  />
                  <span className="text-[11px] font-bold tracking-[0.2em] uppercase text-teal-400">
                    STAGE INSPECTOR
                  </span>
                </div>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-teal-950 text-teal-300 border border-teal-500/40">
                  Stage {activeStage.code}
                </span>
              </div>

              {/* Title & Category */}
              <div>
                <div className="flex items-center gap-2">
                  <span className="p-1 rounded-md bg-slate-800 text-teal-400">
                    {getStageIcon(activeStage.code)}
                  </span>
                  <h2 className="text-lg font-extrabold text-white">
                    {activeStage.name}
                  </h2>
                </div>
                <p className="text-xs text-teal-400/90 font-medium mt-1">
                  Category: {activeStage.category}
                </p>
                <p className="text-xs text-slate-300 mt-2 leading-relaxed">
                  {activeStage.description}
                </p>
              </div>

              {/* Process Inputs & Outputs with clear visual separation */}
              <div className="space-y-3 pt-2 border-t border-slate-800/80">
                {/* Inputs */}
                <div>
                  <div className="flex items-center gap-1.5 text-[11px] font-bold text-sky-400 uppercase tracking-wider mb-1.5">
                    <ArrowRight className="w-3 h-3" />
                    <span>Process Inputs</span>
                  </div>
                  <ul className="space-y-1">
                    {activeStage.inputs.map((inp, i) => (
                      <li key={i} className="text-xs text-slate-300 flex items-start gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-sky-400 mt-1.5 flex-shrink-0" />
                        <span>{inp}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Outputs */}
                <div>
                  <div className="flex items-center gap-1.5 text-[11px] font-bold text-emerald-400 uppercase tracking-wider mb-1.5">
                    <ArrowRight className="w-3 h-3" />
                    <span>Process Outputs</span>
                  </div>
                  <ul className="space-y-1">
                    {activeStage.outputs.map((out, i) => (
                      <li key={i} className="text-xs text-slate-300 flex items-start gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-1.5 flex-shrink-0" />
                        <span>{out}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Equipment Highlights */}
                <div>
                  <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                    Equipment Architecture
                  </div>
                  <ul className="space-y-1">
                    {activeStage.equipmentHighlights.map((eq, i) => (
                      <li key={i} className="text-xs text-slate-400 flex items-start gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-500 mt-1.5 flex-shrink-0" />
                        <span>{eq}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Illustrative Disclaimer Note */}
              <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-600/30 text-[11px] text-amber-300/90 leading-relaxed flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <span>
                  <strong>Illustrative Schematic:</strong> No calculated engineering yields, flow rates,
                  or gas outputs are fabricated on this frontend. Validated scientific data will connect
                  directly to the FastAPI backend calculation service.
                </span>
              </div>
            </div>

          </aside>
        </section>

        {/* =========================================================================
            G. FOOTER
        ========================================================================= */}
        <footer className="pt-4 border-t border-slate-800/80 text-xs text-slate-400 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <p>
            <strong className="text-slate-300 font-semibold">Waste-Potential Platform</strong> · Module P5: Interactive Process Simulator & Process Lab
          </p>
          <p className="text-[11px] text-slate-400">
            SCIENCE BEFORE SPECTACLE · Three.js & React Three Fiber Engine
          </p>
        </footer>

      </div>
    </main>
  );
}
