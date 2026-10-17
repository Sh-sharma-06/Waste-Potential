"use client";

/**
 * SimulatorPage — /simulator
 *
 * Renders the simulation input form, calls POST /simulations via the Zustand
 * store, and shows the result summary card.
 *
 * The status badge on the summary card is fully dynamic — it reads
 * `result.status` from the store and delegates all label/style logic to
 * <StatusBadge>.  No hard-coded badge text or colour lives in this file.
 *
 * Status mapping (owned by StatusBadge):
 *   "illustrative_estimate"  →  "Illustrative Estimate"  (blue)
 *   "extrapolation"          →  "Extrapolation"           (amber)
 */

import React, { useId } from "react";
import { useScenarioStore } from "@/stores/scenario";
import { StatusBadge } from "@/components/Simulator/StatusBadge";
import en from "@/i18n/en.json";
import styles from "./SimulatorPage.module.css";

const t = en.simulator;

// ─── Small helpers ────────────────────────────────────────────────────────────

function fmt(n: number, decimals = 1) {
  return Number.isFinite(n) ? n.toFixed(decimals) : "—";
}

function LabelledInput({
  label,
  id,
  type = "number",
  value,
  onChange,
  min,
  max,
  step,
}: {
  label: string;
  id: string;
  type?: string;
  value: string | number;
  onChange: (v: string) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <div className={styles.field}>
      <label className={styles.fieldLabel} htmlFor={id}>
        {label}
      </label>
      <input
        className={styles.fieldInput}
        id={id}
        type={type}
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function SimulatorPage() {
  const { form, result, loading, error, setForm, runSimulation, reset } =
    useScenarioStore();

  // Stable IDs for <label htmlFor>
  const massId = useId();
  const organicId = useId();
  const suitableId = useId();
  const locationId = useId();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void runSimulation();
  };

  return (
    <main className={styles.page}>
      {/* ── Background video (same as SelectionPage) ── */}
      <video
        className={styles.video}
        src="/bg.mp4"
        poster="/poster.jpg"
        autoPlay
        muted
        loop
        playsInline
      />
      <div className={styles.shade} />

      <div className={styles.content}>
        {/* ── Header ── */}
        <header className={styles.header}>
          <h1 className={styles.title}>{t.title}</h1>
          <p className={styles.subtitle}>{t.subtitle}</p>
        </header>

        <div className={styles.layout}>
          {/* ── Input form ── */}
          <section className={styles.formCard} aria-label="Simulation inputs">
            <form onSubmit={handleSubmit}>
              <LabelledInput
                label={t.form.waste_mass_label}
                id={massId}
                value={form.waste_mass_kg_day}
                onChange={(v) =>
                  setForm({ waste_mass_kg_day: parseFloat(v) || 0 })
                }
                min={1}
                max={1_000_000}
                step={100}
              />
              <LabelledInput
                label={t.form.organic_fraction_label}
                id={organicId}
                value={form.organic_fraction}
                onChange={(v) =>
                  setForm({ organic_fraction: parseFloat(v) || 0 })
                }
                min={0}
                max={1}
                step={0.01}
              />
              <LabelledInput
                label={t.form.suitable_fraction_label}
                id={suitableId}
                value={form.suitable_fraction}
                onChange={(v) =>
                  setForm({ suitable_fraction: parseFloat(v) || 0 })
                }
                min={0}
                max={1}
                step={0.01}
              />
              <LabelledInput
                label={t.form.location_label}
                id={locationId}
                type="text"
                value={form.location_id}
                onChange={(v) => setForm({ location_id: v })}
              />

              <div className={styles.actions}>
                <button
                  type="submit"
                  className={styles.btnPrimary}
                  disabled={loading}
                >
                  {loading ? t.form.running_button : t.form.run_button}
                </button>
                {result && (
                  <button
                    type="button"
                    className={styles.btnSecondary}
                    onClick={reset}
                  >
                    {t.form.reset_button}
                  </button>
                )}
              </div>
            </form>
          </section>

          {/* ── Results card ── */}
          {(result || error) && (
            <section
              className={styles.resultsCard}
              aria-label="Simulation results"
            >
              {error && (
                <p className={styles.errorMsg}>
                  {t.errors.api_error}: {error}
                </p>
              )}

              {result && (
                <>
                  {/* ── Dynamic status badge ──────────────────────────────
                   *  result.status is the top-level SimResponse.status field.
                   *  StatusBadge owns all label/colour logic; no hard-coded
                   *  text or class lives here.
                   * ─────────────────────────────────────────────────────── */}
                  <div className={styles.badgeRow}>
                    <StatusBadge status={result.status} />
                  </div>

                  <h2 className={styles.resultsHeading}>{t.results.heading}</h2>

                  <dl className={styles.metrics}>
                    <div className={styles.metric}>
                      <dt className={styles.metricLabel}>
                        {t.results.net_energy}
                      </dt>
                      <dd className={styles.metricValue}>
                        {fmt(result.results.e_net_kwh_d)}{" "}
                        <span className={styles.unit}>
                          {t.results.unit_kwh_d}
                        </span>
                      </dd>
                    </div>

                    <div className={styles.metric}>
                      <dt className={styles.metricLabel}>{t.results.biogas}</dt>
                      <dd className={styles.metricValue}>
                        {fmt(result.results.biogas_nm3_d)}{" "}
                        <span className={styles.unit}>
                          {t.results.unit_nm3_d}
                        </span>
                      </dd>
                    </div>

                    <div className={styles.metric}>
                      <dt className={styles.metricLabel}>
                        {t.results.digester_volume}
                      </dt>
                      <dd className={styles.metricValue}>
                        {fmt(result.results.digester_m3, 0)}{" "}
                        <span className={styles.unit}>{t.results.unit_m3}</span>
                      </dd>
                    </div>
                  </dl>

                  {/* Warnings */}
                  {result.results.warnings.length > 0 && (
                    <ul className={styles.warnings}>
                      {result.results.warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  )}

                  {/* Footer metadata */}
                  <footer className={styles.runMeta}>
                    <span>
                      {t.results.run_id}: <code>{result.id}</code>
                    </span>
                    <span>
                      {t.results.model_version}:{" "}
                      <code>{result.model_version}</code>
                    </span>
                  </footer>
                </>
              )}
            </section>
          )}
        </div>
      </div>
    </main>
  );
}
