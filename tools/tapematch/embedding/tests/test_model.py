"""test_model.py — unit tests for embedding.model (CC_TAPEMATCH_ADDON Task 7.2).

Covers: forward shape/L2-norm contract, <=10M param HARD budget, and NT-Xent
sanity (scalar/finite, backward works, rewards agreement over random pairs).
Run with tools/tapematch/.venv-emb/bin/python -m pytest (CPU-only, fast).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tools/tapematch
from embedding.model import ConvEncoder, nt_xent  # noqa: E402

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


@pytest.fixture(scope="module")
def cfg() -> dict:
    """Loads the shared Tier C config (config.yaml MODEL/TRAIN blocks)."""
    return yaml.safe_load(CONFIG_PATH.read_text())


def test_forward_shape_and_unit_norm(cfg: dict) -> None:
    """(8,1,64,63) input -> (8,128) output with exactly unit L2 norm."""
    encoder = ConvEncoder(cfg)
    encoder.eval()
    mel = torch.randn(8, 1, 64, 63)
    with torch.no_grad():
        z = encoder(mel)

    assert z.shape == (8, cfg["MODEL"]["EMB_DIM"])
    norms = z.norm(p=2, dim=-1)
    assert torch.allclose(norms, torch.ones_like(norms), atol=1e-5)


def test_param_count_under_10m(cfg: dict) -> None:
    """HARD requirement (spec 7.2): encoder must be <=10M params."""
    encoder = ConvEncoder(cfg)
    n_params = sum(p.numel() for p in encoder.parameters())
    assert n_params <= 10_000_000


def test_runs_on_cpu(cfg: dict) -> None:
    """Encoder + loss both run end-to-end on CPU tensors."""
    encoder = ConvEncoder(cfg).to("cpu")
    mel = torch.randn(4, 1, 64, 63, device="cpu")
    z1 = encoder(mel)
    z2 = encoder(mel)
    loss = nt_xent(z1, z2, temperature=cfg["TRAIN"]["TEMPERATURE"])
    assert loss.device.type == "cpu"


def test_nt_xent_scalar_finite_and_backward(cfg: dict) -> None:
    """Loss is a finite scalar and gradients flow back through the encoder."""
    encoder = ConvEncoder(cfg)
    mel1 = torch.randn(16, 1, 64, 63)
    mel2 = torch.randn(16, 1, 64, 63)
    z1 = encoder(mel1)
    z2 = encoder(mel2)

    loss = nt_xent(z1, z2, temperature=cfg["TRAIN"]["TEMPERATURE"])

    assert loss.dim() == 0
    assert torch.isfinite(loss)
    assert loss.requires_grad

    loss.backward()
    grad_norms = [p.grad.norm().item() for p in encoder.parameters()
                  if p.grad is not None]
    assert len(grad_norms) > 0
    assert any(g > 0 for g in grad_norms)


def test_nt_xent_rewards_agreement(cfg: dict) -> None:
    """Loss is lower for perfect positives (z2==z1) than for random z2."""
    torch.manual_seed(0)
    batch_size, emb_dim = 32, cfg["MODEL"]["EMB_DIM"]
    temperature = cfg["TRAIN"]["TEMPERATURE"]

    z1 = torch.nn.functional.normalize(torch.randn(batch_size, emb_dim), dim=-1)

    z2_perfect = z1.clone()
    z2_random = torch.nn.functional.normalize(
        torch.randn(batch_size, emb_dim), dim=-1)

    loss_perfect = nt_xent(z1, z2_perfect, temperature)
    loss_random = nt_xent(z1, z2_random, temperature)

    assert loss_perfect.item() < loss_random.item()
