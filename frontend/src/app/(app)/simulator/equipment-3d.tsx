"use client";

import React, { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
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
export function WasteReceivingModel({ selected = false }: { selected?: boolean }) {
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

      {/* Hopper interior cavity */}
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
export function SortingModel({ selected = false }: { selected?: boolean }) {
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
export function MixingTankModel({ selected = false }: { selected?: boolean }) {
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
export function DigesterModel({ selected = false }: { selected?: boolean }) {
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

      {/* Architectural vertical ribs */}
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

      {/* Front biological viewing window */}
      <mesh ref={portalRef} position={[0, 1.35, 1.71]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.32, 0.32, 0.08, 24]} />
        <meshStandardMaterial
          color="#34d399"
          emissive="#10b981"
          emissiveIntensity={0.8}
          roughness={0.1}
        />
      </mesh>
    </group>
  );
}

// -------------------------------------------------------------
// 5. Gas Treatment Model (Dual scrubber towers, filter vessels)
// -------------------------------------------------------------
export function GasTreatmentModel({ selected = false }: { selected?: boolean }) {
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
export function CHPGeneratorModel({ selected = false }: { selected?: boolean }) {
  return (
    <group>
      {/* Acoustic generator container enclosure */}
      <mesh position={[0, 0.85, 0]} castShadow>
        <boxGeometry args={[2.2, 1.4, 1.7]} />
        <meshStandardMaterial color="#e11d48" metalness={0.5} roughness={0.4} />
      </mesh>

      {/* Air intake ventilation louvers */}
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
export function DigestateOutputModel({ selected = false }: { selected?: boolean }) {
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
        <mesh rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.3, 0.3, 1.4, 20]} />
          <meshStandardMaterial color="#65a30d" metalness={0.6} roughness={0.3} />
        </mesh>
        <mesh position={[-0.85, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.22, 0.22, 0.35, 16]} />
          <meshStandardMaterial color="#1e293b" metalness={0.7} roughness={0.3} />
        </mesh>
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
        <mesh position={[0, 0.25, 0]}>
          <boxGeometry args={[0.85, 0.25, 1.05]} />
          <meshStandardMaterial color="#365314" roughness={0.95} />
        </mesh>
      </group>

      {/* Liquid digestate holding tank */}
      <group position={[-1.0, 0.8, 0]}>
        <mesh castShadow>
          <cylinderGeometry args={[0.5, 0.5, 1.3, 24]} />
          <meshStandardMaterial color="#4d7c0f" metalness={0.5} roughness={0.3} />
        </mesh>
        <mesh position={[0, 1.48, 0]}>
          <sphereGeometry args={[0.5, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <meshStandardMaterial color="#365314" metalness={0.6} roughness={0.3} />
        </mesh>
      </group>
    </group>
  );
}

// -------------------------------------------------------------
// 8. Furnace & Fire Model (Incineration / Combustor HERO with Animated Fire)
// -------------------------------------------------------------
export function FurnaceFireModel({ selected = false }: { selected?: boolean }) {
  const flame1Ref = useRef<THREE.Mesh>(null);
  const flame2Ref = useRef<THREE.Mesh>(null);
  const flame3Ref = useRef<THREE.PointLight>(null);

  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    if (flame1Ref.current) {
      flame1Ref.current.scale.y = 0.9 + Math.sin(t * 7) * 0.25 + Math.cos(t * 11) * 0.15;
      flame1Ref.current.scale.x = 0.9 + Math.cos(t * 8) * 0.2;
    }
    if (flame2Ref.current) {
      flame2Ref.current.scale.y = 0.85 + Math.sin(t * 9 + 1.2) * 0.3;
      flame2Ref.current.scale.z = 0.9 + Math.cos(t * 6) * 0.2;
    }
    if (flame3Ref.current) {
      flame3Ref.current.intensity = 20 + Math.sin(t * 14) * 8;
    }
  });

  return (
    <group>
      {/* Heavy refractory furnace block casing */}
      <mesh position={[0, 0.9, 0]} castShadow>
        <boxGeometry args={[2.0, 1.6, 1.7]} />
        <meshStandardMaterial color="#1e222d" roughness={0.8} metalness={0.3} />
      </mesh>

      {/* Steel structural support columns */}
      <mesh position={[-1.02, 0.9, -0.87]}>
        <boxGeometry args={[0.1, 1.7, 0.1]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[1.02, 0.9, -0.87]}>
        <boxGeometry args={[0.1, 1.7, 0.1]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[-1.02, 0.9, 0.87]}>
        <boxGeometry args={[0.1, 1.7, 0.1]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[1.02, 0.9, 0.87]}>
        <boxGeometry args={[0.1, 1.7, 0.1]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>

      {/* Recessed furnace viewing combustion hearth port */}
      <mesh position={[0, 0.85, 0.86]}>
        <boxGeometry args={[1.1, 0.75, 0.1]} />
        <meshStandardMaterial color="#0a0a0f" roughness={0.9} />
      </mesh>

      {/* Glowing inner firebox chamber */}
      <group position={[0, 0.8, 0.6]}>
        {/* Animated flame cone 1 (outer orange fire) */}
        <mesh ref={flame1Ref} position={[-0.2, 0, 0]}>
          <coneGeometry args={[0.35, 0.8, 16]} />
          <meshBasicMaterial color="#ea580c" />
        </mesh>
        {/* Animated flame cone 2 (inner yellow core) */}
        <mesh ref={flame2Ref} position={[0.2, 0, 0]}>
          <coneGeometry args={[0.28, 0.7, 16]} />
          <meshBasicMaterial color="#facc15" />
        </mesh>
        {/* Flame center point light casting pulsating fire glow */}
        <pointLight ref={flame3Ref} position={[0, 0.1, 0.2]} color="#f97316" distance={5} />
      </group>

      {/* Upper boiler steam heat exchange tube header */}
      <mesh position={[0, 1.85, 0]}>
        <cylinderGeometry args={[0.65, 0.8, 0.4, 24]} />
        <meshStandardMaterial color="#334155" metalness={0.7} roughness={0.3} />
      </mesh>

      {/* Tall refractory exhaust flue stack */}
      <mesh position={[0, 2.5, 0]}>
        <cylinderGeometry args={[0.22, 0.26, 1.1, 20]} />
        <meshStandardMaterial
          color="#475569"
          metalness={0.8}
          roughness={0.2}
          emissive="#c2410c"
          emissiveIntensity={selected ? 0.5 : 0.2}
        />
      </mesh>

      {/* Bottom moving grate ash hopper discharge chute */}
      <mesh position={[0, 0.1, 0]}>
        <cylinderGeometry args={[0.85, 0.35, 0.3, 16]} />
        <meshStandardMaterial color="#0f172a" roughness={0.8} />
      </mesh>
    </group>
  );
}

// -------------------------------------------------------------
// 9. Pyrolysis & High-Temp Reactor Model (Heating jacket, auger, vapor dome)
// -------------------------------------------------------------
export function PyrolysisReactorModel({ selected = false }: { selected?: boolean }) {
  const heatBandRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (heatBandRef.current) {
      const t = state.clock.getElapsedTime();
      const pulse = 0.6 + Math.sin(t * 3.5) * 0.3;
      (heatBandRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity =
        selected ? pulse * 1.5 : pulse;
    }
  });

  return (
    <group>
      {/* Heavy quad-leg support skid */}
      <mesh position={[0, 0.2, 0]}>
        <cylinderGeometry args={[1.2, 1.35, 0.35, 24]} />
        <meshStandardMaterial color="#1e293b" metalness={0.6} roughness={0.4} />
      </mesh>

      {/* Lower conical reactor transition base */}
      <mesh position={[0, 0.6, 0]}>
        <cylinderGeometry args={[0.7, 0.35, 0.5, 24]} />
        <meshStandardMaterial color="#334155" metalness={0.7} roughness={0.3} />
      </mesh>

      {/* Main fluidized bed / pyrolysis cylindrical reactor vessel */}
      <mesh position={[0, 1.45, 0]} castShadow>
        <cylinderGeometry args={[0.7, 0.7, 1.3, 28]} />
        <meshStandardMaterial color="#1e222a" metalness={0.75} roughness={0.25} />
      </mesh>

      {/* Glowing external induction thermal heating jacket bands */}
      <mesh ref={heatBandRef} position={[0, 1.45, 0]}>
        <cylinderGeometry args={[0.74, 0.74, 0.95, 28, 1, true]} />
        <meshStandardMaterial
          color="#fb923c"
          emissive="#ea580c"
          emissiveIntensity={0.8}
          roughness={0.2}
          wireframe
        />
      </mesh>

      {/* Top vapor disengagement dome head */}
      <mesh position={[0, 2.15, 0]}>
        <sphereGeometry args={[0.7, 24, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>

      {/* Top hot bio-oil vapor conduit pipe */}
      <mesh position={[0, 2.7, 0]}>
        <cylinderGeometry args={[0.14, 0.14, 0.65, 16]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
      </mesh>
      <mesh position={[0.25, 2.9, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.14, 0.14, 0.5, 16]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
      </mesh>

      {/* Side horizontal biomass auger injector screw pipe */}
      <group position={[-0.8, 1.1, 0]} rotation={[0, 0, Math.PI / 2]}>
        <mesh>
          <cylinderGeometry args={[0.15, 0.15, 0.9, 16]} />
          <meshStandardMaterial color="#475569" metalness={0.85} roughness={0.2} />
        </mesh>
        {/* Drive motor for auger */}
        <mesh position={[0, -0.55, 0]}>
          <cylinderGeometry args={[0.2, 0.2, 0.35, 16]} />
          <meshStandardMaterial color="#0f172a" metalness={0.7} roughness={0.3} />
        </mesh>
      </group>
    </group>
  );
}

// -------------------------------------------------------------
// 10. Condenser Coil Model (Rapid quench chilled coils & bio-oil flask)
// -------------------------------------------------------------
export function CondenserCoilModel({ selected = false }: { selected?: boolean }) {
  const coilRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (coilRef.current) {
      const t = state.clock.getElapsedTime();
      coilRef.current.rotation.y = t * 0.4;
    }
  });

  return (
    <group>
      {/* Structural base stand */}
      <mesh position={[0, 0.2, 0]}>
        <cylinderGeometry args={[1.1, 1.2, 0.35, 24]} />
        <meshStandardMaterial color="#1e293b" metalness={0.6} roughness={0.4} />
      </mesh>

      {/* Outer transparent glass/steel heat exchange shell */}
      <mesh position={[0, 1.5, 0]}>
        <cylinderGeometry args={[0.85, 0.85, 2.0, 24, 1, true]} />
        <meshStandardMaterial
          color="#38bdf8"
          roughness={0.1}
          metalness={0.2}
          transparent
          opacity={0.35}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Internal helical cooling coils */}
      <group ref={coilRef} position={[0, 1.5, 0]}>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <mesh key={i} position={[0, (i - 2.5) * 0.3, 0]}>
            <torusGeometry args={[0.55, 0.05, 12, 32]} />
            <meshStandardMaterial
              color="#38bdf8"
              emissive="#0284c7"
              emissiveIntensity={selected ? 1.2 : 0.6}
              metalness={0.8}
              roughness={0.1}
            />
          </mesh>
        ))}
      </group>

      {/* Top vapor manifold intake */}
      <mesh position={[0, 2.6, 0]}>
        <cylinderGeometry args={[0.3, 0.85, 0.3, 24]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[0, 2.85, 0]}>
        <cylinderGeometry args={[0.15, 0.15, 0.35, 16]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
      </mesh>

      {/* Bottom conical condensate collection receiver */}
      <mesh position={[0, 0.4, 0]}>
        <cylinderGeometry args={[0.85, 0.3, 0.4, 24]} />
        <meshStandardMaterial color="#334155" metalness={0.7} roughness={0.3} />
      </mesh>
      {/* Liquid bio-oil level view */}
      <mesh position={[0, 0.4, 0.35]}>
        <boxGeometry args={[0.12, 0.25, 0.08]} />
        <meshStandardMaterial color="#b45309" emissive="#78350f" emissiveIntensity={0.8} />
      </mesh>
    </group>
  );
}

// -------------------------------------------------------------
// 11. High-Temperature Gasifier Reactor Model
// -------------------------------------------------------------
export function GasifierModel({ selected = false }: { selected?: boolean }) {
  return (
    <group>
      {/* Heavy base framework */}
      <mesh position={[0, 0.25, 0]}>
        <boxGeometry args={[1.8, 0.4, 1.8]} />
        <meshStandardMaterial color="#1e293b" roughness={0.7} />
      </mesh>

      {/* Lower ash lockhopper cone */}
      <mesh position={[0, 0.7, 0]}>
        <cylinderGeometry args={[0.8, 0.3, 0.6, 24]} />
        <meshStandardMaterial color="#334155" metalness={0.7} roughness={0.3} />
      </mesh>

      {/* Middle throat gasification hearth zone (glowing high heat) */}
      <mesh position={[0, 1.25, 0]}>
        <cylinderGeometry args={[0.6, 0.8, 0.5, 24]} />
        <meshStandardMaterial
          color="#ea580c"
          emissive="#c2410c"
          emissiveIntensity={selected ? 1.0 : 0.5}
          metalness={0.6}
          roughness={0.3}
        />
      </mesh>

      {/* Upper main shaft expansion vessel */}
      <mesh position={[0, 1.9, 0]}>
        <cylinderGeometry args={[0.85, 0.6, 0.8, 24]} />
        <meshStandardMaterial color="#1e293b" metalness={0.8} roughness={0.2} />
      </mesh>

      {/* Oxygen / steam blast injection manifold ring */}
      <mesh position={[0, 1.25, 0]}>
        <torusGeometry args={[0.88, 0.08, 12, 32]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
      </mesh>

      {/* Top syngas takeoff duct */}
      <mesh position={[0.4, 2.5, 0]} rotation={[0, 0, Math.PI / 4]}>
        <cylinderGeometry args={[0.14, 0.14, 0.6, 16]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.85} roughness={0.15} />
      </mesh>
    </group>
  );
}

// -------------------------------------------------------------
// 12. Cyclone Solids Separator Model
// -------------------------------------------------------------
export function CycloneSeparatorModel({ selected = false }: { selected?: boolean }) {
  return (
    <group>
      {/* Tripod support legs */}
      <mesh position={[-0.5, 0.7, 0.3]} rotation={[0, 0, Math.PI / 18]}>
        <cylinderGeometry args={[0.04, 0.04, 1.4, 8]} />
        <meshStandardMaterial color="#64748b" metalness={0.8} />
      </mesh>
      <mesh position={[0.5, 0.7, 0.3]} rotation={[0, 0, -Math.PI / 18]}>
        <cylinderGeometry args={[0.04, 0.04, 1.4, 8]} />
        <meshStandardMaterial color="#64748b" metalness={0.8} />
      </mesh>
      <mesh position={[0, 0.7, -0.6]} rotation={[-Math.PI / 18, 0, 0]}>
        <cylinderGeometry args={[0.04, 0.04, 1.4, 8]} />
        <meshStandardMaterial color="#64748b" metalness={0.8} />
      </mesh>

      {/* Lower inverted cone separator body */}
      <mesh position={[0, 1.1, 0]}>
        <cylinderGeometry args={[0.7, 0.2, 1.0, 24]} />
        <meshStandardMaterial
          color="#d97706"
          metalness={0.7}
          roughness={0.25}
          emissive="#b45309"
          emissiveIntensity={selected ? 0.6 : 0.2}
        />
      </mesh>

      {/* Upper cylindrical cyclone barrel */}
      <mesh position={[0, 1.85, 0]}>
        <cylinderGeometry args={[0.7, 0.7, 0.6, 24]} />
        <meshStandardMaterial color="#b45309" metalness={0.7} roughness={0.3} />
      </mesh>

      {/* Tangential rectangular gas inlet */}
      <mesh position={[-0.6, 1.85, 0]}>
        <boxGeometry args={[0.5, 0.3, 0.25]} />
        <meshStandardMaterial color="#475569" metalness={0.8} />
      </mesh>

      {/* Top vortex finder clean gas outlet pipe */}
      <mesh position={[0, 2.4, 0]}>
        <cylinderGeometry args={[0.2, 0.2, 0.6, 16]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.1} />
      </mesh>

      {/* Bottom rotary airlock valve & char canister */}
      <mesh position={[0, 0.45, 0]}>
        <cylinderGeometry args={[0.22, 0.22, 0.3, 16]} />
        <meshStandardMaterial color="#1e293b" metalness={0.8} />
      </mesh>
    </group>
  );
}

// -------------------------------------------------------------
// 13. Rotary Drum Biomass Dryer Model
// -------------------------------------------------------------
export function DryerModel({ selected = false }: { selected?: boolean }) {
  const drumRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (drumRef.current) {
      drumRef.current.rotation.x = state.clock.getElapsedTime() * 0.5;
    }
  });

  return (
    <group>
      {/* Concrete support cradle piers */}
      <mesh position={[-0.7, 0.3, 0]}>
        <boxGeometry args={[0.4, 0.6, 1.2]} />
        <meshStandardMaterial color="#334155" roughness={0.8} />
      </mesh>
      <mesh position={[0.7, 0.3, 0]}>
        <boxGeometry args={[0.4, 0.6, 1.2]} />
        <meshStandardMaterial color="#334155" roughness={0.8} />
      </mesh>

      {/* Inclined rotating cylindrical dryer drum */}
      <group position={[0, 0.9, 0]} rotation={[0, 0, Math.PI / 2]}>
        <group ref={drumRef}>
          <mesh castShadow>
            <cylinderGeometry args={[0.55, 0.55, 2.2, 24]} />
            <meshStandardMaterial
              color="#475569"
              metalness={0.7}
              roughness={0.3}
              emissive="#f97316"
              emissiveIntensity={selected ? 0.4 : 0.1}
            />
          </mesh>
          {/* Drive girth ring gear */}
          <mesh position={[0, 0.1, 0]}>
            <cylinderGeometry args={[0.62, 0.62, 0.12, 24]} />
            <meshStandardMaterial color="#f59e0b" metalness={0.9} roughness={0.2} />
          </mesh>
        </group>
      </group>

      {/* Intake hood & exhaust vapor stack */}
      <mesh position={[1.1, 1.3, 0]}>
        <cylinderGeometry args={[0.15, 0.25, 0.7, 16]} />
        <meshStandardMaterial color="#94a3b8" metalness={0.8} />
      </mesh>
    </group>
  );
}

// -------------------------------------------------------------
// 14. Aerated Composting Windrow Tunnel Model
// -------------------------------------------------------------
export function AerationWindrowModel({ selected = false }: { selected?: boolean }) {
  return (
    <group>
      {/* Enclosed concrete bay walls */}
      <mesh position={[0, 0.5, -0.7]}>
        <boxGeometry args={[2.2, 0.9, 0.15]} />
        <meshStandardMaterial color="#334155" roughness={0.7} />
      </mesh>
      <mesh position={[0, 0.5, 0.7]}>
        <boxGeometry args={[2.2, 0.9, 0.15]} />
        <meshStandardMaterial color="#334155" roughness={0.7} />
      </mesh>

      {/* Organic compost windrow pile */}
      <mesh position={[0, 0.4, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.5, 0.5, 2.0, 16, 1, false, 0, Math.PI]} />
        <meshStandardMaterial color="#451a03" roughness={0.95} />
      </mesh>

      {/* Aeration blower fan & manifold duct */}
      <mesh position={[-1.1, 0.5, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.3, 0.3, 0.35, 16]} />
        <meshStandardMaterial
          color="#16a34a"
          metalness={0.6}
          roughness={0.3}
          emissive="#22c55e"
          emissiveIntensity={selected ? 0.6 : 0.2}
        />
      </mesh>
    </group>
  );
}

// -------------------------------------------------------------
// Unified Equipment Component Dispatcher
// -------------------------------------------------------------
export function EquipmentModelSelector({
  equipmentType,
  selected = false,
}: {
  equipmentType?: string;
  selected?: boolean;
}) {
  const type = equipmentType?.toLowerCase() || "";

  if (type.includes("furnace") || type.includes("fire") || type.includes("combust")) {
    return <FurnaceFireModel selected={selected} />;
  }
  if (type.includes("condenser") || type.includes("coil") || type.includes("quench")) {
    return <CondenserCoilModel selected={selected} />;
  }
  if (type.includes("pyro") || type.includes("reactor") || type.includes("autoclave")) {
    return <PyrolysisReactorModel selected={selected} />;
  }
  if (type.includes("gasif")) {
    return <GasifierModel selected={selected} />;
  }
  if (type.includes("cyclone")) {
    return <CycloneSeparatorModel selected={selected} />;
  }
  if (type.includes("dryer")) {
    return <DryerModel selected={selected} />;
  }
  if (type.includes("aeration") || type.includes("windrow") || type.includes("tunnel")) {
    return <AerationWindrowModel selected={selected} />;
  }
  if (type.includes("digester") || type.includes("anaerobic")) {
    return <DigesterModel selected={selected} />;
  }
  if (type.includes("mix") || type.includes("slurry") || type.includes("conditioning")) {
    return <MixingTankModel selected={selected} />;
  }
  if (type.includes("sort") || type.includes("trommel") || type.includes("shred")) {
    return <SortingModel selected={selected} />;
  }
  if (type.includes("intake") || type.includes("receiv") || type.includes("bunker")) {
    return <WasteReceivingModel selected={selected} />;
  }
  if (type.includes("chp") || type.includes("gen") || type.includes("turbine") || type.includes("engine")) {
    return <CHPGeneratorModel selected={selected} />;
  }
  if (type.includes("treat") || type.includes("scrub") || type.includes("clean") || type.includes("fgt")) {
    return <GasTreatmentModel selected={selected} />;
  }
  if (type.includes("output") || type.includes("press") || type.includes("pellet") || type.includes("separator")) {
    return <DigestateOutputModel selected={selected} />;
  }

  // Fallback to Pyrolysis Reactor / Digester
  return <PyrolysisReactorModel selected={selected} />;
}

// -------------------------------------------------------------
// Interactive 3D Canvas Embed for Individual Subprocess Stage Block
// -------------------------------------------------------------
interface StageCanvas3DProps {
  equipmentType?: string;
  stageName?: string;
  accentColor?: string;
  selected?: boolean;
  height?: number | string;
  autoRotate?: boolean;
}

function StageSceneInner({
  equipmentType,
  selected,
  accentColor = "#FB923C",
  autoRotate = true,
}: {
  equipmentType?: string;
  selected?: boolean;
  accentColor?: string;
  autoRotate?: boolean;
}) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (autoRotate && groupRef.current) {
      const t = state.clock.getElapsedTime();
      groupRef.current.rotation.y = Math.sin(t * 0.4) * 0.35;
    }
  });

  return (
    <>
      <color attach="background" args={["#070a0f"]} />

      {/* Targeted Stage Illumination */}
      <ambientLight intensity={0.9} color="#94a3b8" />
      <directionalLight position={[4, 7, 5]} intensity={2.2} color="#ffffff" castShadow />
      <directionalLight position={[-4, 4, -4]} intensity={1.2} color={accentColor} />
      <pointLight position={[0, 4, 2]} intensity={14} color={accentColor} distance={10} />

      {/* Dark Stage Circular Pedestal */}
      <group position={[0, -0.05, 0]}>
        <mesh position={[0, -0.08, 0]}>
          <cylinderGeometry args={[1.7, 1.8, 0.15, 36]} />
          <meshStandardMaterial color="#0c111d" metalness={0.7} roughness={0.3} />
        </mesh>
        <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[1.65, 1.78, 36]} />
          <meshBasicMaterial
            color={selected ? accentColor : "rgba(251,146,60,0.4)"}
            side={THREE.DoubleSide}
            transparent
            opacity={selected ? 0.9 : 0.4}
          />
        </mesh>
      </group>

      {/* Equipment Model Container */}
      <group ref={groupRef} position={[0, 0, 0]}>
        <EquipmentModelSelector equipmentType={equipmentType} selected={selected} />
      </group>

      <OrbitControls
        makeDefault
        enablePan={false}
        enableZoom={false}
        dampingFactor={0.08}
        minPolarAngle={Math.PI / 4}
        maxPolarAngle={Math.PI / 2.1}
      />
    </>
  );
}

export function StageCanvas3D({
  equipmentType,
  selected = false,
  accentColor = "#FB923C",
  height = 180,
  autoRotate = true,
}: StageCanvas3DProps) {
  return (
    <div
      style={{
        width: "100%",
        height,
        position: "relative",
        borderRadius: 14,
        overflow: "hidden",
        background: "radial-gradient(ellipse at 50% 60%, rgba(251,146,60,0.08) 0%, #070a0f 80%)",
      }}
    >
      <Canvas
        camera={{ position: [3.2, 2.5, 3.6], fov: 44 }}
        gl={{ antialias: true, alpha: false }}
        dpr={[1, 1.5]}
      >
        <StageSceneInner
          equipmentType={equipmentType}
          selected={selected}
          accentColor={accentColor}
          autoRotate={autoRotate}
        />
      </Canvas>
    </div>
  );
}

// -------------------------------------------------------------
// Interactive Full-Plant Stage Assembly Wrapper (Legacy / Global 3D View)
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
      {/* Ground Pedestal Ring */}
      <mesh position={[0, 0.05, 0]} receiveShadow>
        <cylinderGeometry args={[index === 3 ? 2.5 : 1.7, index === 3 ? 2.6 : 1.8, 0.08, 36]} />
        <meshStandardMaterial
          color={selected ? "#c2410c" : hovered ? "#1e293b" : "#0f172a"}
          emissive={selected ? "#fb923c" : hovered ? "#ea580c" : "#020617"}
          emissiveIntensity={selected ? 0.7 : hovered ? 0.3 : 0}
          roughness={0.4}
          metalness={0.6}
        />
      </mesh>

      {/* Selected glowing beacon halo ring on floor */}
      {selected && (
        <mesh position={[0, 0.1, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[index === 3 ? 2.55 : 1.75, index === 3 ? 2.75 : 1.95, 36]} />
          <meshBasicMaterial color="#fb923c" side={THREE.DoubleSide} transparent opacity={0.8} />
        </mesh>
      )}

      {/* Render model by equipmentType or index fallback */}
      <EquipmentModelSelector equipmentType={stage.equipmentType || `stage-${index}`} selected={selected} />

      {/* Selected 3D Beacon Pointer hovering above equipment */}
      {selected && (
        <mesh ref={beaconRef} position={[0, 3.2, 0]} rotation={[0, 0, Math.PI]}>
          <coneGeometry args={[0.2, 0.45, 16]} />
          <meshStandardMaterial
            color="#fb923c"
            emissive="#f97316"
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
              ? "bg-slate-900/95 border-amber-400 text-white shadow-amber-500/30 scale-110 ring-2 ring-amber-400/50"
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
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
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
    if (pulseGroupRef.current && stages.length > 1) {
      const t = state.clock.getElapsedTime();
      pulseGroupRef.current.children.forEach((child, idx) => {
        if (idx < stages.length - 1) {
          const phase = (t * 0.8 + idx * 0.4) % 1;
          const startX = stages[idx].position[0];
          const endX = stages[idx + 1].position[0];
          child.position.x = startX + (endX - startX) * phase;
        }
      });
    }
  });

  if (stages.length < 2) return null;

  return (
    <group>
      {stages.slice(0, stages.length - 1).map((_, idx) => {
        const x1 = stages[idx].position[0];
        const x2 = stages[idx + 1].position[0];
        const midX = (x1 + x2) / 2;
        const length = Math.abs(x2 - x1);
        return (
          <group key={`feed-pipe-${idx}`}>
            <mesh position={[midX, 0.55, 0]} rotation={[0, 0, Math.PI / 2]}>
              <cylinderGeometry args={[0.07, 0.07, Math.max(0.2, length - 1.2), 16]} />
              <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
            </mesh>
          </group>
        );
      })}

      <group ref={pulseGroupRef}>
        {stages.slice(0, stages.length - 1).map((_, idx) => (
          <mesh key={`pulse-${idx}`} position={[0, 0.55, 0]}>
            <sphereGeometry args={[0.1, 12, 12]} />
            <meshBasicMaterial color="#fb923c" />
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
      <mesh position={[0, -0.15, 0]} receiveShadow>
        <boxGeometry args={[27.5, 0.3, 10.5]} />
        <meshStandardMaterial color="#090f1d" roughness={0.7} metalness={0.3} />
      </mesh>
      <mesh position={[0, -0.01, 5.25]}>
        <boxGeometry args={[27.6, 0.04, 0.08]} />
        <meshStandardMaterial color="#fb923c" emissive="#c2410c" emissiveIntensity={0.6} />
      </mesh>
      <gridHelper args={[28, 28, "#1e293b", "#0f172a"]} position={[0, 0.01, 0]} />
    </group>
  );
}

// -------------------------------------------------------------
// Main 3D Plant Scene Component (Default Export)
// -------------------------------------------------------------
export default function PlantScene({
  stages,
  selectedStage,
  onSelectStage,
}: Equipment3DProps) {
  return (
    <>
      <color attach="background" args={["#060a14"]} />

      <ambientLight intensity={0.9} color="#94a3b8" />
      <directionalLight
        position={[14, 22, 16]}
        intensity={2.2}
        color="#ffffff"
        castShadow
        shadow-mapSize={[1024, 1024]}
      />
      <directionalLight position={[-16, 12, -12]} intensity={1.0} color="#ea580c" />
      <pointLight position={[0, 6, 4]} intensity={25} color="#fb923c" distance={18} />

      <FacilityPlatform />
      <ProcessPiping stages={stages} />

      {stages.map((stage, idx) => (
        <StageEquipment
          key={stage.id}
          stage={stage}
          index={idx}
          selected={selectedStage === idx}
          onSelect={() => onSelectStage(idx)}
        />
      ))}

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
