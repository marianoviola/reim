"""
Synthetic data generator for REIM experiments.

Generates controlled datasets with known ground truth for validation.
"""

import numpy as np
import pandas as pd
from typing import Optional


class SyntheticDataGenerator:
    """
    Generate synthetic observation data with known ground truth.

    Parameters
    ----------
    n_systems : int
        Number of systems.
    n_observers : int
        Number of observers.
    density : float, default=1.0
        Fraction of (observer, system) pairs that produce observations.
        1.0 = fully observed, 0.1 = very sparse.
    noise_type : str, default="gaussian"
        Distribution of observation noise: "gaussian", "heavy_tailed", "asymmetric".
    adversarial_fraction : float, default=0.0
        Fraction of observers that are adversarial (produce inverted ratings).
    reliable_noise_std : float, default=0.2
        Noise std for reliable observers.
    noisy_noise_std : float, default=0.8
        Noise std for noisy (but honest) observers.
    adversarial_noise_std : float, default=0.5
        Noise std for adversarial observers (around inverted value).
    observer_profile : str, default="mixed"
        "mixed" = 50% reliable, 30% noisy, 20% adversarial (of non-adversarial).
        "uniform" = all observers have the same noise level.
    seed : int or None, default=None
        Random seed for reproducibility.
    """

    def __init__(
        self,
        n_systems: int = 50,
        n_observers: int = 200,
        density: float = 1.0,
        noise_type: str = "gaussian",
        adversarial_fraction: float = 0.0,
        reliable_noise_std: float = 0.2,
        noisy_noise_std: float = 0.8,
        adversarial_noise_std: float = 0.5,
        observer_profile: str = "mixed",
        seed: Optional[int] = None,
    ):
        self.n_systems = n_systems
        self.n_observers = n_observers
        self.density = density
        self.noise_type = noise_type
        self.adversarial_fraction = adversarial_fraction
        self.reliable_noise_std = reliable_noise_std
        self.noisy_noise_std = noisy_noise_std
        self.adversarial_noise_std = adversarial_noise_std
        self.observer_profile = observer_profile
        self.seed = seed

    def generate(self):
        """
        Generate synthetic dataset.

        Returns
        -------
        observations : pd.DataFrame
            Columns: ['observer', 'system', 'value']
        ground_truth : dict
            True property values {system_id: theta}
        observer_info : pd.DataFrame
            Observer metadata: ['observer', 'type', 'true_std']
        """
        rng = np.random.default_rng(self.seed)

        # Generate true system properties (uniform in [1, 5] like ratings)
        theta_true = {f"s_{i}": rng.uniform(1.0, 5.0) for i in range(self.n_systems)}

        # Assign observer types
        n_adversarial = int(self.n_observers * self.adversarial_fraction)
        n_honest = self.n_observers - n_adversarial

        observer_types = []
        observer_stds = []

        if self.observer_profile == "mixed":
            n_reliable = int(n_honest * 0.5)
            n_noisy = n_honest - n_reliable

            for _ in range(n_reliable):
                observer_types.append("reliable")
                observer_stds.append(self.reliable_noise_std)
            for _ in range(n_noisy):
                observer_types.append("noisy")
                observer_stds.append(self.noisy_noise_std)
        else:  # uniform
            for _ in range(n_honest):
                observer_types.append("honest")
                observer_stds.append(self.reliable_noise_std)

        for _ in range(n_adversarial):
            observer_types.append("adversarial")
            observer_stds.append(self.adversarial_noise_std)

        observer_info = pd.DataFrame(
            {
                "observer": [f"u_{i}" for i in range(self.n_observers)],
                "type": observer_types,
                "true_std": observer_stds,
            }
        )

        # Generate observations
        records = []
        systems = list(theta_true.keys())
        observers = list(observer_info["observer"])

        for i, u in enumerate(observers):
            # Determine which systems this observer sees
            if self.density < 1.0:
                n_obs = max(1, int(self.n_systems * self.density))
                observed_systems = rng.choice(systems, size=n_obs, replace=False)
            else:
                observed_systems = systems

            for s in observed_systems:
                true_val = theta_true[s]
                std = observer_stds[i]
                obs_type = observer_types[i]

                # Generate noise
                if obs_type == "adversarial":
                    # Adversarial: invert around midpoint (3.0 for [1,5])
                    midpoint = 3.0
                    base = 2 * midpoint - true_val
                    noise = self._generate_noise(rng, std)
                    value = base + noise
                else:
                    noise = self._generate_noise(rng, std)
                    value = true_val + noise

                # Clip to valid range
                value = np.clip(value, 1.0, 5.0)

                records.append({"observer": u, "system": s, "value": value})

        observations = pd.DataFrame(records)
        return observations, theta_true, observer_info

    def _generate_noise(self, rng, std):
        """Generate noise according to noise_type."""
        if self.noise_type == "gaussian":
            return rng.normal(0, std)
        elif self.noise_type == "heavy_tailed":
            # Student-t with df=3 (heavier tails than Gaussian)
            return rng.standard_t(df=3) * std * 0.5
        elif self.noise_type == "asymmetric":
            # Skewed noise (e.g., positive bias)
            return abs(rng.normal(0, std)) * 0.5
        else:
            raise ValueError(f"Unknown noise_type: {self.noise_type}")
