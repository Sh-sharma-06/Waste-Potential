import json
from pathlib import Path
from datetime import datetime, timezone

from app.core_engine.engine import Params
from app.core_engine.montecarlo import run_mc

def main():
    print("Starting Monte Carlo simulation...")

params = Params()
n_runs = 2000
seed = 42

results = run_mc(
    params=params,
    n=n_runs,
    seed=seed,
)

# Find the backend directory
backend_dir = Path(__file__).resolve().parents[2]
output_dir = backend_dir / "data"
output_dir.mkdir(parents=True, exist_ok=True)

output_path = output_dir / "monte_carlo_results.json"

output = {
    "scenario": "default Params()",
    "n_runs": results["n"],
    "seed": results["seed"],
    "net_kwh_d": {
        "p2_5": results["p2_5"],
        "p50": results["median"],
        "p97_5": results["p97_5"],
    },
    "p_net_le_0": results["p_net_nonpositive"],
    "runs_with_warnings": results["runs_with_warnings"],
    "sensitivity": results["sensitivity"],
    "input_distributions": results["distributions"],
    "assumptions_note": results["assumptions_note"],
    "centred_on": results["centred_on"],
    "fixed_inputs": results["fixed_inputs"],
    "recentred": results["recentred"],
    "clipped_samples": results["clipped_samples"],
    "generated_at": datetime.now(timezone.utc).isoformat(),
}

with output_path.open("w", encoding="utf-8") as file:
    json.dump(output, file, indent=2)

print("\nMonte Carlo simulation completed successfully!")
print(f"Simulation runs: {results['n']}")
print(f"Median net energy: {results['median']:.2f} kWh/day")
print(
    f"95% interval: {results['p2_5']:.2f} to "
    f"{results['p97_5']:.2f} kWh/day"
)
print(f"Runs with warnings: {results['runs_with_warnings']}")
print(f"JSON results saved to: {output_path}")


if __name__ == "__main__":
    main()
