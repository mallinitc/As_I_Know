
"""Thread-safe inference for the fine-tuned grounded language model."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import torch
from transformers import (
    AutoTokenizer,
    T5ForConditionalGeneration,
)


@dataclass(frozen=True)
class LanguageGenerationResult:
    """One raw generation and its inference lineage."""

    task_type: str
    generated_text: str
    serialized_input: str
    input_tokens: int
    generated_tokens: int
    generation_latency_ms: float
    language_model_version: str
    decoding_strategy: str


class GroundedLanguageModelService:
    """Run the frozen fine-tuned FLAN-T5 model safely."""

    MAXIMUM_INPUT_LENGTH = 416
    MAXIMUM_TARGET_LENGTH = 288
    DECODING_STRATEGY = "greedy"

    def __init__(
        self,
        *,
        model_directory: str | Path,
        model_version: str,
        device: str | torch.device | None = None,
        use_bfloat16: bool = True,
    ) -> None:
        self.model_directory = Path(
            model_directory
        )
        self.model_version = (
            model_version.strip()
        )
        self._lock = threading.RLock()

        if not self.model_directory.is_dir():
            raise FileNotFoundError(
                "The versioned language-model directory "
                "is unavailable."
            )

        if not self.model_version:
            raise ValueError(
                "A language-model version is required."
            )

        if device is None:
            selected_device = (
                "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )
        else:
            selected_device = str(device)

        self.device = torch.device(
            selected_device
        )

        self.use_bfloat16 = bool(
            use_bfloat16
            and self.device.type == "cuda"
            and torch.cuda.is_bf16_supported()
        )

        self.inference_dtype = (
            torch.bfloat16
            if self.use_bfloat16
            else torch.float32
        )

        load_started_at = time.perf_counter()

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_directory,
            local_files_only=True,
            use_fast=True,
        )

        self.model = (
            T5ForConditionalGeneration.from_pretrained(
                self.model_directory,
                local_files_only=True,
                torch_dtype=self.inference_dtype,
            )
        )

        self.model.to(
            self.device
        )
        self.model.eval()

        if self.device.type == "cuda":
            torch.cuda.synchronize(
                self.device
            )

        self.model_load_latency_ms = (
            time.perf_counter()
            - load_started_at
        ) * 1000.0

        self._validate_model_contract()

    def _validate_model_contract(
        self,
    ) -> None:
        """Validate the tokenizer and model compatibility."""

        if not self.model.config.is_encoder_decoder:
            raise RuntimeError(
                "The grounded language model must be "
                "an encoder-decoder model."
            )

        if self.tokenizer.pad_token_id is None:
            raise RuntimeError(
                "The tokenizer must define a padding token."
            )

        if self.tokenizer.eos_token_id is None:
            raise RuntimeError(
                "The tokenizer must define an end-of-sequence token."
            )

        embedding_count = int(
            self.model.get_input_embeddings().num_embeddings
        )

        tokenizer_maximum_id = (
            len(self.tokenizer) - 1
        )

        if tokenizer_maximum_id >= embedding_count:
            raise RuntimeError(
                "Tokenizer IDs exceed the model embedding vocabulary."
            )

    @staticmethod
    def _read_serialized_record(
        record: Any,
    ) -> tuple[str, str]:
        """Read task type and input from a mapping or object."""

        if isinstance(record, dict):
            task_type = record.get(
                "task_type"
            )
            serialized_input = record.get(
                "serialized_input"
            )
        else:
            task_type = getattr(
                record,
                "task_type",
                None,
            )
            serialized_input = getattr(
                record,
                "serialized_input",
                None,
            )

        if not isinstance(
            task_type,
            str,
        ) or not task_type.strip():
            raise ValueError(
                "Serialized grounding input requires a task type."
            )

        if not isinstance(
            serialized_input,
            str,
        ) or not serialized_input.strip():
            raise ValueError(
                "Serialized grounding input cannot be blank."
            )

        return (
            task_type.strip(),
            serialized_input.strip(),
        )

    def generate_many(
        self,
        records: Sequence[Any],
    ) -> tuple[LanguageGenerationResult, ...]:
        """Generate one deterministic output for every grounded input."""

        if not records:
            raise ValueError(
                "At least one serialized grounding input is required."
            )

        normalized_records = [
            self._read_serialized_record(
                record
            )
            for record in records
        ]

        task_types = [
            record[0]
            for record in normalized_records
        ]

        serialized_inputs = [
            record[1]
            for record in normalized_records
        ]

        encoded_batch = self.tokenizer(
            serialized_inputs,
            padding=True,
            truncation=False,
            return_tensors="pt",
            add_special_tokens=True,
        )

        attention_mask = encoded_batch[
            "attention_mask"
        ]

        input_lengths = attention_mask.sum(
            dim=1
        ).tolist()

        if max(input_lengths) > self.MAXIMUM_INPUT_LENGTH:
            raise ValueError(
                "A grounded language input exceeds the frozen "
                f"{self.MAXIMUM_INPUT_LENGTH}-token contract."
            )

        encoded_batch = {
            key: value.to(
                self.device
            )
            for key, value
            in encoded_batch.items()
        }

        if self.device.type == "cuda":
            torch.cuda.synchronize(
                self.device
            )

        generation_started_at = (
            time.perf_counter()
        )

        with self._lock:
            self.model.eval()

            with torch.inference_mode():
                generated_ids = self.model.generate(
                    **encoded_batch,
                    do_sample=False,
                    num_beams=1,
                    max_new_tokens=(
                        self.MAXIMUM_TARGET_LENGTH
                    ),
                    use_cache=True,
                )

            if self.device.type == "cuda":
                torch.cuda.synchronize(
                    self.device
                )

        batch_latency_ms = (
            time.perf_counter()
            - generation_started_at
        ) * 1000.0

        generated_texts = (
            self.tokenizer.batch_decode(
                generated_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            )
        )

        generated_lengths = (
            generated_ids.ne(
                self.tokenizer.pad_token_id
            ).sum(
                dim=1
            ).tolist()
        )

        latency_per_record = (
            batch_latency_ms
            / len(normalized_records)
        )

        results = []

        for (
            task_type,
            serialized_input,
            generated_text,
            input_length,
            generated_length,
        ) in zip(
            task_types,
            serialized_inputs,
            generated_texts,
            input_lengths,
            generated_lengths,
            strict=True,
        ):
            normalized_text = (
                generated_text.strip()
            )

            if not normalized_text:
                raise RuntimeError(
                    f"The model returned an empty output for {task_type}."
                )

            results.append(
                LanguageGenerationResult(
                    task_type=task_type,
                    generated_text=normalized_text,
                    serialized_input=serialized_input,
                    input_tokens=int(
                        input_length
                    ),
                    generated_tokens=int(
                        generated_length
                    ),
                    generation_latency_ms=float(
                        latency_per_record
                    ),
                    language_model_version=(
                        self.model_version
                    ),
                    decoding_strategy=(
                        self.DECODING_STRATEGY
                    ),
                )
            )

        return tuple(
            results
        )

    def generate(
        self,
        record: Any,
    ) -> LanguageGenerationResult:
        """Generate a single deterministic grounded output."""

        return self.generate_many(
            [record]
        )[0]
