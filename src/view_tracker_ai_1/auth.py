"""OAuth 2.0 device flow, magazyn tokenów, odświeżanie (SPEC §6 FR-1, docs/api-notes.md §1–3)."""

from __future__ import annotations

# TODO(PLAN stage 2): device flow (start + polling z interwałem), zapis tokenów 600/700 atomowo,
# rotacja refresh tokena (stary ważny 60 s), get_valid_token() bez wypisywania tokenów.
