"""Isolated training behaviour for deterministic batches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch
import torch.nn as nn


@dataclass(frozen=True)
class TrainingTrace:
    """Loss history from repeated optimization."""

    losses: tuple[float, ...]
    initial_loss: float
    final_loss: float
    steps: int
    decreased: bool


class SmallBatchTrainer:
    """Optimize a controlled batch through the training path."""

    def __init__(
        self,
        *,
        model: nn.Module,
        device: str | torch.device,
        learning_rate: float,
        weight_decay: float = 0.0,
        gradient_clip_norm: float = 1.0,
        positive_weights: Sequence[float] | None = None,
        use_bfloat16: bool = True,
    ) -> None:
        if learning_rate <= 0.0:
            raise ValueError("learning_rate must be positive.")

        if weight_decay < 0.0:
            raise ValueError("weight_decay cannot be negative.")

        if gradient_clip_norm <= 0.0:
            raise ValueError("gradient_clip_norm must be positive.")

        self.device = torch.device(device)
        self.model = model.to(self.device)
        self.gradient_clip_norm = gradient_clip_norm
        self.use_bfloat16 = bool(use_bfloat16)

        trainable_parameters = [
            parameter
            for parameter in (self.model.parameters())
            if parameter.requires_grad
        ]

        if not trainable_parameters:
            raise ValueError("The model has no trainable parameters.")

        if positive_weights is None:
            positive_weight_tensor = None
        else:
            positive_weight_tensor = torch.tensor(
                list(positive_weights),
                dtype=torch.float32,
                device=self.device,
            )

        self.criterion = nn.BCEWithLogitsLoss(pos_weight=positive_weight_tensor)
        self.optimizer = torch.optim.AdamW(
            trainable_parameters,
            lr=learning_rate,
            weight_decay=weight_decay,
        )

    def validate_batch(
        self,
        images: torch.Tensor,
        targets: torch.Tensor,
    ) -> None:
        """Validate one multilabel training batch."""
        if images.ndim != 4:
            raise ValueError(
                "Images must have shape " "(batch, channels, height, width)."
            )

        if targets.ndim != 2:
            raise ValueError("Targets must have shape " "(batch, labels).")

        if images.shape[0] != targets.shape[0]:
            raise ValueError("Image and target batch sizes differ.")

        if targets.shape[1] != 14:
            raise ValueError("Targets must contain 14 labels.")

        if not torch.isfinite(images).all():
            raise ValueError("Images contain non-finite values.")

        if not torch.isfinite(targets).all():
            raise ValueError("Targets contain non-finite values.")

    def train_step(
        self,
        images: torch.Tensor,
        targets: torch.Tensor,
    ) -> float:
        """Execute one optimization step."""
        self.validate_batch(images, targets)

        images = images.to(
            self.device,
            non_blocking=True,
        )
        targets = targets.to(
            self.device,
            dtype=torch.float32,
            non_blocking=True,
        )

        self.model.train()
        self.optimizer.zero_grad(set_to_none=True)

        autocast_enabled = bool(
            self.device.type == "cuda"
            and self.use_bfloat16
            and torch.cuda.is_bf16_supported()
        )

        with torch.autocast(
            device_type=self.device.type,
            dtype=torch.bfloat16,
            enabled=autocast_enabled,
        ):
            logits = self.model(images)
            loss = self.criterion(
                logits,
                targets,
            )

        if not torch.isfinite(loss):
            raise FloatingPointError("Training loss is non-finite.")

        loss.backward()

        torch.nn.utils.clip_grad_norm_(
            self.model.parameters(),
            max_norm=self.gradient_clip_norm,
        )

        self.optimizer.step()

        return float(loss.detach().cpu().item())

    def overfit_batch(
        self,
        images: torch.Tensor,
        targets: torch.Tensor,
        *,
        steps: int,
    ) -> TrainingTrace:
        """Optimize one deterministic batch repeatedly."""
        if steps < 2:
            raise ValueError("At least two optimization steps " "are required.")

        losses = tuple(self.train_step(images, targets) for _ in range(steps))

        return TrainingTrace(
            losses=losses,
            initial_loss=losses[0],
            final_loss=losses[-1],
            steps=steps,
            decreased=(losses[-1] < losses[0]),
        )
