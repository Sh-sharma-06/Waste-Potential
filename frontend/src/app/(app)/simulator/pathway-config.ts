import { ProcessStage } from "./types";
import { PATHWAY_STAGES, getStagesByPathway } from "./stages-data";

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

export const PATHWAY_NAMES: Record<string, string> = {
  pyrolysis: "Fast Pyrolysis",
  anaerobic_digestion: "Anaerobic Digestion",
  gasification: "High-Temperature Gasification",
  incineration: "Mass Burn Incineration",
  htc: "Hydrothermal Carbonisation (HTC)",
  torrefaction: "Torrefaction & Bio-Coal",
  composting: "Aerobic In-Vessel Composting",
};

export const PATHWAY_CONFIGS: Record<PathwayId, PathwayConfig> = {
  pyrolysis: {
    id: "pyrolysis",
    name: "Fast Pyrolysis",
    displayName: "Fast Pyrolysis",
    stages: PATHWAY_STAGES.pyrolysis,
  },
  anaerobic_digestion: {
    id: "anaerobic_digestion",
    name: "Anaerobic Digestion",
    displayName: "Anaerobic Digestion",
    stages: PATHWAY_STAGES.anaerobic_digestion,
  },
  gasification: {
    id: "gasification",
    name: "Gasification",
    displayName: "High-Temperature Gasification",
    stages: PATHWAY_STAGES.gasification,
  },
  incineration: {
    id: "incineration",
    name: "Incineration / Mass Burn",
    displayName: "Mass Burn Incineration",
    stages: PATHWAY_STAGES.incineration,
  },
  htc: {
    id: "htc",
    name: "Hydrothermal Carbonisation",
    displayName: "Hydrothermal Carbonisation (HTC)",
    stages: PATHWAY_STAGES.htc,
  },
  torrefaction: {
    id: "torrefaction",
    name: "Torrefaction",
    displayName: "Torrefaction & Bio-Coal",
    stages: PATHWAY_STAGES.torrefaction,
  },
  composting: {
    id: "composting",
    name: "Aerobic Composting",
    displayName: "Aerobic In-Vessel Composting",
    stages: PATHWAY_STAGES.composting,
  },
};

export const getStages = (pathwayId: PathwayId | string): ProcessStage[] => {
  return getStagesByPathway(pathwayId as string);
};