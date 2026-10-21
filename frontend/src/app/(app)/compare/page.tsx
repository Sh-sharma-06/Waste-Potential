"use client";

import { useState } from "react";
import Link from "next/link";
import { MapPin, Search, AlertCircle, CheckCircle2, Info, Compass, Sparkles } from "lucide-react";

const PATHWAYS = [
  { id: "anaerobic_digestion", name: "Anaerobic Digestion" },
  { id: "composting", name: "Aerobic Composting" },
  { id: "incineration", name: "Mass-Burn Incineration" },
  { id: "gasification", name: "Gasification" },
  { id: "pyrolysis", name: "Pyrolysis" },
  { id: "htc", name: "Hydrothermal Carbonisation" },
  { id: "torrefaction", name: "Torrefaction & Pelletisation" },
] as const;

type PathwayResult = {
  pathway: string;
  feasible: boolean;
  reasons: string[];
  outputs: Record<string, number>;
  revenue_inr_y: number;
  cost_inr_y: number;
  annual_net_value_inr: number;
  e_net_kwh_d: number;
  status: string;
  warnings: string[];
  optimality_share?: number | null;
  optimality_note?: string | null;
};

type GeocodeResult = {
  lat: number;
  lng: number;
  display_name: string;
  precision: string;
  source: string;
  cached: boolean;
};

function money(value: number | undefined) {
  if (value === undefined || !Number.isFinite(value)) return "Not specified";
  return value.toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  });
}

export default function ComparePage() {
  const [mass, setMass] = useState("1000");
  const [results, setResults] = useState<PathwayResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Regional location lookup state (Indian PIN code)
  const [pincode, setPincode] = useState("");
  const [location, setLocation] = useState<GeocodeResult | null>(null);
  const [geoLoading, setGeoLoading] = useState(false);
  const [geoError, setGeoError] = useState("");

  async function findLocation() {
    const cleanPin = pincode.trim();
    if (!/^[1-9]\d{5}$/.test(cleanPin)) {
      setGeoError(
        "Please enter a valid 6-digit Indian PIN code (must be 6 digits and cannot start with 0)."
      );
      return;
    }

    setGeoLoading(true);
    setGeoError("");

    try {
      const response = await fetch(
        `/api/geocode?pincode=${encodeURIComponent(cleanPin)}&country=India`
      );
      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Location lookup failed. Please verify the PIN code."
        );
      }

      setLocation(data as GeocodeResult);
    } catch (err) {
      setLocation(null);
      setGeoError(
        err instanceof Error
          ? err.message
          : "Could not retrieve location for the specified PIN code."
      );
    } finally {
      setGeoLoading(false);
    }
  }

  async function comparePathways() {
    const kg = Number(mass);

    if (!Number.isFinite(kg) || kg <= 0) {
      setError("Enter a waste quantity greater than zero.");
      return;
    }

    setLoading(true);
    setError("");
    setResults([]);

    try {
      const response = await fetch("/api/pathways/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          farm_id: "default",
          waste_tpd: kg / 1000,
          pathways: PATHWAYS.map((pathway) => pathway.id),
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail ?? data)
        );
      }

      if (!Array.isArray(data)) {
        throw new Error("The comparison API returned an unexpected response.");
      }

      setResults(
        [...(data as PathwayResult[])].sort((a, b) => {
          if (a.feasible !== b.feasible) return a.feasible ? -1 : 1;
          return (b.optimality_share ?? -1) - (a.optimality_share ?? -1);
        })
      );

      if (data.length === 0) {
        setError("The API returned no pathway results.");
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not compare pathways. Check that the backend is running."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100 sm:px-8">
      <div className="mx-auto max-w-6xl">
        {/* Navigation Bar */}
        <nav aria-label="Main Navigation" className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-500/10 border border-teal-500/30 text-teal-400">
              <Sparkles className="h-4 w-4" />
            </span>
            <div>
              <span className="font-extrabold text-sm tracking-tight text-white">Waste-Potential</span>
              <span className="ml-2 rounded-full border border-teal-500/30 bg-teal-500/10 px-2 py-0.5 text-[10px] font-bold uppercase text-teal-400">
                Decision Hub
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
            <Link href="/compare" className="rounded-lg bg-teal-950 px-3 py-1.5 font-bold text-teal-300 border border-teal-700/50">
              Compare
            </Link>
            <Link href="/assistant" className="rounded-lg px-3 py-1.5 text-slate-400 transition hover:bg-slate-900 hover:text-white">
              AI Assistant
            </Link>
          </div>
        </nav>

        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-teal-400">
          Waste Potential · Decision Support
        </p>

        <h1 className="mt-3 text-3xl font-bold sm:text-4xl">
          Compare Waste Processing Pathways
        </h1>

        <p className="mt-3 max-w-3xl text-slate-400">
          Compare seven treatment options using the available model outputs,
          economic estimates, and optimality analysis.
        </p>

        {/* Input & Location Configuration Panel */}
        <section className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-5 sm:p-7 space-y-6">
          {/* Location & Pincode Lookup Block */}
          <div className="rounded-xl border border-slate-800/80 bg-slate-950/70 p-4 sm:p-5">
            <div className="flex items-center gap-2 text-teal-400">
              <MapPin className="h-4 w-4" />
              <label htmlFor="pincode-input" className="text-sm font-semibold text-slate-200">
                Regional Location (Indian 6-Digit PIN Code)
              </label>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Resolve geographic coordinates and climatic context for your feedstock source.
            </p>

            <div className="mt-3 flex flex-col gap-3 sm:flex-row">
              <input
                id="pincode-input"
                type="text"
                maxLength={6}
                value={pincode}
                onChange={(event) => setPincode(event.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void findLocation();
                  }
                }}
                className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-2.5 text-sm text-white placeholder-slate-500 outline-none focus:border-teal-500"
                placeholder="e.g. 110001 or 411001"
              />

              <button
                type="button"
                onClick={findLocation}
                disabled={geoLoading}
                className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border border-teal-600/50 bg-teal-950/60 px-5 py-2.5 text-sm font-semibold text-teal-300 transition hover:bg-teal-900/60 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Search className="h-4 w-4" />
                <span>{geoLoading ? "Finding..." : "Find location"}</span>
              </button>
            </div>

            {/* Geocode Lookup Error */}
            {geoError && (
              <div
                role="alert"
                className="mt-3 flex items-start gap-2 rounded-lg border border-rose-900/70 bg-rose-950/40 p-3 text-xs text-rose-200"
              >
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
                <span>{geoError}</span>
              </div>
            )}

            {/* Geocode Result Card */}
            {location && (
              <div className="mt-3 rounded-lg border border-teal-800/40 bg-teal-950/30 p-3.5 text-xs text-teal-200 space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 font-semibold text-teal-300">
                    <CheckCircle2 className="h-4 w-4 text-teal-400 shrink-0" />
                    <span>{location.display_name}</span>
                  </div>
                  {location.cached && (
                    <span className="rounded bg-teal-900/50 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-teal-400">
                      Cached
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-slate-400">
                  <span>
                    Coordinates: <strong className="text-slate-200">{location.lat.toFixed(4)}° N, {location.lng.toFixed(4)}° E</strong>
                  </span>
                  <span>Precision: {location.precision}</span>
                  <span className="text-slate-500">Source: {location.source}</span>
                </div>
              </div>
            )}

            {/* Mandatory Location Transparency Disclaimer */}
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-900/50 p-2.5 text-[11px] text-slate-400">
              <Info className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
              <span>
                <strong>Default Location Reference:</strong> Comparisons currently use default location data. The PIN-code lookup provides approximate spatial reference and climate mapping coordinates; it does not change thermodynamic calculation yields or alter baseline comparison models.
              </span>
            </div>
          </div>

          {/* Waste Mass Input Block */}
          <div>
            <label
              htmlFor="waste-mass"
              className="block text-sm font-medium text-slate-200"
            >
              Total waste quantity (kg/day)
            </label>

            <div className="mt-2 flex flex-col gap-3 sm:flex-row">
              <input
                id="waste-mass"
                type="number"
                min="0.01"
                step="any"
                value={mass}
                onChange={(event) => setMass(event.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none focus:border-teal-500"
                placeholder="e.g. 1000"
              />

              <button
                type="button"
                onClick={comparePathways}
                disabled={loading}
                className="shrink-0 rounded-xl bg-teal-600 px-6 py-3 font-semibold text-white transition hover:bg-teal-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? "Comparing..." : "Compare pathways"}
              </button>
            </div>

            <p className="mt-3 text-xs text-slate-500">
              The entered quantity is converted to tonnes/day for the comparison API.
            </p>
          </div>
        </section>

        {error && (
          <div
            role="alert"
            className="mt-6 rounded-xl border border-rose-800 bg-rose-950/40 p-4 text-sm text-rose-200"
          >
            {error}
          </div>
        )}

        {results.length > 0 && (
          <section className="mt-8">
            <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-2xl font-bold">Comparison results</h2>
                <p className="mt-1 text-sm text-slate-400">
                  {results.length} pathway results returned by the backend
                </p>
              </div>
              <span className="rounded-full border border-amber-700 px-3 py-1 text-xs text-amber-300">
                Illustrative model estimates
              </span>
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              {results.map((result) => {
                const pathway = PATHWAYS.find(
                  (item) => item.id === result.pathway
                );
                const share = result.optimality_share;
                const percentage =
                  typeof share === "number" && Number.isFinite(share)
                    ? Math.max(0, Math.min(100, share * 100))
                    : null;

                return (
                  <article
                    key={result.pathway}
                    className={`rounded-2xl border p-5 ${
                      result.feasible
                        ? "border-slate-700 bg-slate-900"
                        : "border-slate-800 bg-slate-900/50 opacity-80"
                    }`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-xs uppercase tracking-wider text-slate-500">
                          {result.pathway.replaceAll("_", " ")}
                        </p>
                        <h3 className="mt-1 text-xl font-semibold">
                          {pathway?.name ?? result.pathway}
                        </h3>
                      </div>

                      <span
                        className={`rounded-full px-3 py-1 text-xs font-semibold ${
                          result.feasible
                            ? "bg-teal-950 text-teal-300"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {result.feasible ? "Feasible" : "Not feasible"}
                      </span>
                    </div>

                    <div className="mt-5 grid grid-cols-2 gap-4">
                      <div className="rounded-xl bg-slate-950 p-3">
                        <p className="text-xs text-slate-500">
                          Annual net value
                        </p>
                        <p className="mt-1 break-words text-lg font-bold">
                          {money(result.annual_net_value_inr)}
                        </p>
                      </div>

                      <div className="rounded-xl bg-slate-950 p-3">
                        <p className="text-xs text-slate-500">
                          Net electricity (kWh/day)
                        </p>
                        <p className="mt-1 text-lg font-bold">
                          {Number.isFinite(result.e_net_kwh_d)
                            ? result.e_net_kwh_d.toLocaleString("en-IN", {
                                maximumFractionDigits: 2,
                              })
                            : "Not specified"}
                        </p>
                      </div>

                      <div className="rounded-xl bg-slate-950 p-3">
                        <p className="text-xs text-slate-500">Annual cost</p>
                        <p className="mt-1 font-semibold">
                          {money(result.cost_inr_y)}
                        </p>
                      </div>

                      <div className="rounded-xl bg-slate-950 p-3">
                        <p className="text-xs text-slate-500">Annual revenue</p>
                        <p className="mt-1 font-semibold">
                          {money(result.revenue_inr_y)}
                        </p>
                      </div>
                    </div>

                    <div className="mt-5">
                      <div className="flex justify-between gap-3 text-sm">
                        <span className="text-slate-300">
                          Chance of being the best option
                        </span>
                        <span className="font-semibold text-teal-300">
                          {percentage === null
                            ? "Not specified"
                            : `${percentage.toFixed(1)}%`}
                        </span>
                      </div>

                      <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800">
                        <div
                          className="h-full rounded-full bg-teal-500 transition-all"
                          style={{ width: `${percentage ?? 0}%` }}
                        />
                      </div>

                      {result.optimality_note && (
                        <p className="mt-2 text-xs text-slate-500">
                          {result.optimality_note}
                        </p>
                      )}
                    </div>

                    {result.reasons?.length > 0 && (
                      <div className="mt-5">
                        <h4 className="text-sm font-semibold text-slate-200">
                          Reasons
                        </h4>
                        <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-400">
                          {result.reasons.map((reason, index) => (
                            <li key={index}>{reason}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {result.warnings?.length > 0 && (
                      <div className="mt-4 rounded-lg border border-amber-900/70 bg-amber-950/20 p-3">
                        <p className="text-xs font-semibold text-amber-300">
                          Model warnings
                        </p>
                        <ul className="mt-1 list-inside list-disc space-y-1 text-xs text-amber-200/80">
                          {result.warnings.map((warning, index) => (
                            <li key={index}>{warning}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {result.outputs &&
                      Object.keys(result.outputs).length > 0 && (
                        <details className="mt-4">
                          <summary className="cursor-pointer text-sm text-slate-400 hover:text-white">
                            View technical outputs
                          </summary>
                          <dl className="mt-3 space-y-2">
                            {Object.entries(result.outputs).map(
                              ([key, value]) => (
                                <div
                                  key={key}
                                  className="flex justify-between gap-4 border-b border-slate-800 pb-2 text-sm"
                                >
                                  <dt className="break-all text-slate-400">
                                    {key.replaceAll("_", " ")}
                                  </dt>
                                  <dd className="text-right text-slate-200">
                                    {typeof value === "number" &&
                                    Number.isFinite(value)
                                      ? value.toLocaleString("en-IN", {
                                          maximumFractionDigits: 3,
                                        })
                                      : "Not specified"}
                                  </dd>
                                </div>
                              )
                            )}
                          </dl>
                        </details>
                      )}

                    <a
                      href={`/simulator?pathway=${encodeURIComponent(result.pathway)}`}
                      className="mt-5 inline-flex w-full items-center justify-center rounded-xl border border-teal-700 px-4 py-3 text-sm font-semibold text-teal-300 transition hover:bg-teal-950"
                    >
                      Explore this pathway in 3D →
                    </a>
                  </article>
                );
              })}
            </div>

            <p className="mt-6 text-xs leading-5 text-slate-500">
              Results are model-based estimates and depend on input
              assumptions, available parameters, and model coverage. An
              optimality share is shown only when supplied by the backend; it
              is not a guarantee of real-world performance.
            </p>
          </section>
        )}

        {results.length === 0 && !loading && !error && (
          <section className="mt-8 rounded-2xl border border-dashed border-slate-800 p-8 text-center">
            <h2 className="text-lg font-semibold">Ready to compare?</h2>
            <p className="mt-2 text-sm text-slate-400">
              Enter your waste quantity and run the comparison to see the
              available pathway estimates.
            </p>
          </section>
        )}
      </div>
    </main>
  );
}
