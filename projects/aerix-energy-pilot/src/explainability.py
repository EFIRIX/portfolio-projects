from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


try:
    import shap

    SHAP_AVAILABLE = True
except Exception:
    shap = None  # type: ignore[assignment]
    SHAP_AVAILABLE = False


def _is_tree_model(model: Any) -> bool:
    name = model.__class__.__name__.lower()
    return any(token in name for token in ["forest", "lgbm", "boosting", "tree"])


def generate_shap_explainability(
    model: Any,
    X_test: pd.DataFrame,
    output_dir: str | Path = "outputs",
    max_samples: int = 1000,
) -> dict[str, Any]:
    """
    Compute optional SHAP explainability for tree-based models.

    Saves:
    - shap_summary.png
    - shap_feature_importance.png
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / "shap_summary.png"
    importance_path = out_dir / "shap_feature_importance.png"

    if not SHAP_AVAILABLE:
        return {
            "status": "skipped",
            "reason": "shap_not_installed",
            "summary_path": str(summary_path),
            "importance_path": str(importance_path),
        }

    if model is None or not _is_tree_model(model):
        return {
            "status": "skipped",
            "reason": "model_not_supported",
            "summary_path": str(summary_path),
            "importance_path": str(importance_path),
        }

    if X_test is None or len(X_test) == 0:
        return {
            "status": "skipped",
            "reason": "empty_test_features",
            "summary_path": str(summary_path),
            "importance_path": str(importance_path),
        }

    try:
        sample_size = min(max_samples, len(X_test))
        X_sample = X_test.sample(n=sample_size, random_state=42) if len(X_test) > sample_size else X_test.copy()

        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_sample)

        plt.figure(figsize=(10, 6))
        shap.summary_plot(shap_values, X_sample, show=False)
        plt.tight_layout()
        plt.savefig(summary_path, dpi=150)
        plt.close()

        if isinstance(shap_values, list):
            # Multiclass safeguard; use first class for regression-like fallback.
            values = np.array(shap_values[0])
        else:
            values = np.array(shap_values)

        mean_abs_shap = np.abs(values).mean(axis=0)
        importance_df = pd.DataFrame(
            {
                "feature": list(X_sample.columns),
                "importance": mean_abs_shap,
            }
        ).sort_values("importance", ascending=False)

        plt.figure(figsize=(10, 6))
        plt.barh(importance_df["feature"].iloc[::-1], importance_df["importance"].iloc[::-1], color="#4F7BFF")
        plt.xlabel("Mean |SHAP value|")
        plt.title("SHAP Feature Importance")
        plt.tight_layout()
        plt.savefig(importance_path, dpi=150)
        plt.close()

        return {
            "status": "ok",
            "reason": "",
            "summary_path": str(summary_path),
            "importance_path": str(importance_path),
        }
    except Exception as exc:
        return {
            "status": "skipped",
            "reason": f"shap_failed: {exc}",
            "summary_path": str(summary_path),
            "importance_path": str(importance_path),
        }
