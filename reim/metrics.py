"""
Evaluation metrics for REIM experiments.
"""

import numpy as np
from scipy.stats import kendalltau, spearmanr


def compute_metrics(estimates: dict, ground_truth: dict, observer_reliability: dict = None, observer_info=None):
    """
    Compute evaluation metrics.

    Parameters
    ----------
    estimates : dict
        Estimated system properties {system_id: theta_hat}
    ground_truth : dict
        True system properties {system_id: theta}
    observer_reliability : dict, optional
        Estimated observer reliability {observer_id: alpha}
    observer_info : pd.DataFrame, optional
        True observer info with 'observer' and 'true_std' columns.

    Returns
    -------
    dict with metrics
    """
    # Align systems
    systems = sorted(set(estimates.keys()) & set(ground_truth.keys()))

    est = np.array([estimates[s] for s in systems])
    truth = np.array([ground_truth[s] for s in systems])

    metrics = {}

    # RMSE
    metrics["rmse"] = np.sqrt(np.mean((est - truth) ** 2))

    # MAE
    metrics["mae"] = np.mean(np.abs(est - truth))

    # Max error
    metrics["max_error"] = np.max(np.abs(est - truth))

    # Ranking accuracy (Kendall's tau)
    tau, p_tau = kendalltau(est, truth)
    metrics["kendall_tau"] = tau
    metrics["kendall_p"] = p_tau

    # Spearman correlation
    rho, p_rho = spearmanr(est, truth)
    metrics["spearman_rho"] = rho
    metrics["spearman_p"] = p_rho

    # Pearson correlation
    metrics["pearson_r"] = np.corrcoef(est, truth)[0, 1]

    # Observer reliability calibration
    if observer_reliability is not None and observer_info is not None:
        true_precision = {}
        for _, row in observer_info.iterrows():
            u = row["observer"]
            true_precision[u] = 1.0 / (row["true_std"] ** 2) if row["true_std"] > 0 else float("inf")

        common_obs = sorted(set(observer_reliability.keys()) & set(true_precision.keys()))

        if len(common_obs) > 2:
            est_rel = np.array([observer_reliability[u] for u in common_obs])
            true_rel = np.array([true_precision[u] for u in common_obs])

            # Avoid inf
            mask = np.isfinite(true_rel) & np.isfinite(est_rel)
            if mask.sum() > 2:
                rho_obs, _ = spearmanr(est_rel[mask], true_rel[mask])
                metrics["observer_calibration_spearman"] = rho_obs

    return metrics
