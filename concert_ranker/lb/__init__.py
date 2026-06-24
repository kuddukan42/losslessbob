"""LosslessBob DB integration for concert_ranker.

These modules are the bridge between the (audio-agnostic) scoring brain and the
real LosslessBob database: persistence of raw metrics + scores (``repo``),
source-class derivation (``source_type``) and human-commentary mining
(``commentary``).
"""
