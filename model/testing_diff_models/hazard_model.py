"""
Multi-Task Hazard Prediction Model (Binary & Multi-Class Classification)
========================================================================
Architecture: Multi-Task Deep Neural Network with shared weather representation backbone
- Head 1 (Binary): Outputs P(Incident) in [0, 1] using Sigmoid
- Head 2 (Multi-Class): Outputs class probability distribution in [0, 1] using Softmax
  Classes: Not Incident, Extreme Heat, Flood, Lightning, Soil Saturation, Wildfire, Wildlife
"""

import sys
import os
import json
import argparse
from pathlib import Path

# Automatically inject workspace venv site-packages if needed
def _find_workspace_root():
    curr = Path(__file__).resolve().parent
    while curr != curr.parent:
        if (curr / ".venv").exists() or (curr / ".git").exists():
            return curr
        curr = curr.parent
    return Path.cwd()

WORKSPACE_ROOT = _find_workspace_root()
_venv_site = WORKSPACE_ROOT / ".venv" / "lib" / "python3.13" / "site-packages"
if _venv_site.exists() and str(_venv_site) not in sys.path:
    sys.path.insert(0, str(_venv_site))

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader


# --------------------------------------------------------------------------
# Multi-Task PyTorch Neural Network Architecture
# --------------------------------------------------------------------------
class MultiTaskHazardNet(nn.Module):
    """
    Dual-headed neural network for simultaneous binary risk prediction
    and multi-class hazard type classification with confidence metrics in [0, 1].
    """
    def __init__(self, input_dim: int, num_classes: int = 7, hidden_dim: int = 128, dropout_rate: float = 0.25):
        super().__init__()
        
        # Shared Feature Representation Backbone
        self.shared_backbone = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.SiLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.SiLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dim, 64),
            nn.LayerNorm(64),
            nn.SiLU(),
        )
        
        # Head 1: Binary Incident Risk Head (Outputs 1 logit -> Sigmoid)
        self.binary_head = nn.Sequential(
            nn.Linear(64, 32),
            nn.SiLU(),
            nn.Dropout(0.15),
            nn.Linear(32, 1)
        )
        
        # Head 2: Multi-class Hazard Type Head (Outputs num_classes logits -> Softmax)
        self.multi_head = nn.Sequential(
            nn.Linear(64, 32),
            nn.SiLU(),
            nn.Dropout(0.15),
            nn.Linear(32, num_classes)
        )

    def forward(self, x):
        features = self.shared_backbone(x)
        binary_logits = self.binary_head(features)
        multi_logits = self.multi_head(features)
        return binary_logits, multi_logits

    def predict_confidences(self, x):
        """Returns calibrated probability / confidence scores in [0, 1]."""
        self.eval()
        with torch.no_grad():
            bin_logits, multi_logits = self.forward(x)
            bin_conf = torch.sigmoid(bin_logits)
            multi_conf = torch.softmax(multi_logits, dim=-1)
        return bin_conf, multi_conf


# --------------------------------------------------------------------------
# High-Level Predictor Class for Inference
# --------------------------------------------------------------------------
class HazardPredictor:
    """Production predictor that accepts raw weather dicts / DataFrames."""
    def __init__(self, model: MultiTaskHazardNet, feature_cols: list, mean: np.ndarray, std: np.ndarray, classes: list):
        self.model = model
        self.feature_cols = feature_cols
        self.mean = np.array(mean, dtype=np.float32)
        self.std = np.array(std, dtype=np.float32)
        self.std[self.std == 0] = 1.0
        self.classes = classes
        self.class_to_idx = {c: i for i, c in enumerate(classes)}

    def predict(self, weather_input) -> dict:
        """
        Accepts a dict or DataFrame of weather features and returns confidence scores:
        {
            'is_incident': bool,
            'incident_confidence': float in [0, 1],
            'predicted_hazard_type': str,
            'hazard_type_confidence': float in [0, 1],
            'hazard_probabilities': {type: float}
        }
        """
        if isinstance(weather_input, dict):
            # Extract features in expected order, default 0.0 if missing
            arr = np.array([[weather_input.get(f, 0.0) for f in self.feature_cols]], dtype=np.float32)
        elif isinstance(weather_input, pd.DataFrame):
            arr = weather_input[self.feature_cols].values.astype(np.float32)
        else:
            arr = np.array(weather_input, dtype=np.float32)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)

        # Standardize using training statistics
        norm_x = (arr - self.mean) / self.std
        tensor_x = torch.tensor(norm_x, dtype=torch.float32)

        bin_conf, multi_conf = self.model.predict_confidences(tensor_x)
        bin_conf = bin_conf.numpy()
        multi_conf = multi_conf.numpy()

        results = []
        for i in range(len(arr)):
            b_conf = float(bin_conf[i, 0])
            m_probs = multi_conf[i]
            top_class_idx = int(np.argmax(m_probs))
            top_class = self.classes[top_class_idx]
            top_class_conf = float(m_probs[top_class_idx])

            prob_dict = {self.classes[j]: round(float(m_probs[j]), 4) for j in range(len(self.classes))}

            results.append({
                "is_incident": bool(b_conf >= 0.5),
                "incident_confidence": round(b_conf, 4),
                "predicted_hazard_type": top_class,
                "hazard_type_confidence": round(top_class_conf, 4),
                "hazard_probabilities": prob_dict
            })

        return results[0] if len(results) == 1 else results

    def save(self, model_dir: str):
        """Saves model weights and preprocessing parameters."""
        os.makedirs(model_dir, exist_ok=True)
        weights_path = os.path.join(model_dir, "hazard_model.pt")
        meta_path = os.path.join(model_dir, "model_metadata.json")

        torch.save(self.model.state_dict(), weights_path)
        metadata = {
            "feature_cols": self.feature_cols,
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "classes": self.classes,
            "input_dim": len(self.feature_cols),
            "num_classes": len(self.classes)
        }
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        print(f"-> Model saved to: {weights_path}")
        print(f"-> Metadata saved to: {meta_path}")

    @classmethod
    def load(cls, model_dir: str):
        """Loads a saved HazardPredictor instance."""
        weights_path = os.path.join(model_dir, "hazard_model.pt")
        meta_path = os.path.join(model_dir, "model_metadata.json")

        with open(meta_path) as f:
            meta = json.load(f)

        model = MultiTaskHazardNet(input_dim=meta["input_dim"], num_classes=meta["num_classes"])
        model.load_state_dict(torch.load(weights_path, map_location="cpu"))
        model.eval()

        return cls(
            model=model,
            feature_cols=meta["feature_cols"],
            mean=np.array(meta["mean"]),
            std=np.array(meta["std"]),
            classes=meta["classes"]
        )


# --------------------------------------------------------------------------
# Training & Evaluation Pipeline
# --------------------------------------------------------------------------
def load_and_preprocess_dataset(csv_path: str):
    """Loads dataset and prepares features and multi-task labels."""
    df = pd.read_csv(csv_path)

    # If dataset has the duplicate label bug (identic features between True and False),
    # check and attempt to assemble from clean_data/parts if available
    features = [c for c in df.columns if c not in ["incident_type", "is_incident"]]
    
    parts_dir = Path(csv_path).parent / "parts"
    valid_p = parts_dir / "valid_incident_weather_info.csv"
    invalid_p = parts_dir / "invalid_incident_weather_info.csv"
    cat_p = parts_dir / "florida_incident_data_w_categories.csv"

    # Check if True and False have exact identical feature means
    means = df.groupby("is_incident")[features].mean()
    if len(means) == 2 and np.allclose(means.iloc[0].values, means.iloc[1].values) and valid_p.exists() and invalid_p.exists():
        print("[!] Detected identical features between True and False in clean_dataset_v1.csv (combining bug).")
        print("    Rebuilding with actual invalid_incident_weather_info.csv from parts/...")
        inc_cats = pd.read_csv(cat_p)[["ID", "incident_type"]]
        valid_df = pd.read_csv(valid_p)
        invalid_df = pd.read_csv(invalid_p)

        complete_inc = pd.merge(inc_cats, valid_df, left_on="ID", right_on="associated_incident_id").drop(columns=["date", "ID", "associated_incident_id"])
        complete_non = invalid_df.drop(columns=["date", "associated_incident_id"]).copy()
        complete_non["incident_type"] = "Not Incident"

        df = pd.concat([complete_non, complete_inc]).dropna().reset_index(drop=True)
        df["is_incident"] = df["incident_type"] != "Not Incident"

    classes = sorted(df["incident_type"].unique())
    class_to_idx = {c: i for i, c in enumerate(classes)}

    X = df[features].values.astype(np.float32)
    y_bin = df["is_incident"].astype(np.float32).values[:, None]
    y_multi = df["incident_type"].map(class_to_idx).values.astype(np.int64)

    return X, y_bin, y_multi, features, classes


def train_hazard_model(
    csv_path: str,
    output_dir: str = None,
    epochs: int = 40,
    batch_size: int = 32,
    lr: float = 0.002
):
    """Executes stratified training and saves the best model."""
    if output_dir is None:
        output_dir = str(Path(__file__).resolve().parent / "saved_models")
    print(f"Loading data from: {csv_path}")
    X, y_bin, y_multi, features, classes = load_and_preprocess_dataset(csv_path)

    # Stratified Train (70%) / Val (15%) / Test (15%)
    np.random.seed(42)
    torch.manual_seed(42)

    indices = np.arange(len(X))
    train_idx, val_idx, test_idx = [], [], []

    for c_idx in range(len(classes)):
        c_samples = indices[y_multi == c_idx]
        np.random.shuffle(c_samples)
        n_train = int(0.70 * len(c_samples))
        n_val = int(0.15 * len(c_samples))
        train_idx.extend(c_samples[:n_train])
        val_idx.extend(c_samples[n_train:n_train+n_val])
        test_idx.extend(c_samples[n_train+n_val:])

    train_idx = np.array(train_idx)
    val_idx = np.array(val_idx)
    test_idx = np.array(test_idx)

    # Standardization (fit on training only)
    mean = X[train_idx].mean(axis=0)
    std = X[train_idx].std(axis=0)
    std[std == 0] = 1.0

    X_train = (X[train_idx] - mean) / std
    X_val = (X[val_idx] - mean) / std
    X_test = (X[test_idx] - mean) / std

    y_b_train, y_b_val, y_b_test = y_bin[train_idx], y_bin[val_idx], y_bin[test_idx]
    y_m_train, y_m_val, y_m_test = y_multi[train_idx], y_multi[val_idx], y_multi[test_idx]

    print(f"Split sizes: Train={len(train_idx)}, Val={len(val_idx)}, Test={len(test_idx)}")
    print(f"Classes ({len(classes)}): {classes}")

    # Compute inverse class frequencies for balanced loss weighting
    cls_counts = np.bincount(y_m_train, minlength=len(classes))
    weights = torch.tensor(len(y_m_train) / (len(classes) * np.maximum(cls_counts, 1).astype(np.float32)), dtype=torch.float32)

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Training on device: {device}")

    model = MultiTaskHazardNet(input_dim=len(features), num_classes=len(classes)).to(device)
    weights = weights.to(device)

    criterion_bin = nn.BCEWithLogitsLoss()
    criterion_multi = nn.CrossEntropyLoss(weight=weights)
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=4)

    train_loader = DataLoader(
        TensorDataset(torch.tensor(X_train), torch.tensor(y_b_train), torch.tensor(y_m_train)),
        batch_size=batch_size, shuffle=True
    )

    best_val_loss = float("inf")
    best_state = None

    for epoch in range(1, epochs + 1):
        model.train()
        total_train_loss = 0.0

        for bx, by_b, by_m in train_loader:
            bx, by_b, by_m = bx.to(device), by_b.to(device), by_m.to(device)
            optimizer.zero_grad()
            out_b, out_m = model(bx)
            loss = criterion_bin(out_b, by_b) + 1.2 * criterion_multi(out_m, by_m)
            loss.backward()
            optimizer.step()
            total_train_loss += loss.item() * len(bx)

        train_loss = total_train_loss / len(train_idx)

        # Validation
        model.eval()
        with torch.no_grad():
            vx = torch.tensor(X_val).to(device)
            vb = torch.tensor(y_b_val).to(device)
            vm = torch.tensor(y_m_val).to(device)
            v_out_b, v_out_m = model(vx)
            val_loss = (criterion_bin(v_out_b, vb) + 1.2 * criterion_multi(v_out_m, vm)).item()

        scheduler.step(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = model.state_dict().copy()

        if epoch % 5 == 0 or epoch == epochs:
            print(f"Epoch {epoch:02d}/{epochs:02d} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}")

    if best_state is not None:
        model.load_state_dict(best_state)

    # Test Evaluation
    model.eval()
    with torch.no_grad():
        tx = torch.tensor(X_test).to(device)
        test_out_b, test_out_m = model(tx)
        pred_b_conf = torch.sigmoid(test_out_b).cpu().numpy().flatten()
        pred_b = (pred_b_conf >= 0.5).astype(int)
        pred_m_conf = torch.softmax(test_out_m, dim=1).cpu().numpy()
        pred_m = np.argmax(pred_m_conf, axis=1)

    bin_acc = (pred_b == y_b_test.flatten()).mean()
    multi_acc = (pred_m == y_m_test).mean()

    print("\n" + "=" * 55)
    print("FINAL TEST EVALUATION")
    print("=" * 55)
    print(f"Binary Incident Accuracy:      {bin_acc * 100:.2f}%")
    print(f"Multi-class Hazard Accuracy:   {multi_acc * 100:.2f}%")
    print("-" * 55)
    print("Per-Class Accuracy on Test Set:")
    for i, c in enumerate(classes):
        mask = (y_m_test == i)
        c_acc = (pred_m[mask] == i).mean() if mask.sum() > 0 else 0.0
        print(f"  {c:34s}: {c_acc * 100:5.1f}% ({mask.sum()} test samples)")
    print("=" * 55)

    # Save Predictor
    model.to("cpu")
    predictor = HazardPredictor(
        model=model,
        feature_cols=features,
        mean=mean,
        std=std,
        classes=classes
    )
    predictor.save(output_dir)
    return predictor


# --------------------------------------------------------------------------
# CLI Execution & Demo
# --------------------------------------------------------------------------
if __name__ == "__main__":
    script_dir = Path(__file__).resolve().parent
    default_data = WORKSPACE_ROOT / "model" / "clean_data" / "clean_dataset_v1.csv"
    default_output = script_dir / "saved_models"

    parser = argparse.ArgumentParser(description="Train Multi-Task Hazard Model")
    parser.add_argument("--data", default=str(default_data), help="Path to clean dataset CSV")
    parser.add_argument("--output-dir", default=str(default_output), help="Directory to save model weights")
    parser.add_argument("--epochs", type=int, default=35, help="Number of training epochs")
    args = parser.parse_args()

    predictor = train_hazard_model(
        csv_path=args.data,
        output_dir=args.output_dir,
        epochs=args.epochs
    )

    # Demonstration Prediction on Sample Data
    print("\nRunning test inference on sample high-heat weather profile:")
    sample_weather = {
        "weather_code": 0,
        "temperature_2m_mean": 32.5,
        "temperature_2m_max": 37.8,  # ~100 F
        "temperature_2m_min": 26.0,
        "apparent_temperature_mean": 38.0,
        "apparent_temperature_max": 43.5,  # Extreme heat index ~110 F
        "apparent_temperature_min": 28.0,
        "precipitation_sum": 0.0,
        "rain_sum": 0.0,
        "snowfall_sum": 0.0,
        "precipitation_hours": 0.0,
        "wind_speed_10m_max": 12.0,
        "wind_gusts_10m_max": 25.0,
        "shortwave_radiation_sum": 28.5,
        "et0_fao_evapotranspiration": 6.2,
        "relative_humidity_2m_mean": 75.0,
        "relative_humidity_2m_max": 88.0,
        "relative_humidity_2m_min": 52.0,
        "soil_moisture_0_to_100cm_mean": 0.12,
        "soil_temperature_0_to_100cm_mean": 31.0
    }

    result = predictor.predict(sample_weather)
    print(json.dumps(result, indent=2))
