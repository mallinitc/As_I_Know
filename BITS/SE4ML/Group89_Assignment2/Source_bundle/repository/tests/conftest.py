"""Shared artifact contracts for the project test suite."""

from __future__ import annotations

import os
from pathlib import Path

SOLUTION_ROOT = Path("/home/jovyan/chest-xray-ai-assistant")
DATA_ROOT = Path("/home/jovyan/apicdsa2-datavol-1/" "chest-xray-ai-assistant-data")
SE4ML_OUTPUT_ROOT = DATA_ROOT / "outputs/se4ml_assignment2"

os.environ.setdefault(
    "CHESTMNIST_MEMMAP_ROOT",
    str(DATA_ROOT / "processed/chestmnist_224_memmap"),
)
os.environ.setdefault(
    "CHESTMNIST_CONFIG_PATH",
    str(SOLUTION_ROOT / "configs/chestmnist_config.yaml"),
)
os.environ.setdefault(
    "CHESTMNIST_MODEL_METADATA",
    str(DATA_ROOT / "models/resnet18-chestmnist-v1/" "model_metadata.yaml"),
)
os.environ.setdefault(
    "CHESTMNIST_MODEL_STATE",
    str(DATA_ROOT / "models/resnet18-chestmnist-v1/" "model_state_dict.pt"),
)
os.environ.setdefault(
    "SE4ML_TRAINING_EVIDENCE",
    str(SE4ML_OUTPUT_ROOT / "test_results/" "training_behavior_test_results.json"),
)
os.environ.setdefault(
    "SE4ML_PARITY_EVIDENCE",
    str(SE4ML_OUTPUT_ROOT / "research_production/" "research_production_parity.json"),
)
