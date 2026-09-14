// Every key below is a member of scripts.prepare_features.PREDICTOR_COLUMNS
// (the backend's exact permitted what-if override list -- see
// backend/app/simulation/overrides.py) restricted to the fields a reviewer
// would plausibly want to hypothesize about. Nothing here is a field the
// backend would reject.
export const SIMULATOR_FIELDS = [
  { key: 'land_acquisition_delay_days', label: 'Land Acquisition Delay (days)', min: 0, step: 1 },
  { key: 'utility_shifting_delay_days', label: 'Utility Shifting Delay (days)', min: 0, step: 1 },
  { key: 'environment_clearance_delay_days', label: 'Environment Clearance Delay (days)', min: 0, step: 1 },
  { key: 'material_delay_days', label: 'Material Delay (days)', min: 0, step: 1 },
  { key: 'labour_shortage_days', label: 'Labour Shortage (days)', min: 0, step: 1 },
  { key: 'equipment_unavailability_days', label: 'Equipment Unavailability (days)', min: 0, step: 1 },
  { key: 'weather_disruption_days', label: 'Weather Disruption (days)', min: 0, step: 1 },
  { key: 'traffic_diversion_delay_days', label: 'Traffic Diversion Delay (days)', min: 0, step: 1 },
  { key: 'design_change_delay_days', label: 'Design Change Delay (days)', min: 0, step: 1 },
  { key: 'approval_delay_days', label: 'Approval Delay (days)', min: 0, step: 1 },
  { key: 'contractor_productivity_factor', label: 'Contractor Productivity Factor', min: 0, step: 0.01 },
  { key: 'planned_physical_progress_pct', label: 'Planned Physical Progress (%)', min: 0, max: 100, step: 0.5 },
  { key: 'actual_physical_progress_pct', label: 'Actual Physical Progress (%)', min: 0, max: 100, step: 0.5 },
  { key: 'planned_financial_progress_pct', label: 'Planned Financial Progress (%)', min: 0, max: 100, step: 0.5 },
  { key: 'actual_financial_progress_pct', label: 'Actual Financial Progress (%)', min: 0, max: 100, step: 0.5 },
]
