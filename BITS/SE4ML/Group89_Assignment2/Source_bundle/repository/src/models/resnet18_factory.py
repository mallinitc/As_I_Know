"""Reusable ResNet-18 construction for ChestMNIST."""

from __future__ import annotations

import torch.nn as nn
from torchvision.models import ResNet18_Weights, resnet18

NUM_LABELS = 14
CLASSIFIER_DROPOUT = 0.20


class ResNet18Factory:
    """Construct the fixed multilabel ResNet-18 architecture."""

    @staticmethod
    def build(
        *,
        weights: ResNet18_Weights | None = (
            ResNet18_Weights.IMAGENET1K_V1
        ),
        num_labels: int = NUM_LABELS,
        classifier_dropout: float = (
            CLASSIFIER_DROPOUT
        ),
    ) -> nn.Module:
        """Build a ResNet-18 with a multilabel classifier."""
        if num_labels <= 0:
            raise ValueError(
                "num_labels must be positive."
            )

        if not 0.0 <= classifier_dropout < 1.0:
            raise ValueError(
                "classifier_dropout must be in [0, 1)."
            )

        model = resnet18(weights=weights)
        classifier_input_features = (
            model.fc.in_features
        )

        model.fc = nn.Sequential(
            nn.Dropout(
                p=classifier_dropout
            ),
            nn.Linear(
                classifier_input_features,
                num_labels,
            ),
        )

        return model

    @staticmethod
    def freeze_backbone(
        model: nn.Module,
    ) -> nn.Module:
        """Freeze all parameters except the classifier head."""
        for parameter in model.parameters():
            parameter.requires_grad = False

        for parameter in model.fc.parameters():
            parameter.requires_grad = True

        return model

    @staticmethod
    def parameter_counts(
        model: nn.Module,
    ) -> dict[str, int]:
        """Return total and trainable parameter counts."""
        total_parameters = sum(
            parameter.numel()
            for parameter in model.parameters()
        )
        trainable_parameters = sum(
            parameter.numel()
            for parameter in model.parameters()
            if parameter.requires_grad
        )

        return {
            "total": total_parameters,
            "trainable": (
                trainable_parameters
            ),
        }
