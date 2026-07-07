"""Tier C contrastive lineage embedding (CC_TAPEMATCH_ADDON Task 7).

The >80%-recall path: a small conv encoder trained from scratch with self-supervised
synthetic positives (transfer-chain augmentations) and same-show different-source HARD
negatives mined from observations.db. Curator labels are EVAL-ONLY (frozen set stays a
valid measuring instrument). Runs in the isolated torch env tools/tapematch/.venv-emb.

Modules:
  config.yaml  — all hyperparameters.
  melspec.py   — shared log-mel front end (train + infer parity).
  augment.py   — transfer-chain augmentation module (synthetic positives).
  model.py     — ConvEncoder + NT-Xent/InfoNCE loss.
  data.py      — hard-negative mining + windowed dataset + batch sampler.
  train.py     — GPU training loop + checkpointing.
  infer.py     — CPU-batch inference → embed_cache/<date>/LB<lb>.npz (Tier B harness format).
"""
