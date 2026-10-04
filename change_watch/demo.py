import numpy as np


def synthetic_pair(seed=42, size=320):
    """Create an illustrative image pair and exact synthetic change mask."""
    if size < 64:
        raise ValueError("Synthetic demo size must be at least 64 pixels.")
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[:size, :size] / size
    noise = rng.integers(-8, 9, size=(size, size, 1))
    terrain = np.clip(np.array([124, 139, 89]) + noise, 0, 255).astype(np.uint8)
    river = np.abs(x - (0.16 + 0.025 * np.sin(14 * y))) < 0.018
    terrain[river] = [71, 116, 141]
    road = np.abs(y - (0.18 + 0.1 * x)) < 0.008
    terrain[road] = [160, 147, 118]
    old_pit = ((x - 0.63) / 0.10) ** 2 + ((y - 0.57) / 0.12) ** 2 < 1
    expanded_pit = ((x - 0.66) / 0.19) ** 2 + ((y - 0.58) / 0.19) ** 2 < 1
    before = terrain.copy()
    before[old_pit] = [150, 139, 119]
    truth = expanded_pit & ~old_pit
    after = before.copy()
    after[truth] = [216, 200, 174]
    return before, after, truth
