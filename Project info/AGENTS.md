# AGENTS.md

view_tracker_ai_1: CLI w Pythonie 3.11+, zbiera liczniki ofert (wyświetlenia, obserwujący)
z API Allegro do SQLite, rysuje wykresy i dodaje komentarz AI.
Specyfikacja: `Project info/SPEC.md`. Plan etapów: `Project info/PLAN.md`.
Dokumenty projektu mieszkają w `Project info/`; kod aplikacji leży w katalogu głównym repo.

## Komendy

```bash
pip install -r requirements.txt -r requirements-dev.txt
ruff check . && pytest                 # przed zakończeniem każdego zadania
pytest tests/test_analytics.py -k delta
python -m view_tracker_ai_1.cli collect --env sandbox
```

## Zasady

- Testy działają offline na mockach. Nie łącz się z prawdziwym API w testach.
- Sekrety tylko w `.env` i poza repo. Nie loguj tokenów ani nie wklejaj ich do przykładów.
- Zapisy do API (`act price`) tylko z `--apply` i tylko w sandboxie.
- `analytics.py` i `storage.py` nie robią żądań sieciowych.
- Przed użyciem endpointu sprawdź go w dokumentacji developer.allegro.pl. Jeśli przeczy SPEC.md, wygrywa dokumentacja.

## Pułapki

- `visitsCount` może maleć (okno czasowe). Nie zakładaj monotoniczności, nie licz ujemnych przyrostów.
- „Polubień” w API nie ma, używaj nazwy „obserwujący” (`watchersCount`).
- Dane syntetyczne trzymaj w osobnej bazie i zawsze oznaczaj na wykresach.

## Dziennik AI

Po każdej zmianie, w której coś Cię zaskoczyło albo poprawiłeś założenie, dopisz wpis w `docs/ai-journal.md`.
