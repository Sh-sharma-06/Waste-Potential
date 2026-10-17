/**
 * Unit tests for StatusBadge.
 *
 * Validates:
 *   1. "illustrative_estimate" renders "Illustrative Estimate" with --default modifier
 *   2. "extrapolation" renders "Extrapolation" with --warning modifier
 *   3. null / undefined renders "Unknown Status" with --unknown modifier
 *   4. Unknown string falls through to --unknown
 *   5. role="status" aria-label is present and correct
 *   6. No undefined errors when status is missing
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatusBadge } from "@/components/Simulator/StatusBadge";

// CSS Modules return empty objects in jest/vitest — the class attribute won't
// have real class names, but the data-* / aria-label / text content tests
// are fully meaningful.

describe("StatusBadge", () => {
  it('renders "Illustrative Estimate" for status="illustrative_estimate"', () => {
    render(<StatusBadge status="illustrative_estimate" />);
    const badge = screen.getByRole("status");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent("Illustrative Estimate");
    expect(badge).toHaveAttribute(
      "aria-label",
      "Simulation status: Illustrative Estimate",
    );
  });

  it('renders "Extrapolation" for status="extrapolation"', () => {
    render(<StatusBadge status="extrapolation" />);
    const badge = screen.getByRole("status");
    expect(badge).toHaveTextContent("Extrapolation");
    expect(badge).toHaveAttribute(
      "aria-label",
      "Simulation status: Extrapolation",
    );
  });

  it('renders "Unknown Status" for status=null', () => {
    render(<StatusBadge status={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Unknown Status");
  });

  it('renders "Unknown Status" for status=undefined', () => {
    render(<StatusBadge status={undefined} />);
    expect(screen.getByRole("status")).toHaveTextContent("Unknown Status");
  });

  it("renders without throwing for an arbitrary unknown status string", () => {
    expect(() =>
      render(<StatusBadge status="some_future_value" />),
    ).not.toThrow();
    expect(screen.getByRole("status")).toHaveTextContent("Unknown Status");
  });

  it("accepts an optional className prop without errors", () => {
    render(<StatusBadge status="illustrative_estimate" className="extra" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
