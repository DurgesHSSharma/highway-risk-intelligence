"""
Generates the Phase 2 synthetic highway-project monthly-snapshot dataset.

*** OUTPUT IS SYNTHETIC DATA. It is NOT real NHAI/MoRTH project data. ***
It is a reproducible simulation loosely informed by publicly reported
aggregate patterns (see docs/SYNTHETIC_DATA_METHODOLOGY.md), used only to
give a Phase 3 ML pipeline something realistic to train against.

Design note (leakage prevention): each project is simulated forward,
month by month. A month's feature values are built only from that
project's latent traits (drawn once, before simulation starts) and from
random shocks drawn for that month and earlier months. The outcome
targets (final_delay_days, final_cost_overrun_pct, significant_delay,
cost_overrun) are read off the trajectory only *after* the full forward
simulation finishes — they are never used to construct any month's
feature values. See docs/SYNTHETIC_DATA_METHODOLOGY.md section 12.

Usage (from backend/.venv, which already has pandas/numpy installed):
    ../backend/.venv/Scripts/python.exe generate_dataset.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_PROJECTS = 400
MAX_SIMULATION_MONTHS_MULTIPLIER = 3  # hard cap = planned_duration * this, floor 30
MAX_SIMULATION_MONTHS_FLOOR = 30
SIGNIFICANT_DELAY_THRESHOLD_DAYS = 60
COST_OVERRUN_THRESHOLD_PCT = 10.0

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "highway_project_snapshots.csv"

STATES = [
    "Uttar Pradesh", "Maharashtra", "Rajasthan", "Madhya Pradesh", "Gujarat",
    "Karnataka", "Tamil Nadu", "Bihar", "West Bengal", "Andhra Pradesh",
    "Telangana", "Odisha", "Punjab", "Haryana", "Kerala", "Assam",
    "Chhattisgarh", "Jharkhand", "Uttarakhand", "Himachal Pradesh",
]

# Illustrative only — NOT calibrated to real project-level data. Loosely
# reflects the general direction of publicly reported aggregate delay
# patterns (land acquisition / monsoon exposure vary by region) without
# claiming state-by-state precision. See methodology doc.
STATE_RISK_MULTIPLIER = {
    "Uttar Pradesh": 1.15, "Maharashtra": 1.10, "Rajasthan": 0.90,
    "Madhya Pradesh": 1.00, "Gujarat": 0.85, "Karnataka": 1.05,
    "Tamil Nadu": 0.95, "Bihar": 1.25, "West Bengal": 1.20,
    "Andhra Pradesh": 1.00, "Telangana": 0.95, "Odisha": 1.05,
    "Punjab": 1.10, "Haryana": 1.00, "Kerala": 1.15, "Assam": 1.30,
    "Chhattisgarh": 1.05, "Jharkhand": 1.15, "Uttarakhand": 1.10,
    "Himachal Pradesh": 1.20,
}
STATE_MONSOON_MULTIPLIER = {  # relative exposure to monsoon disruption
    "Kerala": 1.6, "Assam": 1.6, "West Bengal": 1.4, "Odisha": 1.4,
    "Karnataka": 1.2, "Maharashtra": 1.2, "Himachal Pradesh": 1.3,
    "Uttarakhand": 1.3,
}

PROJECT_TYPES = [
    "Road Widening (2 to 4 lane)",
    "Road Widening (4 to 6 lane)",
    "Greenfield Highway",
    "Expressway",
    "Bypass/Ring Road",
    "Bridge/ROB/Flyover",
]
PROJECT_TYPE_WEIGHTS = [0.28, 0.20, 0.18, 0.10, 0.14, 0.10]

# (mean length km, length gamma shape, min cost/km cr, max cost/km cr, pace km/month)
PROJECT_TYPE_PARAMS = {
    "Road Widening (2 to 4 lane)": dict(len_mean=38.0, len_shape=4.0, cost_km=(6.0, 12.0), pace=3.2),
    "Road Widening (4 to 6 lane)": dict(len_mean=34.0, len_shape=4.0, cost_km=(12.0, 22.0), pace=2.6),
    "Greenfield Highway": dict(len_mean=48.0, len_shape=3.5, cost_km=(18.0, 32.0), pace=2.2),
    "Expressway": dict(len_mean=58.0, len_shape=3.5, cost_km=(32.0, 55.0), pace=1.8),
    "Bypass/Ring Road": dict(len_mean=16.0, len_shape=3.0, cost_km=(20.0, 32.0), pace=1.6),
    "Bridge/ROB/Flyover": dict(len_mean=3.0, len_shape=2.5, cost_km=(70.0, 140.0), pace=0.3),
}

CONTRACTOR_PREFIXES = [
    "Bharat", "Uttam", "Rashtriya", "Trimurti", "Suvidha", "Prakash",
    "Shivalik", "Vishwas", "Ganga", "Deccan", "Konkan", "Sahyadri",
    "Malwa", "Meridian", "Continental", "Apex", "Horizon", "Vertex",
    "Sunrise", "Skyline", "Vindhya", "Narmada", "Satpura", "Aravalli",
]
CONTRACTOR_SUFFIXES = [
    "Infraprojects Pvt Ltd", "Infrastructure Ltd", "Constructions Pvt Ltd",
    "Engineering & Constructions Ltd", "Builders Pvt Ltd", "Highways Ltd",
    "Roadways Pvt Ltd", "Projects Ltd",
]
N_CONTRACTORS = 50


@dataclass
class Contractor:
    name: str
    quality: float  # productivity multiplier, ~1.0 = average


@dataclass
class ProjectStatic:
    project_id: str
    project_name: str
    highway_number: str
    state: str
    project_type: str
    contractor: Contractor
    project_length_km: float
    original_contract_value_inr_cr: float
    planned_start_date: pd.Timestamp
    planned_completion_date: pd.Timestamp
    planned_duration_months: int
    risk_propensity: float = field(repr=False)
    supply_chain_risk: float = field(repr=False)
    design_maturity: float = field(repr=False)


def build_contractor_pool(rng: np.random.Generator) -> list[Contractor]:
    names: set[str] = set()
    contractors: list[Contractor] = []
    while len(contractors) < N_CONTRACTORS:
        name = f"{rng.choice(CONTRACTOR_PREFIXES)} {rng.choice(CONTRACTOR_SUFFIXES)}"
        if name in names:
            continue
        names.add(name)
        quality = float(np.clip(rng.normal(1.0, 0.15), 0.5, 1.3))
        contractors.append(Contractor(name=name, quality=quality))
    return contractors


def sample_project_static(
    rng: np.random.Generator, index: int, contractor_pool: list[Contractor]
) -> ProjectStatic:
    project_type = rng.choice(PROJECT_TYPES, p=PROJECT_TYPE_WEIGHTS)
    params = PROJECT_TYPE_PARAMS[project_type]

    length_km = float(np.clip(rng.gamma(params["len_shape"], params["len_mean"] / params["len_shape"]), 1.0, 160.0))
    cost_per_km = rng.uniform(*params["cost_km"])
    contract_value = round(length_km * cost_per_km * rng.uniform(0.9, 1.15), 2)

    pace = params["pace"] * rng.uniform(0.8, 1.2)
    duration_months = int(np.clip(round(length_km / pace) + rng.integers(3, 7), 12, 60))

    start_date = pd.Timestamp("2019-01-01") + pd.DateOffset(months=int(rng.integers(0, 66)))
    completion_date = start_date + pd.DateOffset(months=duration_months)

    highway_number = f"NH-{rng.integers(1, 966)}"
    state = rng.choice(STATES)
    contractor = contractor_pool[rng.integers(0, len(contractor_pool))]

    type_short = project_type.split(" (")[0]
    project_name = f"{highway_number} {type_short} Package {rng.integers(1, 25)}"

    return ProjectStatic(
        project_id=f"HRI-{index + 1:04d}",
        project_name=project_name,
        highway_number=highway_number,
        state=state,
        project_type=project_type,
        contractor=contractor,
        project_length_km=round(length_km, 2),
        original_contract_value_inr_cr=contract_value,
        planned_start_date=start_date,
        planned_completion_date=completion_date,
        planned_duration_months=duration_months,
        risk_propensity=float(np.clip(rng.beta(2, 5), 0.02, 0.95)),
        supply_chain_risk=float(rng.uniform(0.5, 1.5)),
        design_maturity=float(np.clip(rng.beta(3, 3), 0.05, 0.95)),
    )


def _planned_progress_pct(month_index: int, duration_months: int) -> float:
    """S-curve planned progress; purely a function of the schedule (never leaks actuals)."""
    frac = min(month_index / duration_months, 1.0)
    return 100.0 * (3 * frac**2 - 2 * frac**3)


def _monsoon_factor(calendar_month: int, state: str) -> float:
    base = 2.6 if calendar_month in (6, 7, 8, 9) else 0.6
    return base * STATE_MONSOON_MULTIPLIER.get(state, 1.0)


def simulate_project(rng: np.random.Generator, static: ProjectStatic) -> tuple[list[dict], dict]:
    region_mult = STATE_RISK_MULTIPLIER.get(static.state, 1.0)
    max_months = max(static.planned_duration_months * MAX_SIMULATION_MONTHS_MULTIPLIER, MAX_SIMULATION_MONTHS_FLOOR)

    cum_progress = 0.0
    cum_financial = 0.0
    cum_land = cum_utility = cum_env = cum_material_d = 0.0
    cum_labour_d = cum_equipment_d = cum_weather = cum_traffic = 0.0
    cum_design = cum_approval = 0.0
    cum_material_cost = cum_labour_cost = cum_equipment_cost = 0.0
    cum_variation_cost = cum_delay_cost = 0.0
    productivity_ar = static.contractor.quality
    financial_ratio = 1.0

    size_norm = static.project_length_km / 40.0  # ~1.0 for a mid-sized project
    rows: list[dict] = []
    month_index = 0

    while month_index < max_months:
        month_index += 1
        reporting_month = static.planned_start_date + pd.DateOffset(months=month_index)
        calendar_month = reporting_month.month
        phase = min(month_index / static.planned_duration_months, 1.5)

        # --- this month's NEW delay-day contributions (contemporaneous only) ---
        land_phase = max(0.0, 1.3 - phase)  # front-loaded
        p_land = float(np.clip(static.risk_propensity * region_mult * 0.35 * land_phase, 0, 0.85))
        land_new = rng.exponential(9.0) if rng.random() < p_land else 0.0

        utility_phase = max(0.0, 1.1 - abs(phase - 0.3))
        p_utility = float(np.clip(static.risk_propensity * region_mult * 0.30 * utility_phase, 0, 0.8))
        utility_new = rng.exponential(7.0) if rng.random() < p_utility else 0.0

        env_phase = max(0.0, 1.0 - phase * 1.5)
        p_env = float(np.clip(static.risk_propensity * region_mult * 0.15 * env_phase, 0, 0.6))
        env_new = rng.exponential(14.0) if rng.random() < p_env else 0.0

        p_material = float(np.clip(0.12 * static.supply_chain_risk, 0, 0.5))
        material_new = rng.exponential(5.0) if rng.random() < p_material else 0.0

        p_labour = float(np.clip(0.15 * (1.4 - static.contractor.quality), 0, 0.5))
        labour_new = rng.exponential(4.0) if rng.random() < p_labour else 0.0

        p_equipment = float(np.clip(0.10 * (1.4 - static.contractor.quality) * (0.7 + 0.3 * size_norm), 0, 0.45))
        equipment_new = rng.exponential(4.0) if rng.random() < p_equipment else 0.0

        weather_new = rng.exponential(2.0) * _monsoon_factor(calendar_month, static.state)

        traffic_active = 1.0 if 0.15 < phase < 0.9 else 0.3
        traffic_relevant = static.project_type in ("Road Widening (2 to 4 lane)", "Road Widening (4 to 6 lane)", "Bypass/Ring Road")
        p_traffic = float(np.clip((0.12 if traffic_relevant else 0.03) * traffic_active, 0, 0.4))
        traffic_new = rng.exponential(3.0) if rng.random() < p_traffic else 0.0

        p_design = float(np.clip(0.10 * (1.2 - static.design_maturity) * max(0.0, 1.2 - phase), 0, 0.4))
        design_new = rng.exponential(10.0) if rng.random() < p_design else 0.0

        p_approval = float(np.clip(0.08 * (1.2 - static.design_maturity) * region_mult, 0, 0.35))
        approval_new = rng.exponential(8.0) if rng.random() < p_approval else 0.0

        cum_land += land_new
        cum_utility += utility_new
        cum_env += env_new
        cum_material_d += material_new
        cum_labour_d += labour_new
        cum_equipment_d += equipment_new
        cum_weather += weather_new
        cum_traffic += traffic_new
        cum_design += design_new
        cum_approval += approval_new

        # --- contractor productivity this month (AR(1), contemporaneous) ---
        shock = rng.normal(0, 0.05)
        productivity_ar = float(np.clip(0.85 * productivity_ar + 0.15 * static.contractor.quality + shock, 0.35, 1.35))
        friction_days = land_new + utility_new + env_new + material_new + labour_new + equipment_new + weather_new + traffic_new
        productivity_effective = productivity_ar * float(np.clip(1 - 0.01 * friction_days, 0.15, 1.05))

        # --- physical progress ---
        baseline_increment = 100.0 / static.planned_duration_months
        actual_increment = max(0.0, baseline_increment * productivity_effective + rng.normal(0, 0.6))
        cum_progress = float(np.clip(cum_progress + actual_increment, 0.0, 100.0))

        # --- financial progress (tracks physical with slow independent drift) ---
        financial_ratio = float(np.clip(financial_ratio + rng.normal(0, 0.03), 0.85, 1.15))
        cum_financial = float(np.clip(cum_financial + actual_increment * financial_ratio, 0.0, 100.0))

        # --- cost ---
        core_increment_value = static.original_contract_value_inr_cr * actual_increment / 100.0
        cost_efficiency = float(np.clip(rng.normal(1.0 / static.contractor.quality, 0.05), 0.8, 1.3))
        core_increment_cost = core_increment_value * cost_efficiency
        cum_material_cost += core_increment_cost * rng.uniform(0.50, 0.60)
        cum_labour_cost += core_increment_cost * rng.uniform(0.22, 0.28)
        cum_equipment_cost += core_increment_cost * rng.uniform(0.15, 0.22)

        variation_increment = (design_new + approval_new) * rng.uniform(0.02, 0.05) * (static.original_contract_value_inr_cr / static.planned_duration_months)
        cum_variation_cost += variation_increment

        delay_increment = friction_days * rng.uniform(0.01, 0.025) * (0.5 + 0.5 * size_norm)
        cum_delay_cost += delay_increment

        planned_pct = _planned_progress_pct(month_index, static.planned_duration_months)
        planned_cost_to_date = static.original_contract_value_inr_cr * planned_pct / 100.0
        actual_cost_to_date = cum_material_cost + cum_labour_cost + cum_equipment_cost + cum_variation_cost + cum_delay_cost

        rows.append(
            {
                "project_id": static.project_id,
                "project_name": static.project_name,
                "highway_number": static.highway_number,
                "state": static.state,
                "project_type": static.project_type,
                "contractor": static.contractor.name,
                "project_length_km": static.project_length_km,
                "original_contract_value_inr_cr": static.original_contract_value_inr_cr,
                "planned_start_date": static.planned_start_date.date().isoformat(),
                "planned_completion_date": static.planned_completion_date.date().isoformat(),
                "planned_duration_months": static.planned_duration_months,
                "reporting_month": reporting_month.strftime("%Y-%m"),
                "months_since_start": month_index,
                "project_status": "Ongoing",  # corrected to "Completed" on the final row after the loop
                "planned_physical_progress_pct": round(planned_pct, 2),
                "actual_physical_progress_pct": round(cum_progress, 2),
                "physical_progress_variance_pct": round(cum_progress - planned_pct, 2),
                "planned_financial_progress_pct": round(planned_pct, 2),
                "actual_financial_progress_pct": round(cum_financial, 2),
                "financial_progress_variance_pct": round(cum_financial - planned_pct, 2),
                "planned_expenditure_inr_cr": round(planned_cost_to_date, 2),
                "actual_expenditure_inr_cr": round(static.original_contract_value_inr_cr * cum_financial / 100.0, 2),
                "expenditure_variance_pct": round(cum_financial - planned_pct, 2),
                "land_acquisition_delay_days": round(cum_land, 1),
                "utility_shifting_delay_days": round(cum_utility, 1),
                "environment_clearance_delay_days": round(cum_env, 1),
                "material_delay_days": round(cum_material_d, 1),
                "labour_shortage_days": round(cum_labour_d, 1),
                "equipment_unavailability_days": round(cum_equipment_d, 1),
                "weather_disruption_days": round(cum_weather, 1),
                "contractor_productivity_factor": round(productivity_ar, 3),
                "traffic_diversion_delay_days": round(cum_traffic, 1),
                "design_change_delay_days": round(cum_design, 1),
                "approval_delay_days": round(cum_approval, 1),
                "planned_cost_to_date_inr_cr": round(planned_cost_to_date, 2),
                "actual_cost_to_date_inr_cr": round(actual_cost_to_date, 2),
                "material_cost_inr_cr": round(cum_material_cost, 2),
                "labour_cost_inr_cr": round(cum_labour_cost, 2),
                "equipment_cost_inr_cr": round(cum_equipment_cost, 2),
                "variation_cost_inr_cr": round(cum_variation_cost, 2),
                "delay_related_cost_inr_cr": round(cum_delay_cost, 2),
            }
        )

        if cum_progress >= 100.0:
            break

    rows[-1]["project_status"] = "Completed"
    final_reporting_month = static.planned_start_date + pd.DateOffset(months=month_index)
    final_delay_days = int((final_reporting_month - static.planned_completion_date).days)
    final_actual_cost = rows[-1]["actual_cost_to_date_inr_cr"]
    final_cost_overrun_pct = round(
        (final_actual_cost - static.original_contract_value_inr_cr) / static.original_contract_value_inr_cr * 100.0, 2
    )
    targets = {
        "final_delay_days": final_delay_days,
        "significant_delay": int(final_delay_days > SIGNIFICANT_DELAY_THRESHOLD_DAYS),
        "final_cost_overrun_pct": final_cost_overrun_pct,
        "cost_overrun": int(final_cost_overrun_pct > COST_OVERRUN_THRESHOLD_PCT),
    }
    for row in rows:
        row.update(targets)

    return rows, targets


def apply_missingness(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    df = df.copy()
    n = len(df)

    financial_gap = rng.random(n) < 0.04
    df.loc[financial_gap, ["actual_financial_progress_pct", "financial_progress_variance_pct", "actual_expenditure_inr_cr", "expenditure_variance_pct"]] = np.nan

    df.loc[rng.random(n) < 0.01, "contractor"] = np.nan
    df.loc[rng.random(n) < 0.03, "equipment_unavailability_days"] = np.nan
    df.loc[rng.random(n) < 0.03, "weather_disruption_days"] = np.nan
    df.loc[rng.random(n) < 0.03, "variation_cost_inr_cr"] = np.nan

    return df


def generate_dataset(n_projects: int = N_PROJECTS, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    contractor_pool = build_contractor_pool(rng)

    all_rows: list[dict] = []
    for i in range(n_projects):
        static = sample_project_static(rng, i, contractor_pool)
        rows, _ = simulate_project(rng, static)
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    df.insert(0, "data_provenance", "SYNTHETIC")
    df = apply_missingness(df, rng)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-projects", type=int, default=N_PROJECTS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    print("*** Generating SYNTHETIC highway project data. Not real NHAI/MoRTH data. ***")
    df = generate_dataset(n_projects=args.n_projects, seed=args.seed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)

    print(f"\nWrote {len(df):,} rows x {len(df.columns)} columns -> {args.output}")
    print(f"Unique projects: {df['project_id'].nunique():,}")
    print(f"Reporting months: {df['reporting_month'].min()} .. {df['reporting_month'].max()}")
    print("\nTarget distributions:")
    print(f"  significant_delay=1: {df.groupby('project_id')['significant_delay'].first().mean():.1%} of projects")
    print(f"  cost_overrun=1:      {df.groupby('project_id')['cost_overrun'].first().mean():.1%} of projects")
    print(f"  final_delay_days:    mean={df.groupby('project_id')['final_delay_days'].first().mean():.1f}, "
          f"median={df.groupby('project_id')['final_delay_days'].first().median():.1f}")
    print(f"  final_cost_overrun_pct: mean={df.groupby('project_id')['final_cost_overrun_pct'].first().mean():.1f}%, "
          f"median={df.groupby('project_id')['final_cost_overrun_pct'].first().median():.1f}%")


if __name__ == "__main__":
    main()
