"use client";

/**
 * StatusBadge
 *
 * Renders a pill-shaped badge driven entirely by the `status` string returned
 * by POST /simulations (SimResponse.status / SimResults.status).
 *
 * Mapping:
 *   "illustrative_estimate"  →  "Illustrative Estimate"   standard blue badge
 *   "extrapolation"          →  "Extrapolation"           amber warning badge
 *   anything else / undefined → "Unknown Status"          neutral grey badge
 *
 * No hard-coded badge text lives in the parent component; this component is the
 * single source of truth for label and visual treatment.
 */

import React from "react";
import styles from "./StatusBadge.module.css";

export type SimStatus =
  | "illustrative_estimate"
  | "extrapolation"
  | (string & Record<never, never>); // allow passthrough of unknown values

interface StatusBadgeProps {
  /** SimResponse.status from the API — may be undefined on first render */
  status: SimStatus | null | undefined;
  className?: string;
}

interface BadgeConfig {
  label: string;
  modifier: "default" | "warning" | "unknown";
}

function resolveConfig(status: SimStatus | null | undefined): BadgeConfig {
  switch (status) {
    case "illustrative_estimate":
      return { label: "Illustrative Estimate", modifier: "default" };
    case "extrapolation":
      return { label: "Extrapolation", modifier: "warning" };
    default:
      return { label: "Unknown Status", modifier: "unknown" };
  }
}

export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const { label, modifier } = resolveConfig(status);
  return (
    <span
      className={`${styles.badge} ${styles[`badge--${modifier}`]} ${className}`}
      role="status"
      aria-label={`Simulation status: ${label}`}
    >
      {label}
    </span>
  );
}
