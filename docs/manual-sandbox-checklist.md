# Checklista ręczna: Sandbox Allegro

Kroki, których **nie może wykonać agent** (`Project info/SPEC.md` §16). Wykonuje człowiek.

## 1. Rejestracja aplikacji (sandbox)

1. Wejdź na <https://apps.developer.allegro.pl.allegrosandbox.pl/> i utwórz aplikację typu
   **„bez dostępu do przeglądarki”** (device flow) — typ jest niezmienny po rejestracji.
2. W panelu aplikacji sprawdź, że włączone są scope'y: `allegro:api:sale:offers:read`
   (oraz `allegro:api:sale:offers:write`, jeśli faz 3 ma być testowana).
3. Skopiuj `CLIENT ID` i `CLIENT SECRET` do `.env` w katalogu projektu (**poza repo**).
4. Uzupełnij `ALLEGRO_ENV=sandbox` i `ALLEGRO_USER_AGENT` (format `NazwaAplikacji/Wersja (+URL)`).

## 2. Konto i oferty testowe

1. Załóż konto sprzedawcy w sandboxie i wystaw kilka ofert (opcja „Chcę sprzedawać”).
2. Upewnij się, że oferty mają status `ACTIVE`, inaczej `collect` ich nie pobierze.

## 3. Pierwsze uruchomienie

```bash
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
python -m view_tracker_ai_1.cli auth login --env sandbox
python -m view_tracker_ai_1.cli collect --env sandbox
python -m view_tracker_ai_1.cli offers list
```

Oczekiwane: `auth status` pokazuje ważny token bez wypisywania go; `offers list` pokazuje oferty;
`DB_PATH` (domyślnie `data/sandbox.db`) rośnie o snapshoty.

## 4. Ruch na ofertach

1. Wejdź na swoje oferty z drugiego konta kupującego (kilka odsłon, kilka obserwacji).
2. Odczekaj ≥ 1 h i uruchom `collect` ponownie — sprawdź, czy `visitsCount`/`watchersCount` się
   zmieniły. W sandboxie ruch jest znikomy, więc przy zerach użyj trybu demo
   (`scripts/seed_demo_data.py`).

## 5. Do domknięcia po pierwszym uruchomieniu (TODO(verify) z `docs/api-notes.md` §8)

- Czy `scope` w device flow idzie w query stringu, czy w ciele żądania.
- Czy endpoint `device` na sandboxie to `POST https://allegro.pl.allegrosandbox.pl/auth/oauth/device`.
- Czy `429` zawiera nagłówek `Retry-After`.
- Znaczenie `count` vs `totalCount` w odpowiedzi `GET /sale/offers`.
- ~~Czy zmiana ceny (`act price --apply`) działa na sandboxie~~ — nieaktualne: etap 9 odłożony,
  aplikacja jest read-only (patrz `Project info/PLAN.md`).
- (Faza 0) Czy `visitsCount` maleje — uruchom `scripts/probe_counter.py` na ≥ 48 h na koncie
  z realnym ruchem.

## 6. Zrzuty ekranu

Lista plików i tego, co ma być widoczne (oraz co zamaskować): `docs/screenshots/README.md`.
