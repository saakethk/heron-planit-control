"""Multi-Task PyTorch Neural Network Architecture and Trainer for Hazard Prediction."""

from pathlib import Path
from typing import Dict, Tuple
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset


class FocalLoss(nn.Module):
    """Multi-class Focal Loss for imbalanced target classes."""
    def __init__(self, alpha: torch.Tensor = None, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.ce = nn.CrossEntropyLoss(weight=alpha, reduction="none")

    def forward(self, inputs, targets):
        ce_loss = self.ce(inputs, targets)
        pt = torch.exp(-ce_loss)
        focal_loss = ((1 - pt) ** self.gamma) * ce_loss
        return focal_loss.mean()


class MultiTaskHazardNet(nn.Module):
    """Dual-head neural network:

    - Head 1: Binary risk prediction (incident vs no incident)
    - Head 2: Multi-class hazard classification across the 5 categories
    """
    def __init__(self, input_dim: int = 24, num_classes: int = 5, hidden_dim: int = 128, dropout_rate: float = 0.2):
        super().__init__()
        self.shared_backbone = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.SiLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dim, 64),
            nn.BatchNorm1d(64),
            nn.SiLU(),
            nn.Dropout(dropout_rate),
        )

        # Binary Head (P(Incident))
        self.binary_head = nn.Sequential(
            nn.Linear(64, 32),
            nn.SiLU(),
            nn.Linear(32, 1),
        )

        # Multi-class Hazard Type Head
        self.multi_head = nn.Sequential(
            nn.Linear(64, 32),
            nn.SiLU(),
            nn.Linear(32, num_classes),
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        features = self.shared_backbone(x)
        bin_logits = self.binary_head(features).squeeze(-1)
        multi_logits = self.multi_head(features)
        return bin_logits, multi_logits

    def predict(self, x: torch.Tensor) -> Tuple[np.ndarray, np.ndarray]:
        self.eval()
        with torch.no_grad():
            bin_logits, multi_logits = self.forward(x)
            p_incident = torch.sigmoid(bin_logits).cpu().numpy()
            p_classes = torch.softmax(multi_logits, dim=-1).cpu().numpy()
        return p_incident, p_classes


def train_hazard_net(
    X_train: np.ndarray,
    y_bin_train: np.ndarray,
    y_multi_train: np.ndarray,
    X_val: np.ndarray,
    y_bin_val: np.ndarray,
    y_multi_val: np.ndarray,
    epochs: int = 35,
    batch_size: int = 64,
    lr: float = 0.001,
) -> MultiTaskHazardNet:
    """Trains the Multi-Task network with balanced focal loss."""
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

    # Compute class weights inversely proportional to frequencies
    classes, counts = np.unique(y_multi_train, return_counts=True)
    weights = len(y_multi_train) / (len(classes) * counts)
    class_weights_t = torch.tensor(weights, dtype=torch.float32).to(device)

    # Tensor conversions
    train_dataset = TensorDataset(
        torch.tensor(X_train, dtype=torch.float32),
        torch.tensor(y_bin_train, dtype=torch.float32),
        torch.tensor(y_multi_train, dtype=torch.long),
    )
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

    model = MultiTaskHazardNet(input_dim=X_train.shape[1], num_classes=len(classes)).to(device)
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    bce_loss_fn = nn.BCEWithLogitsLoss()
    focal_loss_fn = FocalLoss(alpha=class_weights_t, gamma=2.0)

    model.train()
    for epoch in range(epochs):
        for bx, by_bin, by_multi in train_loader:
            bx = bx.to(device)
            by_bin = by_bin.to(device)
            by_multi = by_multi.to(device)

            optimizer.zero_grad()
            out_bin, out_multi = model(bx)

            loss_bin = bce_loss_fn(out_bin, by_bin)
            loss_multi = focal_loss_fn(out_multi, by_multi)

            # Joint multi-task objective
            loss = loss_bin + 1.2 * loss_multi
            loss.backward()
            optimizer.step()

    return model
