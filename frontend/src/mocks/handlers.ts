/**
 * MSW (Mock Service Worker) request handlers for development and testing.
 *
 * Intercepts:
 *   POST /api/simulations  — returns a mock SimResponse from simulation.json,
 *                            but echoes back organic_fraction and suitable_fraction
 *                            from the request body so the UI sees its own inputs.
 *   POST /simulations      — same handler, covers when BASE_URL is the bare path.
 */

import { http, HttpResponse } from "msw";
import mockResponse from "./simulation.json";

type SimRequestBody = {
  organic_fraction?: number;
  suitable_fraction?: number;
  waste_mass_kg_day?: number;
};

function buildResponse(body: SimRequestBody) {
  return {
    ...mockResponse,
    inputs: {
      ...mockResponse.inputs,
      organic_fraction: body.organic_fraction ?? mockResponse.inputs.organic_fraction,
      suitable_fraction: body.suitable_fraction ?? mockResponse.inputs.suitable_fraction,
      waste_mass_kg_day: body.waste_mass_kg_day ?? mockResponse.inputs.waste_mass_kg_day,
    },
    // Simulate "extrapolation" when organic_fraction > 0.85 so devs can see both badge states.
    status:
      (body.organic_fraction ?? 0) > 0.85 ? "extrapolation" : "illustrative_estimate",
    results: {
      ...mockResponse.results,
      status:
        (body.organic_fraction ?? 0) > 0.85 ? "extrapolation" : "illustrative_estimate",
    },
  };
}

export const handlers = [
  http.post("/api/simulations", async ({ request }) => {
    const body = (await request.json()) as SimRequestBody;
    return HttpResponse.json(buildResponse(body), { status: 200 });
  }),
  http.post("/simulations", async ({ request }) => {
    const body = (await request.json()) as SimRequestBody;
    return HttpResponse.json(buildResponse(body), { status: 200 });
  }),
];
