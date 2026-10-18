"""Central Configuration for PlanIT Control Pipeline and API."""

from pathlib import Path

# Workspace Root
ROOT_DIR = Path(__file__).resolve().parent.parent
PIPELINE_DIR = ROOT_DIR / "pipeline"

# Data Directories & Storage
DATA_DIR = PIPELINE_DIR / "data"
DB_PATH = DATA_DIR / "incidents.db"
WEATHER_CACHE_PATH = DATA_DIR / ".weather_cache.sqlite"
EVENT_STREAM_JSONL_PATH = DATA_DIR / "event_stream.jsonl"
EIA_EXCEL_PATH = DATA_DIR / "eia860m.xlsx"

# Model Directories & Artifacts
MODEL_DIR = PIPELINE_DIR / "model"
ARTIFACTS_DIR = MODEL_DIR / "artifacts"
BEST_MODEL_PATH = ARTIFACTS_DIR / "best_hazard_model.joblib"
HAZARD_SCALER_PATH = ARTIFACTS_DIR / "hazard_scaler.joblib"
HAZARD_NET_PATH = ARTIFACTS_DIR / "best_hazard_net.pt"

# API & Streaming Network Settings
API_HOST = "127.0.0.1"
API_PORT = 8000
STREAM_PORT = 8050
USER_AGENT = "(PlanIT-Control-Jobsite-Safety, contact@planitcontrol.org)"

# Safety Guardrail Thresholds
LIGHTNING_STOP_WORK_MILES = 10.0
HEAT_INDEX_ADVISORY_F = 105.0
HEAT_INDEX_STOP_WORK_F = 115.0
FEMA_SFHA_RAIN_THRESHOLD_MM = 25.0

# Continuous Training Settings
RETRAIN_SAMPLE_BATCH_TRIGGER = 50
MIN_VALIDATION_F1_HOTSWAP = 0.80
