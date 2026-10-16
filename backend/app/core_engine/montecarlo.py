import random
from typing import Dict
from app.core_engine.engine import net_electricity


def run_monte_carlo(vs_mass_kg: float, iterations: int = 1000) -> Dict[str, float]:
    """Runs a Monte Carlo simulation varying parameters to generate percentile distribution ranges."""
    results = []
    for _ in range(iterations):
        sampled_yield = random.gauss(0.35, 0.05)
        sampled_demand = random.uniform(50.0, 150.0)

        res = net_electricity(
            vs_mass_kg=vs_mass_kg,
            ch4_yield_per_vs=sampled_yield,
            q_demand_kwh=sampled_demand,
        )
        results.append(res["net_electricity_kwh"])

    results.sort()
    return {
        "p2_5": results[int(iterations * 0.025)],
        "p50": results[int(iterations * 0.50)],
        "p97_5": results[int(iterations * 0.975)],
    }
