"use client";

import { useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { INDUSTRY_PAGE_BG } from "@/lib/industryTheme";

const FONT = '"Rubik",sans-serif';

function MarketRouterInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const output = searchParams.get("output");
    const breakdown = searchParams.get("breakdown");

    if (output) {
      router.replace(`/market/energy?${searchParams.toString()}`);
    } else if (breakdown) {
      router.replace(`/market/non-energy?${searchParams.toString()}`);
    }
  }, [router, searchParams]);

  const pincode = searchParams.get("pincode") || "110001";
  const queryString = searchParams.toString();
  const querySuffix = queryString ? `?${queryString}` : `?pincode=${pincode}`;

  return (
    <main style={{
      minHeight: "100vh",
      ...INDUSTRY_PAGE_BG,
      fontFamily: FONT,
      color: "#27120A",
      padding: "60px 5vw",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
    }}>
      <div style={{ maxWidth: 840, width: "100%", textAlign: "center" }}>
        <span style={{
          fontSize: ".75rem",
          letterSpacing: ".1em",
          color: "#C2410C",
          border: "1px solid rgba(251,146,60,0.4)",
          borderRadius: 999,
          padding: "6px 16px",
          background: "rgba(251,146,60,0.1)",
          textTransform: "uppercase",
          fontWeight: 700,
          display: "inline-block",
          marginBottom: 16,
        }}>
          Industrial Offtake Portals
        </span>

        <h1 style={{
          fontSize: "clamp(1.8rem, 4vw, 2.8rem)",
          fontWeight: 800,
          letterSpacing: ".04em",
          margin: "0 0 12px",
          backgroundImage: "linear-gradient(90deg,#FFE4D6,#FB923C)",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
        }}>
          SELECT MARKETPLACE
        </h1>
        <p style={{ color: "#431E12", fontSize: "1rem", margin: "0 auto 40px", maxWidth: 580, lineHeight: 1.6 }}>
          Choose what you want to sell.
        </p>

        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 24,
          textAlign: "left",
        }}>
          {/* Energy Marketplace Option */}
          <Link
            href={`/market/energy${querySuffix}`}
            style={{
              textDecoration: "none",
              color: "inherit",
              padding: "32px 28px",
              borderRadius: 20,
              background: "rgba(255,255,255,0.55)",
              border: "1.5px solid rgba(251,146,60,0.4)",
              boxShadow: "0 10px 40px rgba(120,53,15,0.16), 0 0 30px rgba(226,98,58,.08)",
              backdropFilter: "blur(14px)",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              transition: "transform 0.2s ease, border-color 0.2s ease",
            }}
          >
            <div>
              <div style={{
                width: 52,
                height: 52,
                borderRadius: 14,
                background: "rgba(251,146,60,0.2)",
                border: "1px solid #FB923C",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "1.6rem",
                marginBottom: 18,
              }}>
                ⚡
              </div>
              <h3 style={{ margin: "0 0 8px", fontSize: "1.3rem", fontWeight: 800, color: "#27120A" }}>
                Industrial Energy Marketplace
              </h3>
              <p style={{ margin: 0, fontSize: ".86rem", color: "#C2410C", lineHeight: 1.5 }}>
                Sell Bio-CNG, syngas, bio-oil or electricity to nearby industries.
              </p>
            </div>

            <div style={{
              marginTop: 24,
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              color: "#C2410C",
              fontWeight: 800,
              fontSize: ".9rem",
            }}>
              <span>Launch Energy Market</span>
              <span>→</span>
            </div>
          </Link>

          {/* Non-Energy Marketplace Option */}
          <Link
            href={`/market/non-energy${querySuffix}`}
            style={{
              textDecoration: "none",
              color: "inherit",
              padding: "32px 28px",
              borderRadius: 20,
              background: "rgba(255,255,255,0.55)",
              border: "1.5px solid rgba(226,98,58,0.4)",
              boxShadow: "0 10px 40px rgba(120,53,15,0.16), 0 0 30px rgba(226,98,58,.08)",
              backdropFilter: "blur(14px)",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              transition: "transform 0.2s ease, border-color 0.2s ease",
            }}
          >
            <div>
              <div style={{
                width: 52,
                height: 52,
                borderRadius: 14,
                background: "rgba(34,197,94,0.15)",
                border: "1px solid rgba(34,197,94,0.4)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "1.6rem",
                marginBottom: 18,
              }}>
                📦
              </div>
              <h3 style={{ margin: "0 0 8px", fontSize: "1.3rem", fontWeight: 800, color: "#27120A" }}>
                Non-Energy Recoverable Marketplace
              </h3>
              <p style={{ margin: 0, fontSize: ".86rem", color: "#C2410C", lineHeight: 1.5 }}>
                Sell plastic, metal, glass, e-waste and cardboard to recyclers.
              </p>
            </div>

            <div style={{
              marginTop: 24,
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              color: "#15803d",
              fontWeight: 800,
              fontSize: ".9rem",
            }}>
              <span>Launch Recyclables Market</span>
              <span>→</span>
            </div>
          </Link>
        </div>

        <div style={{ marginTop: 40 }}>
          <Link
            href="/explore/industry"
            style={{
              color: "#9A3412",
              textDecoration: "none",
              fontSize: ".88rem",
              letterSpacing: ".06em",
            }}
          >
            ← Return to Industry Exploration Hub
          </Link>
        </div>
      </div>
    </main>
  );
}

export default function MarketDispatcherPage() {
  return (
    <Suspense fallback={
      <main style={{ minHeight: "100vh", ...INDUSTRY_PAGE_BG, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "#9A3412", fontFamily: FONT }}>Loading Marketplace…</span>
      </main>
    }>
      <MarketRouterInner />
    </Suspense>
  );
}
