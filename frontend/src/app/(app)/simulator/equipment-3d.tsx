"use client";

import React, { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { ProcessStage } from "./types";

interface Equipment3DProps {
  stages: ProcessStage[];
  selectedStage: number;
  onSelectStage: (index: number) => void;
}

// -------------------------------------------------------------
// 1. Waste Receiving Model (Intake hopper, ramp, organic pile)
// -------------------------------------------------------------
function WasteReceivingModel({ selected }: { selected: boolean }) {
  return (
    <group>
      {/* Concrete intake pit foundation */}
      <mesh position={[0, 0.4, 0]} castShadow receiveShadow>
        <boxGeometry args={[2.4, 0.8, 2.2]} />
        <meshStandardMaterial color="#334155" roughness={0.7} metalness={0.2} />
      </mesh>

      {/* Sloped vehicle access ramp */}
      <mesh position={[-1.2, 0.25, 0]} rotation={[0, 0, Math.PI / 12]}>
        <boxGeometry args={[1.0, 0.15, 2.0]} />
        <meshStandardMaterial color="#475569" roughness={0.8} metalness={0.1} />
      </mesh>

      {/* Steel hopper receiving walls */}
      <mesh position={[0.2, 1.0, 0]} castShadow>
        <boxGeometry args={[1.8, 0.7, 1.8]} />
        <meshStandardMaterial color="#1e293b" roughness={0.4} metalness={0.6} />
      </mesh>

      {/* Hopper interior cavity (darker recess) */}
      <mesh position={[0.2, 1.1, 0]}>
        <boxGeometry args={[1.5, 0.55, 1.5]} />
        <meshStandardMaterial color="#0f172a" roughness={0.9} />
      </mesh>

      {/* Organic feedstock cluster inside pit */}
      <group position={[0.2, 1.1, 0]}>
        <mesh position={[-0.3, 0.1, -0.2]}>
          <boxGeometry args={[0.5, 0.4, 0.6]} />
          <meshStandardMaterial color="#65a30d" roughness={0.9} />
        </mesh>
        <mesh position={[0.2, 0.05, 0.2]}>
          <boxGeometry args={[0.6, 0.35, 0.5]} />
          <meshStandardMaterial color="#78350f" roughness={0.95} />
        </mesh>
        <mesh position={[0, 0.15, 0]}>
          <sphereGeometry args={[0.28, 12, 12]} />
          <meshStandardMaterial color="#4d7c0f" roughness={0.9} />
        </mesh>
      </group>

      {/* Yellow / black hazard curb stripe on intake */}
      <mesh position={[-0.8, 0.82, 0]}>
        <boxGeometry args={[0.15, 0.08, 2.1]} />
        <meshStandardMaterial
          color="#f59e0b"
          roughness={0.3}
          metalness={0.5}
          emissive="#78350f"
          emissiveIntensity={selected ? 0.8 : 0.3}
        />
      </mesh>

      {/* Overhead intake dust canopy / suction hood */}
      <mesh position={[0.2, 1.9, 0]}>
        <cylinderGeometry args={[0.9, 1.1, 0.35, 16]} />
        <meshStandardMaterial color="#475569" roughness={0.4} metalness={0.7} />
      </mesh>
      {/* Ventilation duct from canopy */}
      <mesh position={[0.2, 2.2, -0.4]}>
        <cylinderGeometry args={[0.12, 0.12, 0.6, 12]} />
        <meshStandardMaterial color="#64748b" roughness={0.3} metalness={0.8} />
      </mesh>
    </group>
  );
}

// -------------------------------------------------------------
// 2. Sorting Model (Conveyor, magnetic separator, reject bin)
// -------------------------------------------------------------
function SortingModel({ selected }: { selected: boolean }) {
  return (
    <group>
      {/* Support framework legs */}
      <mesh position={[-0.7, 0.5, 0.4]}>
        <cylinderGeometry args={[0.04, 0.04, 1.0, 8]} />
        <meshStandardMaterial color="#64748b" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[-0.7, 0.5, -0.4]}>
        <cylinderGeometry args={[0.04, 0.04, 1.0, 8]} />
        <meshStandardMaterial color="#64748b" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[0.7, 0.7, 0.4]}>
        <cylinderGeometry args={[0.04, 0.04, 1.4, 8]} />
        <meshStandardMaterial color="#64748b" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[0.7, 0.7, -0.4]}>
        <cylinderGeometry args={[0.04, 0.04, 1.4, 8]} />
        <meshStandardMaterial color="#64748b" metalness={0.8} roughness={0.2} />
      </mesh>

      {/* Inclined conveyor belt bed */}
      <group position={[0, 0.85, 0]} rotation={[0, 0, -Math.PI / 16]}>
        <mesh castShadow>
          <boxGeometry args={[1.9, 0.12, 0.9]} />
          <meshStandardMaterial color="#1e293b" metalness={0.4} roughness={0.6} />
        </mesh>
        {/* Conveyor belt surface */}
        <mesh position={[0, 0.08, 0]}>
          <boxGeometry args={[1.85, 0.04, 0.75]} />
          <meshStandardMaterial color="#020617" roughness={0.9} />
        </mesh>
        {/* Conveyor rollers */}
        <mesh position={[-0.9, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.09, 0.09, 0.85, 16]} />
          <meshStandardMaterial color="#94a3b8" metalness={0.9} roughness={0.1} />
        </mesh>
        <mesh position={[0.9, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.09, 0.09, 0.85, 16]} />
          <meshStandardMaterial color="#94a3b8" metalness={0.9} roughness={0.1} />
        </mesh>
      </group>

      {/* Overhead optical & magnetic cross-belt separator */}
      <mesh position={[0, 1.5, 0]} castShadow>
        <boxGeometry args={[0.8, 0.5, 1.1]} />
        <meshStandardMaterial color="#d97706" metalness={0.7} roughness={0.3} />
      </mesh>
      {/* Sensor optical scanner bar */}
      <mesh position={[0, 1.22, 0]}>
        <boxGeometry args={[0.65, 0.05, 0.8]} />
        <meshStandardMaterial
          color="#38bdf8"
          emissive="#0284c7"
          emissiveIntensity={selected ? 1.0 : 0.4}
        />
      </mesh>

      {/* Side reject container for separated plastics/metals */}
      <group position={[0, 0.35, 0.8]}>
        <mesh castShadow>
          <boxGeometry args={[0.7, 0.65, 0.55]} />
          <meshStandardMaterial color="#b45309" roughness={0.6} metalness={0.4} />
        </mesh>
        <mesh position={[0, 0.28, 0]}>
          <boxGeometry args={[0.6, 0.2, 0.45]} />
          <meshStandardMaterial color="#475569" roughness={0.8} />
        </mesh>
      </group>
    </group>
  );
}

// -------------------------------------------------------------
// 3. Mixing Tank Model (Vertical vessel, agitator motor, piping)
// -------------------------------------------------------------
function MixingTankModel({ selected }: { selected: boolean }) {
  return (
    <group>
      {/* Base ring foundation */}
      <mesh position={[0, 0.15, 0]}>
        <cylinderGeometry args={[1.15, 1.25, 0.3, 32]} />
        <meshStandardMaterial color="#334155" metalness={0.4} roughness={0.6} />
      </mesh>

      {/* Cylindrical insulated mixing vessel */}
      <mesh position={[0, 1.15, 0]} castShadow>
        <cylinderGeometry args={[1.05, 1.05, 1.7, 32]} />
        <meshStandardMaterial color="#0891b2" metalness={0.5} roughness={0.3} />
      </mesh>

      {/* Stainless reinforcement rings around tank */}
      <mesh position={[0, 0.6, 0]}>
        <cylinderGeometry args={[1.08, 1.08, 0.06, 32]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
      </mesh>
      <mesh position={[0, 1.2, 0]}>
        <cylinderGeometry args={[1.08, 1.08, 0.06, 32]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
      </mesh>
      <mesh position={[0, 1.8, 0]}>
        <cylinderGeometry args={[1.08, 1.08, 0.06, 32]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
      </mesh>

      {/* Top vessel cover dome */}
      <mesh position={[0, 2.05, 0]}>
        <cylinderGeometry args={[0.9, 1.05, 0.2, 32]} />
        <meshStandardMaterial color="#164e63" metalness={0.6} roughness={0.3} />
      </mesh>

      {/* Top-mounted agitator electric motor & gearbox */}
      <mesh position={[0, 2.35, 0]}>
        <cylinderGeometry args={[0.3, 0.35, 0.45, 16]} />
        <meshStandardMaterial color="#0f172a" metalness={0.7} roughness={0.3} />
      </mesh>
      <mesh position={[0, 2.65, 0]}>
        <cylinderGeometry args={[0.15, 0.15, 0.2, 16]} />
        <meshStandardMaterial color="#0284c7" metalness={0.5} roughness={0.4} />
      </mesh>

      {/* Liquid level sight glass strip on front */}
      <mesh position={[0, 1.2, 1.06]}>
        <boxGeometry args={[0.08, 1.1, 0.04]} />
        <meshStandardMaterial
          color="#38bdf8"
          emissive="#06b6d4"
          emissiveIntensity={selected ? 1.0 : 0.4}
          roughness={0.1}
        />
      </mesh>

      {/* Water / dilution dosing line entering top */}
      <mesh position={[0.6, 2.2, 0]} rotation={[0, 0, Math.PI / 4]}>
        <cylinderGeometry args={[0.06, 0.06, 0.5, 12]} />
        <meshStandardMaterial color="#94a3b8" metalness={0.8} roughness={0.2} />
      </mesh>
    </group>
  );
}

// -------------------------------------------------------------
// 4. Anaerobic Digester Model (CENTERPIECE HERO)
// -------------------------------------------------------------
function DigesterModel({ selected }: { selected: boolean }) {
  const portalRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (portalRef.current) {
      const t = state.clock.getElapsedTime();
      const intensity = 0.5 + Math.sin(t * 2.5) * 0.25;
      (portalRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity =
        selected ? intensity * 1.5 : intensity;
    }
  });

  return (
    <group>
      {/* Heavy circular concrete foundation */}
      <mesh position={[0, 0.2, 0]} receiveShadow>
        <cylinderGeometry args={[1.8, 1.95, 0.4, 40]} />
        <meshStandardMaterial color="#1e293b" roughness={0.8} metalness={0.2} />
      </mesh>

      {/* Foundation perimeter accent ring */}
      <mesh position={[0, 0.38, 0]}>
        <cylinderGeometry args={[1.85, 1.85, 0.05, 40]} />
        <meshStandardMaterial
          color="#10b981"
          emissive="#059669"
          emissiveIntensity={selected ? 1.2 : 0.5}
        />
      </mesh>

      {/* Main digester reactor cylinder */}
      <mesh position={[0, 1.35, 0]} castShadow>
        <cylinderGeometry args={[1.7, 1.7, 1.9, 40]} />
        <meshStandardMaterial color="#0f766e" metalness={0.4} roughness={0.35} />
      </mesh>

      {/* Architectural vertical ribs / reinforcement seams */}
      {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => {
        const angle = (i * Math.PI) / 4;
        const x = Math.cos(angle) * 1.71;
        const z = Math.sin(angle) * 1.71;
        return (
          <mesh key={i} position={[x, 1.35, z]}>
            <boxGeometry args={[0.06, 1.9, 0.06]} />
            <meshStandardMaterial color="#042f2e" metalness={0.8} roughness={0.2} />
          </mesh>
        );
      })}

      {/* Circumferential inspection gallery walkway */}
      <mesh position={[0, 2.15, 0]}>
        <cylinderGeometry args={[1.9, 1.9, 0.08, 40]} />
        <meshStandardMaterial color="#334155" metalness={0.8} roughness={0.2} />
      </mesh>
      {/* Walkway safety railing */}
      <mesh position={[0, 2.35, 0]}>
        <cylinderGeometry args={[1.88, 1.88, 0.3, 40, 1, true]} />
        <meshStandardMaterial
          color="#64748b"
          metalness={0.8}
          roughness={0.2}
          wireframe
        />
      </mesh>

      {/* Double-membrane gas holder hemispherical dome */}
      <mesh position={[0, 2.3, 0]} castShadow>
        <sphereGeometry args={[1.68, 36, 18, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial
          color="#14b8a6"
          metalness={0.3}
          roughness={0.25}
          emissive="#0f766e"
          emissiveIntensity={selected ? 0.6 : 0.25}
        />
      </mesh>

      {/* Top gas collection turret & safety pressure relief valve */}
      <mesh position={[0, 3.2, 0]}>
        <cylinderGeometry args={[0.3, 0.35, 0.3, 20]} />
        <meshStandardMaterial color="#334155" metalness={0.9} roughness={0.1} />
      </mesh>
      <mesh position={[0, 3.42, 0]}>
        <cylinderGeometry args={[0.12, 0.12, 0.25, 16]} />
        <meshStandardMaterial color="#f59e0b" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[0, 3.58, 0]}>
        <sphereGeometry args={[0.14, 16, 16]} />
        <meshStandardMaterial
          color="#e11d48"
          emissive="#be123c"
          emissiveIntensity={selected ? 1.0 : 0.4}
        />
      </mesh>

      {/* Front biological viewing window / microbial activity portal */}
      <mesh ref={portalRef} position={[0, 1.35, 1.71]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.32, 0.32, 0.08, 24]} />
        <meshStandardMaterial
          color="#34d399"
          emissive="#10b981"
          emissiveIntensity={0.8}
          roughness={0.1}
        />
      </mesh>
      {/* Portal bezel frame */}
      <mesh position={[0, 1.35, 1.73]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.33, 0.05, 12, 32]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
      </mesh>
    </group>
  );
}

// -------------------------------------------------------------
// 5. Gas Treatment Model (Dual scrubber towers, filter vessels)
// -------------------------------------------------------------
function GasTreatmentModel({ selected }: { selected: boolean }) {
  return (
    <group>
      {/* Heavy equipment skid platform */}
      <mesh position={[0, 0.15, 0]} castShadow>
        <boxGeometry args={[2.0, 0.3, 1.8]} />
        <meshStandardMaterial color="#1e293b" roughness={0.6} metalness={0.5} />
      </mesh>

      {/* Primary biological desulfurization scrubber column */}
      <group position={[-0.5, 0, 0]}>
        <mesh position={[0, 1.1, 0]} castShadow>
          <cylinderGeometry args={[0.42, 0.42, 1.7, 24]} />
          <meshStandardMaterial color="#7c3aed" metalness={0.6} roughness={0.25} />
        </mesh>
        <mesh position={[0, 2.0, 0]}>
          <sphereGeometry args={[0.42, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <meshStandardMaterial color="#6d28d9" metalness={0.7} roughness={0.2} />
        </mesh>
        <mesh position={[0, 0.8, 0.43]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.07, 0.07, 0.08, 16]} />
          <meshStandardMaterial
            color="#a855f7"
            emissive="#9333ea"
            emissiveIntensity={selected ? 1.0 : 0.4}
          />
        </mesh>
      </group>

      {/* Secondary moisture condensing / chilling column */}
      <group position={[0.5, 0, 0]}>
        <mesh position={[0, 0.95, 0]} castShadow>
          <cylinderGeometry args={[0.35, 0.35, 1.4, 24]} />
          <meshStandardMaterial color="#8b5cf6" metalness={0.65} roughness={0.2} />
        </mesh>
        <mesh position={[0, 1.7, 0]}>
          <sphereGeometry args={[0.35, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <meshStandardMaterial color="#6d28d9" metalness={0.7} roughness={0.2} />
        </mesh>
      </group>

      {/* Interconnecting gas manifold bridge */}
      <mesh position={[0, 1.7, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.07, 0.07, 1.0, 12]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
      </mesh>

      {/* Twin activated carbon polishing adsorbers */}
      <group position={[0, 0.6, 0.55]}>
        <mesh castShadow>
          <cylinderGeometry args={[0.22, 0.22, 0.65, 16]} />
          <meshStandardMaterial color="#334155" metalness={0.8} roughness={0.3} />
        </mesh>
      </group>
      <group position={[0.6, 0.6, 0.55]}>
        <mesh castShadow>
          <cylinderGeometry args={[0.22, 0.22, 0.65, 16]} />
          <meshStandardMaterial color="#334155" metalness={0.8} roughness={0.3} />
        </mesh>
      </group>
    </group>
  );
}

// -------------------------------------------------------------
// 6. CHP Generator Model (Acoustic container, exhaust stack, heat unit)
// -------------------------------------------------------------
function CHPGeneratorModel({ selected }: { selected: boolean }) {
  return (
    <group>
      {/* Acoustic generator container enclosure */}
      <mesh position={[0, 0.85, 0]} castShadow>
        <boxGeometry args={[2.2, 1.4, 1.7]} />
        <meshStandardMaterial color="#e11d48" metalness={0.5} roughness={0.4} />
      </mesh>

      {/* Air intake ventilation louvers (front/back) */}
      <mesh position={[-0.4, 0.9, 0.86]}>
        <boxGeometry args={[0.8, 0.7, 0.04]} />
        <meshStandardMaterial color="#0f172a" roughness={0.8} />
      </mesh>
      <mesh position={[0.5, 0.9, 0.86]}>
        <boxGeometry args={[0.7, 0.7, 0.04]} />
        <meshStandardMaterial color="#1e293b" roughness={0.7} />
      </mesh>

      {/* Turbo exhaust silencer & muffler assembly */}
      <mesh position={[0.3, 1.75, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.26, 0.26, 0.9, 20]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>

      {/* Tall stainless engine exhaust stack */}
      <mesh position={[0.6, 2.5, 0]}>
        <cylinderGeometry args={[0.13, 0.13, 1.2, 16]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
      </mesh>
      {/* Exhaust rain cap */}
      <mesh position={[0.6, 3.15, 0]}>
        <cylinderGeometry args={[0.22, 0.04, 0.15, 16]} />
        <meshStandardMaterial color="#94a3b8" metalness={0.8} roughness={0.2} />
      </mesh>

      {/* Heat recovery exchanger module (side unit) */}
      <mesh position={[-1.2, 0.7, 0]} castShadow>
        <boxGeometry args={[0.35, 1.1, 1.2]} />
        <meshStandardMaterial color="#0284c7" metalness={0.6} roughness={0.3} />
      </mesh>
      {/* Insulated thermal hot water pipes */}
      <mesh position={[-1.2, 1.4, 0.2]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.06, 0.06, 0.6, 12]} />
        <meshStandardMaterial
          color="#f43f5e"
          emissive="#e11d48"
          emissiveIntensity={selected ? 0.9 : 0.3}
        />
      </mesh>
    </group>
  );
}

// -------------------------------------------------------------
// 7. Digestate Output Model (Screw press separator, solids & liquid)
// -------------------------------------------------------------
function DigestateOutputModel({ selected }: { selected: boolean }) {
  return (
    <group>
      {/* Elevated steel support framework */}
      <mesh position={[-0.6, 0.65, 0.5]}>
        <boxGeometry args={[0.1, 1.3, 0.1]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[-0.6, 0.65, -0.5]}>
        <boxGeometry args={[0.1, 1.3, 0.1]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[0.6, 0.65, 0.5]}>
        <boxGeometry args={[0.1, 1.3, 0.1]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[0.6, 0.65, -0.5]}>
        <boxGeometry args={[0.1, 1.3, 0.1]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>

      {/* Screw-press solid-liquid separator unit */}
      <group position={[0, 1.5, 0]}>
        {/* Separator barrel cylinder */}
        <mesh rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.3, 0.3, 1.4, 20]} />
          <meshStandardMaterial color="#65a30d" metalness={0.6} roughness={0.3} />
        </mesh>
        {/* Drive electric motor */}
        <mesh position={[-0.85, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.22, 0.22, 0.35, 16]} />
          <meshStandardMaterial color="#1e293b" metalness={0.7} roughness={0.3} />
        </mesh>
        {/* Solids discharge cone chute */}
        <mesh position={[0.65, -0.2, 0]} rotation={[0, 0, -Math.PI / 4]}>
          <cylinderGeometry args={[0.18, 0.25, 0.45, 16]} />
          <meshStandardMaterial color="#4d7c0f" metalness={0.4} roughness={0.5} />
        </mesh>
      </group>

      {/* Dewatered solid fertilizer collection bunker below */}
      <group position={[0.5, 0.3, 0]}>
        <mesh castShadow>
          <boxGeometry args={[1.0, 0.55, 1.2]} />
          <meshStandardMaterial color="#334155" roughness={0.7} metalness={0.3} />
        </mesh>
        {/* Solid organic compost cake pile */}
        <mesh position={[0, 0.25, 0]}>
          <boxGeometry args={[0.85, 0.25, 1.05]} />
          <meshStandardMaterial color="#365314" roughness={0.95} />
        </mesh>
      </group>

      {/* Liquid digestate holding tank (beside) */}
      <group position={[-1.0, 0.8, 0]}>
        <mesh castShadow>
          <cylinderGeometry args={[0.5, 0.5, 1.3, 24]} />
          <meshStandardMaterial color="#4d7c0f" metalness={0.5} roughness={0.3} />
        </mesh>
        <mesh position={[0, 1.48, 0]}>
          <sphereGeometry args={[0.5, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <meshStandardMaterial color="#365314" metalness={0.6} roughness={0.3} />
        </mesh>
        {/* Effluent level indicator */}
        <mesh position={[0, 0.1, 0.51]}>
          <boxGeometry args={[0.06, 0.9, 0.03]} />
          <meshStandardMaterial
            color="#84cc16"
            emissive="#65a30d"
            emissiveIntensity={selected ? 1.0 : 0.4}
          />
        </mesh>
      </group>
    </group>
  );
}

// -------------------------------------------------------------
// Interactive Stage Assembly Wrapper
// -------------------------------------------------------------
function StageEquipment({
  stage,
  index,
  selected,
  onSelect,
}: {
  stage: ProcessStage;
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const [hovered, setHovered] = React.useState(false);
  const beaconRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (selected && beaconRef.current) {
      const t = state.clock.getElapsedTime();
      beaconRef.current.position.y = 3.2 + Math.sin(t * 3.5) * 0.15;
    }
  });

  return (
    <group
      position={stage.position}
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHovered(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHovered(false);
        document.body.style.cursor = "auto";
      }}
    >
      {/* Ground Pedestal Ring & Circular Stage Marker */}
      <mesh position={[0, 0.05, 0]} receiveShadow>
        <cylinderGeometry args={[index === 3 ? 2.5 : 1.7, index === 3 ? 2.6 : 1.8, 0.08, 36]} />
        <meshStandardMaterial
          color={selected ? "#0f766e" : hovered ? "#1e293b" : "#0f172a"}
          emissive={selected ? "#14b8a6" : hovered ? "#0f766e" : "#020617"}
          emissiveIntensity={selected ? 0.7 : hovered ? 0.3 : 0}
          roughness={0.4}
          metalness={0.6}
        />
      </mesh>

      {/* Selected glowing beacon halo ring on floor */}
      {selected && (
        <mesh position={[0, 0.1, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[index === 3 ? 2.55 : 1.75, index === 3 ? 2.75 : 1.95, 36]} />
          <meshBasicMaterial color="#2dd4bf" side={THREE.DoubleSide} transparent opacity={0.8} />
        </mesh>
      )}

      {/* Specific 3D Equipment Model by stage index */}
      {index === 0 && <WasteReceivingModel selected={selected} />}
      {index === 1 && <SortingModel selected={selected} />}
      {index === 2 && <MixingTankModel selected={selected} />}
      {index === 3 && <DigesterModel selected={selected} />}
      {index === 4 && <GasTreatmentModel selected={selected} />}
      {index === 5 && <CHPGeneratorModel selected={selected} />}
      {index === 6 && <DigestateOutputModel selected={selected} />}

      {/* Selected 3D Beacon Pointer hovering above equipment */}
      {selected && (
        <mesh ref={beaconRef} position={[0, 3.2, 0]} rotation={[0, 0, Math.PI]}>
          <coneGeometry args={[0.2, 0.45, 16]} />
          <meshStandardMaterial
            color="#2dd4bf"
            emissive="#14b8a6"
            emissiveIntensity={1.5}
            roughness={0.2}
          />
        </mesh>
      )}

      {/* Floating HTML Stage Label / Callout */}
      <Html
        position={[0, index === 3 ? 4.2 : index % 2 === 0 ? 3.4 : 3.8, 0]}
        center
        distanceFactor={18}
        zIndexRange={[15, 0]}
      >
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSelect();
          }}
          aria-label={`Select stage ${stage.code}: ${stage.name}`}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full transition-all duration-300 select-none shadow-xl border ${
            selected
              ? "bg-slate-900/95 border-teal-400 text-white shadow-teal-500/30 scale-110 ring-2 ring-teal-400/50"
              : hovered
              ? "bg-slate-900/90 border-slate-500 text-slate-100 scale-105"
              : "bg-slate-950/80 border-slate-700/70 text-slate-300"
          }`}
          style={{
            backdropFilter: "blur(8px)",
            WebkitBackdropFilter: "blur(8px)",
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          <span
            className="flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold"
            style={{
              backgroundColor: selected ? stage.accentColor : stage.color,
              color: "#020617",
            }}
          >
            {stage.code}
          </span>
          <span className="text-xs font-semibold tracking-wide">{stage.name}</span>
          {selected && (
            <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse" />
          )}
        </button>
      </Html>
    </group>
  );
}

// -------------------------------------------------------------
// Interconnecting Process Piping with Animated Flow Pulses
// -------------------------------------------------------------
function ProcessPiping({ stages }: { stages: ProcessStage[] }) {
  const pulseGroupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (pulseGroupRef.current) {
      const t = state.clock.getElapsedTime();
      pulseGroupRef.current.children.forEach((child, idx) => {
        // Continuous cycle along each pipe segment
        const phase = (t * 0.8 + idx * 0.4) % 1;
        const startX = stages[idx].position[0];
        const endX = stages[idx + 1].position[0];
        child.position.x = startX + (endX - startX) * phase;
      });
    }
  });

  return (
    <group>
      {/* 1. Main Feedstock Slurry Pipe (Stages 0 -> 1 -> 2 -> 3) at height Y = 0.55 */}
      {[0, 1, 2].map((idx) => {
        const x1 = stages[idx].position[0];
        const x2 = stages[idx + 1].position[0];
        const midX = (x1 + x2) / 2;
        const length = Math.abs(x2 - x1);
        return (
          <group key={`feed-pipe-${idx}`}>
            <mesh position={[midX, 0.55, 0]} rotation={[0, 0, Math.PI / 2]}>
              <cylinderGeometry args={[0.07, 0.07, length - 1.2, 16]} />
              <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
            </mesh>
            {/* Flange collars */}
            <mesh position={[midX - length / 3, 0.55, 0]} rotation={[0, 0, Math.PI / 2]}>
              <cylinderGeometry args={[0.1, 0.1, 0.05, 16]} />
              <meshStandardMaterial color="#64748b" metalness={0.9} roughness={0.1} />
            </mesh>
            <mesh position={[midX + length / 3, 0.55, 0]} rotation={[0, 0, Math.PI / 2]}>
              <cylinderGeometry args={[0.1, 0.1, 0.05, 16]} />
              <meshStandardMaterial color="#64748b" metalness={0.9} roughness={0.1} />
            </mesh>
          </group>
        );
      })}

      {/* 2. Elevated Raw Biogas Extraction Pipe (Stage 3 Digester -> Stage 4 Gas Treatment) at height Y = 2.6 */}
      <group>
        <mesh
          position={[
            (stages[3].position[0] + stages[4].position[0]) / 2,
            2.5,
            0,
          ]}
          rotation={[0, 0, Math.PI / 2]}
        >
          <cylinderGeometry
            args={[0.06, 0.06, stages[4].position[0] - stages[3].position[0] - 1.4, 16]}
          />
          <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
        </mesh>
      </group>

      {/* 3. Scrubbed Biogas Fuel Pipe (Stage 4 Gas Treatment -> Stage 5 CHP Generator) at height Y = 2.1 */}
      <group>
        <mesh
          position={[
            (stages[4].position[0] + stages[5].position[0]) / 2,
            2.1,
            0,
          ]}
          rotation={[0, 0, Math.PI / 2]}
        >
          <cylinderGeometry
            args={[0.055, 0.055, stages[5].position[0] - stages[4].position[0] - 1.2, 16]}
          />
          <meshStandardMaterial color="#94a3b8" metalness={0.85} roughness={0.2} />
        </mesh>
      </group>

      {/* 4. Digestate Transfer Pipe (Stage 3 Digester -> Stage 6 Digestate Output) along rear corridor */}
      <group>
        <mesh
          position={[
            (stages[3].position[0] + stages[6].position[0]) / 2,
            0.4,
            -1.5,
          ]}
          rotation={[0, 0, Math.PI / 2]}
        >
          <cylinderGeometry
            args={[0.065, 0.065, stages[6].position[0] - stages[3].position[0] - 1.5, 16]}
          />
          <meshStandardMaterial color="#65a30d" metalness={0.6} roughness={0.3} />
        </mesh>
      </group>

      {/* Animated Flow Pulses traveling along the main process line */}
      <group ref={pulseGroupRef}>
        {stages.slice(0, 6).map((_, idx) => (
          <mesh key={`pulse-${idx}`} position={[0, idx >= 3 && idx <= 4 ? 2.5 : 0.55, 0]}>
            <sphereGeometry args={[0.1, 12, 12]} />
            <meshBasicMaterial color={idx >= 3 ? "#38bdf8" : "#2dd4bf"} />
          </mesh>
        ))}
      </group>
    </group>
  );
}

// -------------------------------------------------------------
// Facility Floor Platform & Environment
// -------------------------------------------------------------
function FacilityPlatform() {
  return (
    <group>
      {/* Main Industrial Composite Base Slab */}
      <mesh position={[0, -0.15, 0]} receiveShadow>
        <boxGeometry args={[27.5, 0.3, 10.5]} />
        <meshStandardMaterial color="#090f1d" roughness={0.7} metalness={0.3} />
      </mesh>

      {/* Slab Metallic Edge Bevel Trim */}
      <mesh position={[0, -0.01, 5.25]}>
        <boxGeometry args={[27.6, 0.04, 0.08]} />
        <meshStandardMaterial
          color="#14b8a6"
          emissive="#0d9488"
          emissiveIntensity={0.6}
        />
      </mesh>
      <mesh position={[0, -0.01, -5.25]}>
        <boxGeometry args={[27.6, 0.04, 0.08]} />
        <meshStandardMaterial
          color="#14b8a6"
          emissive="#0d9488"
          emissiveIntensity={0.4}
        />
      </mesh>

      {/* Sleek Subdued Floor Grid */}
      <gridHelper args={[28, 28, "#1e293b", "#0f172a"]} position={[0, 0.01, 0]} />
    </group>
  );
}

// -------------------------------------------------------------
// Main 3D Plant Scene Component
// -------------------------------------------------------------
export default function PlantScene({
  stages,
  selectedStage,
  onSelectStage,
}: Equipment3DProps) {
  return (
    <>
      <color attach="background" args={["#060a14"]} />

      {/* Balanced 3-Point Industrial Lighting */}
      <ambientLight intensity={0.9} color="#94a3b8" />
      <directionalLight
        position={[14, 22, 16]}
        intensity={2.2}
        color="#ffffff"
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-camera-left={-15}
        shadow-camera-right={15}
        shadow-camera-top={10}
        shadow-camera-bottom={-10}
      />
      <directionalLight position={[-16, 12, -12]} intensity={1.0} color="#0d9488" />
      <pointLight position={[0, 6, 4]} intensity={25} color="#2dd4bf" distance={18} />
      <pointLight position={[7.6, 5, 3]} intensity={20} color="#fb7185" distance={14} />

      {/* Ground Platform */}
      <FacilityPlatform />

      {/* Connecting Process Pipe Network */}
      <ProcessPiping stages={stages} />

      {/* Seven Process Equipment Units */}
      {stages.map((stage, idx) => (
        <StageEquipment
          key={stage.id}
          stage={stage}
          index={idx}
          selected={selectedStage === idx}
          onSelect={() => onSelectStage(idx)}
        />
      ))}

      {/* Orbit Controls with Damping & Useful Constraints */}
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.06}
        minDistance={9}
        maxDistance={38}
        minPolarAngle={Math.PI / 6}
        maxPolarAngle={Math.PI / 2.08}
        target={[0, 1.2, 0]}
      />
    </>
  );
}
