
"""Thread-safe visual explainability for the frozen ChestMNIST model."""

from __future__ import annotations

import base64
import io
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import torch.nn.functional as functional
from captum.attr import LayerGradCam
from PIL import Image
from torchvision import transforms


@dataclass(frozen=True)
class GradCAMResult:
    """Controlled visual evidence for one model-output label."""

    label_id: int
    label_name: str
    probability: float
    frozen_threshold: float
    threshold_decision: bool
    method: str
    target_layer: str
    heatmap_png_base64: str
    overlay_png_base64: str
    generation_latency_ms: float
    limitation: str


class GradCAMService:
    """Generate visual evidence from the frozen classification model."""

    METHOD = "LayerGradCam"
    TARGET_LAYER = "layer4[-1].conv2"

    def __init__(
        self,
        *,
        model: torch.nn.Module,
        device: torch.device | str,
        limitation: str,
        image_size: int = 224,
        overlay_alpha: float = 0.40,
    ) -> None:
        if not limitation.strip():
            raise ValueError(
                "A Grad-CAM limitation statement is required."
            )

        if image_size <= 0:
            raise ValueError(
                "The model-facing image size must be positive."
            )

        if not 0.0 <= overlay_alpha <= 1.0:
            raise ValueError(
                "The overlay alpha must be between zero and one."
            )

        self.model = model
        self.device = torch.device(device)
        self.limitation = limitation.strip()
        self.image_size = int(image_size)
        self.overlay_alpha = float(overlay_alpha)
        self._lock = threading.RLock()

        try:
            self.target_layer = (
                self.model.layer4[-1].conv2
            )
        except (AttributeError, IndexError, TypeError) as error:
            raise ValueError(
                "The frozen Grad-CAM target layer "
                "layer4[-1].conv2 is unavailable."
            ) from error

        self._preprocess = transforms.Compose(
            [
                transforms.Resize(
                    (self.image_size, self.image_size)
                ),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[
                        0.485,
                        0.456,
                        0.406,
                    ],
                    std=[
                        0.229,
                        0.224,
                        0.225,
                    ],
                ),
            ]
        )

        self.model.to(self.device)
        self.model.eval()

        self._layer_gradcam = LayerGradCam(
            self.model,
            self.target_layer,
        )

    @property
    def model_dtype(self) -> torch.dtype:
        """Return the dtype used by the model parameters."""

        return next(
            self.model.parameters()
        ).dtype

    @staticmethod
    def _read_value(
        record: Any,
        *names: str,
    ) -> Any:
        """Read a field from either a mapping or an object."""

        for name in names:
            if isinstance(record, Mapping):
                if name in record:
                    return record[name]
            elif hasattr(record, name):
                return getattr(record, name)

        raise KeyError(
            "Required finding field was not available: "
            + ", ".join(names)
        )

    @staticmethod
    def _encode_png(image: Image.Image) -> str:
        """Encode an image as a base64 PNG string."""

        buffer = io.BytesIO()
        image.save(
            buffer,
            format="PNG",
            optimize=True,
        )

        return base64.b64encode(
            buffer.getvalue()
        ).decode("ascii")

    @staticmethod
    def _normalize_attribution(
        attribution: torch.Tensor,
    ) -> np.ndarray:
        """Normalize attribution values into the zero-to-one range."""

        attribution = attribution.detach().float()

        if attribution.ndim != 4:
            raise RuntimeError(
                "Grad-CAM attribution must contain four dimensions."
            )

        if attribution.shape[1] > 1:
            attribution = attribution.mean(
                dim=1,
                keepdim=True,
            )

        attribution = attribution.squeeze(
            dim=0
        ).squeeze(
            dim=0
        )

        attribution = torch.clamp(
            attribution,
            min=0.0,
        )

        minimum = attribution.min()
        maximum = attribution.max()

        if not torch.isfinite(
            attribution
        ).all():
            raise RuntimeError(
                "Grad-CAM produced non-finite attribution values."
            )

        value_range = maximum - minimum

        if float(value_range.item()) <= 1e-12:
            normalized = torch.zeros_like(
                attribution
            )
        else:
            normalized = (
                attribution - minimum
            ) / value_range

        return normalized.cpu().numpy()

    @staticmethod
    def _build_heatmap(
        normalized_attribution: np.ndarray,
    ) -> Image.Image:
        """Convert normalized attribution into a controlled RGB heatmap."""

        attribution = np.clip(
            normalized_attribution,
            0.0,
            1.0,
        )

        red = attribution
        green = np.sqrt(
            attribution
        )
        blue = np.clip(
            1.0 - (2.0 * attribution),
            0.0,
            1.0,
        )

        heatmap_array = np.stack(
            [
                red,
                green,
                blue,
            ],
            axis=-1,
        )

        heatmap_uint8 = np.round(
            heatmap_array * 255.0
        ).astype(
            np.uint8
        )

        return Image.fromarray(
            heatmap_uint8,
            mode="RGB",
        )

    def _prepare_image(
        self,
        image: Image.Image,
    ) -> tuple[Image.Image, torch.Tensor]:
        """Create the display image and model-facing tensor."""

        if not isinstance(
            image,
            Image.Image,
        ):
            raise TypeError(
                "Grad-CAM input must be a decoded PIL image."
            )

        rgb_image = image.convert(
            "RGB"
        ).resize(
            (
                self.image_size,
                self.image_size,
            ),
            Image.Resampling.BILINEAR,
        )

        input_tensor = self._preprocess(
            rgb_image
        ).unsqueeze(
            dim=0
        )

        input_tensor = input_tensor.to(
            device=self.device,
            dtype=self.model_dtype,
        )

        input_tensor.requires_grad_(
            True
        )

        return rgb_image, input_tensor

    def generate(
        self,
        *,
        image: Image.Image,
        label_id: int,
        label_name: str,
        probability: float,
        frozen_threshold: float,
        threshold_decision: bool,
    ) -> GradCAMResult:
        """Generate visual evidence for one supplied model output."""

        if not 0 <= int(label_id) < 14:
            raise ValueError(
                "Grad-CAM label ID must be between zero and thirteen."
            )

        if not label_name.strip():
            raise ValueError(
                "Grad-CAM requires a finding name."
            )

        if not 0.0 <= float(probability) <= 1.0:
            raise ValueError(
                "Finding probability must be between zero and one."
            )

        if not 0.0 <= float(frozen_threshold) <= 1.0:
            raise ValueError(
                "Frozen threshold must be between zero and one."
            )

        expected_decision = (
            float(probability)
            >= float(frozen_threshold)
        )

        if bool(threshold_decision) != expected_decision:
            raise ValueError(
                "The supplied threshold decision does not match "
                "the probability and frozen threshold."
            )

        started_at = time.perf_counter()

        with self._lock:
            display_image, input_tensor = (
                self._prepare_image(
                    image
                )
            )

            self.model.eval()
            self.model.zero_grad(
                set_to_none=True
            )

            with torch.enable_grad():
                attribution = (
                    self._layer_gradcam.attribute(
                        input_tensor,
                        target=int(label_id),
                        relu_attributions=True,
                    )
                )

                attribution = (
                    functional.interpolate(
                        attribution.float(),
                        size=(
                            self.image_size,
                            self.image_size,
                        ),
                        mode="bilinear",
                        align_corners=False,
                    )
                )

            self.model.zero_grad(
                set_to_none=True
            )

        normalized_attribution = (
            self._normalize_attribution(
                attribution
            )
        )

        heatmap_image = self._build_heatmap(
            normalized_attribution
        )

        overlay_image = Image.blend(
            display_image,
            heatmap_image,
            alpha=self.overlay_alpha,
        )

        latency_ms = (
            time.perf_counter()
            - started_at
        ) * 1000.0

        return GradCAMResult(
            label_id=int(label_id),
            label_name=label_name.strip(),
            probability=float(probability),
            frozen_threshold=float(frozen_threshold),
            threshold_decision=bool(
                threshold_decision
            ),
            method=self.METHOD,
            target_layer=self.TARGET_LAYER,
            heatmap_png_base64=self._encode_png(
                heatmap_image
            ),
            overlay_png_base64=self._encode_png(
                overlay_image
            ),
            generation_latency_ms=float(
                latency_ms
            ),
            limitation=self.limitation,
        )

    def generate_for_crossed_findings(
        self,
        *,
        image: Image.Image,
        findings: Sequence[Any],
    ) -> tuple[GradCAMResult, ...]:
        """Generate evidence only for threshold-crossing findings."""

        results = []

        for finding in findings:
            decision = bool(
                self._read_value(
                    finding,
                    "threshold_decision",
                    "crossed_threshold",
                    "decision",
                )
            )

            if not decision:
                continue

            result = self.generate(
                image=image,
                label_id=int(
                    self._read_value(
                        finding,
                        "label_id",
                        "finding_id",
                    )
                ),
                label_name=str(
                    self._read_value(
                        finding,
                        "label_name",
                        "finding_name",
                    )
                ),
                probability=float(
                    self._read_value(
                        finding,
                        "probability",
                        "score",
                    )
                ),
                frozen_threshold=float(
                    self._read_value(
                        finding,
                        "frozen_threshold",
                        "threshold",
                    )
                ),
                threshold_decision=True,
            )

            results.append(
                result
            )

        return tuple(
            results
        )
