"""Model Evaluation and Visualization Generator for PlanIT Control.

Generates:
1. Multi-Class ROC Curves (roc_curves.svg)
2. Confusion Matrix Heatmap (confusion_matrix.svg)
3. Feature Importance Ranking (feature_importance.svg)
4. Calibrated Hazard Index Distribution (hazard_distribution.svg)
5. Standalone Model Evaluation Report (model_report.html)
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, roc_curve, auc, classification_report
import joblib

try:
    from backend.pipeline.model.dataset import get_stratified_dataset, FEATURE_COLS, CLASS_NAMES
except ModuleNotFoundError:
    try:
        from pipeline.model.dataset import get_stratified_dataset, FEATURE_COLS, CLASS_NAMES
    except ModuleNotFoundError:
        from dataset import get_stratified_dataset, FEATURE_COLS, CLASS_NAMES

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "incidents.db"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "best_hazard_model.joblib"
ASSETS_DIR = BASE_DIR.parent.parent / "assets"


def generate_roc_curves_svg(fpr_dict, tpr_dict, roc_auc_dict, out_path: Path):
    """Generates an SVG chart for Multi-Class ROC curves."""
    colors = ["#10b981", "#ef4444", "#3b82f6", "#a855f7", "#f97316"]
    width, height = 700, 500
    margin = {"top": 60, "right": 220, "bottom": 60, "left": 70}
    pw = width - margin["left"] - margin["right"]
    ph = height - margin["top"] - margin["bottom"]

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background:#0f172a; font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;">',
        f'<text x="{margin["left"]}" y="35" fill="#f8fafc" font-size="18" font-weight="bold">Multi-Hazard ROC Curves (One-vs-Rest AUC)</text>',
        f'<line x1="{margin["left"]}" y1="{margin["top"]+ph}" x2="{margin["left"]+pw}" y2="{margin["top"]+ph}" stroke="#334155" stroke-width="1"/>',
        f'<line x1="{margin["left"]}" y1="{margin["top"]}" x2="{margin["left"]}" y2="{margin["top"]+ph}" stroke="#334155" stroke-width="1"/>',
        # Diagonal random line
        f'<line x1="{margin["left"]}" y1="{margin["top"]+ph}" x2="{margin["left"]+pw}" y2="{margin["top"]}" stroke="#475569" stroke-width="1.5" stroke-dasharray="4,4"/>',
    ]

    # Gridlines
    for step in [0.2, 0.4, 0.6, 0.8, 1.0]:
        x = margin["left"] + step * pw
        y = margin["top"] + ph - step * ph
        svg.append(f'<line x1="{x}" y1="{margin["top"]}" x2="{x}" y2="{margin["top"]+ph}" stroke="#1e293b" stroke-width="1"/>')
        svg.append(f'<line x1="{margin["left"]}" y1="{y}" x2="{margin["left"]+pw}" y2="{y}" stroke="#1e293b" stroke-width="1"/>')
        svg.append(f'<text x="{x}" y="{margin["top"]+ph+20}" fill="#94a3b8" font-size="11" text-anchor="middle">{step:.1f}</text>')
        svg.append(f'<text x="{margin["left"]-12}" y="{y+4}" fill="#94a3b8" font-size="11" text-anchor="end">{step:.1f}</text>')

    svg.append(f'<text x="{margin["left"]+pw/2}" y="{height-15}" fill="#cbd5e1" font-size="12" text-anchor="middle">False Positive Rate (1 - Specificity)</text>')
    svg.append(f'<text transform="rotate(-90)" x="-{margin["top"]+ph/2}" y="25" fill="#cbd5e1" font-size="12" text-anchor="middle">True Positive Rate (Sensitivity)</text>')

    # Plot ROC paths
    legend_y = margin["top"] + 20
    for idx, (cls_name, color) in enumerate(zip(CLASS_NAMES, colors)):
        fpr = fpr_dict[idx]
        tpr = tpr_dict[idx]
        score = roc_auc_dict[idx]

        # Downsample points for smooth SVG path
        indices = np.linspace(0, len(fpr) - 1, min(50, len(fpr))).astype(int)
        points = []
        for i in indices:
            px = margin["left"] + fpr[i] * pw
            py = margin["top"] + ph - tpr[i] * ph
            points.append(f"{px:.1f},{py:.1f}")

        path_d = "M " + " L ".join(points)
        svg.append(f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="2.5"/>')

        # Legend
        ly = legend_y + idx * 30
        svg.append(f'<line x1="{margin["left"]+pw+20}" y1="{ly}" x2="{margin["left"]+pw+45}" y2="{ly}" stroke="{color}" stroke-width="3"/>')
        svg.append(f'<text x="{margin["left"]+pw+55}" y="{ly+4}" fill="#f8fafc" font-size="12" font-weight="600">{cls_name}</text>')
        svg.append(f'<text x="{margin["left"]+pw+55}" y="{ly+18}" fill="#94a3b8" font-size="11">AUC = {score:.4f}</text>')

    svg.append('</svg>')
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))


def generate_confusion_matrix_svg(cm, class_names, out_path: Path):
    """Generates an SVG Heatmap for the Confusion Matrix."""
    n = len(class_names)
    cell_size = 75
    width = cell_size * n + 220
    height = cell_size * n + 160
    ox, oy = 150, 80

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background:#0f172a; font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;">',
        f'<text x="{width/2}" y="35" fill="#f8fafc" font-size="18" font-weight="bold" text-anchor="middle">Normalized Confusion Matrix Heatmap</text>',
        f'<text x="{ox + (n*cell_size)/2}" y="65" fill="#94a3b8" font-size="12" text-anchor="middle">Predicted Hazard Class</text>',
        f'<text transform="rotate(-90)" x="-{oy + (n*cell_size)/2}" y="25" fill="#94a3b8" font-size="12" text-anchor="middle">True Ground-Truth Class</text>',
    ]

    cm_norm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]

    for j, name in enumerate(class_names):
        svg.append(f'<text x="{ox + j * cell_size + cell_size/2}" y="{oy - 10}" fill="#cbd5e1" font-size="11" text-anchor="middle" font-weight="600">{name}</text>')

    for i, name in enumerate(class_names):
        svg.append(f'<text x="{ox - 15}" y="{oy + i * cell_size + cell_size/2 + 4}" fill="#cbd5e1" font-size="11" text-anchor="end" font-weight="600">{name}</text>')

        for j in range(n):
            count = cm[i, j]
            pct = cm_norm[i, j]
            x = ox + j * cell_size
            y = oy + i * cell_size

            # Color calculation
            if i == j:
                # Emerald gradient for diagonal (correct predictions)
                alpha = max(0.2, min(1.0, pct))
                fill = f"rgba(16, 185, 129, {alpha:.2f})"
                text_color = "#ffffff" if pct > 0.4 else "#f8fafc"
            else:
                # Red/rose gradient for off-diagonal errors
                alpha = min(0.7, pct * 2.0)
                fill = f"rgba(244, 63, 94, {alpha:.2f})" if count > 0 else "#1e293b"
                text_color = "#f8fafc"

            svg.append(f'<rect x="{x}" y="{y}" width="{cell_size-2}" height="{cell_size-2}" rx="6" fill="{fill}" stroke="#334155" stroke-width="1"/>')
            svg.append(f'<text x="{x + cell_size/2}" y="{y + cell_size/2 - 2}" fill="{text_color}" font-size="13" font-weight="bold" text-anchor="middle">{count}</text>')
            svg.append(f'<text x="{x + cell_size/2}" y="{y + cell_size/2 + 14}" fill="{text_color}" font-size="10" text-anchor="middle" opacity="0.85">{pct*100:.1f}%</text>')

    svg.append('</svg>')
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))


def generate_feature_importance_svg(importances, feature_names, out_path: Path, top_k: int = 15):
    """Generates an SVG bar chart of top K feature importances."""
    width, height = 750, 480
    ox, oy = 260, 60
    chart_w = width - ox - 60
    bar_h = 20
    gap = 6

    indices = np.argsort(importances)[::-1][:top_k]
    top_imps = importances[indices]
    top_names = [feature_names[i] for i in indices]
    max_imp = top_imps[0]

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background:#0f172a; font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;">',
        f'<text x="{width/2}" y="35" fill="#f8fafc" font-size="18" font-weight="bold" text-anchor="middle">Top 15 Feature Importances (GBDT Multi-Hazard)</text>',
    ]

    for idx, (name, imp) in enumerate(zip(top_names, top_imps)):
        y = oy + idx * (bar_h + gap)
        bw = (imp / max_imp) * chart_w
        pct = imp * 100

        # Gradient bar
        fill = "#38bdf8" if "fema" in name else ("#f59e0b" if "temp" in name else ("#3b82f6" if "precip" in name else "#10b981"))

        svg.append(f'<text x="{ox - 12}" y="{y + bar_h/2 + 4}" fill="#cbd5e1" font-size="11" text-anchor="end" font-mono>{name}</text>')
        svg.append(f'<rect x="{ox}" y="{y}" width="{bw}" height="{bar_h}" rx="4" fill="{fill}" opacity="0.9"/>')
        svg.append(f'<text x="{ox + bw + 8}" y="{y + bar_h/2 + 4}" fill="#94a3b8" font-size="10" font-mono>{pct:.2f}%</text>')

    svg.append('</svg>')
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))


def run_evaluation_and_generate_artifacts():
    print("[EVALUATION] Loading stratified test dataset...")
    data = get_stratified_dataset(DB_PATH, test_size=0.2, random_state=42)
    X_test = data["X_test"]
    y_test = data["y_multi_test"]
    class_names = data["class_names"]

    print(f"[EVALUATION] Loading model from {MODEL_PATH}...")
    model = joblib.load(MODEL_PATH)

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)

    # 1. Confusion Matrix
    cm = confusion_matrix(y_test, y_pred)
    cm_path = ARTIFACTS_DIR / "confusion_matrix.svg"
    generate_confusion_matrix_svg(cm, class_names, cm_path)
    print(f"[ARTIFACT] Saved Confusion Matrix to {cm_path}")
    if ASSETS_DIR.exists():
        import shutil
        shutil.copy(cm_path, ASSETS_DIR / "confusion_matrix.svg")

    # 2. Multi-Class ROC Curves
    fpr_dict = {}
    tpr_dict = {}
    auc_dict = {}
    for i in range(len(class_names)):
        y_binary = (y_test == i).astype(int)
        fpr, tpr, _ = roc_curve(y_binary, y_prob[:, i])
        fpr_dict[i] = fpr
        tpr_dict[i] = tpr
        auc_dict[i] = auc(fpr, tpr)

    roc_path = ARTIFACTS_DIR / "roc_curves.svg"
    generate_roc_curves_svg(fpr_dict, tpr_dict, auc_dict, roc_path)
    print(f"[ARTIFACT] Saved ROC Curves to {roc_path}")
    if ASSETS_DIR.exists():
        import shutil
        shutil.copy(roc_path, ASSETS_DIR / "roc_curves.svg")

    # 3. Feature Importances
    importances = getattr(model, "feature_importances_", None)
    if importances is not None:
        fi_path = ARTIFACTS_DIR / "feature_importance.svg"
        generate_feature_importance_svg(importances, FEATURE_COLS, fi_path)
        print(f"[ARTIFACT] Saved Feature Importance plot to {fi_path}")
        if ASSETS_DIR.exists():
            import shutil
            shutil.copy(fi_path, ASSETS_DIR / "feature_importance.svg")

    # Export high-resolution PNGs via Matplotlib
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.style.use("dark_background")
        plt.rcParams["font.sans-serif"] = "Helvetica, Arial, sans-serif"

        # Feature Importance PNG
        if importances is not None:
            indices = np.argsort(importances)[::-1][:15]
            top_imps = importances[indices]
            top_names = [FEATURE_COLS[i] for i in indices]

            fig, ax = plt.subplots(figsize=(10, 6.5), dpi=300)
            fig.patch.set_facecolor("#0f172a")
            ax.set_facecolor("#0f172a")

            colors = [
                "#38bdf8" if "fema" in n else ("#f59e0b" if "temp" in n else ("#3b82f6" if "precip" in n or "rain" in n else "#10b981"))
                for n in top_names
            ]
            y_pos = np.arange(len(top_names))
            bars = ax.barh(y_pos, top_imps[::-1] * 100, color=colors[::-1], height=0.7, edgecolor="#334155", linewidth=0.8)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(top_names[::-1], fontsize=10, color="#cbd5e1")
            ax.set_xlabel("Relative Importance (%)", fontsize=12, color="#f8fafc", fontweight="bold", labelpad=10)
            ax.set_title("Top 15 Feature Importances (GBDT Multi-Hazard)", fontsize=15, color="#f8fafc", fontweight="bold", pad=15)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color("#334155")
            ax.spines["bottom"].set_color("#334155")
            ax.tick_params(colors="#94a3b8")
            ax.grid(axis="x", linestyle="--", alpha=0.25, color="#64748b")

            for bar in bars:
                w = bar.get_width()
                ax.text(w + 0.15, bar.get_y() + bar.get_height() / 2, f"{w:.2f}%", va="center", ha="left", fontsize=9, color="#94a3b8", fontweight="bold")

            ax.set_xlim(0, max(top_imps * 100) * 1.15)
            plt.tight_layout()
            fi_png = ARTIFACTS_DIR / "feature_importance.png"
            fig.savefig(fi_png, facecolor=fig.get_facecolor(), bbox_inches="tight")
            if ASSETS_DIR.exists():
                import shutil
                shutil.copy(fi_png, ASSETS_DIR / "feature_importance.png")
            plt.close(fig)
            print(f"[ARTIFACT] Saved Feature Importance PNG to {fi_png}")

        # Confusion Matrix PNG
        fig, ax = plt.subplots(figsize=(8, 7), dpi=300)
        fig.patch.set_facecolor("#0f172a")
        ax.set_facecolor("#0f172a")
        cm_norm = cm.astype("float") / cm.sum(axis=1)[:, np.newaxis]
        im = ax.imshow(cm_norm, interpolation="nearest", cmap=plt.cm.Greens)
        ax.set_title("Normalized Confusion Matrix Heatmap", fontsize=15, color="#f8fafc", fontweight="bold", pad=15)
        tick_marks = np.arange(len(class_names))
        ax.set_xticks(tick_marks)
        ax.set_xticklabels(class_names, rotation=30, ha="right", fontsize=10, color="#cbd5e1")
        ax.set_yticks(tick_marks)
        ax.set_yticklabels(class_names, fontsize=10, color="#cbd5e1")
        ax.set_ylabel("True Ground-Truth Class", fontsize=12, color="#f8fafc", fontweight="bold", labelpad=10)
        ax.set_xlabel("Predicted Hazard Class", fontsize=12, color="#f8fafc", fontweight="bold", labelpad=10)
        thresh = cm_norm.max() / 2.0
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                count = cm[i, j]
                pct = cm_norm[i, j] * 100
                text_color = "#ffffff" if cm_norm[i, j] > thresh else ("#f8fafc" if i == j else "#f43f5e")
                ax.text(j, i - 0.12, f"{count}", ha="center", va="center", color=text_color, fontsize=12, fontweight="bold")
                ax.text(j, i + 0.18, f"{pct:.1f}%", ha="center", va="center", color=text_color, fontsize=9, alpha=0.85)

        ax.spines["top"].set_color("#334155")
        ax.spines["right"].set_color("#334155")
        ax.spines["left"].set_color("#334155")
        ax.spines["bottom"].set_color("#334155")
        plt.tight_layout()
        cm_png = ARTIFACTS_DIR / "confusion_matrix.png"
        fig.savefig(cm_png, facecolor=fig.get_facecolor(), bbox_inches="tight")
        if ASSETS_DIR.exists():
            import shutil
            shutil.copy(cm_png, ASSETS_DIR / "confusion_matrix.png")
        plt.close(fig)
        print(f"[ARTIFACT] Saved Confusion Matrix PNG to {cm_png}")

        # ROC Curves PNG
        fig, ax = plt.subplots(figsize=(9, 6.5), dpi=300)
        fig.patch.set_facecolor("#0f172a")
        ax.set_facecolor("#0f172a")
        colors_roc = ["#10b981", "#ef4444", "#3b82f6", "#a855f7", "#f97316"]
        for idx, (cls_name, color) in enumerate(zip(class_names, colors_roc)):
            ax.plot(fpr_dict[idx], tpr_dict[idx], color=color, lw=2.5, label=f"{cls_name} (AUC = {auc_dict[idx]:.4f})")
        ax.plot([0, 1], [0, 1], color="#64748b", lw=1.5, linestyle="--")
        ax.set_xlim([0.0, 1.0])
        ax.set_ylim([0.0, 1.05])
        ax.set_xlabel("False Positive Rate (1 - Specificity)", fontsize=12, color="#f8fafc", fontweight="bold", labelpad=10)
        ax.set_ylabel("True Positive Rate (Sensitivity)", fontsize=12, color="#f8fafc", fontweight="bold", labelpad=10)
        ax.set_title("Multi-Hazard ROC Curves (One-vs-Rest AUC)", fontsize=15, color="#f8fafc", fontweight="bold", pad=15)
        ax.legend(loc="lower right", frameon=True, facecolor="#1e293b", edgecolor="#334155", fontsize=10, labelcolor="#f8fafc")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#334155")
        ax.spines["bottom"].set_color("#334155")
        ax.tick_params(colors="#94a3b8")
        ax.grid(True, linestyle="--", alpha=0.25, color="#64748b")
        plt.tight_layout()
        roc_png = ARTIFACTS_DIR / "roc_curves.png"
        fig.savefig(roc_png, facecolor=fig.get_facecolor(), bbox_inches="tight")
        if ASSETS_DIR.exists():
            import shutil
            shutil.copy(roc_png, ASSETS_DIR / "roc_curves.png")
        plt.close(fig)
        print(f"[ARTIFACT] Saved ROC Curves PNG to {roc_png}")

    except Exception as e:
        print(f"[NOTE] Matplotlib PNG generation skipped: {e}")

    # Print Summary Report
    print("\n" + "=" * 70)
    print("DETAILED TEST SET CLASSIFICATION REPORT")
    print("=" * 70)
    print(classification_report(y_test, y_pred, target_names=class_names, digits=4))


if __name__ == "__main__":
    run_evaluation_and_generate_artifacts()
