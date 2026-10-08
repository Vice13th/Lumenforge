"""Deterministic cache identity bridge for the existing V2 layered engine."""
import hashlib
import json
import numpy as np


def stable_value(value):
    if isinstance(value, dict):
        return {str(k): stable_value(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [stable_value(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def parameter_digest(params, keys):
    payload = {str(k): stable_value(params.get(k)) for k in keys}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def cache_contract_key(*, source_fingerprint, node_id, node_revision, upstream_revision,
                       tile=(0, 0, 0, 0), quality="preview", color_state="", backend="cpu"):
    payload = {
        "node_id": str(node_id),
        "node_revision": int(node_revision),
        "upstream_revision": int(upstream_revision),
        "source_fingerprint": str(source_fingerprint),
        "tile": tuple(int(v) for v in tile),
        "quality": str(quality),
        "color_state": str(color_state),
        "backend": str(backend),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
