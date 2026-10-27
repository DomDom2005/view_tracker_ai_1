# Dziennik AI

Zapis pracy agenta: co zaproponował, jak to sprawdzono i czy się potwierdziło.
Format wpisu jak w `Project info/SPEC.md` §14. Wpisy są uczciwe — błędy i korekty też.

|Data|Zadanie|Co zaproponowało/zrobiło AI|Jak zweryfikowano|Wynik (trafne / poprawione / błędne)|
|---|---|---|---|---|
| 2026-10-27 | Uporządkowanie dokumentów projektu (nazwy, ścieżki, bloki kodu) | Ujednolicenie nazwy na `view_tracker_ai_1` w `SPEC.md`, `PLAN.md`, `AGENTS.md`, `Allegro API - Prototyp.md`; poprawa bloków kodu w `AGENTS.md` (niewidzialny znak U+200B w fence); nota o pierwszeństwie dokumentacji Allegro w nocie koncepcyjnej | Porównanie z nazwą repo (`git ls-tree origin/main`), `grep` po `Project info/` | poprawione (dokumenty mówiły „Allegro Trends” / `allegro_trends`) |
| 2026-10-27 | Etap 0 — szkielet repo, środowisko, bramka | Struktura `src/view_tracker_ai_1/` + `scripts/` + `tests/` + `docs/`; `pyproject.toml` (src layout, pytest, ruff), przypięte `requirements*.txt`, `.env.example` bez wartości, `tests/conftest.py` z blokadą gniazd, smoke test (15 testów), root `AGENTS.md` + `CLAUDE.md`, `docs/data-flow.md`, `docs/manual-sandbox-checklist.md`, `docs/screenshots/README.md` | `ruff check .` → All checks passed; `pytest -q` → 15 passed; `python -m view_tracker_ai_1.cli --version` → `view_tracker_ai_1 0.0.1` (z `PYTHONPATH=src`) | trafne, z zastrzeżeniami środowiskowymi (poniżej) |

## Uwagi o środowisku (etap 0)

- Python w PATH nie istnieje (Windows alias), użyty `C:\Users\domin\AppData\Local\Python\pythoncore-3.14-64\python.exe` (3.14.6).
- `python -m venv` nie potrafił doinstalować `pip` — sandboxowy filtr plików blokuje zapis do katalogów tworzonych przez `tempfile.mkdtemp`. `pip` w venv doinstalowany przez `uv`; zależności instalowane `uv pip install`.
- `pip install -r requirements-dev.txt` przechodzi (wszystko „already satisfied”), ale kończy się kodem 1, bo pip nie może posprzątać swoich katalogów tymczasowych w sandboxie. Na zwykłej maszynie problem nie występuje.
- `pip install -e .` **nie dało się zweryfikować** w sandboxie (build wheel używa katalogów tymczasowych). Do sprawdzenia przez człowieka: `pip install -e .` i `view_tracker_ai_1 --version`.
- `pytest` ostrzega `PytestCacheWarning` — to ten sam problem z katalogami tymczasowymi sandboxa, nie błąd projektu.

## Odstępstwa od SPEC

Miejsce na rozbieżności między dokumentacją Allegro a założeniami `SPEC.md`.
Każdy wpis: czego dotyczył SPEC, co mówi dokumentacja, URL, data, co zmieniono w kodzie.

1. **`limit` w `GET /sale/offers` ma domyślnie 20 (maks. 1000).** SPEC tego nie precyzował, a implementacja „pierwsza strona bez `limit`” gubiłaby oferty. Kolektor musi ustawiać `limit` jawnie i paginować po `offset`. Źródło: [dokumentacja](https://developer.allegro.pl/documentation) — 2026-10-27.
2. **Obowiązkowy nagłówek `User-Agent`** — od 2026-06-30 żądania bez poprawnego UA są odrzucane. SPEC w ogóle o nim nie mówił. Dodano do SPEC §4.1 i §13 (`ALLEGRO_USER_AGENT`). Źródło: [FAQ](https://developer.allegro.pl/faq) — 2026-10-27.
3. **Cena to `sellingMode.price`, nie `buyNowPrice`.** `PATCH /sale/product-offers/{offerId}` przyjmuje `{"sellingMode":{"price":{"amount":"49.99","currency":"PLN"}}}`, a stary `PUT /sale/offers/{offerId}` usunięto 2024-01-01. Źródło: [poradnik](https://developer.allegro.pl/tutorials/jak-zarzadzac-ofertami-7GzB2L37ase#edytuj-pola-oferty) — 2026-10-27.
4. **`Retry-After` przy `429` nie jest potwierdzony w dokumentacji.** SPEC §9 zakładał „jeśli jest”; polityka retry musi działać także bez nagłówka (fallback ~60 s). Źródło: [limity](https://developer.allegro.pl/tutorials/informacje-podstawowe-b21569boAI1#ograniczenie-liczby-zapytan-limity) — 2026-10-27.
5. **Semantyka `visitsCount` bez potwierdzenia w dokumentacji.** Brak opisu unikalności, okna 30 dni i odświeżania — to nadal hipoteza z forum (SPEC §4.2). Wnioski: zapisujemy poziomy, spadki traktujemy jako anomalie, niepewność opisujemy w README. Źródło: [poradnik](https://developer.allegro.pl/tutorials/jak-zarzadzac-ofertami-7GzB2L37ase#jak-pobrac-moje-oferty-w-rest-api) — 2026-10-27.

## Refleksja

Sekcja dla człowieka (`Project info/SPEC.md` §16 pkt 8). Agent jej nie wypełnia.
