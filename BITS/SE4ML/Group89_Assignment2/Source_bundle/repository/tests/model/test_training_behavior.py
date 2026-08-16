"""Behavioural test for the ResNet-18 training path."""

from __future__ import annotations

import json
import os
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Subset
from torchvision import transforms

from src.data import ChestMNISTMemmapDataset
from src.models import ResNet18Factory
from src.training import SmallBatchTrainer

IMAGENET_MEAN = (
    0.485,
    0.456,
    0.406,
)
IMAGENET_STANDARD_DEVIATION = (
    0.229,
    0.224,
    0.225,
)


def test_small_batch_loss_decreases() -> None:
    """Repeated optimization must reduce controlled-batch loss."""
    seed = 42
    batch_size = 8
    optimization_steps = 20

    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    data_root = Path(os.environ["CHESTMNIST_MEMMAP_ROOT"])

    evidence_path = Path(os.environ["SE4ML_TRAINING_EVIDENCE"])

    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=IMAGENET_MEAN,
                std=(IMAGENET_STANDARD_DEVIATION),
            ),
        ]
    )

    dataset = ChestMNISTMemmapDataset(
        data_root=data_root,
        split="train",
        transform=transform,
    )

    deterministic_subset = Subset(
        dataset,
        list(range(batch_size)),
    )

    data_loader = DataLoader(
        deterministic_subset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
    )

    images, targets, indexes = next(iter(data_loader))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = ResNet18Factory.build(
        weights=None,
        classifier_dropout=0.0,
    )
    model = ResNet18Factory.freeze_backbone(model)

    parameter_counts = ResNet18Factory.parameter_counts(model)

    trainer = SmallBatchTrainer(
        model=model,
        device=device,
        learning_rate=0.02,
        weight_decay=0.0,
        gradient_clip_norm=1.0,
        use_bfloat16=False,
    )

    try:
        trace = trainer.overfit_batch(
            images,
            targets,
            steps=optimization_steps,
        )

        loss_reduction = trace.initial_loss - trace.final_loss
        relative_reduction = loss_reduction / trace.initial_loss

        result = {
            "test_name": ("test_small_batch_loss_decreases"),
            "seed": seed,
            "device": str(device),
            "batch_size": batch_size,
            "batch_indexes": [int(index) for index in indexes.tolist()],
            "optimization_steps": (optimization_steps),
            "initial_loss": (trace.initial_loss),
            "final_loss": trace.final_loss,
            "loss_reduction": loss_reduction,
            "relative_reduction": (relative_reduction),
            "losses": list(trace.losses),
            "total_parameters": (parameter_counts["total"]),
            "trainable_parameters": (parameter_counts["trainable"]),
            "backbone_frozen": True,
            "checkpoint_written": False,
            "passed": (trace.final_loss < trace.initial_loss),
        }

        evidence_path.write_text(
            json.dumps(
                result,
                indent=2,
            ),
            encoding="utf-8",
        )

        assert torch.isfinite(torch.tensor(trace.losses)).all()
        assert trace.final_loss < (trace.initial_loss)

    finally:
        del trainer
        del model
        del images
        del targets

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
