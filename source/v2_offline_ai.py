"""Local-only ONNX sentence embedding boundary recovered from LumenParallel."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import numpy as np


@dataclass(frozen=True)
class InferenceReceipt:
    model_sha256: str
    tokenizer_sha256: str
    provider: str
    batch_size: int
    sequence_length: int
    embedding_dim: int
    latency_ms: float
    local_only: bool = True
    network_required: bool = False


class LocalSentenceEncoder:
    def __init__(self, model_dir: str | Path, *, provider: str = "CPUExecutionProvider"):
        from tokenizers import Tokenizer
        import onnxruntime as ort
        root = Path(model_dir)
        self.model_path = root / "onnx" / "model.onnx"
        self.tokenizer_path = root / "tokenizer.json"
        if not self.model_path.is_file() or not self.tokenizer_path.is_file():
            raise FileNotFoundError("local ONNX model or tokenizer.json is missing")
        self.tokenizer = Tokenizer.from_file(str(self.tokenizer_path))
        self.session = ort.InferenceSession(str(self.model_path), providers=[provider])
        self.provider = self.session.get_providers()[0]
        inputs = {x.name for x in self.session.get_inputs()}
        required = {"input_ids", "attention_mask", "token_type_ids"}
        if not required.issubset(inputs):
            raise ValueError(f"unexpected ONNX inputs: {sorted(inputs)}")

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def encode(self, texts: list[str], *, max_length: int = 128) -> np.ndarray:
        if not texts:
            raise ValueError("texts must not be empty")
        self.tokenizer.enable_truncation(max_length=max_length)
        self.tokenizer.enable_padding(length=max_length)
        batch = self.tokenizer.encode_batch(texts)
        ids = np.asarray([x.ids for x in batch], dtype=np.int64)
        mask = np.asarray([x.attention_mask for x in batch], dtype=np.int64)
        type_ids = np.asarray([x.type_ids for x in batch], dtype=np.int64)
        outputs = self.session.run(["last_hidden_state"], {
            "input_ids": ids,
            "attention_mask": mask,
            "token_type_ids": type_ids,
        })[0]
        weights = mask[..., None].astype(np.float32)
        pooled = (outputs * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1.0)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        return pooled / np.maximum(norms, 1e-12)

    def receipt(self, batch_size: int, sequence_length: int, embedding_dim: int, latency_ms: float) -> InferenceReceipt:
        return InferenceReceipt(
            model_sha256=self._sha256(self.model_path),
            tokenizer_sha256=self._sha256(self.tokenizer_path),
            provider=self.provider,
            batch_size=batch_size,
            sequence_length=sequence_length,
            embedding_dim=embedding_dim,
            latency_ms=float(latency_ms),
        )
