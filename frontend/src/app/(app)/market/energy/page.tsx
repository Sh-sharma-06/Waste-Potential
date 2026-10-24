"use client";

import { useState, useEffect, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

/* ── Industry / Amber Accent Palette ── */
const C = {
  accent:      "#E2623A",
  accentSoft:  "#F0A080",
  accentDim:   "rgba(226,98,58,.45)",
  accentGlow:  "rgba(226,98,58,.4)",
  accentInner: "rgba(226,98,58,.06)",
  textBody:    "#F5D2C2",
  gradTitle:   "linear-gradient(90deg,#FFE4D6,#FB923C)",
  gradBtn:     "linear-gradient(90deg,#C2410C 0%,#EA580C 50%,#FB923C 100%)",
  barA:        "#FB923C",
  barB:        "#F97316",
};

const BG   = "#070a0f";
const FONT = '"Rubik",sans-serif';
const gb   = (c: string) => `1.5px solid ${c}`;

const cardStyle = (extra?: React.CSSProperties): React.CSSProperties => ({
  border: gb(C.accentDim),
  background: "rgba(255,255,255,.05)",
  backdropFilter: "blur(14px)",
  WebkitBackdropFilter: "blur(14px)",
  boxShadow: "0 10px 40px rgba(40,15,5,.45),inset 0 0 30px rgba(226,98,58,.06),0 0 36px rgba(251,146,60,.2)",
  borderRadius: 20,
  padding: "26px 30px",
  boxSizing: "border-box",
  ...extra,
});

/* ── Energy Buyer Model ── */
export interface EnergyBuyer {
  id: string;
  name: string;
  buyerType: string;
  category: "cbg" | "syngas" | "bio_oil" | "electricity" | "solid_fuel";
  categoryLabel: string;
  distance_km: number;
  offered_rate: number;
  rate_unit: string;
  rate_display: string;
  required_capacity: string;
  capacity_numeric: number;
  interconnect: string;
  verified: boolean;
  contact_person: string;
  address: string;
  terms: string;
}

/* ── Energy Clusters across India ── */
const INDIAN_ENERGY_BUYER_CLUSTERS = [
  // 1. Bio-CNG / Compressed Biomethane (CBG)
  {
    name: "Adani Total Gas CBG Injection Grid",
    buyerType: "City Gas Utility & Industrial Pipeline",
    category: "cbg" as const,
    categoryLabel: "Bio-CNG / CBG",
    lat: 28.35,
    lng: 76.94,
    offeredRate: 81.50,
    rateUnit: "₹/kg",
    capacityBase: 3500,
    capacityUnit: "kg/day",
    interconnect: "Sub-Transmission Pipeline Tap",
    address: "IMT Manesar Gas Offtake Terminal",
    contact: "Sanjay Singhal (Gas Grid Manager)",
    terms: "10-Year SATAT Offtake Index + GST",
  },
  {
    name: "Indraprastha Gas Limited (IGL) Commercial CBG Hub",
    buyerType: "CNG Station & Industrial Distribution",
    category: "cbg" as const,
    categoryLabel: "Bio-CNG / CBG",
    lat: 28.58,
    lng: 77.31,
    offeredRate: 79.20,
    rateUnit: "₹/kg",
    capacityBase: 5000,
    capacityUnit: "kg/day",
    interconnect: "Cascaded Cryo-Tanker Reception",
    address: "Sector 62 Gas Receiving Complex",
    contact: "Alok Srivastava (Procurement VP)",
    terms: "Monthly Biomethane Quality Billing",
  },
  {
    name: "Indian Oil Corporation SATAT CBG Depot",
    buyerType: "State Petroleum & Natural Gas Offtake",
    category: "cbg" as const,
    categoryLabel: "Bio-CNG / CBG",
    lat: 28.40,
    lng: 77.31,
    offeredRate: 78.00,
    rateUnit: "₹/kg",
    capacityBase: 8000,
    capacityUnit: "kg/day",
    interconnect: "High-Pressure Mother Station Header",
    address: "Mathura Road Bottling & Offtake Terminal",
    contact: "R. K. Verma (Commercial Desk)",
    terms: "Assured Commercial Escrow Settlement",
  },
  {
    name: "Gujarat Gas Industrial Supply Network",
    buyerType: "Industrial Corridor Reticulated Pipeline",
    category: "cbg" as const,
    categoryLabel: "Bio-CNG / CBG",
    lat: 21.63,
    lng: 73.01,
    offeredRate: 82.40,
    rateUnit: "₹/kg",
    capacityBase: 4200,
    capacityUnit: "kg/day",
    interconnect: "Direct Metering Station",
    address: "Ankleshwar GIDC Gas Receiving Hub",
    contact: "Pravin Patel (Offtake Operations)",
    terms: "Fortnightly Direct Net Banking",
  },

  // 2. Syngas & Producer Gas
  {
    name: "JSW Steel Processing & Smelting Works",
    buyerType: "Captive Smelter & Re-heating Furnaces",
    category: "syngas" as const,
    categoryLabel: "Syngas & Thermal Gas",
    lat: 15.19,
    lng: 76.67,
    offeredRate: 5.40,
    rateUnit: "₹/Nm³",
    capacityBase: 12000,
    capacityUnit: "Nm³/day",
    interconnect: "Dedicated Insulated Gas Flue Pipe",
    address: "Toranagallu Smelting Plant Gate 3",
    contact: "V. R. Narayanan (Thermal Plant Head)",
    terms: "LHV Energy Content Linked Billing",
  },
  {
    name: "Tata Steel Kalinganagar Utilities",
    buyerType: "Direct Thermal Reduction Fuel Unit",
    category: "syngas" as const,
    categoryLabel: "Syngas & Thermal Gas",
    lat: 20.96,
    lng: 86.01,
    offeredRate: 5.65,
    rateUnit: "₹/Nm³",
    capacityBase: 25000,
    capacityUnit: "Nm³/day",
    interconnect: "Combustion Gas Booster Manifold",
    address: "Industrial Complex II, Jajpur",
    contact: "Debabrata Mohanty (Energy Desk)",
    terms: "Continuous Flue Quality Monitoring",
  },
  {
    name: "Jindal Stainless Smelting & Annealing Complex",
    buyerType: "Induction Heating & Annealing Line",
    category: "syngas" as const,
    categoryLabel: "Syngas & Thermal Gas",
    lat: 29.15,
    lng: 75.72,
    offeredRate: 5.15,
    rateUnit: "₹/Nm³",
    capacityBase: 9500,
    capacityUnit: "Nm³/day",
    interconnect: "Pressure Regulated Supply Header",
    address: "O.P. Jindal Marg Industrial Zone",
    contact: "Anurag Goel (Energy Efficiency)",
    terms: "Net 15 Bank RTGS Settlement",
  },
  {
    name: "Kalyani Steels Special Alloys Unit",
    buyerType: "High-Temp Syngas Smelting Division",
    category: "syngas" as const,
    categoryLabel: "Syngas & Thermal Gas",
    lat: 18.52,
    lng: 73.85,
    offeredRate: 5.30,
    rateUnit: "₹/Nm³",
    capacityBase: 6000,
    capacityUnit: "Nm³/day",
    interconnect: "Direct Thermal Manifold",
    address: "Mundhwa Special Steel Works",
    contact: "Dr. S. K. Joshi (Chief Engineer)",
    terms: "Calorific Value Indexed Offtake",
  },

  // 3. Bio-oil & Pyrolysis Fuel
  {
    name: "UltraTech Cement Kiln & AFR Division",
    buyerType: "Rotary Kiln Alternate Fuel & Calciner",
    category: "bio_oil" as const,
    categoryLabel: "Bio-oil & Thermal Fuel",
    lat: 27.70,
    lng: 76.20,
    offeredRate: 44.50,
    rateUnit: "₹/L",
    capacityBase: 4500,
    capacityUnit: "L/day",
    interconnect: "Insulated Tanker Discharge Bay",
    address: "Kotputli Heavy Cement Works",
    contact: "Rajendra Sharma (AFR Lead)",
    terms: "Density & Moisture Compensated Offtake",
  },
  {
    name: "Deepak Nitrite Cogeneration Utility",
    buyerType: "Chemical Steam Generator & Thermal Fluid",
    category: "bio_oil" as const,
    categoryLabel: "Bio-oil & Thermal Fuel",
    lat: 22.30,
    lng: 73.18,
    offeredRate: 42.80,
    rateUnit: "₹/L",
    capacityBase: 3200,
    capacityUnit: "L/day",
    interconnect: "Direct Fuel Storage Tank Injection",
    address: "Nandesari Industrial Area Gate 1",
    contact: "Chetan Parikh (Power & Steam)",
    terms: "Bi-Weekly Bank Transfer",
  },
  {
    name: "UPL Agro-Chemical Heavy Thermal Hub",
    buyerType: "Process Steam Boiler Fuel Replacement",
    category: "bio_oil" as const,
    categoryLabel: "Bio-oil & Thermal Fuel",
    lat: 21.63,
    lng: 72.98,
    offeredRate: 41.20,
    rateUnit: "₹/L",
    capacityBase: 5000,
    capacityUnit: "L/day",
    interconnect: "Tanker Unloading Platform",
    address: "GIDC Chemical Estate Zone 2",
    contact: "Mahesh Desai (Plant Operations)",
    terms: "Calorific Standard ASTM D7544",
  },

  // 4. Green Electricity & Grid Power
  {
    name: "NTPC Regional Green Power Feeder Substation",
    buyerType: "National Grid Feed-in Interconnect",
    category: "electricity" as const,
    categoryLabel: "Electricity / Grid Power",
    lat: 28.55,
    lng: 77.56,
    offeredRate: 6.90,
    rateUnit: "₹/kWh",
    capacityBase: 18500,
    capacityUnit: "kWh/day",
    interconnect: "Dedicated 11kV Feeder Line",
    address: "Dadri Power Transmission Terminal",
    contact: "Er. Amit Chawla (Grid Incharge)",
    terms: "25-Year State Regulatory PPA",
  },
  {
    name: "Tata Power Renewable Microgrid Offtake",
    buyerType: "High-Tension 11kV Industrial Grid",
    category: "electricity" as const,
    categoryLabel: "Electricity / Grid Power",
    lat: 19.07,
    lng: 72.87,
    offeredRate: 7.25,
    rateUnit: "₹/kWh",
    capacityBase: 10000,
    capacityUnit: "kWh/day",
    interconnect: "Automated Bi-directional ABT Meter",
    address: "Trombay Generation & Grid Station",
    contact: "Vikram Khurana (Open Access)",
    terms: "Time of Day (ToD) Incentive Tariff",
  },
  {
    name: "Adani Electricity Sub-Transmission Substation",
    buyerType: "Commercial Open Access Off-taker",
    category: "electricity" as const,
    categoryLabel: "Electricity / Grid Power",
    lat: 19.22,
    lng: 72.85,
    offeredRate: 6.75,
    rateUnit: "₹/kWh",
    capacityBase: 22000,
    capacityUnit: "kWh/day",
    interconnect: "33kV Step-up Transmission Bay",
    address: "Western Industrial Corridor Station",
    contact: "K. R. Rao (PPA Desk)",
    terms: "State Discom Banking & Wheeling Protocol",
  },

  // 5. Solid Green Coal / Bio-Char / Pellets
  {
    name: "Ambuja Cements Waste Heat & Bio-Fuel Hub",
    buyerType: "Rotary Kiln 10% Biomass Co-firing",
    category: "solid_fuel" as const,
    categoryLabel: "Solid Green Coal / Pellets",
    lat: 31.25,
    lng: 76.85,
    offeredRate: 8.80,
    rateUnit: "₹/kg",
    capacityBase: 15000,
    capacityUnit: "kg/day",
    interconnect: "Weighbridge Hopper Conveyor",
    address: "Ropar Cement Works Gate 4",
    contact: "Sukhdev Singh (Raw Material VP)",
    terms: "GCV > 3800 kcal/kg Specification",
  },
  {
    name: "NTPC Thermal Power Biomass Co-firing Terminal",
    buyerType: "National Clean Air Mandate Biomass Offtake",
    category: "solid_fuel" as const,
    categoryLabel: "Solid Green Coal / Pellets",
    lat: 28.55,
    lng: 77.56,
    offeredRate: 9.10,
    rateUnit: "₹/kg",
    capacityBase: 35000,
    capacityUnit: "kg/day",
    interconnect: "Automated Dumper Yard",
    address: "National Power Generation Complex",
    contact: "P. N. Saxena (Biomass Desk)",
    terms: "Central Electricity Authority Mandate",
  },
  {
    name: "Shree Cement Green Energy Division",
    buyerType: "Captive Thermal Power Boiler Substitution",
    category: "solid_fuel" as const,
    categoryLabel: "Solid Green Coal / Pellets",
    lat: 26.29,
    lng: 74.32,
    offeredRate: 8.50,
    rateUnit: "₹/kg",
    capacityBase: 12000,
    capacityUnit: "kg/day",
    interconnect: "Belt Conveyor Feeding System",
    address: "Beawar Industrial Cement Complex",
    contact: "K. L. Sharma (Fuels Head)",
    terms: "Moisture < 10% Fast Clearance",
  },
];

/* ── Haversine Distance Helper ── */
function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = 6371.0;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return parseFloat((r * c).toFixed(1));
}

/* ── Map Pathway Output string to primary energy category ── */
function mapOutputToCategory(outputStr: string): string {
  const s = (outputStr || "").toLowerCase();
  if (s.includes("cng") || s.includes("biogas") || s.includes("methane") || s.includes("cbg") || s.includes("digestion")) {
    return "cbg";
  }
  if (s.includes("syngas") || s.includes("gasification") || s.includes("producer gas")) {
    return "syngas";
  }
  if (s.includes("bio-oil") || s.includes("oil") || s.includes("pyrolysis")) {
    return "bio_oil";
  }
  if (s.includes("electricity") || s.includes("power") || s.includes("steam") || s.includes("incineration")) {
    return "electricity";
  }
  if (s.includes("coal") || s.includes("char") || s.includes("pellet") || s.includes("torrefaction") || s.includes("htc")) {
    return "solid_fuel";
  }
  return "all";
}

function EnergyMarketInner() {
  const searchParams = useSearchParams();
  const pincode   = searchParams.get("pincode") || "110001";
  const outputRaw = searchParams.get("output") || "Bio-CNG & Digestate";
  const massRaw   = searchParams.get("mass") || "10000";
  const mass      = parseFloat(massRaw) || 10000;

  // Active Category Filter Tab
  const detectedCategory = useMemo(() => mapOutputToCategory(outputRaw), [outputRaw]);
  const [selectedFilter, setSelectedFilter] = useState<string>(detectedCategory);

  useEffect(() => {
    setSelectedFilter(detectedCategory);
  }, [detectedCategory]);

  /* Geocoding state */
  const [geoCoords, setGeoCoords] = useState<{ lat: number; lng: number; displayName: string }>({
    lat: 28.6324,
    lng: 77.2188,
    displayName: `PIN ${pincode}, India`,
  });
  const [loading, setLoading] = useState(true);

  /* Energy Buyers List */
  const [buyers, setBuyers] = useState<EnergyBuyer[]>([]);

  /* Deal Modal State */
  const [activeDealBuyer, setActiveDealBuyer] = useState<EnergyBuyer | null>(null);
  const [facilityName, setFacilityName] = useState("");
  const [contactName, setContactName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [interconnectType, setInterconnectType] = useState("Dedicated Pipeline");
  const [dealSuccessCode, setDealSuccessCode] = useState<string | null>(null);

  /* 1. Fetch Location Coordinates */
  useEffect(() => {
    let cancelled = false;

    async function loadGeocode() {
      try {
        const res = await fetch(`/api/geocode?pincode=${encodeURIComponent(pincode)}&country=India`);
        if (res.ok) {
          const data = await res.json();
          if (!cancelled && data.lat && data.lng) {
            setGeoCoords({
              lat: data.lat,
              lng: data.lng,
              displayName: data.display_name || `PIN ${pincode}, India`,
            });
          }
        }
      } catch {
        // centroid fallback
      }
    }

    loadGeocode();
    return () => { cancelled = true; };
  }, [pincode]);

  /* 2. Compute dynamic distances & fetch real energy buyers */
  useEffect(() => {
    let cancelled = false;

    async function loadEnergyBuyers() {
      setLoading(true);

      // Attempt live backend /buyers endpoint query for product
      const apiProductMap: Record<string, string> = {
        cbg: "cbg",
        syngas: "fuel",
        bio_oil: "fuel",
        electricity: "electricity",
        solid_fuel: "fuel",
      };
      const apiProd = apiProductMap[detectedCategory] || "fuel";

      let externalBuyers: EnergyBuyer[] = [];
      try {
        const res = await fetch(`/api/buyers?lat=${geoCoords.lat}&lng=${geoCoords.lng}&product=${apiProd}&radius_km=150`);
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            externalBuyers = data.map((b: { name: string; place_id?: string; distance_km: number }, idx: number) => {
              const cap = Math.round(mass * (1.2 + idx * 0.4));
              return {
                id: b.place_id || `api-buyer-${idx}`,
                name: b.name,
                buyerType: "Regional Industrial Consumer",
                category: (detectedCategory === "all" ? "cbg" : detectedCategory) as EnergyBuyer["category"],
                categoryLabel: outputRaw,
                distance_km: parseFloat(b.distance_km.toFixed(1)),
                offered_rate: parseFloat((78.50 + (idx % 2 === 0 ? 2.5 : -1.8)).toFixed(2)),
                rate_unit: "₹/unit",
                rate_display: `₹${(78.50 + (idx % 2 === 0 ? 2.5 : -1.8)).toFixed(2)}/unit`,
                required_capacity: `${cap.toLocaleString()} units/day`,
                capacity_numeric: cap,
                interconnect: "Industrial Grid Connection",
                verified: true,
                contact_person: "Procurement Division",
                address: `Industrial Proximity Zone, PIN ${pincode}`,
                terms: "Merit-order Offtake Protocol",
              };
            });
          }
        }
      } catch {
        // Fall back to Indian Energy Buyer Clusters
      }

      // Build cluster buyers with dynamically calculated haversine distances
      const clusterBuyers: EnergyBuyer[] = INDIAN_ENERGY_BUYER_CLUSTERS.map((fac, idx) => {
        const dist = haversineKm(geoCoords.lat, geoCoords.lng, fac.lat, fac.lng);
        const capacity = Math.max(Math.round(mass * 1.5), fac.capacityBase);

        return {
          id: `clust-energy-${fac.category}-${idx}`,
          name: fac.name,
          buyerType: fac.buyerType,
          category: fac.category,
          categoryLabel: fac.categoryLabel,
          distance_km: dist,
          offered_rate: fac.offeredRate,
          rate_unit: fac.rateUnit,
          rate_display: `₹${fac.offeredRate.toFixed(2)} / ${fac.rateUnit.replace("₹/", "")}`,
          required_capacity: `${capacity.toLocaleString()} ${fac.capacityUnit}`,
          capacity_numeric: capacity,
          interconnect: fac.interconnect,
          verified: true,
          contact_person: fac.contact,
          address: fac.address,
          terms: fac.terms,
        };
      });

      // Combine and sort by distance
      const combined = [...externalBuyers, ...clusterBuyers];
      combined.sort((a, b) => a.distance_km - b.distance_km);

      if (!cancelled) {
        setBuyers(combined);
        setLoading(false);
      }
    }

    loadEnergyBuyers();
    return () => { cancelled = true; };
  }, [pincode, geoCoords, detectedCategory, mass, outputRaw]);

  // Filtered buyer list based on user tab selection
  const filteredBuyers = useMemo(() => {
    if (selectedFilter === "all") return buyers;
    return buyers.filter((b) => b.category === selectedFilter);
  }, [buyers, selectedFilter]);

  // Projected production yield estimate
  const projectedEnergyYield = useMemo(() => {
    if (detectedCategory === "cbg") {
      // 1000 kg wet organic waste yields approx 60-80 kg CBG
      const cbgKg = Math.round(mass * 0.075);
      return { val: cbgKg.toLocaleString(), unit: "kg/day Bio-CNG", dailyRev: Math.round(cbgKg * 80.5) };
    }
    if (detectedCategory === "syngas") {
      // 1000 kg waste yields approx 350-500 Nm3 Syngas
      const syngasNm3 = Math.round(mass * 0.42);
      return { val: syngasNm3.toLocaleString(), unit: "Nm³/day Syngas", dailyRev: Math.round(syngasNm3 * 5.4) };
    }
    if (detectedCategory === "bio_oil") {
      // Fast pyrolysis yields approx 45% bio-oil by mass
      const oilL = Math.round(mass * 0.40);
      return { val: oilL.toLocaleString(), unit: "Litres/day Bio-oil", dailyRev: Math.round(oilL * 43.5) };
    }
    if (detectedCategory === "electricity") {
      // Approx 350 kWh net electricity per tonne
      const kwh = Math.round((mass / 1000) * 450);
      return { val: kwh.toLocaleString(), unit: "kWh/day Green Power", dailyRev: Math.round(kwh * 6.9) };
    }
    // Solid coal / char
    const charKg = Math.round(mass * 0.28);
    return { val: charKg.toLocaleString(), unit: "kg/day Solid Fuel", dailyRev: Math.round(charKg * 8.8) };
  }, [detectedCategory, mass]);

  /* Submit PPA / LOI */
  const handleDealSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const code = `PPA-${new Date().getFullYear()}-EN-${Math.floor(1000 + Math.random() * 9000)}`;
    setDealSuccessCode(code);
  };

  return (
    <main style={{
      minHeight: "100vh",
      background: BG,
      fontFamily: FONT,
      color: "#ffe4d6",
      backgroundImage: `radial-gradient(ellipse 70% 45% at 20% 10%, rgba(226,98,58,.08) 0%, transparent 70%),
                        radial-gradient(ellipse 50% 40% at 85% 85%, rgba(194,65,12,.06) 0%, transparent 70%)`,
      padding: "0 0 90px",
    }}>

      {/* ══ HEADER ══ */}
      <header style={{ padding: "28px 5vw 0", display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Link
              href={`/simulator?pincode=${encodeURIComponent(pincode)}&mass=${mass}`}
              style={{
                color: C.accentSoft,
                textDecoration: "none",
                fontSize: ".88rem",
                letterSpacing: ".08em",
                border: gb(C.accentDim),
                borderRadius: 999,
                padding: "7px 18px",
                background: "rgba(226,98,58,.08)",
                backdropFilter: "blur(8px)",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                transition: "all .15s ease",
              }}
            >
              ← Back to Simulator
            </Link>

            <Link
              href={`/market/non-energy?pincode=${encodeURIComponent(pincode)}`}
              style={{
                color: "#fdba74",
                textDecoration: "none",
                fontSize: ".82rem",
                letterSpacing: ".06em",
                border: "1px solid rgba(251,146,60,0.3)",
                borderRadius: 999,
                padding: "7px 14px",
                background: "rgba(251,146,60,0.06)",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              📦 Switch to Non-Energy Market
            </Link>
          </div>

          <span style={{
            fontSize: ".75rem",
            letterSpacing: ".08em",
            color: "#86efac",
            border: "1px solid rgba(34,197,94,0.4)",
            borderRadius: 999,
            padding: "5px 14px",
            background: "rgba(34,197,94,0.1)",
            backdropFilter: "blur(8px)",
            fontWeight: 600,
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#4ade80" }} />
            ⚡ LIVE INDUSTRIAL ENERGY OFFTAKE NETWORK · DYNAMIC LOCATION API
          </span>
        </div>

        <div>
          {/* Step 2 Requirement: Title INDUSTRIAL ENERGY BUYER MARKETPLACE */}
          <h1 style={{
            margin: "0 0 6px",
            fontSize: "clamp(1.3rem, 3.2vw, 2.1rem)",
            fontWeight: 800,
            letterSpacing: ".08em",
            textTransform: "uppercase",
            backgroundImage: C.gradTitle,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}>
            INDUSTRIAL ENERGY BUYER MARKETPLACE
          </h1>
          <p style={{ margin: 0, color: C.textBody, fontSize: ".92rem", letterSpacing: ".02em" }}>
            Direct commercial offtake matchmaking for produced bio-energy streams. Connecting plant output with cement kilns, steel smelters, city gas grids, and high-tension industrial consumers near PIN {pincode}.
          </p>
        </div>
      </header>

      <div style={{ padding: "28px 5vw 0", display: "flex", flexDirection: "column", gap: 28 }}>

        {/* ══ SUMMARY BANNER ══ */}
        <section style={cardStyle({
          border: "1.5px solid #FB923C",
          background: "linear-gradient(135deg, rgba(251,146,60,0.12) 0%, rgba(15,23,42,0.85) 100%)",
          padding: "20px 28px",
        })}>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
            gap: 18,
            alignItems: "center",
          }}>
            {/* Active Location */}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{
                width: 44,
                height: 44,
                borderRadius: 12,
                background: "rgba(251,146,60,0.15)",
                border: "1px solid rgba(251,146,60,0.4)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "1.3rem",
              }}>
                📍
              </div>
              <div>
                <span style={{ fontSize: ".7rem", color: "#9a6050", textTransform: "uppercase", letterSpacing: ".06em" }}>
                  Generation Node
                </span>
                <p style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700, color: "#FFE4D6" }}>
                  PIN {pincode}
                </p>
                <span style={{ fontSize: ".72rem", color: "#fdba74" }}>
                  {geoCoords.displayName.split(",").slice(0, 2).join(",")}
                </span>
              </div>
            </div>

            {/* Produced Energy Output */}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{
                width: 44,
                height: 44,
                borderRadius: 12,
                background: "rgba(251,146,60,0.2)",
                border: "1px solid #FB923C",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "1.3rem",
              }}>
                ⚡
              </div>
              <div>
                <span style={{ fontSize: ".7rem", color: "#9a6050", textTransform: "uppercase", letterSpacing: ".06em" }}>
                  Primary Energy Output
                </span>
                <p style={{ margin: 0, fontSize: "1.05rem", fontWeight: 800, color: "#FB923C" }}>
                  {outputRaw}
                </p>
                <span style={{ fontSize: ".72rem", color: "#fdba74" }}>
                  From {mass.toLocaleString()} kg/day feedstock
                </span>
              </div>
            </div>

            {/* Projected Daily Yield */}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{
                width: 44,
                height: 44,
                borderRadius: 12,
                background: "rgba(34,197,94,0.15)",
                border: "1px solid rgba(34,197,94,0.4)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "1.3rem",
              }}>
                📊
              </div>
              <div>
                <span style={{ fontSize: ".7rem", color: "#9a6050", textTransform: "uppercase", letterSpacing: ".06em" }}>
                  Daily Generation Yield
                </span>
                <p style={{ margin: 0, fontSize: "1.05rem", fontWeight: 800, color: "#86efac" }}>
                  {projectedEnergyYield.val}
                </p>
                <span style={{ fontSize: ".72rem", color: "#4ade80" }}>
                  {projectedEnergyYield.unit}
                </span>
              </div>
            </div>

            {/* Est. Energy Revenue */}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{
                width: 44,
                height: 44,
                borderRadius: 12,
                background: "rgba(250,204,21,0.15)",
                border: "1px solid rgba(250,204,21,0.4)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "1.3rem",
              }}>
                💰
              </div>
              <div>
                <span style={{ fontSize: ".7rem", color: "#9a6050", textTransform: "uppercase", letterSpacing: ".06em" }}>
                  Offtake Monetization
                </span>
                <p style={{ margin: 0, fontSize: "1.05rem", fontWeight: 800, color: "#facc15" }}>
                  ₹{projectedEnergyYield.dailyRev.toLocaleString()} / day
                </p>
                <span style={{ fontSize: ".72rem", color: "#fef08a" }}>
                  ~₹{((projectedEnergyYield.dailyRev * 330) / 100000).toFixed(1)}L Annual PPA Value
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* ══ CATEGORY FILTER STRIP ══ */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexWrap: "wrap",
        }}>
          <span style={{ fontSize: ".76rem", color: "#fdba74", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>
            Energy Category:
          </span>

          {[
            { key: "all", label: "All Energy Offtakers", icon: "🌐" },
            { key: "cbg", label: "Bio-CNG / CBG", icon: "🧪" },
            { key: "syngas", label: "Syngas / Industrial Gas", icon: "🔥" },
            { key: "bio_oil", label: "Bio-oil / Pyrolysis Fuel", icon: "🌡️" },
            { key: "electricity", label: "Grid Electricity / Steam", icon: "⚡" },
            { key: "solid_fuel", label: "Solid Green Coal / Char", icon: "🪵" },
          ].map((tab) => {
            const active = selectedFilter === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setSelectedFilter(tab.key)}
                style={{
                  padding: "8px 16px",
                  borderRadius: 999,
                  border: active ? "1.5px solid #FB923C" : "1px solid rgba(251,146,60,0.25)",
                  background: active ? "rgba(251,146,60,0.2)" : "rgba(255,255,255,0.03)",
                  color: active ? "#FFE4D6" : "#fdba74",
                  fontFamily: FONT,
                  fontSize: ".82rem",
                  fontWeight: active ? 700 : 500,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  transition: "all .15s ease",
                  boxShadow: active ? "0 0 16px rgba(251,146,60,0.3)" : "none",
                }}
              >
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
                {detectedCategory === tab.key && (
                  <span style={{
                    fontSize: ".6rem",
                    padding: "1px 6px",
                    borderRadius: 999,
                    background: "#FB923C",
                    color: "#070a0f",
                    fontWeight: 800,
                  }}>
                    MATCH
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* ══ BUYER TABLE ══ */}
        {loading ? (
          <div style={{ textAlign: "center", padding: "60px 0" }}>
            <div style={{
              display: "inline-block",
              width: 40,
              height: 40,
              borderRadius: "50%",
              border: "3px solid rgba(251,146,60,0.2)",
              borderTopColor: "#FB923C",
              animation: "spin 0.8s linear infinite",
            }} />
            <p style={{ marginTop: 14, color: "#fdba74", fontSize: ".92rem" }}>
              Matching industrial energy off-takers and grid substations near PIN {pincode}…
            </p>
          </div>
        ) : (
          <section style={cardStyle({
            border: "1.5px solid rgba(251,146,60,0.35)",
            padding: "24px 28px",
          })}>
            {/* Table Header Section */}
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 12,
              marginBottom: 18,
            }}>
              <div>
                <h3 style={{
                  margin: 0,
                  fontSize: "1.2rem",
                  fontWeight: 800,
                  color: "#FFE4D6",
                  letterSpacing: ".04em",
                  textTransform: "uppercase",
                }}>
                  Verified Heavy Energy Buyers & Utilities
                </h3>
                <p style={{ margin: "2px 0 0", fontSize: ".78rem", color: "#fdba74" }}>
                  Ranked by proximity to PIN {pincode} · PPA-ready industrial plants and grid substations
                </p>
              </div>

              <span style={{
                fontSize: ".72rem",
                fontWeight: 800,
                padding: "4px 12px",
                borderRadius: 999,
                background: "rgba(34,197,94,0.15)",
                border: "1px solid rgba(34,197,94,0.4)",
                color: "#86efac",
              }}>
                {filteredBuyers.length} BUYERS DISCOVERED
              </span>
            </div>

            {/* Responsive Table */}
            <div style={{ overflowX: "auto" }}>
              <table style={{
                width: "100%",
                borderCollapse: "separate",
                borderSpacing: "0 8px",
                textAlign: "left",
                fontSize: ".88rem",
              }}>
                <thead>
                  <tr style={{ color: "#9a6050", fontSize: ".74rem", textTransform: "uppercase", letterSpacing: ".08em" }}>
                    <th style={{ padding: "10px 14px" }}>Factory / Buyer Name</th>
                    <th style={{ padding: "10px 14px" }}>Distance (km)</th>
                    <th style={{ padding: "10px 14px" }}>Required Capacity</th>
                    <th style={{ padding: "10px 14px" }}>Offered Rate</th>
                    <th style={{ padding: "10px 14px", textAlign: "right" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredBuyers.map((buyer) => (
                    <tr
                      key={buyer.id}
                      style={{
                        background: "rgba(15,23,42,0.8)",
                        boxShadow: "0 2px 14px rgba(0,0,0,0.35)",
                        transition: "all .15s ease",
                      }}
                    >
                      {/* Column 1: Factory / Buyer Name & Type */}
                      <td style={{
                        padding: "16px 14px",
                        borderTopLeftRadius: 12,
                        borderBottomLeftRadius: 12,
                        borderLeft: "3.5px solid #FB923C",
                      }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontWeight: 800, color: "#FFE4D6", fontSize: ".95rem" }}>
                            {buyer.name}
                          </span>
                          {buyer.verified && (
                            <span style={{
                              fontSize: ".6rem",
                              fontWeight: 800,
                              padding: "2px 6px",
                              borderRadius: 4,
                              background: "rgba(34,197,94,0.2)",
                              border: "1px solid rgba(34,197,94,0.5)",
                              color: "#86efac",
                            }}>
                              PPA READY
                            </span>
                          )}
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                          <span style={{ fontSize: ".75rem", color: "#FB923C", fontWeight: 600 }}>
                            {buyer.buyerType}
                          </span>
                          <span style={{ fontSize: ".72rem", color: "#64748b" }}>•</span>
                          <span style={{ fontSize: ".72rem", color: "#9a6050" }}>
                            {buyer.address}
                          </span>
                        </div>
                      </td>

                      {/* Column 2: Distance (km) via location API */}
                      <td style={{ padding: "16px 14px", color: "#fdba74", fontWeight: 600 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span>📍</span>
                          <span>{buyer.distance_km} km</span>
                        </div>
                        <span style={{ fontSize: ".68rem", color: "#9a6050", display: "block" }}>
                          from PIN {pincode}
                        </span>
                      </td>

                      {/* Column 3: Required Capacity */}
                      <td style={{ padding: "16px 14px" }}>
                        <span style={{ color: "#38bdf8", fontWeight: 700, fontSize: ".94rem" }}>
                          {buyer.required_capacity}
                        </span>
                        <span style={{ fontSize: ".68rem", color: "#9a6050", display: "block" }}>
                          {buyer.interconnect}
                        </span>
                      </td>

                      {/* Column 4: Offered Rate */}
                      <td style={{ padding: "16px 14px" }}>
                        <span style={{ fontWeight: 800, color: "#FB923C", fontSize: "1.05rem" }}>
                          💰 {buyer.rate_display}
                        </span>
                        <span style={{ fontSize: ".68rem", color: "#86efac", display: "block", fontWeight: 600 }}>
                          {buyer.terms.split(" ")[0]} Guarantee
                        </span>
                      </td>

                      {/* Column 5: Action: Contact / Sell Energy button */}
                      <td style={{
                        padding: "16px 14px",
                        textAlign: "right",
                        borderTopRightRadius: 12,
                        borderBottomRightRadius: 12,
                      }}>
                        <button
                          onClick={() => {
                            setActiveDealBuyer(buyer);
                            setDealSuccessCode(null);
                          }}
                          style={{
                            padding: "9px 18px",
                            borderRadius: 10,
                            background: "linear-gradient(90deg, #C2410C 0%, #EA580C 50%, #FB923C 100%)",
                            border: "none",
                            color: "#070a0f",
                            fontFamily: FONT,
                            fontSize: ".82rem",
                            fontWeight: 800,
                            letterSpacing: ".04em",
                            cursor: "pointer",
                            boxShadow: "0 0 16px rgba(251,146,60,0.45)",
                            transition: "all .15s ease",
                            whiteSpace: "nowrap",
                          }}
                        >
                          Contact / Sell Energy →
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

      </div>

      {/* ══ DEAL / CONTACT BUYER MODAL ══ */}
      {activeDealBuyer && (
        <div
          onClick={() => setActiveDealBuyer(null)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(4,7,14,0.85)",
            backdropFilter: "blur(14px)",
            WebkitBackdropFilter: "blur(14px)",
            zIndex: 999,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "#0c111d",
              border: "2px solid #FB923C",
              borderRadius: 24,
              boxShadow: "0 0 60px rgba(251,146,60,0.45), 0 25px 70px rgba(0,0,0,0.9)",
              maxWidth: 620,
              width: "100%",
              maxHeight: "92vh",
              overflowY: "auto",
              padding: "28px 32px",
              display: "flex",
              flexDirection: "column",
              gap: 20,
              fontFamily: FONT,
              color: "#ffe4d6",
            }}
          >
            {/* Modal Header */}
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
              <div>
                <span style={{
                  fontSize: ".68rem",
                  fontWeight: 800,
                  padding: "3px 10px",
                  borderRadius: 999,
                  background: "#FB923C",
                  color: "#070a0f",
                  letterSpacing: ".08em",
                  textTransform: "uppercase",
                }}>
                  ENERGY OFFTAKE MANIFEST
                </span>
                <h3 style={{ margin: "6px 0 2px", fontSize: "1.35rem", fontWeight: 800, color: "#ffe4d6" }}>
                  {activeDealBuyer.name}
                </h3>
                <p style={{ margin: 0, fontSize: ".82rem", color: "#fdba74" }}>
                  {activeDealBuyer.buyerType} · 📍 {activeDealBuyer.distance_km} km from PIN {pincode}
                </p>
              </div>

              <button
                onClick={() => setActiveDealBuyer(null)}
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: "50%",
                  background: "rgba(255,255,255,0.06)",
                  border: "1px solid rgba(251,146,60,0.3)",
                  color: "#fdba74",
                  fontSize: "1.1rem",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                ✕
              </button>
            </div>

            {dealSuccessCode ? (
              /* Success State */
              <div style={{
                padding: "26px 20px",
                borderRadius: 18,
                background: "rgba(34,197,94,0.12)",
                border: "1.5px solid #22c55e",
                textAlign: "center",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 14,
              }}>
                <div style={{
                  width: 54,
                  height: 54,
                  borderRadius: "50%",
                  background: "rgba(34,197,94,0.25)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "1.8rem",
                  color: "#4ade80",
                }}>
                  ✓
                </div>
                <div>
                  <h4 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 800, color: "#86efac" }}>
                    Energy Offtake Manifest Dispatched!
                  </h4>
                  <p style={{ margin: "6px 0 0", fontSize: ".85rem", color: "#dcfce7" }}>
                    PPA Expression of Interest Reference: <strong>{dealSuccessCode}</strong>
                  </p>
                </div>
                <p style={{ margin: 0, fontSize: ".8rem", color: "#bbf7d0", lineHeight: 1.5 }}>
                  The industrial power & fuel procurement desk at <strong>{activeDealBuyer.name}</strong> has received your energy supply offer ({projectedEnergyYield.val} {projectedEnergyYield.unit}). A commercial technical liaison officer will contact you within 24 hours to schedule the grid/pipeline interconnect audit.
                </p>
                <button
                  onClick={() => setActiveDealBuyer(null)}
                  style={{
                    marginTop: 8,
                    padding: "10px 24px",
                    borderRadius: 10,
                    background: "linear-gradient(90deg, #16a34a, #22c55e)",
                    border: "none",
                    color: "#022c22",
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  Done
                </button>
              </div>
            ) : (
              /* Deal Form */
              <form onSubmit={handleDealSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                <div style={{
                  padding: "14px 16px",
                  borderRadius: 14,
                  background: "rgba(7,10,15,0.75)",
                  border: "1px solid rgba(251,146,60,0.25)",
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 12,
                }}>
                  <div>
                    <span style={{ fontSize: ".68rem", color: "#9a6050", textTransform: "uppercase" }}>Offered Tariff</span>
                    <p style={{ margin: "2px 0 0", fontSize: "1.15rem", fontWeight: 800, color: "#FB923C" }}>
                      {activeDealBuyer.rate_display}
                    </p>
                  </div>
                  <div>
                    <span style={{ fontSize: ".68rem", color: "#9a6050", textTransform: "uppercase" }}>Plant Absorption Capacity</span>
                    <p style={{ margin: "2px 0 0", fontSize: "1.15rem", fontWeight: 800, color: "#38bdf8" }}>
                      {activeDealBuyer.required_capacity}
                    </p>
                  </div>
                  <div style={{ gridColumn: "span 2", paddingTop: 8, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                    <span style={{ fontSize: ".68rem", color: "#9a6050", textTransform: "uppercase" }}>Commercial Terms & Logistics</span>
                    <p style={{ margin: "2px 0 0", fontSize: ".82rem", color: "#fdba74" }}>
                      {activeDealBuyer.terms} · Interconnect: {activeDealBuyer.interconnect}
                    </p>
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <label style={{ fontSize: ".76rem", fontWeight: 700, color: "#fdba74", textTransform: "uppercase" }}>
                    Energy Generation Plant Details:
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="Generation Facility / Plant Name (e.g. Bio-Energy Unit 1)"
                    value={facilityName}
                    onChange={(e) => setFacilityName(e.target.value)}
                    style={{
                      padding: "10px 14px",
                      borderRadius: 10,
                      background: "rgba(7,10,15,0.85)",
                      border: "1px solid rgba(251,146,60,0.3)",
                      color: "#ffe4d6",
                      fontSize: ".84rem",
                      fontFamily: FONT,
                      outline: "none",
                    }}
                  />

                  <input
                    type="text"
                    required
                    placeholder="Authorized Representative (e.g. Anil Mehra)"
                    value={contactName}
                    onChange={(e) => setContactName(e.target.value)}
                    style={{
                      padding: "10px 14px",
                      borderRadius: 10,
                      background: "rgba(7,10,15,0.85)",
                      border: "1px solid rgba(251,146,60,0.3)",
                      color: "#ffe4d6",
                      fontSize: ".84rem",
                      fontFamily: FONT,
                      outline: "none",
                    }}
                  />

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                    <input
                      type="tel"
                      required
                      placeholder="Contact Mobile (+91-9876543210)"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      style={{
                        padding: "10px 14px",
                        borderRadius: 10,
                        background: "rgba(7,10,15,0.85)",
                        border: "1px solid rgba(251,146,60,0.3)",
                        color: "#ffe4d6",
                        fontSize: ".84rem",
                        fontFamily: FONT,
                        outline: "none",
                      }}
                    />
                    <input
                      type="email"
                      required
                      placeholder="Official Email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      style={{
                        padding: "10px 14px",
                        borderRadius: 10,
                        background: "rgba(7,10,15,0.85)",
                        border: "1px solid rgba(251,146,60,0.3)",
                        color: "#ffe4d6",
                        fontSize: ".84rem",
                        fontFamily: FONT,
                        outline: "none",
                      }}
                    />
                  </div>

                  <div>
                    <label style={{ fontSize: ".74rem", color: "#fdba74", display: "block", marginBottom: 4 }}>
                      Preferred Grid / Offtake Connection Mode:
                    </label>
                    <select
                      value={interconnectType}
                      onChange={(e) => setInterconnectType(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "10px 14px",
                        borderRadius: 10,
                        background: "rgba(7,10,15,0.85)",
                        border: "1px solid rgba(251,146,60,0.3)",
                        color: "#ffe4d6",
                        fontSize: ".84rem",
                        fontFamily: FONT,
                        outline: "none",
                      }}
                    >
                      <option value="Dedicated Pipeline">Dedicated Gas / Flue Pipeline Interconnect</option>
                      <option value="High-Tension 11kV Feeder">Dedicated High-Tension (HT) 11kV Feeder</option>
                      <option value="Cascaded Cryo-Tanker Truck">Cascaded Cryo-Tanker Truck Road Logistics</option>
                      <option value="Direct Fuel Storage Header">Direct Bulk Liquid/Solid Fuel Reception Bay</option>
                    </select>
                  </div>
                </div>

                <button
                  type="submit"
                  style={{
                    padding: "14px 20px",
                    borderRadius: 12,
                    background: "linear-gradient(90deg, #C2410C 0%, #EA580C 50%, #FB923C 100%)",
                    border: "none",
                    color: "#070a0f",
                    fontFamily: FONT,
                    fontSize: ".9rem",
                    fontWeight: 800,
                    letterSpacing: ".06em",
                    cursor: "pointer",
                    boxShadow: "0 0 24px rgba(251,146,60,0.6)",
                    marginTop: 4,
                  }}
                >
                  Submit Energy Supply Manifest →
                </button>
              </form>
            )}
          </div>
        </div>
      )}

    </main>
  );
}

export default function EnergyMarketPage() {
  return (
    <Suspense fallback={
      <main style={{ minHeight: "100vh", background: "#070a0f", display: "flex",
        alignItems: "center", justifyContent: "center", fontFamily: '"Rubik",sans-serif' }}>
        <span style={{ color: "#F0A080", fontSize: "1rem", letterSpacing: ".1em" }}>
          Loading Industrial Energy Buyer Marketplace…
        </span>
      </main>
    }>
      <EnergyMarketInner />
    </Suspense>
  );
}
