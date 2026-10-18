"""Hierarchical Two-Stage Hazard Classifier.

Stage 1: Binary Hazard Detector (Benign Control vs. Active Meteorological Hazard).
Stage 2: Multi-Class Hazard Specialist (Flood, Wildfire, Lightning, Heat, Wildlife, Soil Saturation).
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, classification_report

from pipeline.model.dataset import get_stratified_dataset, IDX_TO_CLASS, CLASS_TO_IDX


class HierarchicalHazardClassifier(BaseEstimator, ClassifierMixin):
    """Two-stage hierarchical hazard classifier combining binary risk gating and multi-hazard specialization."""

    def __init__(
        self,
        max_iter: int = 250,
        learning_rate: float = 0.08,
        max_depth: int = 10,
        random_state: int = 42,
    ):
        self.max_iter = max_iter
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.random_state = random_state

        self.stage1_binary_clf: Optional[HistGradientBoostingClassifier] = None
        self.stage2_multi_clf: Optional[HistGradientBoostingClassifier] = None
        self.positive_classes_: List[int] = []

    def fit(self, X: np.ndarray, y_multi: np.ndarray, y_binary: np.ndarray):
        """Fits both Stage 1 (Binary Hazard Detector) and Stage 2 (Multi-Class Specialist)."""
        # 1. Fit Stage 1: Benign (0) vs Hazard (1)
        self.stage1_binary_clf = HistGradientBoostingClassifier(
            max_iter=self.max_iter,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            random_state=self.random_state,
        )
        self.stage1_binary_clf.fit(X, y_binary)

        # 2. Fit Stage 2 on positive hazard incidents only (classes 1..6)
        pos_mask = (y_binary == 1)
        X_pos = X[pos_mask]
        y_pos = y_multi[pos_mask]

        self.stage2_multi_clf = HistGradientBoostingClassifier(
            max_iter=self.max_iter,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            random_state=self.random_state,
        )
        self.stage2_multi_clf.fit(X_pos, y_pos)
        self.positive_classes_ = list(self.stage2_multi_clf.classes_)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Computes joint Bayesian probabilities: P(Class_k) = P(Hazard) * P(Class_k | Hazard)."""
        p_hazard = self.stage1_binary_clf.predict_proba(X)[:, 1]
        p_none = 1.0 - p_hazard

        p_s2 = self.stage2_multi_clf.predict_proba(X)

        n_samples = len(X)
        P_joint = np.zeros((n_samples, 7))
        P_joint[:, 0] = p_none

        for idx, c in enumerate(self.positive_classes_):
            P_joint[:, c] = p_hazard * p_s2[:, idx]

        # Normalize rows to ensure exact sum to 1.0
        row_sums = P_joint.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        return P_joint / row_sums

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predicts class with highest joint Bayesian probability."""
        p_joint = self.predict_proba(X)
        return np.argmax(p_joint, axis=1)

    def save(self, filepath: Union[str, Path]):
        """Serializes fitted pipeline to disk."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, filepath)

    @classmethod
    def load(cls, filepath: Union[str, Path]) -> "HierarchicalHazardClassifier":
        """Loads fitted pipeline from disk."""
        return joblib.load(filepath)


def train_and_evaluate_two_stage(max_samples_per_class: int = 500) -> Dict:
    """Trains the hierarchical classifier on the balanced dataset and outputs performance."""
    db_path = Path(__file__).resolve().parent.parent / "data" / "incidents.db"
    data = get_stratified_dataset(
        db_path,
        test_size=0.2,
        random_state=42,
        max_samples_per_class=max_samples_per_class,
    )

    X_train, X_test = data["X_train"], data["X_test"]
    y_multi_train, y_multi_test = data["y_multi_train"], data["y_multi_test"]
    y_bin_train, y_bin_test = data["y_bin_train"], data["y_bin_test"]

    model = HierarchicalHazardClassifier()
    model.fit(X_train, y_multi_train, y_bin_train)

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)

    acc = accuracy_score(y_multi_test, y_pred)
    f1_macro = f1_score(y_multi_test, y_pred, average="macro", zero_division=0)
    auc_macro = roc_auc_score(y_multi_test, y_prob, multi_class="ovr", average="macro")

    labels = [IDX_TO_CLASS[i] for i in range(7)]
    report = classification_report(y_multi_test, y_pred, target_names=labels, zero_division=0, output_dict=True)

    artifact_path = Path(__file__).resolve().parent / "artifacts" / "hierarchical_two_stage.joblib"
    model.save(artifact_path)

    return {
        "Accuracy": acc,
        "Macro F1": f1_macro,
        "Macro AUC": auc_macro,
        "Report": report,
        "ArtifactPath": str(artifact_path),
    }


if __name__ == "__main__":
    res = train_and_evaluate_two_stage()
    print("=" * 60)
    print("HIERARCHICAL TWO-STAGE HAZARD MODEL RESULTS")
    print("=" * 60)
    print(f"Accuracy:  {res['Accuracy']:.4f}")
    print(f"Macro F1:  {res['Macro F1']:.4f}")
    print(f"Macro AUC: {res['Macro AUC']:.4f}")
    print(f"Saved to:  {res['ArtifactPath']}")
