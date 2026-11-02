# Checklista ręczna: Sandbox Allegro (2.0)

Kroki, których **nie może wykonać agent** (`Project info/SPEC-2.0.md` §16). Wykonuje człowiek.

## 1. Rejestracja aplikacji (sandbox)

1. Wejdź na <https://apps.developer.allegro.pl.allegrosandbox.pl/> i utwórz aplikację typu
   **„bez dostępu do przeglądarki”** (device flow) — typ jest niezmienny po rejestracji.
2. Włącz scope `allegro:api:sale:offers:read`. Jeśli chcesz korzystać z warstwy zdarzeń,
   sprawdź, czy `GET /sale/offer-events` wymaga dodatkowego uprawnienia — dokumentacja tego
   nie rozstrzyga (`docs/api-notes.md` §9). Przy `403` aplikacja pokaże komunikat, a adnotacje
   ręczne nadal działają.
3. Skopiuj `CLIENT ID` i `CLIENT SECRET` do `.env` w katalogu projektu (**poza repo**),
   ustaw `ALLEGRO_ENV=sandbox` i (opcjonalnie) `ALLEGRO_USER_AGENT`.

## 2. Konto i oferty testowe

1. Załóż konto sprzedawcy w sandboxie i wystaw kilka ofert („Chcę sprzedawać”).
2. Oferty muszą mieć status `ACTIVE`, inaczej zbieranie ich nie pobierze.

## 3. Pierwsze uruchomienie aplikacji

```bash
pip install -r requirements.txt
pip install -e .
python -m view_tracker_ai_1.ui
```

W przeglądarce (`http://127.0.0.1:8501`):

1. **Dane → „Rozpocznij logowanie”** — przepisz kod na stronie Allegro, wróć i kliknij
   **„Sprawdź zatwierdzenie”**.
2. **Dane → „Odśwież teraz”** — sprawdź, że pojawia się wpis przebiegu i snapshoty.
3. **Przegląd / Oferta** — sprawdź kafle, ranking, wykres i kartę podsumowania.

Oczekiwane: token ważny (data w belce statusu), `data/sandbox.db` rośnie, `collect_runs`
ma wpis `ok`.

## 4. Ruch na ofertach

1. Wejdź na swoje oferty z drugiego konta kupującego (kilka odsłon, obserwacji).
2. Odczekaj ≥ 1 h i kliknij „Odśwież teraz” — sprawdź, czy liczniki się zmieniły.
   W sandboxie ruch jest znikomy, więc przy zerach użyj **Ustawienia → „Wygeneruj dane demo”**
   i wybierz bazę demo w panelu bocznym.

## 5. Do domknięcia po pierwszym uruchomieniu (`TODO(verify)` z `docs/api-notes.md`)

- Czy `scope` w device flow idzie w query, czy w ciele żądania.
- Czy endpoint `device` na sandboxie to `POST https://allegro.pl.allegrosandbox.pl/auth/oauth/device`.
- Czy `429` zawiera `Retry-After`.
- Znaczenie `count` vs `totalCount` w `GET /sale/offers`.
- Kształt odpowiedzi i wymagany scope `GET /sale/offer-events` (parser jest tolerancyjny).
- Czy `visitsCount` maleje — `scripts/probe_counter.py` na ≥ 48 h.

## 6. Zrzuty ekranu

Lista plików i tego, co ma być widoczne (oraz co zamaskować): `docs/screenshots/README.md`.
