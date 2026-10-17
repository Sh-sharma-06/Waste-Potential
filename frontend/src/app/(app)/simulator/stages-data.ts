import { ProcessStage } from "./types";

export const STAGES: ProcessStage[] = [
  {
    id: "waste-receiving",
    code: "01",
    name: "Waste Receiving",
    shortName: "Receiving",
    category: "Feedstock Ingestion",
    position: [-11.4, 0, 0],
    color: "#94a3b8",
    accentColor: "#38bdf8",
    description:
      "Municipal, commercial, and agricultural organic waste arrives at the enclosed reception bay for weighbridge verification, physical contamination screening, and odor-controlled pit unloading.",
    role: "Intake, gross inspection, and odor-controlled buffering of raw organic waste.",
    inputs: [
      "Source-separated organic waste (SSOW)",
      "Food market residuals & food waste",
      "Agricultural manures & crop residues"
    ],
    outputs: [
      "Batched raw feedstock stream",
      "Controlled foul-air exhaust to biofilter"
    ],
    equipmentHighlights: [
      "Enclosed hydraulic tipping hopper",
      "Weighbridge & manifest logging",
      "Negative-pressure biofilter air extraction"
    ]
  },
  {
    id: "sorting",
    code: "02",
    name: "Sorting",
    shortName: "Sorting",
    category: "Contaminant Removal",
    position: [-7.6, 0, 0],
    color: "#f59e0b",
    accentColor: "#fbbf24",
    description:
      "Automated mechanical and magnetic separators remove non-biodegradable plastics, metals, and inert grit from the feed stream, followed by shredding to optimize surface area for microbial digestion.",
    role: "Separation of contraries and mechanical size reduction of organic material.",
    inputs: [
      "Raw unrefined organic waste",
      "Magnetic & mechanical screening feeds"
    ],
    outputs: [
      "Purified organic fraction (<12 mm particle size)",
      "Ferrous and non-ferrous metals for recycling",
      "Inert residual debris for disposal"
    ],
    equipmentHighlights: [
      "Overband cross-belt magnetic separator",
      "Rotary drum trommel screen",
      "Twin-shaft industrial shredder"
    ]
  },
  {
    id: "mixing-tank",
    code: "03",
    name: "Mixing Tank",
    shortName: "Mixing",
    category: "Slurry Conditioning",
    position: [-3.8, 0, 0],
    color: "#06b6d4",
    accentColor: "#22d3ee",
    description:
      "The shredded organic fraction is blended with recirculated process liquid or dilution water to formulate a pumpable, homogeneous slurry with balanced total solids content and stable pH.",
    role: "Slurry homogenization, moisture balancing, and thermal pre-conditioning.",
    inputs: [
      "Sorted organic pulp",
      "Recirculated digestate centrate / dilution liquid",
      "pH buffering agents (if necessary)"
    ],
    outputs: [
      "Homogeneous pumpable feedstock slurry (10-15% TS)",
      "Thermally pre-conditioned digester feed"
    ],
    equipmentHighlights: [
      "High-torque vertical paddle agitator",
      "Level and dry-matter density sensors",
      "Heavy-duty progressive cavity feed pump"
    ]
  },
  {
    id: "anaerobic-digester",
    code: "04",
    name: "Anaerobic Digester",
    shortName: "Digester",
    category: "Biological Conversion (Core)",
    position: [0, 0, 0],
    color: "#10b981",
    accentColor: "#2dd4bf",
    description:
      "The core reactor of the facility. Under strictly anaerobic (oxygen-free) and heated conditions, specialized microbial consortia break down organic compounds through hydrolysis, acidogenesis, acetogenesis, and methanogenesis to generate raw biogas.",
    role: "Anaerobic biological degradation of volatile solids and production of methane-rich biogas.",
    inputs: [
      "Conditioned organic slurry from mixing tank",
      "Parasitic thermal heating water to maintain temperature"
    ],
    outputs: [
      "Raw biogas (approx. 55-65% CH₄, 35-45% CO₂, trace H₂S)",
      "Degraded biological digestate slurry"
    ],
    equipmentHighlights: [
      "Continuously stirred tank reactor (CSTR)",
      "Flexible double-membrane gasholder dome",
      "Internal heating grid & mechanical draft mixer",
      "Over/under pressure safety relief valve"
    ]
  },
  {
    id: "gas-treatment",
    code: "05",
    name: "Gas Treatment",
    shortName: "Gas Clean",
    category: "Biogas Upgrading",
    position: [3.8, 0, 0],
    color: "#a855f7",
    accentColor: "#c084fc",
    description:
      "Raw biogas leaving the digester is saturated with water vapor and contains corrosive hydrogen sulfide (H₂S) and siloxanes. The gas treatment unit cools, dehydrates, and desulfurizes the gas stream to protect downstream engines.",
    role: "Dehydration, particulate filtration, and sulfur removal for equipment protection.",
    inputs: [
      "Raw saturated biogas from digester dome",
      "Chilled cooling water loop",
      "Activated carbon / desulfurizing media"
    ],
    outputs: [
      "Dry, scrubbed biomethane fuel gas",
      "Acidic condensation effluent (neutralized)"
    ],
    equipmentHighlights: [
      "Biological trickling desulfurization scrubber",
      "Chilled gas condensing demister",
      "Dual lead-lag activated carbon filtration beds"
    ]
  },
  {
    id: "chp-generator",
    code: "06",
    name: "CHP Generator",
    shortName: "CHP Unit",
    category: "Energy Cogeneration",
    position: [7.6, 0, 0],
    color: "#f43f5e",
    accentColor: "#fb7185",
    description:
      "The Combined Heat and Power (CHP) reciprocating gas engine converts clean biogas into electricity for grid export and captures jacket and exhaust heat to warm the digester tanks and support regional heating needs.",
    role: "Simultaneous cogeneration of renewable electricity and reusable high-grade thermal heat.",
    inputs: [
      "Scrubbed biogas fuel line",
      "Combustion air with oxygen sensor trim",
      "Engine jacket cooling water loop"
    ],
    outputs: [
      "Renewable electricity (grid export & plant load)",
      "High-grade thermal hot water",
      "Treated, low-emission exhaust flue gas"
    ],
    equipmentHighlights: [
      "Lean-burn reciprocating gas engine & alternator",
      "Acoustic weatherproof container enclosure",
      "Exhaust gas heat recovery exchanger",
      "Synchronous electrical switchgear and inverter"
    ]
  },
  {
    id: "digestate-output",
    code: "07",
    name: "Digestate Output",
    shortName: "Digestate",
    category: "Resource Recovery",
    position: [11.4, 0, 0],
    color: "#84cc16",
    accentColor: "#a3e635",
    description:
      "The fully digested slurry is separated into dewatered solid bio-fertilizer and liquid nutrient effluent. Both streams are rich in plant-available nitrogen, phosphorus, and organic carbon, creating a complete circular agricultural loop.",
    role: "Mechanical solid-liquid separation and storage of stabilized organic fertilizer.",
    inputs: [
      "Digested slurry discharged from reactor base",
      "Polymer flocculant conditioning (if required)"
    ],
    outputs: [
      "Dewatered solid organic compost / soil conditioner",
      "Liquid bio-fertilizer rich in ammoniacal nitrogen",
      "Recirculation liquid returned to Stage 03 mixing"
    ],
    equipmentHighlights: [
      "Continuous screw-press or decanter centrifuge",
      "Enclosed solid cake storage bay",
      "Covered liquid digestate storage lagoon"
    ]
  }
];
