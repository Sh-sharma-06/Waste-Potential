/**
 * Typed API client for the Waste-Potential backend.
 *
 * Base URL is read from NEXT_PUBLIC_API_URL (falls back to the Next.js /api
 * rewrite proxy which forwards to http://localhost:8000).
 *
 * All functions throw an Error with a human-readable message on non-2xx
 * responses, including the raw detail string from the backend where available.
 */

import type { SimRequest, SimResponse, ProcessCatalogEntry } from "./api.d";

const BASE =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL
    ? process.env.NEXT_PUBLIC_API_URL
    : "/api";

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail))
        detail = body.detail.map((e: { msg: string }) => e.msg).join("; ");
    } catch {
      // body was not JSON — keep statusText
    }
    throw new Error(`[${res.status}] ${detail}`);
  }

  return res.json() as Promise<T>;
}

// ─── /simulations ─────────────────────────────────────────────────────────────

/**
 * POST /simulations — run a simulation and receive the full SimResponse.
 *
 * The returned `status` field ("illustrative_estimate" | "extrapolation") is
 * hoisted to the top-level envelope and also present inside `results.status`.
 */
export async function postSimulation(body: SimRequest): Promise<SimResponse> {
  return request<SimResponse>("/simulations", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ─── /runs ────────────────────────────────────────────────────────────────────

export async function getRuns(limit = 20): Promise<SimResponse[]> {
  return request<SimResponse[]>(`/runs?limit=${limit}`);
}

export async function getRun(runId: string): Promise<SimResponse> {
  return request<SimResponse>(`/runs/${encodeURIComponent(runId)}`);
}

// ─── /pathways/catalog/{process_id} ──────────────────────────────────────────

export async function getProcessCatalog(
  processId: string,
  wasteKg: number = 1000
): Promise<ProcessCatalogEntry> {
  return request<ProcessCatalogEntry>(
    `/pathways/catalog/${encodeURIComponent(processId)}?waste_kg=${encodeURIComponent(wasteKg)}`
  );
}
