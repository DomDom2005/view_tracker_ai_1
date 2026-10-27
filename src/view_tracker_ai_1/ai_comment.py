"""Komentarz AI: CommentGenerator, AnthropicCommentGenerator, Fake; bramka danych i cache."""

from __future__ import annotations

# TODO(PLAN stage 7): bramka n_points < 6 lub coverage < 0.3 → brak wywołania LLM; prompt systemowy
# SPEC §10 z nazwą oferty w bloku danych; przycięcie do 700 znaków; cache po hashu wejścia.
