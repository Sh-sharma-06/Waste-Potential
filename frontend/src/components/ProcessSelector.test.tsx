import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ProcessSelector, { PROCESSES } from "./ProcessSelector";

describe("ProcessSelector Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders all 7 waste processing methods", () => {
    // Mock global fetch to return recommendation
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/recommend")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ suggested_process: "Pyrolysis" }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ details: "Detailed briefing markdown" }),
      });
    });

    render(
      <ProcessSelector
        location="Bengaluru"
        weight={15}
        weather="28°C sunny"
        duration="standard"
      />
    );

    PROCESSES.forEach(({ name }) => {
      expect(screen.getByRole("heading", { name, level: 3 })).toBeInTheDocument();
    });
    expect(screen.queryByText("Pelletization")).not.toBeInTheDocument();
  });

  it("calls /simulator/recommend on mount and renders ✨ Suggested badge", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/recommend")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ suggested_process: "Anaerobic Digestion" }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ details: "Test briefing" }),
      });
    });
    global.fetch = fetchMock;

    render(
      <ProcessSelector
        location="Bengaluru"
        weight={20}
        weather="Tropical"
        duration="< 24h"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("✨ Suggested")).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/recommend"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          location: "Bengaluru",
          weight: 20,
          category: null,
          pincode: null,
          lat: null,
          lng: null,
          weather: "Tropical",
          duration_pref: "< 24h",
        }),
      })
    );
  });

  it("fetches process details on-demand and caches the result", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/recommend")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ suggested_process: "Pyrolysis" }),
        });
      }
      if (url.includes("/process-details")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              details: "## Technical Pros\n- High bio-oil yield\n- Carbon sequestration",
              target_process: "Pyrolysis",
              suggested_process: "Pyrolysis",
            }),
        });
      }
      return Promise.reject(new Error("Unknown URL"));
    });
    global.fetch = fetchMock;

    render(
      <ProcessSelector
        location="Bengaluru"
        weight={15}
        weather="Sunny"
        duration="Fast"
      />
    );

    // Briefings are cached per suggestion, so let the recommendation settle first
    await waitFor(() => expect(screen.getByText("✨ Suggested")).toBeInTheDocument());

    // Find the Show Details buttons
    const showDetailsButtons = screen.getAllByRole("button", { name: /Show Details/i });
    expect(showDetailsButtons.length).toBe(7);

    // Click Show Details on the first process (Pyrolysis)
    fireEvent.click(showDetailsButtons[0]);

    // Check that explanation markdown appears
    await waitFor(() => {
      expect(screen.getByText("Technical Pros")).toBeInTheDocument();
      expect(screen.getByText(/High bio-oil yield/i)).toBeInTheDocument();
    });

    // Verify /simulator/process-details was called with target_process and suggested_process
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/process-details"),
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"target_process":"Pyrolysis"'),
      })
    );

    const callCountAfterFirstFetch = fetchMock.mock.calls.length;

    // Toggle close
    const hideButton = screen.getByRole("button", { name: /Hide Details/i });
    fireEvent.click(hideButton);

    // Toggle open again - should use detailsCache without firing another network request
    const showAgainButton = screen.getAllByRole("button", { name: /Show Details/i })[0];
    fireEvent.click(showAgainButton);

    await waitFor(() => {
      expect(screen.getByText("Technical Pros")).toBeInTheDocument();
    });

    expect(fetchMock.mock.calls.length).toBe(callCountAfterFirstFetch);
  });

  it("calls onSelectProcess when Select This Process button is clicked", async () => {
    const handleSelect = vi.fn();
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/recommend")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ suggested_process: "Gasification" }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ details: "Gasification analysis" }),
      });
    });

    render(
      <ProcessSelector
        location="Bengaluru"
        weight={50}
        weather="Rainy"
        duration="48h"
        onSelectProcess={handleSelect}
      />
    );

    // Expand details for Gasification (second button)
    const showButtons = screen.getAllByRole("button", { name: /Show Details/i });
    fireEvent.click(showButtons[1]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Select This Process/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Select This Process/i }));
    expect(handleSelect).toHaveBeenCalledWith("gasification");
  });

  it.each([
    "htc",
    "HTC",
    "Hydrothermal Carbonisation (HTC)",
    "Hydrothermal Carbonization",
  ])("highlights the HTC card when the recommendation is %s", async (suggestion) => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ suggested_process: suggestion }),
    });

    const { container } = render(
      <ProcessSelector location="Pune" weight={5} weather="Humid" />
    );

    await waitFor(() => {
      expect(container.querySelector('[data-process-id="htc"][data-suggested]')).not.toBeNull();
    });
    expect(container.querySelectorAll("[data-suggested]").length).toBe(1);
  });

  it("highlights whichever card is selected, including the parent's controlled selection", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ suggested_process: "pyrolysis", details: "Briefing" }),
    });

    const { container, rerender } = render(
      <ProcessSelector location="Pune" weight={5} weather="Humid" selectedProcessId="torrefaction" />
    );
    expect(container.querySelector('[data-process-id="torrefaction"][data-selected]')).not.toBeNull();

    rerender(<ProcessSelector location="Pune" weight={5} weather="Humid" selectedProcessId="htc" />);
    expect(container.querySelector('[data-process-id="htc"][data-selected]')).not.toBeNull();
    expect(container.querySelectorAll("[data-selected]").length).toBe(1);
  });

  it("sends the chosen duration preference with the recommendation request", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ suggested_process: "composting" }),
    });
    global.fetch = fetchMock;

    render(<ProcessSelector location="Pune" weight={5} category="energy" pincode="411001" />);
    await waitFor(() => expect(screen.getByText("✨ Suggested")).toBeInTheDocument());

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "Weeks (2–8 weeks)" } });

    await waitFor(() => {
      const bodies = fetchMock.mock.calls.map((c) => JSON.parse(c[1].body));
      expect(bodies.at(-1)).toMatchObject({
        category: "energy",
        pincode: "411001",
        weather: null,
        duration_pref: "Weeks (2–8 weeks)",
      });
    });
  });
});
