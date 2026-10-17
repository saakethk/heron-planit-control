# Model

Contains all the code necessary for model development, data processing, and spatial visualization.

## Tools & Scripts

### 1. Power Plant & Safety Incident Visualizer (`visualize_sites_and_incidents.py`)
Calculates the spatial proximity between 346 Florida power generation sites (EIA August 2026 data) and OSHA severe injury incident reports within a configurable buffer (default: 1km / 1,000m).

- **Script:** [`model/development/eda/visualize_sites_and_incidents.py`](development/eda/visualize_sites_and_incidents.py)
- **Output Interactive Map:** [`model/development/eda/florida_power_plants_incidents_map.html`](development/eda/florida_power_plants_incidents_map.html)
- **Output CSV Report:** [`model/development/eda/incidents_within_1km_of_power_plants.csv`](development/eda/incidents_within_1km_of_power_plants.csv)

#### Usage:
```bash
# From workspace root:
python3 model/development/eda/visualize_sites_and_incidents.py

# Or from inside model/development/eda:
cd model/development/eda
python3 visualize_sites_and_incidents.py
```