import { ProcessStage } from "./types";

export type PathwayId =
  | "anaerobic_digestion"
  | "composting"
  | "incineration"
  | "gasification"
  | "pyrolysis"
  | "htc"
  | "torrefaction";

export interface PathwayConfig {
  id: PathwayId;
  name: string;
  /** Human readable name displayed in selector */
  displayName: string;
  stages: ProcessStage[];
}

export const PATHWAY_CONFIGS: Record<PathwayId, PathwayConfig> = {
  anaerobic_digestion: {
    id: "anaerobic_digestion",
    name: "Anaerobic Digestion",
    displayName: "Anaerobic Digestion",
    stages: [
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
          "Agricultural manures & crop residues",
        ],
        outputs: [
          "Batched raw feedstock stream",
          "Controlled foul-air exhaust to biofilter",
        ],
        equipmentHighlights: [
          "Enclosed hydraulic tipping hopper",
          "Weighbridge & manifest logging",
          "Negative-pressure biofilter air extraction",
        ],
        equipmentType: "waste_receiving",
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
          "Magnetic & mechanical screening feeds",
        ],
        outputs: [
          "Purified organic fraction (<12 mm particle size)",
          "Ferrous and non-ferrous metals for recycling",
          "Inert residual debris for disposal",
        ],
        equipmentHighlights: [
          "Overband cross-belt magnetic separator",
          "Rotary drum trommel screen",
          "Twin-shaft industrial shredder",
        ],
        equipmentType: "sorting",
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
          "pH buffering agents (if necessary)",
        ],
        outputs: [
          "Homogeneous pumpable feedstock slurry (10-15% TS)",
          "Thermally pre-conditioned digester feed",
        ],
        equipmentHighlights: [
          "High-torque vertical paddle agitator",
          "Level and dry-matter density sensors",
          "Heavy-duty progressive cavity feed pump",
        ],
        equipmentType: "mixing_tank",
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
          "Parasitic thermal heating water to maintain temperature",
        ],
        outputs: [
          "Raw biogas (approx. 55-65% CH₄, 35-45% CO₂, trace H₂S)",
          "Degraded biological digestate slurry",
        ],
        equipmentHighlights: [
          "Continuously stirred tank reactor (CSTR)",
          "Flexible double-membrane gasholder dome",
          "Internal heating grid & mechanical draft mixer",
          "Over/under pressure safety relief valve",
        ],
        equipmentType: "anaerobic_digester",
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
          "Activated carbon / desulfurizing media",
        ],
        outputs: [
          "Dry, scrubbed biomethane fuel gas",
          "Acidic condensation effluent (neutralized)",
        ],
        equipmentHighlights: [
          "Biological trickling desulfurization scrubber",
          "Chilled gas condensing demister",
          "Dual lead-lag activated carbon filtration beds",
        ],
        equipmentType: "gas_treatment",
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
          "Engine jacket cooling water loop",
        ],
        outputs: [
          "Renewable electricity (grid export & plant load)",
          "High-grade thermal hot water",
          "Treated, low-emission exhaust flue gas",
        ],
        equipmentHighlights: [
          "Lean-burn reciprocating gas engine & alternator",
          "Acoustic weatherproof container enclosure",
          "Exhaust gas heat recovery exchanger",
          "Synchronous electrical switchgear and inverter",
        ],
        equipmentType: "chp_generator",
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
          "Polymer flocculant conditioning (if required)",
        ],
        outputs: [
          "Dewatered solid organic compost / soil conditioner",
          "Liquid bio-fertilizer rich in ammoniacal nitrogen",
          "Recirculation liquid returned to Stage 03 mixing",
        ],
        equipmentHighlights: [
          "Continuous screw-press or decanter centrifuge",
          "Enclosed solid cake storage bay",
          "Covered liquid digestate storage lagoon",
        ],
        equipmentType: "digestate_output",
      },
    ],
  },
  composting: {
    id: "composting",
    name: "Aerobic Composting",
    displayName: "Aerobic Composting",
    stages: [
      {
        id: "comp-receiving",
        code: "01",
        name: "Feedstock Intake",
        shortName: "Intake",
        category: "Feedstock Ingestion",
        position: [-11.4, 0, 0],
        color: "#94a3b8",
        accentColor: "#38bdf8",
        description:
          "Green waste, agricultural manures, and source-separated organics arrive at the covered intake facility for weighing, physical quality inspection, and bulk contamination sorting.",
        role: "Intake, manifest inspection, and buffering of raw compostable biomass.",
        inputs: [
          "Municipal yard & park trimmings",
          "Food market & commercial food residuals",
          "Livestock bedding manures",
        ],
        outputs: [
          "Gross-sorted compostable feedstock stream",
          "Reject non-compostable packaging & debris",
        ],
        equipmentHighlights: [
          "Enclosed intake tipping hall",
          "Automated weighbridge logger",
          "Overhead dust suppression misting ring",
        ],
        equipmentType: "waste_receiving",
      },
      {
        id: "comp-shred-mix",
        code: "02",
        name: "Shredding & Bulking Mix",
        shortName: "Shredding",
        category: "Mechanical Conditioning",
        position: [-7.6, 0, 0],
        color: "#f59e0b",
        accentColor: "#fbbf24",
        description:
          "Mechanical high-torque shredding fractures fibrous residues, which are blended with coarse carbonaceous bulking agents (woodchips) to establish optimal C:N ratio (25:1-30:1) and internal air porosity.",
        role: "Size reduction and structural blending for aerobic pore space optimization.",
        inputs: [
          "Inspected green & food waste fraction",
          "Recycled woodchips & bark bulking agents",
        ],
        outputs: [
          "Homogeneous high-porosity compost blend",
          "Extracted ferrous contaminants",
        ],
        equipmentHighlights: [
          "Slow-speed high-torque industrial shredder",
          "Overband cross-belt magnet separator",
          "Proportional bulk blending hopper",
        ],
        equipmentType: "sorting",
      },
      {
        id: "comp-aeration-prep",
        code: "03",
        name: "Moisture & Tunnel Feed",
        shortName: "Conditioning",
        category: "Moisture Conditioning",
        position: [-3.8, 0, 0],
        color: "#06b6d4",
        accentColor: "#22d3ee",
        description:
          "Feedstock moisture is analyzed and adjusted with recirculated process leachate to achieve 55-60% moisture content prior to loading into aerated composting tunnels.",
        role: "Moisture balancing and batch loading into positive-aeration vessels.",
        inputs: [
          "Blended structural compost feed",
          "Recirculated compost leachate / process water",
        ],
        outputs: [
          "Moisture-optimized composting substrate (55-60% moisture)",
          "Prepared vessel batch feeds",
        ],
        equipmentHighlights: [
          "Continuous twin-shaft pugmill mixer",
          "Microwave moisture sensor array",
          "Telescopic overhead loading conveyor",
        ],
        equipmentType: "mixing_tank",
      },
      {
        id: "comp-reactor",
        code: "04",
        name: "Aerated Composting Tunnel",
        shortName: "Bio-Tunnel",
        category: "Biological Conversion (Core)",
        position: [0, 0, 0],
        color: "#10b981",
        accentColor: "#2dd4bf",
        description:
          "High-rate thermophilic composting under computer-controlled positive aeration. Microbial metabolism raises internal temperatures to 55-65°C, ensuring rapid organic decomposition and complete pathogen destruction.",
        role: "Intensive aerobic biodegradation and thermal sanitization of compost mass.",
        inputs: [
          "Conditioned moist compost blend",
          "Forced temperature-controlled process air",
        ],
        outputs: [
          "Pathogen-free sanitized compost substrate",
          "Humid warm exhaust air containing CO₂ and ammonia",
        ],
        equipmentHighlights: [
          "Reinforced concrete aerated tunnel vessel",
          "Floor spigot forced-aeration manifold",
          "Multi-point wireless temperature probes",
          "Automated climate control dampers",
        ],
        equipmentType: "anaerobic_digester",
      },
      {
        id: "comp-biofilter",
        code: "05",
        name: "Exhaust Biofiltration",
        shortName: "Biofilter",
        category: "Odor & Emission Control",
        position: [3.8, 0, 0],
        color: "#a855f7",
        accentColor: "#c084fc",
        description:
          "Warm process air from the active composting bays is captured under negative pressure, conditioned through an acid scrubber to remove ammonia, and passed through an organic biofilter bed.",
        role: "Neutralization of process odors, ammonia, and volatile organic compounds (VOCs).",
        inputs: [
          "Foul process air from composting tunnels",
          "Sulfuric acid dosing solution (for ammonia scrubbing)",
          "Humidification spray water",
        ],
        outputs: [
          "Clean, neutralized atmospheric air discharge",
          "Neutralized ammonium sulfate scrubber effluent",
        ],
        equipmentHighlights: [
          "Packed-bed wet chemical ammonia scrubber",
          "Humidification conditioning tower",
          "Root-wood and organic bark biofilter bed",
        ],
        equipmentType: "gas_treatment",
      },
      {
        id: "comp-curing",
        code: "06",
        name: "Curing & Stabilization",
        shortName: "Curing Pad",
        category: "Mesophilic Maturation",
        position: [7.6, 0, 0],
        color: "#f43f5e",
        accentColor: "#fb7185",
        description:
          "Sanitized compost is transferred to aerated curing bays for 4 to 8 weeks. Mesophilic fungi and actinomycetes synthesize complex humic substances, stabilizing carbon and preventing plant phytotoxicity.",
        role: "Secondary curing, humification, and biological stabilization into mature compost.",
        inputs: [
          "Active-phase sanitized compost mass",
          "Controlled ambient aeration",
        ],
        outputs: [
          "Fully matured, dark, crumbly humus-rich compost",
          "Residual process water captured in pad drain",
        ],
        equipmentHighlights: [
          "Self-propelled straddle windrow turner",
          "Covered curing pad with subfloor drainage",
          "Respiration and maturity test sensors (Solvita)",
        ],
        equipmentType: "chp_generator",
      },
      {
        id: "comp-refining",
        code: "07",
        name: "Screening & Refining",
        shortName: "Refining",
        category: "Resource Recovery",
        position: [11.4, 0, 0],
        color: "#84cc16",
        accentColor: "#a3e635",
        description:
          "Mature compost is trommel-screened to separate fine, premium horticultural compost from oversize woodchips (which are recycled as bulking agent) and inert glass/plastic contraries.",
        role: "Classification, contraries separation, and final packaging of certified compost.",
        inputs: [
          "Cured mature compost material",
        ],
        outputs: [
          "High-grade horticultural soil conditioner (<10 mm)",
          "Recycled woodchip bulking fraction (>10 mm)",
          "Fine inert rejects for disposal",
        ],
        equipmentHighlights: [
          "High-speed rotary trommel screen (10 mm)",
          "Air-knife density separator for light plastics",
          "Automated bulk packaging and bagging station",
        ],
        equipmentType: "digestate_output",
      },
    ],
  },
  incineration: {
    id: "incineration",
    name: "Mass-Burn Incineration",
    displayName: "Mass-Burn Incineration",
    stages: [
      {
        id: "inc-bunker",
        code: "01",
        name: "Waste Bunker & Tipping",
        shortName: "Bunker",
        category: "Feedstock Ingestion",
        position: [-11.4, 0, 0],
        color: "#94a3b8",
        accentColor: "#38bdf8",
        description:
          "Municipal waste collection trucks discharge residual waste into an enclosed, negative-pressure storage bunker. Negative air suction directs fugitive dust and odor directly to furnace combustion air.",
        role: "Bulk intake, buffer containment, and draft odor containment of municipal residual waste.",
        inputs: [
          "Mixed municipal solid waste (MSW)",
          "Commercial & industrial non-hazardous residuals",
        ],
        outputs: [
          "Stored waste fuel mass",
          "Negative-pressure primary combustion intake air",
        ],
        equipmentHighlights: [
          "Reinclosed concrete tipping bay with air curtains",
          "Infrared pyrometer automated fire-monitor cannons",
          "Negative-pressure primary air extraction ports",
        ],
        equipmentType: "waste_receiving",
      },
      {
        id: "inc-crane",
        code: "02",
        name: "Waste Crane & Feeding",
        shortName: "Crane Feed",
        category: "Feedstock Handling",
        position: [-7.6, 0, 0],
        color: "#f59e0b",
        accentColor: "#fbbf24",
        description:
          "Semi-automated overhead grab cranes mix and homogenize the waste to smooth out calorific variations, then lift and charge waste into water-cooled feed hoppers.",
        role: "Calorific homogenization, bulk pile mixing, and furnace hopper charging.",
        inputs: [
          "Heterogeneous bunkered MSW",
        ],
        outputs: [
          "Homogenized waste fuel batches metered into feed chute",
        ],
        equipmentHighlights: [
          "Dual hydraulic orange-peel grab cranes (10 m³)",
          "Integrated load cell dynamometer weighing",
          "Water-cooled vertical feed chute with level radar",
        ],
        equipmentType: "sorting",
      },
      {
        id: "inc-feeder",
        code: "03",
        name: "Hydraulic Ram Feeder",
        shortName: "Ram Feeder",
        category: "Fuel Injection",
        position: [-3.8, 0, 0],
        color: "#06b6d4",
        accentColor: "#22d3ee",
        description:
          "Heavy-duty hydraulic pusher rams feed municipal waste forward across water-cooled tables onto the inclined moving grate at precisely regulated volumetric flow rates.",
        role: "Continuous regulated forward displacement and air-seal maintenance into the combustion chamber.",
        inputs: [
          "Solid fuel column from feed chute",
        ],
        outputs: [
          "Uniformly metered fuel bed entering grate drying zone",
        ],
        equipmentHighlights: [
          "Multi-cylinder stepped hydraulic pusher ram",
          "Water-cooled wear-resistant feeding table",
          "Guillotine fire isolation shut-off gate",
        ],
        equipmentType: "mixing_tank",
      },
      {
        id: "inc-grate-boiler",
        code: "04",
        name: "Moving Grate & Boiler",
        shortName: "Grate Boiler",
        category: "Thermal Conversion (Core)",
        position: [0, 0, 0],
        color: "#10b981",
        accentColor: "#2dd4bf",
        description:
          "The core thermal unit. Waste moves through drying, ignition, combustion (850-1050°C, >2s residence time), and burnout zones on stepped grate bars, releasing heat to membrane waterwall tubes generating high-pressure steam.",
        role: "High-temperature mass-burn combustion and superheated steam generation.",
        inputs: [
          "Metered municipal solid waste fuel",
          "Primary preheated underfire combustion air",
          "Secondary high-velocity overfire air jets",
        ],
        outputs: [
          "High-pressure superheated steam (40-60 bar, 400°C)",
          "Vitrified bottom ash clinker discharge",
          "Hot flue gas stream carrying fly ash",
        ],
        equipmentHighlights: [
          "Air-cooled or water-cooled reciprocating moving grate",
          "Four-pass membrane waterwall boiler with radiant furnace",
          "Automated sootblowers & mechanical rapping hammers",
        ],
        equipmentType: "anaerobic_digester",
      },
      {
        id: "inc-fgcs",
        code: "05",
        name: "Flue Gas Cleaning",
        shortName: "Gas Clean",
        category: "Emission Abatement",
        position: [3.8, 0, 0],
        color: "#a855f7",
        accentColor: "#c084fc",
        description:
          "Advanced dry/semi-dry gas scrubbers inject hydrated lime/sodium bicarbonate to neutralize acid gases (HCl, SO₂), activated carbon to capture dioxins and mercury, and pulse-jet fabric baghouses to catch particulates.",
        role: "Acid gas neutralization, heavy metal adsorption, and sub-micron particulate filtration.",
        inputs: [
          "Raw boiler flue gas at 180°C",
          "Hydrated lime / sodium bicarbonate reagent",
          "Powdered activated carbon (PAC)",
        ],
        outputs: [
          "Purified flue gas meeting strict industrial emission limits",
          "Air Pollution Control residues (APCr fly ash)",
        ],
        equipmentHighlights: [
          "Semi-dry atomizing spray dryer absorber",
          "Powdered activated carbon pneumatic dosing skid",
          "Multi-compartment pulse-jet baghouse fabric filter",
          "SNCR ammonia / urea DeNOx injection system",
        ],
        equipmentType: "gas_treatment",
      },
      {
        id: "inc-turbine",
        code: "06",
        name: "Steam Turbine Generator",
        shortName: "Turbine Gen",
        category: "Energy Generation",
        position: [7.6, 0, 0],
        color: "#f43f5e",
        accentColor: "#fb7185",
        description:
          "Superheated steam expands through a multistage axial condensing steam turbine coupled to an electric generator, exporting electricity to the grid and supplying low-pressure steam to district heating networks.",
        role: "Conversion of thermal steam enthalpy into electrical power and district heat.",
        inputs: [
          "High-pressure superheated steam from boiler",
          "Closed-loop cooling water / condenser airflow",
        ],
        outputs: [
          "High-voltage electricity exported to the regional grid",
          "Hot water for municipal district heating networks",
          "Condensed boiler feedwater returned to economizer",
        ],
        equipmentHighlights: [
          "Multistage reaction/impulse axial steam turbine",
          "Brushless synchronous high-voltage generator",
          "Air-cooled condenser (ACC) array & vacuum ejector",
        ],
        equipmentType: "chp_generator",
      },
      {
        id: "inc-ash-recovery",
        code: "07",
        name: "Bottom Ash & Metals Recovery",
        shortName: "Ash Recovery",
        category: "Resource Recovery",
        position: [11.4, 0, 0],
        color: "#84cc16",
        accentColor: "#a3e635",
        description:
          "Water-quenched bottom ash from the grate is dewatered and processed through magnetic and eddy-current separators to recover ferrous and non-ferrous metals (copper, aluminum) before secondary aggregate reuse.",
        role: "Quenching, metal extraction, and mineral aggregate recovery from combustion ash.",
        inputs: [
          "Red-hot grate bottom ash clinker",
          "Ash quench basin cooling water",
        ],
        outputs: [
          "Clean secondary aggregate for road base construction",
          "Recovered ferrous scrap metal for recycling",
          "Recovered aluminum and copper non-ferrous metals",
        ],
        equipmentHighlights: [
          "Water-filled bottom ash submerged scraper conveyor (SSC)",
          "Overband cross-belt neodymium permanent magnet",
          "High-frequency eddy current separator (ECS)",
        ],
        equipmentType: "digestate_output",
      },
    ],
  },
  gasification: {
    id: "gasification",
    name: "Thermochemical Gasification",
    displayName: "Gasification",
    stages: [
      {
        id: "gas-receiving",
        code: "01",
        name: "Biomass Intake & Bunker",
        shortName: "Intake",
        category: "Feedstock Ingestion",
        position: [-11.4, 0, 0],
        color: "#94a3b8",
        accentColor: "#38bdf8",
        description:
          "Clean woody residues, refuse-derived fuel (RDF) pellets, or forestry thinnings arrive at the enclosed intake station for moisture sampling, automated density logging, and storage buffering.",
        role: "Intake, manifest verification, and buffer storage of solid combustible biomass.",
        inputs: [
          "Forestry wood residues & sawmill chips",
          "Refuse-derived fuel (RDF / SRF)",
          "Agricultural nut shells & crop stalks",
        ],
        outputs: [
          "Batched solid biomass fuel stream",
          "Oversize reject fractions",
        ],
        equipmentHighlights: [
          "Enclosed truck tipper platform",
          "Live-bottom push-floor storage bunker",
          "Continuous optical belt weighfeeder",
        ],
        equipmentType: "waste_receiving",
      },
      {
        id: "gas-sorting",
        code: "02",
        name: "Sizing & Tramp Metal Removal",
        shortName: "Sizing",
        category: "Fuel Preparation",
        position: [-7.6, 0, 0],
        color: "#f59e0b",
        accentColor: "#fbbf24",
        description:
          "Rotary disc screens and secondary shredders calibrate fuel particle size to a uniform 10-50 mm specification, while high-intensity magnetic separators extract tramp metals to prevent fluidized bed clinkering.",
        role: "Mechanical size calibration and metallic contaminant extraction.",
        inputs: [
          "Raw bulk woody biomass & RDF",
        ],
        outputs: [
          "Uniformly sized biomass chips (10-50 mm)",
          "Extracted ferrous and tramp metals",
        ],
        equipmentHighlights: [
          "Multi-deck vibrating disc screen",
          "High-speed wood secondary grinder",
          "Neodymium cross-belt tramp magnet",
        ],
        equipmentType: "sorting",
      },
      {
        id: "gas-dryer",
        code: "03",
        name: "Thermal Pre-Drying",
        shortName: "Pre-Dryer",
        category: "Moisture Conditioning",
        position: [-3.8, 0, 0],
        color: "#06b6d4",
        accentColor: "#22d3ee",
        description:
          "Continuous low-temperature belt dryer using recovered engine exhaust heat lowers fuel moisture content from up to 45% down to <15%, ensuring high gasification efficiency and stable syngas calorific value.",
        role: "Thermal moisture reduction to stabilize gasifier thermal balance.",
        inputs: [
          "Sized moist biomass chips (30-45% moisture)",
          "Low-grade engine heat & exhaust heat loop",
        ],
        outputs: [
          "Bone-dry biomass feed (<15% moisture)",
          "Moist low-temperature exhaust air",
        ],
        equipmentHighlights: [
          "Perforated steel continuous belt dryer",
          "Finned-tube water-to-air heat exchangers",
          "Continuous online infrared moisture analyzer",
        ],
        equipmentType: "mixing_tank",
      },
      {
        id: "gas-reactor",
        code: "04",
        name: "Fluidized Bed Gasifier",
        shortName: "Gasifier",
        category: "Thermochemical Conversion (Core)",
        position: [0, 0, 0],
        color: "#10b981",
        accentColor: "#2dd4bf",
        description:
          "The core thermochemical reactor. Under sub-stoichiometric oxygen and steam at 750-900°C, biomass undergoes rapid pyrolysis, partial oxidation, and char reduction to yield energetic synthesis gas (CO, H₂, CH₄).",
        role: "Sub-stoichiometric thermal conversion of solid carbonaceous fuel into combustible syngas.",
        inputs: [
          "Pre-dried biomass fuel pellets/chips",
          "Preheated gasification air / oxygen-enriched blast",
          "Moderating process steam",
        ],
        outputs: [
          "Raw synthesis gas (LHV approx. 4.5-6.5 MJ/Nm³)",
          "Residual bottom char and vitrified bed ash",
        ],
        equipmentHighlights: [
          "Refractory-lined bubbling fluidized bed (BFB) gasifier",
          "Refractory nozzle air-distribution bottom grid",
          "Multi-zone fuel screw injection with nitrogen purge lock",
          "Emergency pressure-relief rupture disc assembly",
        ],
        equipmentType: "anaerobic_digester",
      },
      {
        id: "gas-cleanup",
        code: "05",
        name: "Syngas Cleanup & Tar Cracking",
        shortName: "Syngas Clean",
        category: "Gas Conditioning",
        position: [3.8, 0, 0],
        color: "#a855f7",
        accentColor: "#c084fc",
        description:
          "Raw syngas contains particulates, acidic contaminants, and heavy condensable tars. Cyclones, thermal/catalytic tar reformers, and water quench scrubbers remove tars and particulate ash prior to power generation.",
        role: "Particulate elimination, tar cracking, and gas cooling for engine fuel specification.",
        inputs: [
          "Raw hot synthesis gas leaving gasifier (650°C)",
          "Catalytic reforming agent / active guard bed",
          "Circulating chilled scrubber water loop",
        ],
        outputs: [
          "Cool, dry, tar-free synthesis gas",
          "Condensed bio-tar residue (recycled to gasifier)",
          "Dry particulate char cake",
        ],
        equipmentHighlights: [
          "High-efficiency refractory gas cyclone separator",
          "Catalytic thermal tar-cracking reactor",
          "Venturi gas scrubber & demisting coalescer",
          "Wet electrostatic precipitator (WESP)",
        ],
        equipmentType: "gas_treatment",
      },
      {
        id: "gas-engine",
        code: "06",
        name: "Syngas Engine CHP",
        shortName: "Syngas CHP",
        category: "Energy Cogeneration",
        position: [7.6, 0, 0],
        color: "#f43f5e",
        accentColor: "#fb7185",
        description:
          "Treated synthesis gas is combusted in modified lean-burn spark-ignited reciprocating gas engines or microturbines driving alternators, generating base-load green electricity and high-temperature drying heat.",
        role: "Conversion of clean syngas into electrical power and recuperative process thermal energy.",
        inputs: [
          "Conditioned synthesis gas fuel stream",
          "Filtered turbocharged combustion air",
        ],
        outputs: [
          "Clean base-load electrical power to grid",
          "High-grade exhaust heat fed back to Stage 03 dryer",
          "Treated low-emission combustion exhaust",
        ],
        equipmentHighlights: [
          "Low-BTU lean-burn reciprocating gas engine",
          "High-efficiency synchronous alternator (400V/11kV)",
          "Exhaust shell-and-tube heat recovery steam generator",
        ],
        equipmentType: "chp_generator",
      },
      {
        id: "gas-char",
        code: "07",
        name: "Biochar & Ash Extraction",
        shortName: "Biochar Out",
        category: "Resource Recovery",
        position: [11.4, 0, 0],
        color: "#84cc16",
        accentColor: "#a3e635",
        description:
          "Water-jacketed screw conveyors extract and cool residual solid biochar and inert mineral bed ash. The stable carbon-rich biochar is bagged as an agricultural soil amendment and verified carbon-removal sink.",
        role: "Ash cooling, biochar stabilization, and permanent carbon-removal packaging.",
        inputs: [
          "Hot cyclone char & gasifier bottom bed ash",
          "Indirect cooling water loop",
        ],
        outputs: [
          "Commercial agricultural biochar (high carbon, porous)",
          "Inert bottom bed mineral ash",
        ],
        equipmentHighlights: [
          "Water-jacketed dual cooling screw conveyor",
          "Double-flap nitrogen-sealed rotary discharge valves",
          "Automated dust-free bulk big-bag filling station",
        ],
        equipmentType: "digestate_output",
      },
    ],
  },
  pyrolysis: {
    id: "pyrolysis",
    name: "Fast Pyrolysis",
    displayName: "Fast Pyrolysis",
    stages: [
      {
        id: "pyro-receiving",
        code: "01",
        name: "Biomass Receiving Bay",
        shortName: "Intake",
        category: "Feedstock Ingestion",
        position: [-11.4, 0, 0],
        color: "#94a3b8",
        accentColor: "#38bdf8",
        description:
          "Dedicated enclosed intake for clean forest slash, sawdust, agricultural straw, and nut shells. Material is sampled for initial moisture, ash content, and chemical composition.",
        role: "Unloading, moisture verification, and bulk containment of dry biomass.",
        inputs: [
          "Forestry sawmill sawdust & shavings",
          "Agricultural crop stalks & husks",
          "Dedicated short-rotation woody crops",
        ],
        outputs: [
          "Batched dry-basis biomass feedstock",
          "Coarse foreign rejects",
        ],
        equipmentHighlights: [
          "Covered hydraulic truck tipper ramp",
          "Fully enclosed automated walking floor silo",
          "Continuous microwave moisture sensor",
        ],
        equipmentType: "waste_receiving",
      },
      {
        id: "pyro-milling",
        code: "02",
        name: "Fine Hammer Milling",
        shortName: "Milling",
        category: "Mechanical Micronisation",
        position: [-7.6, 0, 0],
        color: "#f59e0b",
        accentColor: "#fbbf24",
        description:
          "High-speed hammer mills pulverize biomass chips down to micro-particles (<2 mm). Extremely small particle size is strictly required to facilitate the rapid heat-transfer rates (>1000°C/s) essential for fast pyrolysis.",
        role: "Micro-particle sizing to eliminate thermal resistance during flash heating.",
        inputs: [
          "Raw biomass chips & shavings",
        ],
        outputs: [
          "Biomass micro-powder (<2 mm particle size)",
        ],
        equipmentHighlights: [
          "High-speed multi-hammer industrial mill",
          "Precision interchangeable 2 mm perforated screen",
          "Pneumatic pulse-jet collector cyclone & bagfilter",
        ],
        equipmentType: "sorting",
      },
      {
        id: "pyro-dryer",
        code: "03",
        name: "Flash Pneumatic Dryer",
        shortName: "Flash Dryer",
        category: "Thermal Drying",
        position: [-3.8, 0, 0],
        color: "#06b6d4",
        accentColor: "#22d3ee",
        description:
          "Biomass flour is suspended in a vertical stream of hot recycled flue gas in a pneumatic flash dryer, stripping moisture down to <7% in seconds without thermal degradation.",
        role: "Ultra-rapid moisture removal down to below 7% water content.",
        inputs: [
          "Milled biomass flour (15-25% moisture)",
          "Clean hot combustion gas from Stage 06 burner",
        ],
        outputs: [
          "Bone-dry biomass particles (<7% moisture)",
          "Moist exhaust steam to condensing economizer",
        ],
        equipmentHighlights: [
          "Vertical pneumatic entrainment flash drying column",
          "High-velocity gas-solid separation cyclone",
          "Hermetic rotary airlock feeding valve",
        ],
        equipmentType: "mixing_tank",
      },
      {
        id: "pyro-reactor",
        code: "04",
        name: "Fast Pyrolysis Reactor",
        shortName: "Pyrolyzer",
        category: "Thermal Conversion (Core)",
        position: [0, 0, 0],
        color: "#10b981",
        accentColor: "#2dd4bf",
        description:
          "The core flash reactor. Dried biomass is injected into a recirculating fluidized bed of hot sand at 450-520°C in the total absence of oxygen. Vapor residence time is kept under 2 seconds to maximize liquid bio-oil yield.",
        role: "Oxygen-free ultra-fast thermal cracking into condensable pyrolytic vapors and biochar.",
        inputs: [
          "Bone-dry biomass powder (<2 mm, <7% moisture)",
          "Circulating hot silica sand heat carrier (500°C)",
          "Inert nitrogen / recycled gas carrier stream",
        ],
        outputs: [
          "Rich pyrolytic aerosol vapor cloud",
          "Solid fine biochar particles",
          "Cooled circulating sand heat carrier",
        ],
        equipmentHighlights: [
          "Fluidized bed fast pyrolyzer / rotating cone reactor",
          "Ultra-fast water-cooled biomass injection nozzle",
          "Internal refractory lining with sand recirculation loop",
          "Gas-sealed hermetic expansion joints",
        ],
        equipmentType: "anaerobic_digester",
      },
      {
        id: "pyro-quench",
        code: "05",
        name: "Char Cyclone & Spray Quench",
        shortName: "Quench Unit",
        category: "Condensation & Recovery",
        position: [3.8, 0, 0],
        color: "#a855f7",
        accentColor: "#c084fc",
        description:
          "Cyclones rapidly remove solid char particles from the vapor stream, followed immediately by direct spray quench towers that condense hot vapors into dark liquid bio-oil before secondary thermal cracking can occur.",
        role: "Rapid vapor condensation and primary aerosol recovery into liquid bio-oil.",
        inputs: [
          "Hot pyrolytic vapor stream leaving reactor (480°C)",
          "Chilled recirculating bio-oil liquid spray",
        ],
        outputs: [
          "Raw liquid pyrolysis bio-oil (65-75% yield)",
          "Non-condensable pyrolytic combustible gas",
          "Separated fine biochar powder",
        ],
        equipmentHighlights: [
          "Dual series hot gas cyclone separators",
          "Direct contact liquid bio-oil spray condensing tower",
          "Wet electrostatic aerosol precipitator (WESP)",
        ],
        equipmentType: "gas_treatment",
      },
      {
        id: "pyro-combustor",
        code: "06",
        name: "Non-Condensable Gas Burner",
        shortName: "Off-Gas Burner",
        category: "Thermal Integration",
        position: [7.6, 0, 0],
        color: "#f43f5e",
        accentColor: "#fb7185",
        description:
          "The non-condensable pyrolytic off-gas (CO, CO₂, CH₄, H₂) is combusted in a specialized low-NOx swirl burner, providing 100% of the thermal energy needed to reheat the circulating reactor sand and run the flash dryer.",
        role: "Self-sustaining heat loop recycling non-condensable gas into process thermal energy.",
        inputs: [
          "Non-condensable pyrolytic combustible gas",
          "Combustion air with oxygen trim",
          "Portion of char fines (supplementary)",
        ],
        outputs: [
          "High-temperature flue gas heating sand reheater",
          "Process drying heat sent to Stage 03",
        ],
        equipmentHighlights: [
          "Cyclonic low-BTU gas burner chamber",
          "Sand-reheating fluidized bed riser",
          "Flue gas heat recovery recuperator",
        ],
        equipmentType: "chp_generator",
      },
      {
        id: "pyro-oil-storage",
        code: "07",
        name: "Bio-Oil Refining & Packaging",
        shortName: "Bio-Oil Storage",
        category: "Resource Recovery",
        position: [11.4, 0, 0],
        color: "#84cc16",
        accentColor: "#a3e635",
        description:
          "Condensed bio-oil is micro-filtered to remove residual char sub-micron particles, stabilized with alcohol additives, and transferred to insulated stainless steel bulk storage tanks for refinery or boiler use.",
        role: "Filtration, chemical stabilization, and bulk storage of renewable liquid bio-oil.",
        inputs: [
          "Raw condensed bio-oil liquid",
          "Stabilization additives / alcohol modifiers (optional)",
          "Solid biochar from cyclones",
        ],
        outputs: [
          "Refined, stabilized renewable liquid bio-oil (HHV ~17-19 MJ/kg)",
          "Packaged premium pyrogenic biochar",
        ],
        equipmentHighlights: [
          "Automated backwashing duplex filter skid",
          "Nitrogen-blanketed 316L stainless steel storage tanks",
          "Cooling screw and sealed biochar packaging system",
        ],
        equipmentType: "digestate_output",
      },
    ],
  },
  htc: {
    id: "htc",
    name: "Hydrothermal Carbonisation",
    displayName: "Hydrothermal Carbonisation",
    stages: [
      {
        id: "htc-receiving",
        code: "01",
        name: "Wet Sludge Reception",
        shortName: "Sludge Intake",
        category: "Feedstock Ingestion",
        position: [-11.4, 0, 0],
        color: "#94a3b8",
        accentColor: "#38bdf8",
        description:
          "High-moisture organic wastes (65-85% moisture) such as municipal dewatered sewage sludge, spent brewer grains, and digestates arrive directly at sealed covered receiving silos without requiring preliminary drying.",
        role: "Intake, containment, and metering of wet, high-moisture organic slurries.",
        inputs: [
          "Municipal digested & primary sewage sludges",
          "Spent brewer's yeast & brewery grains",
          "Food processing fruit/vegetable pomaces",
        ],
        outputs: [
          "Batched raw wet sludge feed (70-85% moisture)",
          "Enclosed foul air to odor scrubber",
        ],
        equipmentHighlights: [
          "Covered reception pit with hydraulic push-floors",
          "High-torque live-bottom dosing screw augers",
          "Integrated dry solids microwave density sensor",
        ],
        equipmentType: "waste_receiving",
      },
      {
        id: "htc-macerator",
        code: "02",
        name: "Slurry Maceration & De-Stoning",
        shortName: "Macerator",
        category: "Mechanical Homogenisation",
        position: [-7.6, 0, 0],
        color: "#f59e0b",
        accentColor: "#fbbf24",
        description:
          "Heavy-duty inline cutters and gravity stone traps shred fibrous biomass down to <5 mm particle size, protecting high-pressure valves and creating a stable, pumpable colloidal suspension.",
        role: "Contaminant stone rejection and particle micronisation for uniform fluid flow.",
        inputs: [
          "Raw wet organic sludge",
        ],
        outputs: [
          "Micronized fluid slurry (<5 mm particle size)",
          "Extracted stones, gravel, and heavy inert contraries",
        ],
        equipmentHighlights: [
          "Twin-shaft counter-rotating inline macerator",
          "Centrifugal grit & stone trap classifier",
          "Progressive cavity positive-displacement slurry pump",
        ],
        equipmentType: "sorting",
      },
      {
        id: "htc-hp-pump",
        code: "03",
        name: "High-Pressure Injection Pump",
        shortName: "HP Pump",
        category: "Pressurisation",
        position: [-3.8, 0, 0],
        color: "#06b6d4",
        accentColor: "#22d3ee",
        description:
          "Heavy hydraulic piston ram pumps pressurize the slurry up to 25-35 bar, elevating pressure above water's saturation vapor pressure to maintain water strictly in its liquid subcritical state inside the reactor.",
        role: "High-pressure charging to suppress boiling and maintain liquid-phase subcritical conditions.",
        inputs: [
          "Macerated organic slurry at atmospheric pressure",
        ],
        outputs: [
          "High-pressure slurry stream (25-35 bar gauge)",
        ],
        equipmentHighlights: [
          "Dual-cylinder hydraulic piston ram pump",
          "Hardened ceramic ball-check valves",
          "Pulsation dampener nitrogen accumulator bottle",
        ],
        equipmentType: "mixing_tank",
      },
      {
        id: "htc-reactor",
        code: "04",
        name: "Subcritical HTC Autoclave",
        shortName: "HTC Reactor",
        category: "Thermochemical Conversion (Core)",
        position: [0, 0, 0],
        color: "#10b981",
        accentColor: "#2dd4bf",
        description:
          "The core pressurized vessel. At 180-230°C and 20-30 bar, subcritical hot water acts as a reactive non-toxic solvent, catalyzing rapid hydrolysis, dehydration, decarboxylation, and condensation of biopolymers into synthetic coal (hydrochar).",
        role: "Subcritical hydrothermal carbonisation converting wet biopolymers into hydrophobic hydrochar.",
        inputs: [
          "Pressurized organic slurry (25 bar)",
          "Recirculated thermal oil / high-pressure steam heat loop",
        ],
        outputs: [
          "Reacted hydrochar slurry suspension",
          "Minor non-condensable gas fraction (principally CO₂)",
        ],
        equipmentHighlights: [
          "Titanium-clad continuous tubular autoclave reactor",
          "High-pressure thermal oil heat jacket",
          "Internal turbulent static mixing elements",
          "Automated dual safety relief valves & burst discs",
        ],
        equipmentType: "anaerobic_digester",
      },
      {
        id: "htc-flash-recovery",
        code: "05",
        name: "Flash Expansion & Heat Recovery",
        shortName: "Flash Vessel",
        category: "Heat Recovery & Degassing",
        position: [3.8, 0, 0],
        color: "#a855f7",
        accentColor: "#c084fc",
        description:
          "Hot slurry passes through stepped pressure-letdown control valves into flash expansion vessels. Clean flash steam is recovered and routed to pre-heat incoming cold feed slurry, recovering up to 60% of process heat.",
        role: "Depressurisation, degassing of CO₂, and regenerative steam heat recovery.",
        inputs: [
          "Hot reacted hydrochar slurry (210°C, 25 bar)",
        ],
        outputs: [
          "Cooled, depressurized hydrochar slurry (90°C)",
          "Clean flash steam recycled to inlet pre-heaters",
          "Separated biogenic CO₂ off-gas",
        ],
        equipmentHighlights: [
          "Stepped tungsten carbide pressure-reduction valves",
          "Dual-stage cyclonic flash expansion separator",
          "Shell-and-tube regenerative slurry economizer",
        ],
        equipmentType: "gas_treatment",
      },
      {
        id: "htc-filter-press",
        code: "06",
        name: "Membrane Filter Dewatering",
        shortName: "Filter Press",
        category: "Solid-Liquid Dewatering",
        position: [7.6, 0, 0],
        color: "#f43f5e",
        accentColor: "#fb7185",
        description:
          "Because HTC destroys biological water-binding cellular structures, the resulting hydrochar is strongly hydrophobic. High-pressure membrane filter presses dewater the cake to 65-70% dry solids mechanically without thermal evaporative energy.",
        role: "High-pressure mechanical dewatering of hydrophobic hydrochar solids.",
        inputs: [
          "Depressurized hydrochar slurry (15-20% solids)",
          "High-pressure hydraulic squeeze water",
        ],
        outputs: [
          "Dewatered solid hydrochar filter cake (65-70% DS)",
          "Sterile nutrient-rich liquid process water (HTC liquor)",
        ],
        equipmentHighlights: [
          "Automated recessed membrane chamber filter press (16 bar squeeze)",
          "High-pressure core-blow compressed air system",
          "Automatic cake discharge cloth vibrating mechanism",
        ],
        equipmentType: "chp_generator",
      },
      {
        id: "htc-pelleting",
        code: "07",
        name: "Hydrochar Pelleting & Bagging",
        shortName: "Pellet Plant",
        category: "Resource Recovery",
        position: [11.4, 0, 0],
        color: "#84cc16",
        accentColor: "#a3e635",
        description:
          "The dewatered hydrochar cake is granulated and extruded through ring-die pellet mills into hard, dust-free fuel pellets (HHV ~20-24 MJ/kg, comparable to sub-bituminous coal) or premium soil amendment carbon.",
        role: "Extrusion, cooling, and automated bulk packaging of high-energy hydrochar pellets.",
        inputs: [
          "Dewatered hydrochar cake (70% dry solids)",
        ],
        outputs: [
          "Commercial hydrochar fuel pellets (HHV ~22 MJ/kg)",
          "Process water effluent sent to anaerobic wastewater treatment",
        ],
        equipmentHighlights: [
          "Industrial ring-die biomass pellet mill",
          "Counterflow ambient air pellet cooler",
          "Automated dust-tight big-bag packaging station",
        ],
        equipmentType: "digestate_output",
      },
    ],
  },
  torrefaction: {
    id: "torrefaction",
    name: "Torrefaction & Pelletisation",
    displayName: "Torrefaction & Pelletisation",
    stages: [
      {
        id: "torr-receiving",
        code: "01",
        name: "Woody Feedstock Intake",
        shortName: "Intake Bay",
        category: "Feedstock Ingestion",
        position: [-11.4, 0, 0],
        color: "#94a3b8",
        accentColor: "#38bdf8",
        description:
          "Forestry thinnings, logging slash, and sawmill residues arrive at the dry biomass yard. Logs and bulky residues are weighed, moisture-checked, and loaded onto heavy-duty infeed conveyors.",
        role: "Intake, weight verification, and bulk handling of raw woody biomass.",
        inputs: [
          "Forestry logs & branch wood",
          "Sawmill slabwood & woodchip residues",
          "Clean untreated arboricultural waste",
        ],
        outputs: [
          "Batched raw wood infeed flow",
          "Bark and grit reject fraction",
        ],
        equipmentHighlights: [
          "Heavy-duty live-floor intake receiving deck",
          "Automated timber grapple crane",
          "Optical in-line weighfeeder logger",
        ],
        equipmentType: "waste_receiving",
      },
      {
        id: "torr-chipper",
        code: "02",
        name: "Precision Drum Chipping",
        shortName: "Chipping",
        category: "Size Reduction",
        position: [-7.6, 0, 0],
        color: "#f59e0b",
        accentColor: "#fbbf24",
        description:
          "Heavy drum chippers reduce wood to precise 15-30 mm chips, followed by multi-deck star screening to eliminate fines and oversize chunks to assure uniform heat transfer in the torrefier.",
        role: "Precision size calibration and magnetic metal elimination.",
        inputs: [
          "Raw timber and bulk wood residues",
        ],
        outputs: [
          "Calibrated woodchips (15-30 mm)",
          "Separated tramp ferrous metal",
        ],
        equipmentHighlights: [
          "High-capacity industrial drum chipper",
          "Neodymium cross-belt tramp magnet",
          "Multi-deck oscillating star sizing screen",
        ],
        equipmentType: "sorting",
      },
      {
        id: "torr-dryer",
        code: "03",
        name: "Rotary Drum Pre-Dryer",
        shortName: "Pre-Dryer",
        category: "Moisture Conditioning",
        position: [-3.8, 0, 0],
        color: "#06b6d4",
        accentColor: "#22d3ee",
        description:
          "Direct-contact rotary drum dryer lowers woodchip moisture from 40-50% down to <10% using hot recycled flue gas from the torgas combustor, preventing steam dilution in the torrefaction reactor.",
        role: "Thermal moisture reduction down to under 10% water content.",
        inputs: [
          "Fresh woodchips (40-50% moisture)",
          "Hot flue gas from Stage 05 torgas combustor",
        ],
        outputs: [
          "Pre-dried woodchips (<10% moisture)",
          "Moist exhaust gas directed to wet scrubber",
        ],
        equipmentHighlights: [
          "Triple-pass rotary drying drum with internal flights",
          "Discharge separation cyclone collector",
          "Automated spark detection and water quenching system",
        ],
        equipmentType: "mixing_tank",
      },
      {
        id: "torr-reactor",
        code: "04",
        name: "Anoxic Torrefaction Reactor",
        shortName: "Torrefier",
        category: "Thermochemical Conversion (Core)",
        position: [0, 0, 0],
        color: "#10b981",
        accentColor: "#2dd4bf",
        description:
          "The core roasting kiln. Biomass is heated to 250-300°C in an oxygen-free atmosphere. Hemicellulose decomposes, releasing volatile torgas and transforming tough fibrous wood into brittle, hydrophobic, high-energy bio-coal.",
        role: "Mild thermal roasting decomposing hemicellulose to produce hydrophobic bio-coal.",
        inputs: [
          "Pre-dried woodchips (<10% moisture)",
          "Recirculated hot inert process gas loop",
        ],
        outputs: [
          "Torrefied roasted biomass (approx. 70% solid mass yield)",
          "Combustible volatile torgas (acids, CO, CO₂, H₂O)",
        ],
        equipmentHighlights: [
          "Indirectly heated rotary kiln / continuous torrefaction screw",
          "Nitrogen-purged double rotary airlocks",
          "Multi-zone temperature control pyrometers",
          "Oxygen-sensor monitoring (<1% O₂ safety interlock)",
        ],
        equipmentType: "anaerobic_digester",
      },
      {
        id: "torr-torgas-combustor",
        code: "05",
        name: "Torgas Combustor & Loop",
        shortName: "Torgas Burner",
        category: "Thermal Integration",
        position: [3.8, 0, 0],
        color: "#a855f7",
        accentColor: "#c084fc",
        description:
          "Volatile gases released during roasting (torgas: acetic acid, furfurals, CO, CO₂) are burned in a high-efficiency cyclonic combustion chamber at 950°C, supplying 100% of the plant's drying and roasting heat.",
        role: "Autothermal combustion of torrefaction off-gases for complete energy self-sufficiency.",
        inputs: [
          "Hot volatile torgas from torrefaction kiln",
          "Preheated combustion air",
        ],
        outputs: [
          "High-temperature flue gas supplying reactor jacket & dryer",
          "Low-emission clean atmospheric exhaust",
        ],
        equipmentHighlights: [
          "High-temperature cyclonic torgas burner chamber",
          "Hot gas recirculation fan with variable frequency drive",
          "Emergency thermal relief bypass stack",
        ],
        equipmentType: "gas_treatment",
      },
      {
        id: "torr-grinder",
        code: "06",
        name: "Fine Grinding & Conditioning",
        shortName: "Grinder",
        category: "Mechanical Conditioning",
        position: [7.6, 0, 0],
        color: "#f43f5e",
        accentColor: "#fb7185",
        description:
          "Because torrefied wood loses its fibrous plasticity and becomes extremely brittle, grinding energy is cut by 85-90%. Fine pin mills grind the bio-coal into uniform meal and steam conditions it for pelleting.",
        role: "Low-energy pulverisation and conditioning into uniform pelleting meal.",
        inputs: [
          "Cooled torrefied bio-coal chips",
          "Conditioning steam mist (lubricant/binder activation)",
        ],
        outputs: [
          "Uniform torrefied meal ready for die extrusion",
        ],
        equipmentHighlights: [
          "High-efficiency impact pin mill",
          "Inert gas-blanketed pneumatic collection cyclone",
          "Continuous steam-injection conditioning conditioner",
        ],
        equipmentType: "chp_generator",
      },
      {
        id: "torr-pellet-mill",
        code: "07",
        name: "Heavy-Duty Pellet Mill & Cooler",
        shortName: "Pellet Press",
        category: "Resource Recovery",
        position: [11.4, 0, 0],
        color: "#84cc16",
        accentColor: "#a3e635",
        description:
          "Heavy ring-die presses extrude the conditioned meal into dense, black, waterproof torrefied pellets (bulk density >650 kg/m³, HHV ~20-22 MJ/kg), followed by counterflow cooling and silo storage.",
        role: "High-density pellet extrusion, counterflow cooling, and bulk silo storage.",
        inputs: [
          "Conditioned torrefied bio-coal meal",
        ],
        outputs: [
          "Premium torrefied bio-coal pellets (water-resistant, drop-in coal replacement)",
        ],
        equipmentHighlights: [
          "Heavy-duty ring die biomass pellet extrusion press",
          "Counterflow ambient air pellet cooler",
          "Vibrating fines-removal screening deck",
          "Automated weather-protected bulk storage silo",
        ],
        equipmentType: "digestate_output",
      },
    ],
  },
};

export const getStages = (pathwayId: PathwayId): ProcessStage[] => {
  return PATHWAY_CONFIGS[pathwayId]?.stages ?? PATHWAY_CONFIGS.anaerobic_digestion.stages;
};