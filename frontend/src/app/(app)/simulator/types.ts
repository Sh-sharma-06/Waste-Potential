export interface OperatingConditions {
  temperature: string;
  pressure: string;
  residenceTime: string;
  conversionYield: string;
}

export interface ProcessStage {
  id: string;
  code: string;
  name: string;
  shortName: string;
  category: string;
  position: [number, number, number];
  color: string;
  accentColor: string;
  description: string;
  role: string;
  inputs: string[];
  outputs: string[];
  equipmentHighlights: string[];
  equipmentType?: string;
  subprocessInputs?: string[];
  operatingConditions?: OperatingConditions;
}

