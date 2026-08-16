"""Frozen ResNet-18 ChestMNIST inference service."""

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms

from api.core.config import (
    ServiceSettings,
    get_settings,
    load_yaml_file,
)
from api.core.errors import (
    ModelNotReadyError,
    ServiceExecutionError,
)
from api.schemas.prediction import FindingEvidence
from src.services.image_service import ValidatedImage


IMAGENET_MEAN = [
    0.485,
    0.456,
    0.406,
]
IMAGENET_STANDARD_DEVIATION = [
    0.229,
    0.224,
    0.225,
]


@dataclass
class ClassificationResult:
    """Internal classification result with reusable model tensors."""

    findings: list[FindingEvidence]
    crossed_finding_names: list[str]
    no_target_finding: bool
    interpretation: str
    inference_latency_ms: float
    probabilities: np.ndarray = field(
        repr=False
    )
    logits: torch.Tensor = field(
        repr=False
    )
    input_tensor: torch.Tensor = field(
        repr=False
    )


class ComputerVisionService:
    """Load and execute the frozen multilabel ResNet-18 model."""

    def __init__(
        self,
        settings: ServiceSettings | None = None,
        device: str | None = None,
    ) -> None:
        self.settings = (
            settings or get_settings()
        )
        self.device = torch.device(
            device
            if device is not None
            else (
                "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )
        )
        self._inference_lock = (
            threading.Lock()
        )
        self._ready = False
        self.model_load_latency_ms = 0.0

        finding_contract_path = (
            self.settings.solution_root
            / "configs"
            / "finding_contract.yaml"
        )
        self.finding_contract = (
            load_yaml_file(
                finding_contract_path
            )
        )
        self.findings = (
            self.finding_contract[
                "findings"
            ]
        )
        self.controlled_language = (
            self.finding_contract[
                "controlled_language"
            ]
        )

        self.thresholds = np.asarray(
            [
                finding[
                    "frozen_threshold"
                ]
                for finding in self.findings
            ],
            dtype=np.float32,
        )

        self.preprocess_transform = (
            transforms.Compose(
                [
                    transforms.Resize(
                        (224, 224),
                        antialias=True,
                    ),
                    transforms.ToTensor(),
                    transforms.Normalize(
                        mean=IMAGENET_MEAN,
                        std=(
                            IMAGENET_STANDARD_DEVIATION
                        ),
                    ),
                ]
            )
        )

        self.model = self._load_model()
        self._ready = True

    def _load_model(
        self,
    ) -> nn.Module:
        """Reconstruct and load the frozen ResNet-18 model."""

        load_start_time = (
            time.perf_counter()
        )

        model = models.resnet18(
            weights=None
        )
        model.fc = nn.Sequential(
            nn.Dropout(p=0.2),
            nn.Linear(
                model.fc.in_features,
                14,
            ),
        )

        try:
            checkpoint_value = torch.load(
                self.settings
                .computer_vision_weights_path,
                map_location="cpu",
                weights_only=True,
            )

            if (
                isinstance(
                    checkpoint_value,
                    dict,
                )
                and "model_state_dict"
                in checkpoint_value
            ):
                state_dict = checkpoint_value[
                    "model_state_dict"
                ]
            else:
                state_dict = checkpoint_value

            model.load_state_dict(
                state_dict,
                strict=True,
            )

        except Exception as error:
            raise ModelNotReadyError(
                details={
                    "component": (
                        "computer_vision"
                    ),
                    "reason": (
                        "Frozen model loading failed."
                    ),
                }
            ) from error

        model.to(self.device)
        model.eval()

        self.model_load_latency_ms = (
            (
                time.perf_counter()
                - load_start_time
            )
            * 1000.0
        )

        return model

    @property
    def is_ready(self) -> bool:
        """Report whether frozen inference is available."""

        return self._ready

    @staticmethod
    def confidence_category(
        probability: float,
        threshold: float,
    ) -> str:
        """Map probability distance to the frozen language bands."""

        margin = probability - threshold

        if margin < 0.0:
            return "below_threshold"

        if margin < 0.03:
            return "borderline"

        if margin < 0.10:
            return "moderate"

        return "higher"

    def preprocess(
        self,
        image: Image.Image,
    ) -> torch.Tensor:
        """Create one normalized RGB model tensor."""

        rgb_image = image.convert("RGB")
        input_tensor = (
            self.preprocess_transform(
                rgb_image
            )
            .unsqueeze(0)
            .to(self.device)
        )

        return input_tensor

    def predict(
        self,
        validated_image: ValidatedImage,
    ) -> ClassificationResult:
        """Run one frozen multilabel prediction."""

        if not self.is_ready:
            raise ModelNotReadyError(
                details={
                    "component": (
                        "computer_vision"
                    )
                }
            )

        input_tensor = self.preprocess(
            validated_image.rgb_image
        )

        try:
            with self._inference_lock:
                if self.device.type == "cuda":
                    torch.cuda.synchronize()

                inference_start_time = (
                    time.perf_counter()
                )

                with torch.inference_mode():
                    with torch.autocast(
                        device_type=(
                            self.device.type
                        ),
                        dtype=torch.bfloat16,
                        enabled=(
                            self.device.type
                            == "cuda"
                            and torch.cuda
                            .is_bf16_supported()
                        ),
                    ):
                        logits = self.model(
                            input_tensor
                        )
                        probability_tensor = (
                            torch.sigmoid(
                                logits
                            )
                        )

                if self.device.type == "cuda":
                    torch.cuda.synchronize()

                inference_latency_ms = (
                    (
                        time.perf_counter()
                        - inference_start_time
                    )
                    * 1000.0
                )

        except Exception as error:
            raise ServiceExecutionError(
                message=(
                    "Computer-vision inference failed."
                ),
                details={
                    "component": (
                        "computer_vision"
                    )
                },
            ) from error

        probabilities = (
            probability_tensor
            .detach()
            .float()
            .cpu()
            .numpy()[0]
        )

        decisions = (
            probabilities
            >= self.thresholds
        )

        finding_results = [
            FindingEvidence(
                label_id=int(
                    finding["label_id"]
                ),
                label_name=(
                    finding["label_name"]
                ),
                display_name=(
                    finding["display_name"]
                ),
                probability=float(
                    probabilities[
                        finding["label_id"]
                    ]
                ),
                frozen_threshold=float(
                    finding[
                        "frozen_threshold"
                    ]
                ),
                crossed_threshold=bool(
                    decisions[
                        finding["label_id"]
                    ]
                ),
                confidence_category=(
                    self.confidence_category(
                        float(
                            probabilities[
                                finding[
                                    "label_id"
                                ]
                            ]
                        ),
                        float(
                            finding[
                                "frozen_threshold"
                            ]
                        ),
                    )
                ),
                approved_description=(
                    finding[
                        "approved_description"
                    ]
                ),
            )
            for finding in self.findings
        ]

        crossed_finding_names = [
            finding.label_name
            for finding in finding_results
            if finding.crossed_threshold
        ]

        no_target_finding = (
            len(crossed_finding_names)
            == 0
        )

        if no_target_finding:
            interpretation = (
                self.controlled_language[
                    "no_target_finding"
                ]
            )
        else:
            finding_count = len(
                crossed_finding_names
            )
            interpretation = (
                f"{finding_count} of the 14 supported "
                f"findings crossed their frozen "
                f"decision thresholds. "
                f"{self.controlled_language['educational_use_limitation']}"
            )

        return ClassificationResult(
            findings=finding_results,
            crossed_finding_names=(
                crossed_finding_names
            ),
            no_target_finding=(
                no_target_finding
            ),
            interpretation=interpretation,
            inference_latency_ms=(
                inference_latency_ms
            ),
            probabilities=probabilities,
            logits=logits.detach(),
            input_tensor=input_tensor.detach(),
        )
