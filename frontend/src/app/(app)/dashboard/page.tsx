"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Sparkles,
  Layers,
  Flame,
  MessageSquare,
  Sprout,
  Activity,
  Zap,
  Recycle,
  MapPin,
  Search,
  ArrowRight,
  TrendingUp,
  Cpu,
  ShieldCheck,
  Thermometer,
  CloudSun,
  Database,
  Building2,
  Users,
  Compass,
} from "lucide-react";
import { useScenarioStore } from "@/stores/scenario";
import { StatusBadge } from "@/components/Simulator/StatusBadge";

type GeocodeResult = {
  lat: number;
  lng: number;
  display_name: string;
  precision: string;
  source: string;
  cached: boolean;
};

type WeatherData = {
  ambient_temp_c: number;
  relative_humidity: number;
};

export default function DashboardPage() {
  const { form, result } = useScenarioStore();

  // Regional weather & geocode state
  const [pincode, setPincode] = useState("411001"); // Default Pune
  const [location, setLocation] = useState<GeocodeResult | null>(null);
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [geoLoading, setGeoLoading] = useState(false);
  const [geoError, setGeoError] = useState("");

  async function fetchRegionalData(pinToFetch: string) {
    const cleanPin = pinToFetch.trim();
    if (!/^[1-9]\d{5}$/.test(cleanPin)) {
      setGeoError("Please enter a valid 6-digit Indian PIN code.");
      return;
    }

    setGeoLoading(true);
    setGeoError("");

    try {
      const geoRes = await fetch(
        `/api/geocode?pincode=${encodeURIComponent(cleanPin)}&country=India`
      );
      const geoData = await geoRes.json();

      if (!geoRes.ok) {
        throw new Error(
          typeof geoData.detail === "string"
            ? geoData.detail
            : "Location lookup failed for this PIN code."
        );
      }

      const geo = geoData as GeocodeResult;
      setLocation(geo);

      // Fetch ambient weather if coordinates exist
      try {
        const weatherRes = await fetch(
          `/api/weather?latitude=${geo.lat}&longitude=${geo.lng}`
        );
        if (weatherRes.ok) {
          const wData = await weatherRes.json();
          setWeather(wData as WeatherData);
        } else {
          setWeather(null);
        }
      } catch {
        setWeather(null);
      }
    } catch (err) {
      setLocation(null);
      setWeather(null);
      setGeoError(
        err instanceof Error
          ? err.message
          : "Could not retrieve regional data."
      );
    } finally {
      setGeoLoading(false);
    }
  }

  // Load initial default regional data
  useEffect(() => {
    void fetchRegionalData("411001");
  }, []);

  // Proportional KPI calculations based on active scenario form
  const mass = form.waste_mass_kg_day || 1000;
  const org = form.organic_fraction || 0.55;
  const netEnergyKwh = result?.results?.e_net_kwh_d ?? mass * org * 0.22;
  const biogasYield = result?.results?.biogas_nm3_d ?? mass * org * 0.11;
  const co2AvoidedTons = (biogasYield * 0.6 * 1.8) / 1000; // Methane diverted GWP factor
  const bioFertilizerKg = mass * org * 0.85;

  return (
    <main className="min-h-screen bg-[#060a14] px-4 py-8 text-slate-100 sm:px-8">
      <div className="mx-auto max-w-7xl space-y-8">

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
                Executive Dashboard
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-medium">
            <Link href="/dashboard" className="rounded-lg bg-teal-950 px-3 py-1.5 font-bold text-teal-300 border border-teal-700/50">
              Dashboard
            </Link>
            <Link href="/simulator" className="rounded-lg px-3 py-1.5 text-slate-400 transition hover:bg-slate-900 hover:text-white">
              3D Simulator
            </Link>
            <Link href="/compare" className="rounded-lg px-3 py-1.5 text-slate-400 transition hover:bg-slate-900 hover:text-white">
              Compare
            </Link>
            <Link href="/assistant" className="rounded-lg px-3 py-1.5 text-slate-400 transition hover:bg-slate-900 hover:text-white">
              AI Assistant
            </Link>
          </div>
        </nav>

        {/* =========================================================================
            EXECUTIVE HEADER
        ========================================================================= */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-teal-400">
              Operations &amp; Intelligence Overview
            </p>
            <h1 className="mt-1 text-3xl font-extrabold tracking-tight sm:text-4xl text-white">
              Facility Executive Dashboard
            </h1>
            <p className="mt-1 text-sm text-slate-400 max-w-3xl leading-relaxed">
              Real-time monitoring of organic waste conversion, bio-energetic yields, regional climate parameters,
              and multi-pathway decision support.
            </p>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-xs">
              <span className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
              <span className="text-slate-300">FastAPI Core Active</span>
            </div>
            {result ? (
              <StatusBadge status={result.status} />
            ) : (
              <span className="px-3 py-1.5 rounded-full bg-slate-900/80 border border-slate-800 text-xs text-slate-400">
                Scenario: Baseline Standby
              </span>
            )}
          </div>
        </div>

        {/* =========================================================================
            FOUR PRIMARY KPI SUMMARY CARDS
        ========================================================================= */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Daily Waste Throughput */}
          <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 transition shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Feedstock Intake
              </span>
              <div className="w-8 h-8 rounded-lg bg-teal-500/10 border border-teal-500/30 flex items-center justify-center text-teal-400">
                <Recycle className="w-4 h-4" />
              </div>
            </div>
            <p className="text-2xl sm:text-3xl font-extrabold text-white mt-3 font-mono">
              {mass.toLocaleString()}{" "}
              <span className="text-xs font-medium text-slate-400 font-sans">kg/day</span>
            </p>
            <p className="text-[11px] text-teal-400/90 mt-1.5 flex items-center gap-1">
              <TrendingUp className="w-3 h-3" />
              <span>{(org * 100).toFixed(0)}% organic biodegradable fraction</span>
            </p>
          </div>

          {/* Card 2: Clean Energy Potential */}
          <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 transition shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Net Energy Output
              </span>
              <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
                <Zap className="w-4 h-4" />
              </div>
            </div>
            <p className="text-2xl sm:text-3xl font-extrabold text-amber-300 mt-3 font-mono">
              {netEnergyKwh.toFixed(1)}{" "}
              <span className="text-xs font-medium text-slate-400 font-sans">kWh/day</span>
            </p>
            <p className="text-[11px] text-slate-400 mt-1.5">
              Cogeneration electrical &amp; thermal balance
            </p>
          </div>

          {/* Card 3: Biomethane Yield & Methane Abated */}
          <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 transition shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Biogas Generation
              </span>
              <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                <Activity className="w-4 h-4" />
              </div>
            </div>
            <p className="text-2xl sm:text-3xl font-extrabold text-cyan-300 mt-3 font-mono">
              {biogasYield.toFixed(1)}{" "}
              <span className="text-xs font-medium text-slate-400 font-sans">Nm³/day</span>
            </p>
            <p className="text-[11px] text-slate-400 mt-1.5">
              ~{co2AvoidedTons.toFixed(2)} t CO₂e landfill emissions mitigated
            </p>
          </div>

          {/* Card 4: Bio-Fertilizer Yield */}
          <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 transition shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Nutrient Digestate
              </span>
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <Sprout className="w-4 h-4" />
              </div>
            </div>
            <p className="text-2xl sm:text-3xl font-extrabold text-emerald-300 mt-3 font-mono">
              {bioFertilizerKg.toFixed(0)}{" "}
              <span className="text-xs font-medium text-slate-400 font-sans">kg/day</span>
            </p>
            <p className="text-[11px] text-slate-400 mt-1.5">
              Stabilized N-P-K mineralized soil amendment
            </p>
          </div>
        </section>

        {/* =========================================================================
            TWO-COLUMN: ACTIVE SCENARIO SUMMARY & REGIONAL CONTEXT
        ========================================================================= */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">

          {/* Left Column (7 cols): Active Scenario & Twin Status */}
          <div className="lg:col-span-7 rounded-2xl border border-slate-800 bg-slate-900/50 p-6 space-y-5 shadow-xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-teal-500/10 border border-teal-500/30 flex items-center justify-center text-teal-400">
                  <Database className="w-4 h-4" />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-white uppercase tracking-wider">
                    Active Facility Twin State
                  </h2>
                  <p className="text-xs text-slate-400">
                    Shared state synchronized across 3D Simulator, Compare, and Assistant
                  </p>
                </div>
              </div>

              {result ? (
                <StatusBadge status={result.status} />
              ) : (
                <span className="text-[11px] font-semibold text-amber-400 bg-amber-950/40 border border-amber-600/30 px-2 py-0.5 rounded-full">
                  Unsimulated Form Values
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                <span className="text-[10px] font-bold uppercase text-slate-400">Gross Feedstock</span>
                <p className="text-base font-extrabold text-white mt-1 font-mono">{mass.toLocaleString()} kg/d</p>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                <span className="text-[10px] font-bold uppercase text-slate-400">Organics Fraction</span>
                <p className="text-base font-extrabold text-teal-400 mt-1 font-mono">{(org * 100).toFixed(0)}%</p>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                <span className="text-[10px] font-bold uppercase text-slate-400">Suitable Ratio</span>
                <p className="text-base font-extrabold text-sky-400 mt-1 font-mono">{(form.suitable_fraction * 100).toFixed(0)}%</p>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                <span className="text-[10px] font-bold uppercase text-slate-400">Active Digester Size</span>
                <p className="text-base font-extrabold text-emerald-400 mt-1 font-mono">
                  {result ? `${result.results.digester_m3.toFixed(0)} m³` : `${(mass * org * 0.05).toFixed(0)} m³ est.`}
                </p>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                <span className="text-[10px] font-bold uppercase text-slate-400">Model Verification</span>
                <p className="text-xs font-semibold text-slate-200 mt-1.5 truncate">
                  {result ? `Run: ${result.id.slice(0, 8)}...` : "Awaiting API run"}
                </p>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                <span className="text-[10px] font-bold uppercase text-slate-400">Facility Location ID</span>
                <p className="text-xs font-semibold text-slate-300 mt-1.5 truncate">
                  {form.location_id || "National Baseline"}
                </p>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
              <Link
                href="/simulator"
                className="w-full sm:w-auto flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-500 text-slate-950 text-xs font-bold transition shadow-lg shadow-teal-500/20"
              >
                <Layers className="w-3.5 h-3.5" />
                <span>Open 3D Process Simulator</span>
              </Link>

              <Link
                href="/compare"
                className="w-full sm:w-auto flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-bold transition"
              >
                <Flame className="w-3.5 h-3.5 text-amber-400" />
                <span>Evaluate 7 Pathways</span>
              </Link>
            </div>
          </div>

          {/* Right Column (5 cols): Regional Geocoding & Weather Context */}
          <div className="lg:col-span-5 rounded-2xl border border-slate-800 bg-slate-900/50 p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <MapPin className="w-4 h-4 text-teal-400" />
                <span className="text-xs font-bold uppercase tracking-wider text-white">
                  Regional Climate Context
                </span>
              </div>
              <span className="text-[10px] text-slate-400 font-mono">/geocode &amp; /weather</span>
            </div>

            {/* PIN Search Form */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <MapPin className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-500" />
                <input
                  type="text"
                  maxLength={6}
                  value={pincode}
                  onChange={(e) => setPincode(e.target.value.replace(/\D/g, ""))}
                  placeholder="6-digit Indian PIN (e.g. 411001)"
                  className="w-full bg-slate-950 border border-slate-700 hover:border-teal-400 focus:border-teal-400 focus:ring-1 focus:ring-teal-400 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 outline-none transition font-mono"
                />
              </div>
              <button
                type="button"
                onClick={() => fetchRegionalData(pincode)}
                disabled={geoLoading || pincode.length !== 6}
                className="px-3 py-2 rounded-xl bg-teal-500/20 hover:bg-teal-500/30 border border-teal-500/40 text-teal-300 text-xs font-bold transition disabled:opacity-40 flex items-center gap-1.5"
              >
                <Search className="w-3.5 h-3.5" />
                <span>{geoLoading ? "Searching..." : "Lookup"}</span>
              </button>
            </div>

            {/* Quick PIN Presets */}
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <span>Quick Presets:</span>
              {[
                { label: "Pune", pin: "411001" },
                { label: "Bengaluru", pin: "560001" },
                { label: "Anand", pin: "388001" },
                { label: "Delhi", pin: "110001" },
              ].map((city) => (
                <button
                  key={city.pin}
                  type="button"
                  onClick={() => {
                    setPincode(city.pin);
                    void fetchRegionalData(city.pin);
                  }}
                  className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] transition"
                >
                  {city.label}
                </button>
              ))}
            </div>

            {geoError && (
              <p className="text-xs text-rose-400 bg-rose-950/40 p-2.5 rounded-lg border border-rose-500/30">
                {geoError}
              </p>
            )}

            {/* Resolved Regional Card */}
            {location && (
              <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3">
                <div>
                  <span className="text-[10px] font-bold uppercase text-slate-400">Resolved Location</span>
                  <p className="text-xs font-semibold text-white mt-0.5 leading-snug">
                    {location.display_name}
                  </p>
                  <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                    Lat: {location.lat.toFixed(4)}°, Lng: {location.lng.toFixed(4)}°
                  </p>
                </div>

                {weather ? (
                  <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800/80">
                    <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center gap-2">
                      <Thermometer className="w-4 h-4 text-amber-400 flex-shrink-0" />
                      <div>
                        <span className="text-[9px] uppercase font-bold text-slate-400 block">Ambient Temp</span>
                        <span className="text-xs font-bold text-white font-mono">{weather.ambient_temp_c}°C</span>
                      </div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center gap-2">
                      <CloudSun className="w-4 h-4 text-sky-400 flex-shrink-0" />
                      <div>
                        <span className="text-[9px] uppercase font-bold text-slate-400 block">Rel. Humidity</span>
                        <span className="text-xs font-bold text-white font-mono">{(weather.relative_humidity * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-[11px] text-slate-500 pt-1">
                    Ambient weather observation offline or loading.
                  </p>
                )}

                <p className="text-[10px] text-slate-400 leading-normal">
                  Ambient temperatures influence parasitic digester jacket heating requirements to maintain 38°C mesophilic operation.
                </p>
              </div>
            )}
          </div>
        </section>

        {/* =========================================================================
            PLATFORM MODULE LAUNCHERS GRID
        ========================================================================= */}
        <section className="space-y-4">
          <div>
            <h2 className="text-xs font-bold uppercase tracking-[0.2em] text-teal-400">
              Platform Modules
            </h2>
            <h3 className="text-xl font-bold text-white mt-1">
              Integrated Tools &amp; Applications
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

            {/* 1. 3D Process Simulator */}
            <Link
              href="/simulator"
              className="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-900/90 border border-slate-800 hover:border-teal-500/50 transition-all flex flex-col justify-between group shadow-lg"
            >
              <div className="space-y-2.5">
                <div className="w-9 h-9 rounded-xl bg-teal-500/10 border border-teal-500/30 flex items-center justify-center text-teal-400 group-hover:scale-105 transition-transform">
                  <Layers className="w-4 h-4" />
                </div>
                <h4 className="text-sm font-bold text-white group-hover:text-teal-300 transition-colors">
                  3D Process Simulator &amp; Digital Twin
                </h4>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Interactive 7-stage 3D facility simulation across all 7 pathways with dynamic throughput tracking.
                </p>
              </div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-teal-400 mt-4 group-hover:translate-x-1 transition-transform">
                <span>Launch Simulator</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            </Link>

            {/* 2. Compare Pathways */}
            <Link
              href="/compare"
              className="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-900/90 border border-slate-800 hover:border-teal-500/50 transition-all flex flex-col justify-between group shadow-lg"
            >
              <div className="space-y-2.5">
                <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 group-hover:scale-105 transition-transform">
                  <Flame className="w-4 h-4" />
                </div>
                <h4 className="text-sm font-bold text-white group-hover:text-teal-300 transition-colors">
                  Decision Support &amp; 7-Pathway Comparison
                </h4>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Screen all 7 thermal and biochemical pathways by techno-economic feasibility, revenue, and optimality.
                </p>
              </div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-teal-400 mt-4 group-hover:translate-x-1 transition-transform">
                <span>Compare Pathways</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            </Link>

            {/* 3. AI Technical Assistant */}
            <Link
              href="/assistant"
              className="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-900/90 border border-slate-800 hover:border-teal-500/50 transition-all flex flex-col justify-between group shadow-lg"
            >
              <div className="space-y-2.5">
                <div className="w-9 h-9 rounded-xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400 group-hover:scale-105 transition-transform">
                  <MessageSquare className="w-4 h-4" />
                </div>
                <h4 className="text-sm font-bold text-white group-hover:text-teal-300 transition-colors">
                  AI Technical Assistant &amp; Parser
                </h4>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Ask technical questions, parse unformatted waste text into verified numbers, and generate scientific audits.
                </p>
              </div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-teal-400 mt-4 group-hover:translate-x-1 transition-transform">
                <span>Open Assistant</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            </Link>

            {/* 4. Citizen Segregation PWA */}
            <Link
              href="/citizen"
              className="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-900/90 border border-slate-800 hover:border-teal-500/50 transition-all flex flex-col justify-between group shadow-lg"
            >
              <div className="space-y-2.5">
                <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 group-hover:scale-105 transition-transform">
                  <Users className="w-4 h-4" />
                </div>
                <h4 className="text-sm font-bold text-white group-hover:text-teal-300 transition-colors">
                  Citizen Waste Segregation PWA
                </h4>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Mobile-friendly guide for household waste segregation, local collection points, and circular practices.
                </p>
              </div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-teal-400 mt-4 group-hover:translate-x-1 transition-transform">
                <span>Open Citizen App</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            </Link>

            {/* 5. Farm & Bio-Fertilizer PWA */}
            <Link
              href="/farm"
              className="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-900/90 border border-slate-800 hover:border-teal-500/50 transition-all flex flex-col justify-between group shadow-lg"
            >
              <div className="space-y-2.5">
                <div className="w-9 h-9 rounded-xl bg-lime-500/10 border border-lime-500/30 flex items-center justify-center text-lime-400 group-hover:scale-105 transition-transform">
                  <Sprout className="w-4 h-4" />
                </div>
                <h4 className="text-sm font-bold text-white group-hover:text-teal-300 transition-colors">
                  Farm &amp; Bio-Fertilizer PWA
                </h4>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Agricultural waste supply matching, manure co-digestion, and circular organic nutrient application.
                </p>
              </div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-teal-400 mt-4 group-hover:translate-x-1 transition-transform">
                <span>Open Farm App</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            </Link>

            {/* 6. Marketplace & Buyers */}
            <Link
              href="/market"
              className="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-900/90 border border-slate-800 hover:border-teal-500/50 transition-all flex flex-col justify-between group shadow-lg"
            >
              <div className="space-y-2.5">
                <div className="w-9 h-9 rounded-xl bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400 group-hover:scale-105 transition-transform">
                  <Building2 className="w-4 h-4" />
                </div>
                <h4 className="text-sm font-bold text-white group-hover:text-teal-300 transition-colors">
                  Recyclables &amp; Byproduct Marketplace
                </h4>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Buyer matching for recyclables, stabilized biochar, RDF pellets, and refined organic compost.
                </p>
              </div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-teal-400 mt-4 group-hover:translate-x-1 transition-transform">
                <span>View Marketplace</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            </Link>

          </div>
        </section>

        {/* =========================================================================
            SEVEN-PATHWAY CONVERSION MATRIX
        ========================================================================= */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-teal-400">
                Continuous Conversion Matrix
              </span>
              <h3 className="text-base font-bold text-white mt-0.5">
                7 Supported Waste Processing Pathways
              </h3>
            </div>
            <Link
              href="/compare"
              className="text-xs text-teal-400 hover:text-teal-300 font-semibold flex items-center gap-1"
            >
              <span>Full Comparison</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-2.5 text-center">
            {[
              { name: "Anaerobic Digestion", type: "Biochemical", yield: "Biomethane + Digestate", color: "#2dd4bf" },
              { name: "Aerobic Composting", type: "Biological", yield: "Humus Bio-Fertilizer", color: "#84cc16" },
              { name: "Mass-Burn Incineration", type: "Thermal", yield: "Steam + Power + Ash", color: "#f97316" },
              { name: "Gasification", type: "Thermochemical", yield: "Syngas (CO + H₂)", color: "#06b6d4" },
              { name: "Fast Pyrolysis", type: "Thermochemical", yield: "Bio-Oil + Biochar", color: "#a855f7" },
              { name: "Hydrothermal (HTC)", type: "Thermochemical", yield: "Hydrochar Slurry", color: "#3b82f6" },
              { name: "Torrefaction", type: "Thermal", yield: "Densified Pellets", color: "#eab308" },
            ].map((p, idx) => (
              <div
                key={idx}
                className="p-3 rounded-xl bg-slate-950/50 border border-slate-800 hover:border-slate-700 transition space-y-1"
              >
                <div
                  className="w-2.5 h-2.5 rounded-full mx-auto"
                  style={{ backgroundColor: p.color }}
                />
                <p className="text-xs font-bold text-white truncate">{p.name}</p>
                <p className="text-[10px] text-teal-400 font-medium">{p.type}</p>
                <p className="text-[10px] text-slate-400 truncate">{p.yield}</p>
              </div>
            ))}
          </div>
        </section>

        {/* =========================================================================
            FOOTER
        ========================================================================= */}
        <footer className="pt-4 border-t border-slate-800/80 text-xs text-slate-400 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <p>
            <strong className="text-slate-300 font-semibold">Waste-Potential Platform</strong> · Module P5: Executive Dashboard &amp; Operational Hub
          </p>
          <p className="text-[11px] text-slate-400">
            SCIENCE BEFORE SPECTACLE · Decentralized Circular Economy Engine
          </p>
        </footer>

      </div>
    </main>
  );
}