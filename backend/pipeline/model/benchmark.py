"""Benchmarks all candidate architectures on the uniform stratified test set.

Architectures evaluated:
1. Logistic Regression (Linear baseline with class weights)
2. Random Forest Classifier (Tree ensemble with balanced class weights)
3. Histogram Gradient Boosting (Modern GBDT with sample weights)
4. Multi-Task Deep Neural Net (PyTorch MultiTaskHazardNet with Focal Loss)
"""

from pathlib import Path
import time
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, classification_report
import torch

from pipeline.model.dataset import get_stratified_dataset, IDX_TO_CLASS
from pipeline.model.hazard_net import train_hazard_net


def evaluate_predictions(y_true, y_pred, y_prob=None, average="macro"):
    """Calculates accuracy, macro F1, weighted F1, and multi-class AUC if probabilities present."""
    acc = accuracy_score(y_true, y_pred)
    f1_macro = f1_score(y_true, y_pred, average="macro", zero_division=0)
    f1_weighted = f1_score(y_true, y_pred, average="weighted", zero_division=0)

    auc = None
    if y_prob is not None:
        try:
            auc = roc_auc_score(y_true, y_prob, multi_class="ovr", average="macro")
        except Exception:
            auc = None

    return {
        "Accuracy": acc,
        "Macro F1": f1_macro,
        "Weighted F1": f1_weighted,
        "Macro AUC": auc,
    }


def run_benchmark():
    db_path = Path(__file__).resolve().parent.parent / "data" / "incidents.db"
    print(f"[BENCHMARK] Loading uniform stratified dataset from {db_path.name}...")
    data = get_stratified_dataset(db_path, test_size=0.2, random_state=42)

    X_train_raw = data["X_train"]
    X_test_raw = data["X_test"]
    X_train_scaled = data["X_train_scaled"]
    X_test_scaled = data["X_test_scaled"]

    y_train = data["y_multi_train"]
    y_test = data["y_multi_test"]
    y_bin_train = data["y_bin_train"]
    y_bin_test = data["y_bin_test"]

    class_names = data["class_names"]

    # Sample weights for tree models to handle class imbalance
    classes, counts = np.unique(y_train, return_counts=True)
    weight_map = {c: len(y_train) / (len(classes) * cnt) for c, cnt in zip(classes, counts)}
    sample_weights_train = np.array([weight_map[y] for y in y_train])

    models_results = []

    print("\n" + "=" * 70)
    print(f"BENCHMARKING CANDIDATE ARCHITECTURES ({len(class_names)}-Class Meteorological Hazards)")
    print("=" * 70)

    # --------------------------------------------------------------------------
    # 1. Baseline: Logistic Regression
    # --------------------------------------------------------------------------
    print("\n--> 1/4: Training Logistic Regression (Balanced)...")
    t0 = time.time()
    lr_model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    lr_model.fit(X_train_scaled, y_train)
    t_train_lr = time.time() - t0
    y_pred_lr = lr_model.predict(X_test_scaled)
    y_prob_lr = lr_model.predict_proba(X_test_scaled)
    m_lr = evaluate_predictions(y_test, y_pred_lr, y_prob_lr)
    m_lr["Model"] = "Logistic Regression"
    m_lr["Train Time (s)"] = t_train_lr
    models_results.append(m_lr)

    # --------------------------------------------------------------------------
    # 2. Random Forest
    # --------------------------------------------------------------------------
    print("--> 2/4: Training Random Forest (Balanced Subsample)...")
    t0 = time.time()
    rf_model = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )
    rf_model.fit(X_train_raw, y_train)
    t_train_rf = time.time() - t0
    y_pred_rf = rf_model.predict(X_test_raw)
    y_prob_rf = rf_model.predict_proba(X_test_raw)
    m_rf = evaluate_predictions(y_test, y_pred_rf, y_prob_rf)
    m_rf["Model"] = "Random Forest"
    m_rf["Train Time (s)"] = t_train_rf
    models_results.append(m_rf)

    # --------------------------------------------------------------------------
    # 3. Histogram Gradient Boosting (Modern GBDT)
    # --------------------------------------------------------------------------
    print("--> 3/4: Training Histogram Gradient Boosting (GBDT)...")
    t0 = time.time()
    gbdt_model = HistGradientBoostingClassifier(
        max_iter=150,
        learning_rate=0.08,
        max_leaf_nodes=31,
        random_state=42,
    )
    gbdt_model.fit(X_train_raw, y_train, sample_weight=sample_weights_train)
    t_train_gbdt = time.time() - t0
    y_pred_gbdt = gbdt_model.predict(X_test_raw)
    y_prob_gbdt = gbdt_model.predict_proba(X_test_raw)
    m_gbdt = evaluate_predictions(y_test, y_pred_gbdt, y_prob_gbdt)
    m_gbdt["Model"] = "Hist Gradient Boosting (GBDT)"
    m_gbdt["Train Time (s)"] = t_train_gbdt
    models_results.append(m_gbdt)

    # --------------------------------------------------------------------------
    # 4. Multi-Task Deep Neural Net (PyTorch + Focal Loss)
    # --------------------------------------------------------------------------
    print("--> 4/4: Training Multi-Task PyTorch HazardNet (Focal Loss)...")
    t0 = time.time()
    nn_model = train_hazard_net(
        X_train=X_train_scaled,
        y_bin_train=y_bin_train,
        y_multi_train=y_train,
        X_val=X_test_scaled,
        y_bin_val=y_bin_test,
        y_multi_val=y_test,
        epochs=35,
        batch_size=64,
        lr=0.001,
    )
    t_train_nn = time.time() - t0

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    X_test_t = torch.tensor(X_test_scaled, dtype=torch.float32).to(device)
    _, p_classes_nn = nn_model.predict(X_test_t)
    y_pred_nn = np.argmax(p_classes_nn, axis=1)

    m_nn = evaluate_predictions(y_test, y_pred_nn, p_classes_nn)
    m_nn["Model"] = "Multi-Task HazardNet (PyTorch)"
    m_nn["Train Time (s)"] = t_train_nn
    models_results.append(m_nn)

    # --------------------------------------------------------------------------
    # Comparison Summary Table
    # --------------------------------------------------------------------------
    res_df = pd.DataFrame(models_results)
    cols = ["Model", "Accuracy", "Macro F1", "Weighted F1", "Macro AUC", "Train Time (s)"]
    res_df = res_df[cols].sort_values(by="Macro F1", ascending=False).reset_index(drop=True)

    print("\n" + "=" * 70)
    print("UNIFORM BENCHMARK PERFORMANCE COMPARISON")
    print("=" * 70)
    print(res_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # Per-Class breakdown of best model
    best_model_name = res_df.iloc[0]["Model"]
    print(f"\n--> Detailed Classification Report for top model ({best_model_name}):")
    if best_model_name == "Hist Gradient Boosting (GBDT)":
        best_preds = y_pred_gbdt
    elif best_model_name == "Random Forest":
        best_preds = y_pred_rf
    elif best_model_name == "Multi-Task HazardNet (PyTorch)":
        best_preds = y_pred_nn
    else:
        best_preds = y_pred_lr

    target_labels = class_names
    print(classification_report(y_test, best_preds, target_names=target_labels, zero_division=0))

    import joblib
    artifact_dir = Path(__file__).resolve().parent / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if best_model_name == "Multi-Task HazardNet (PyTorch)":
        torch.save(nn_model.state_dict(), artifact_dir / "best_hazard_net.pt")
        joblib.dump(gbdt_model, artifact_dir / "best_hazard_model.joblib")
    elif best_model_name == "Hist Gradient Boosting (GBDT)":
        joblib.dump(gbdt_model, artifact_dir / "best_hazard_model.joblib")
    else:
        joblib.dump(rf_model, artifact_dir / "best_hazard_model.joblib")

    joblib.dump(data["scaler"], artifact_dir / "hazard_scaler.joblib")
    print(f"\n[ARTIFACT] Saved top model ({best_model_name}) and scaler to {artifact_dir}/")

    return res_df


if __name__ == "__main__":
    run_benchmark()
