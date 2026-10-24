"use client";

import { useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

const BG = "#070a0f";
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
      background: BG,
      fontFamily: FONT,
      color: "#ffe4d6",
      backgroundImage: `radial-gradient(ellipse 70% 45% at 20% 10%, rgba(226,98,58,.08) 0%, transparent 70%),
                        radial-gradient(ellipse 50% 40% at 85% 85%, rgba(194,65,12,.06) 0%, transparent 70%)`,
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
          color: "#FB923C",
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
        <p style={{ color: "#F5D2C2", fontSize: "1rem", margin: "0 auto 40px", maxWidth: 580, lineHeight: 1.6 }}>
          Choose your commercial offtake terminal based on whether you are selling produced bio-energy or non-energy recyclable materials.
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
              background: "rgba(255,255,255,0.05)",
              border: "1.5px solid rgba(251,146,60,0.4)",
              boxShadow: "0 10px 40px rgba(40,15,5,.45), 0 0 30px rgba(226,98,58,.08)",
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
              <h3 style={{ margin: "0 0 8px", fontSize: "1.3rem", fontWeight: 800, color: "#FFE4D6" }}>
                Industrial Energy Marketplace
              </h3>
              <p style={{ margin: 0, fontSize: ".86rem", color: "#fdba74", lineHeight: 1.5 }}>
                Direct commercial matching for Bio-CNG, Syngas, Bio-oil, and Green Electricity with cement kilns, steel smelters, and city gas grids.
              </p>
            </div>

            <div style={{
              marginTop: 24,
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              color: "#FB923C",
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
              background: "rgba(255,255,255,0.05)",
              border: "1.5px solid rgba(226,98,58,0.4)",
              boxShadow: "0 10px 40px rgba(40,15,5,.45), 0 0 30px rgba(226,98,58,.08)",
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
              <h3 style={{ margin: "0 0 8px", fontSize: "1.3rem", fontWeight: 800, color: "#FFE4D6" }}>
                Non-Energy Recoverable Marketplace
              </h3>
              <p style={{ margin: 0, fontSize: ".86rem", color: "#fdba74", lineHeight: 1.5 }}>
                Itemized scrap & secondary resource offtake tables for plastics, scrap metals, cullet glass, e-waste, and pulp cardboard.
              </p>
            </div>

            <div style={{
              marginTop: 24,
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              color: "#86efac",
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
              color: "#F0A080",
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
      <main style={{ minHeight: "100vh", background: BG, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "#F0A080", fontFamily: FONT }}>Loading Marketplace…</span>
      </main>
    }>
      <MarketRouterInner />
    </Suspense>
  );
}
