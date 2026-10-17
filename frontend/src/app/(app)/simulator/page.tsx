
"use client";

import { useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import * as THREE from "three";

const stages = [
  { name: "Waste Receiving", short: "01", position: [-7.2, 0, 0] as [number, number, number], color: "#a3a3a3", description: "Organic waste arrives at the facility for inspection and weighing." },
  { name: "Sorting", short: "02", position: [-4.8, 0, 0] as [number, number, number], color: "#f59e0b", description: "Unwanted materials are separated from suitable organic feedstock." },
  { name: "Mixing Tank", short: "03", position: [-2.4, 0, 0] as [number, number, number], color: "#38bdf8", description: "The feedstock is mixed with water to prepare a suitable slurry." },
  { name: "Anaerobic Digester", short: "04", position: [0, 0, 0] as [number, number, number], color: "#2dd4bf", description: "Microorganisms break down organic material in an oxygen-free tank." },
  { name: "Gas Treatment", short: "05", position: [2.4, 0, 0] as [number, number, number], color: "#c084fc", description: "Biogas is collected and treated before its intended use." },
  { name: "CHP Generator", short: "06", position: [4.8, 0, 0] as [number, number, number], color: "#fb7185", description: "A combined heat and power unit can convert biogas energy into electricity and useful heat." },
  { name: "Digestate Output", short: "07", position: [7.2, 0, 0] as [number, number, number], color: "#84cc16", description: "Remaining digestate leaves the process for appropriate handling or further treatment." },
];

function Equipment({
  position,
  color,
  index,
  selected,
  onSelect,
}: {
  position: [number, number, number];
  color: string;
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <group position={position} onClick={onSelect}>
      {index === 0 || index === 6 ? (
        <>
          <mesh position={[0, 0.55, 0]} castShadow>
            <boxGeometry args={[1.25, 1.1, 1.15]} />
            <meshStandardMaterial color={color} metalness={0.25} roughness={0.55} />
          </mesh>
          <mesh position={[0, 1.15, 0]}>
            <boxGeometry args={[1.3, 0.08, 1.2]} />
            <meshStandardMaterial color="#cbd5e1" metalness={0.5} />
          </mesh>
        </>
      ) : index === 1 || index === 4 ? (
        <>
          <mesh position={[0, 0.75, 0]} castShadow>
            <cylinderGeometry args={[0.42, 0.5, 1.5, 20]} />
            <meshStandardMaterial color={color} metalness={0.55} roughness={0.3} />
          </mesh>
          <mesh position={[0, 1.52, 0]}>
            <cylinderGeometry args={[0.43, 0.43, 0.08, 20]} />
            <meshStandardMaterial color="#cbd5e1" metalness={0.6} />
          </mesh>
        </>
      ) : index === 2 || index === 3 ? (
        <>
          <mesh position={[0, 0.7, 0]} castShadow>
            <cylinderGeometry args={[0.72, 0.72, 1.4, 32]} />
            <meshStandardMaterial color={color} metalness={0.3} roughness={0.35} />
          </mesh>
          <mesh position={[0, 1.43, 0]}>
            <cylinderGeometry args={[0.72, 0.72, 0.08, 32]} />
            <meshStandardMaterial color="#cbd5e1" metalness={0.6} />
          </mesh>
          {index === 3 && (
            <mesh position={[0, 1.8, 0]}>
              <sphereGeometry args={[0.53, 24, 16]} />
              <meshStandardMaterial color="#0f766e" metalness={0.15} roughness={0.4} />
            </mesh>
          )}
        </>
      ) : (
        <>
          <mesh position={[0, 0.55, 0]} castShadow>
            <boxGeometry args={[1.25, 1.1, 1]} />
            <meshStandardMaterial color={color} metalness={0.65} roughness={0.3} />
          </mesh>
          <mesh position={[0, 1.25, 0]}>
            <cylinderGeometry args={[0.25, 0.25, 0.4, 16]} />
            <meshStandardMaterial color="#cbd5e1" metalness={0.7} />
          </mesh>
        </>
      )}

      <mesh position={[0, 0.04, 0]}>
        <boxGeometry args={[1.65, 0.08, 1.5]} />
        <meshStandardMaterial
          color={selected ? "#2dd4bf" : "#334155"}
          emissive={selected ? "#0f766e" : "#000000"}
          emissiveIntensity={selected ? 0.5 : 0}
        />
      </mesh>

      <Html position={[0, 2.25, 0]} center distanceFactor={13} zIndexRange={[10, 0]}>
        <button
          onClick={(event) => {
            event.stopPropagation();
            onSelect();
          }}
          style={{
            whiteSpace: "nowrap",
            background: selected ? "#0f766e" : "#111a2b",
            color: "#f1f5f9",
            border: `1px solid ${selected ? "#2dd4bf" : "#475569"}`,
            borderRadius: 8,
            padding: "5px 8px",
            fontSize: 11,
            cursor: "pointer",
          }}
        >
          {stages[index].short} · {stages[index].name}
        </button>
      </Html>
    </group>
  );
}

function PlantScene({
  selected,
  onSelect,
}: {
  selected: number;
  onSelect: (index: number) => void;
}) {
  return (
    <>
      <color attach="background" args={["#0b1220"]} />
      <ambientLight intensity={1.5} />
      <directionalLight position={[4, 9, 6]} intensity={2} castShadow />
      <pointLight position={[-5, 4, -3]} intensity={35} color="#0d9488" />

      <gridHelper args={[22, 22, "#334155", "#1e293b"]} position={[0, 0.01, 0]} />

      {stages.map((stage, index) => (
        <group key={stage.short}>
          <Equipment
            position={stage.position}
            color={stage.color}
            index={index}
            selected={selected === index}
            onSelect={() => onSelect(index)}
          />
          {index < stages.length - 1 && (
            <mesh
              position={[
                (stage.position[0] + stages[index + 1].position[0]) / 2,
                0.45,
                0,
              ]}
              rotation={[0, 0, Math.PI / 2]}
            >
              <cylinderGeometry args={[0.055, 0.055, 1.1, 12]} />
              <meshStandardMaterial
                color="#64748b"
                metalness={0.7}
                roughness={0.3}
              />
            </mesh>
          )}
        </group>
      ))}

      <OrbitControls
        makeDefault
        enableDamping
        minDistance={8}
        maxDistance={25}
        maxPolarAngle={Math.PI / 2.05}
        target={[0, 0.8, 0]}
      />
    </>
  );
}

export default function SimulatorPage() {
  const [selected, setSelected] = useState(3);
  const [tourRunning, setTourRunning] = useState(false);

  function moveStage(direction: number) {
    setSelected((current) => Math.max(0, Math.min(stages.length - 1, current + direction)));
  }

  return (
    <main style={{ minHeight: "100vh", padding: 24, background: "#080d18", color: "#e8eef7" }}>
      <header style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
        <div>
          <p style={{ color: "#2dd4bf", letterSpacing: 3, fontSize: 11, fontWeight: 700 }}>
            WASTE-POTENTIAL / PROCESS LAB
          </p>
          <h1 style={{ fontSize: 30, fontWeight: 750, margin: "8px 0" }}>
            Anaerobic Digestion
          </h1>
          <p style={{ color: "#94a3b8", margin: 0 }}>
            Explore the journey from organic waste to useful energy.
          </p>
        </div>
        <div style={{ alignSelf: "center", display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span style={{ border: "1px solid #334155", borderRadius: 20, padding: "7px 12px", fontSize: 12 }}>
            3D VISUAL PREVIEW
          </span>
          <span style={{ border: "1px solid #854d0e", color: "#fbbf24", borderRadius: 20, padding: "7px 12px", fontSize: 12 }}>
            Illustrative · Not calculated
          </span>
        </div>
      </header>

      <section style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 290px", gap: 18 }}>
        <div style={{ minWidth: 0 }}>
          <div className="panel" style={{ overflow: "hidden", height: 500, position: "relative" }}>
            <div style={{ position: "absolute", zIndex: 2, top: 14, left: 16, pointerEvents: "none" }}>
              <p style={{ margin: 0, fontSize: 11, color: "#94a3b8" }}>PROCESS FLOW / 3D VIEWPORT</p>
              <p style={{ margin: "5px 0", fontSize: 13 }}>Drag to orbit · Scroll to zoom · Select a stage</p>
            </div>
            <Canvas
              camera={{ position: [0, 8, 20], fov: 43 }}
              dpr={[1, 1.5]}
              gl={{ antialias: true, alpha: false }}
            >
              <PlantScene selected={selected} onSelect={setSelected} />
            </Canvas>
            <div style={{ position: "absolute", bottom: 14, left: 16, fontSize: 11, color: "#94a3b8", pointerEvents: "none" }}>
              SCHEMATIC EQUIPMENT · NOT TO SCALE
            </div>
          </div>

          <div className="panel" style={{ marginTop: 16, padding: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            <div>
              <p style={{ margin: 0, fontSize: 11, color: "#94a3b8" }}>GUIDED WALKTHROUGH</p>
              <p style={{ margin: "5px 0 0" }}>Stage {selected + 1} of {stages.length}</p>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => moveStage(-1)} disabled={selected === 0} style={controlStyle}>
                ← Previous
              </button>
              <button
                onClick={() => setTourRunning((running) => !running)}
                style={{ ...controlStyle, background: tourRunning ? "#7f1d1d" : "#115e59" }}
              >
                {tourRunning ? "Pause tour" : "Start tour"}
              </button>
              <button onClick={() => moveStage(1)} disabled={selected === stages.length - 1} style={controlStyle}>
                Next →
              </button>
              <button onClick={() => { setSelected(0); setTourRunning(false); }} style={controlStyle}>
                Restart
              </button>
            </div>
          </div>
        </div>

        <aside className="panel" style={{ padding: 16 }}>
          <p style={{ margin: "0 0 12px", color: "#94a3b8", fontSize: 11, letterSpacing: 1.5 }}>
            PROCESS STAGES
          </p>
          <div style={{ display: "grid", gap: 5 }}>
            {stages.map((stage, index) => (
              <button
                key={stage.short}
                className={`stage-button ${selected === index ? "active" : ""}`}
                onClick={() => setSelected(index)}
              >
                <span style={{ color: stage.color, fontSize: 11, fontWeight: 700 }}>{stage.short}</span>
                <span style={{ display: "block", marginTop: 4, fontWeight: 600, fontSize: 13 }}>
                  {stage.name}
                </span>
              </button>
            ))}
          </div>

          <div style={{ borderTop: "1px solid #263349", marginTop: 18, paddingTop: 18 }}>
            <p style={{ margin: 0, color: "#2dd4bf", fontSize: 11, letterSpacing: 1.5 }}>
              STAGE INSPECTOR
            </p>
            <h2 style={{ fontSize: 19, margin: "10px 0" }}>{stages[selected].name}</h2>
            <p style={{ fontSize: 13, lineHeight: 1.7, color: "#b6c2d2" }}>
              {stages[selected].description}
            </p>
            <p style={{ color: "#fbbf24", fontSize: 11, lineHeight: 1.6 }}>
              No measured or calculated energy values are shown in this visual prototype.
            </p>
          </div>
        </aside>
      </section>

      <footer style={{ marginTop: 20, color: "#64748b", fontSize: 11, lineHeight: 1.6 }}>
        SCIENCE BEFORE SPECTACLE · The 3D scene is schematic. Validated process results will be supplied by the backend calculation engine when integration is implemented.
      </footer>
    </main>
  );
}

const controlStyle: React.CSSProperties = {
  background: "#1e293b",
  color: "#e2e8f0",
  border: "1px solid #475569",
  borderRadius: 8,
  padding: "9px 12px",
  fontSize: 12,
};
