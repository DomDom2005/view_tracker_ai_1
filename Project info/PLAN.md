# PLAN.md — plan działania agenta (view_tracker_ai_1)

> Wersja 1.0 · 2026-10-27
> Plan wykonawczy do `Project info/SPEC.md`. **SPEC.md mówi, co zbudować. PLAN.md mówi, w jakiej kolejności i jak to sprawdzać.**
> Ścieżki: dokumenty projektu leżą w `Project info/` (`SPEC.md`, `PLAN.md`, `AGENTS.md`, `Allegro API - Prototyp.md`); one się nie przenoszą. Kod aplikacji (`src/view_tracker_ai_1/`, `tests/`, `scripts/`, `docs/`) powstaje w katalogu głównym repo. Nazwa kanoniczna: **`view_tracker_ai_1`** (pakiet i komenda).
> Reguły pracy w repo są w `Project info/AGENTS.md` — czytaj je przed każdym etapem.

---

## Jak korzystać z tego pliku

- Pracuj **etapami, po kolei**. Etap kończy się **bramką** (komendy + kryteria). Dopóki bramka jest czerwona, nie przechodź dalej.
- Na bieżąco odhaczaj zadania (`[x]`) i aktualizuj tabelę statusu. Dzięki temu nowa sesja może wznowić pracę bez Twojej pamięci (sekcja „Wznowienie pracy”).
- Odwołania typu „SPEC §9” oznaczają sekcję 9 pliku `SPEC.md`.
- Rozmiar etapu: **S** (mały), **M** (średni), **L** (duży). To orientacyjna skala pracy, nie obietnica czasu.

## Status etapów

| Etap | Nazwa                                          | Rozmiar | Faza SPEC | Status |
| ---- | ---------------------------------------------- | ------- | --------- | ------ |
| 0    | Szkielet repo i weryfikacja dokumentacji       | M       | 1         | [x]    |
| 1    | Fundament: config, błędy, modele, storage      | M       | 1         | [x]    |
| 2    | Autoryzacja OAuth                              | L       | 1         | [x]    |
| 3    | Klient HTTP: retry, błędy, paginacja           | L       | 1         | [x]    |
| 4    | Kolektor i podstawowe CLI                      | M       | 1         | [x]    |
| 5    | Analityka                                      | L       | 2         | [ ]    |
| 6    | Dane demo i wykresy                            | M       | 2         | [ ]    |
| 7    | Moduł AI                                       | M       | 2         | [ ]    |
| 8    | Raport HTML                                    | M       | 2         | [ ]    |
| 9    | Zmiana ceny przez API (opcjonalny, decyzja D1) | M       | 3         | [ ]    |
| 10   | Dokumentacja                                   | M       | —         | [ ]    |
| 11   | Domknięcie i kontrola jakości                  | S       | —         | [ ]    |

Zależności: 0 → 1 → (2, 3) → 4 → 5 → 6 → (7, 8) → 9 → 10 → 11. Etapy 2 i 3 możesz zamienić miejscami, ale 4 wymaga obu.

---

## Protokół pracy w każdym etapie

1. Przeczytaj wskazane sekcje SPEC.md i ostatnie wpisy `docs/ai-journal.md`.
2. Jeśli etap dotyka Allegro API, najpierw sprawdź `docs/api-notes.md`. Brakujące punkty zweryfikuj w dokumentacji (https://developer.allegro.pl), zanim napiszesz kod.
3. Pisz testy razem z kodem (albo przed nim). Test, który nie może nigdy zawieść, nie jest testem.
4. Uruchom bramkę etapu. Napraw wszystko, co czerwone.
5. Dopisz wpis do `docs/ai-journal.md` (co zrobiłeś, co sprawdziłeś, co musiałeś poprawić). **Uczciwie, bez upiększania.**
6. Zrób commit (Conventional Commits, po angielsku, np. `feat(client): add retry policy for 429`).
7. Odhacz etap w tabeli i napisz krótki raport do człowieka (≤ 10 linii: co zrobione, odstępstwa od SPEC, otwarte pytania).

### Kiedy się zatrzymać i zapytać człowieka

- Dokumentacja Allegro przeczy SPEC-owi w sposób zmieniający architekturę (np. brak `stats` na liście ofert).
- Do dalszej pracy potrzebne są poświadczenia lub dostęp do konta (nie masz ich, patrz SPEC §0 pkt 3). Wtedy dokończ na mockach i zapisz, co człowiek musi zrobić.
- Chcesz usunąć lub zmienić coś, co jest poza bieżącym etapem.
- Test wymaga prawdziwego połączenia sieciowego.

---

## Etap 0 — Szkielet repo i weryfikacja dokumentacji

**Cel:** gotowe środowisko pracy i potwierdzone fakty o API, zanim powstanie jakikolwiek kod integracji.
**Zależy od:** — · **Czyta:** SPEC §0, §4, §5, §13

**Zadania**
- [x] `git init`, struktura katalogów wg SPEC §5 (pliki puste lub z minimalną treścią).
- [x] `pyproject.toml` (layout `src/`, konfiguracja `pytest` i `ruff`), `.gitignore` (SPEC §13), `.env.example` (same nazwy zmiennych z SPEC §13, bez wartości).
- [x] Środowisko wirtualne, instalacja zależności, **przypięcie przetestowanych wersji** w `requirements.txt` i `requirements-dev.txt`. Dodaj `tzdata` (strefa `Europe/Warsaw` na Windows). Wersje z Pythonem 3.14.6: `anthropic 2.3.0`, `matplotlib 3.11.2`, `jinja2 3.1.6`, `requests 2.34.2`, `pytest 9.2.0`, `ruff 0.17.3`.
- [x] `tests/conftest.py` z blokadą połączeń sieciowych (test próbujący otworzyć gniazdo ma zawieść).
- [x] `Project info/AGENTS.md` już istnieje — nie przenoszony do roota (dokumenty projektu zostają w `Project info/`). W rootcie dodany cienki `AGENTS.md` wskazujący na `Project info/AGENTS.md` (bez niego reguły nie działają poza tym katalogiem) oraz `CLAUDE.md` z jedną linią `@AGENTS.md`.
- [x] `docs/ai-journal.md` ze szkieletem (tabela wpisów, sekcje „Odstępstwa od SPEC” i „Refleksja”).
- [x] **Weryfikacja SPEC §4.3** (6 punktów) w oficjalnej dokumentacji — wykonane 2026-10-27. Wynik w `docs/api-notes.md` (punkt → ustalenie → URL źródła → data sprawdzenia). Punkty niepotwierdzone oznaczone `NIEZWERYFIKOWANE` + `TODO(verify)`; lista w `docs/api-notes.md` §8. Uwaga: weryfikacja ujawniła nowy wymóg — obowiązkowy nagłówek `User-Agent` (SPEC §4.1, §13).

**Bramka**
```bash
pip install -r requirements-dev.txt
ruff check .
pytest -q          # 0 testów jest akceptowalne, ale zbieranie nie może się wywalić
```
- `docs/api-notes.md` ma wpis dla każdego z 6 punktów.
- `.env.example` nie zawiera żadnych wartości.

**Commit:** `chore: project skeleton and API facts verification`
**Dziennik AI:** które punkty 4.3 okazały się inne niż zakładał SPEC.
**Stop, jeśli:** dokumentacja Allegro jest niedostępna. Wtedy oznacz punkty jako niezweryfikowane i jedź dalej, bez blokowania.

---

## Etap 1 — Fundament: config, błędy, modele, storage

**Cel:** warstwa danych i konfiguracji, na której stoi reszta.
**Zależy od:** 0 · **Czyta:** SPEC §6 (NFR), §7, §9, §13

**Zadania**
- [x] `errors.py`: `AuthError`, `RateLimitError` (z `retry_after`), `ValidationError` (z listą `errors` + `describe()`), `ApiError` (status + skrócone ciało), wspólna baza `AppError` + `ConfigError`/`StorageError`.
- [x] `config.py`: ładowanie env (`python-dotenv`), walidacja (`ALLEGRO_ENV` ∈ `sandbox|prod`), dataclass `Config` przekazywany jawnie (bez globalnego stanu). Komendy niewymagające API (np. raport z bazy demo) nie wymagają sekretów Allegro — `require_allegro_credentials()` wołane dopiero tam, gdzie trzeba. Hosty API/auth per środowisko w jednym miejscu (`API_BASE_URLS`, `AUTH_BASE_URLS`).
- [x] W `config.py` także `setup_logging()` z **filtrem redakcji** (maskuje `Authorization`, tokeny, `client_secret`, klucze API, JWT, `sk-ant-…`).
- [x] `models.py`: `Offer`, `Snapshot`, `Series`, `SeriesSummary` (pola z SPEC §6 FR-4) + `SeriesPoint`, `DailyGain`, `Anomaly`.
- [x] `storage.py`: schemat z SPEC §7 (wszystkie tabele od razu, z `schema_version`), idempotentny init, funkcje: `upsert_offer`, `insert_snapshots` (transakcja), `get_series(offer_id, since, until, source)`, `list_offers`, `get_last_snapshot`, `count_snapshots`, cache komentarzy AI (`get/put`), `log_action`. Czas w UTC (`to_iso`/`from_iso`). Decyzja: powtórzony zapis tego samego `(offer_id, captured_at)` jest ignorowany (`ON CONFLICT DO NOTHING`), a `insert_snapshots` zwraca liczbę faktycznie dodanych wierszy.
- [x] Testy: init idempotentny, `UNIQUE` (idempotentny re-insert), zapytania po przedziale, osobne bazy per środowisko, walidacja configu, redakcja logów.

**Bramka**
```bash
ruff check . && pytest -q --cov=src/view_tracker_ai_1 --cov-report=term-missing
```
- Pokrycie `storage.py` i `config.py` ≥ 80%.

**Commit:** `feat: config, errors, models and SQLite storage`
**Dziennik AI:** decyzje projektowe, które nie wynikały wprost z SPEC (np. kształt API `storage`).

---

## Etap 2 — Autoryzacja OAuth

**Cel:** bezpieczne logowanie i odświeżanie tokenów.
**Zależy od:** 1 · **Czyta:** SPEC §4.3 (pkt 1–3), §6 FR-1, §13; `docs/api-notes.md`

**Zadania**
- [x] `auth.py`: device flow (start, polling z respektowaniem interwału, obsługa „oczekiwanie / odmowa / wygaśnięcie kodu”), endpointy i parametry **z `api-notes.md`**, nie z pamięci.
- [x] Magazyn tokenów: ścieżka z `TOKEN_STORE_PATH`, katalog `700`, plik `600`, zapis atomowy (plik tymczasowy + `os.replace`).
- [x] Odświeżanie tokenu z **zapisem nowego refresh tokena po każdym odświeżeniu** (rotacja potwierdzona w dokumentacji: nowy refresh token jednorazowy, stary ważny 60 s).
- [x] `get_valid_token()` odświeża przed wygaśnięciem (bufor 5 min) i nigdy nie wypisuje tokenów.
- [x] Testy (mock HTTP): sukces i porażka odświeżania, zapis nowego refresh tokena, uprawnienia plików, brak tokenów w logach/`repr`. Odświeżenie **po `401`** sprawdza dopiero `client.py` (etap 3) — tutaj jest tylko mechanizm odświeżania.

**Bramka**
```bash
ruff check . && pytest -q tests/test_auth.py --cov=src/view_tracker_ai_1
```
- Pokrycie `auth.py` ≥ 80%. Żadnego prawdziwego żądania sieciowego.

**Commit:** `feat(auth): device flow, token store and refresh`
**Dziennik AI:** co dokumentacja mówi o rotacji refresh tokena i czy zgadzało się z założeniem.
**Stop, jeśli:** dokumentacja opisuje inny przepływ niż device flow dla aplikacji CLI. Opisz alternatywę i zapytaj.

---

## Etap 3 — Klient HTTP: retry, błędy, paginacja

**Cel:** jedno miejsce, które rozmawia z Allegro i poprawnie zachowuje się przy błędach.
**Zależy od:** 1, 2 · **Czyta:** SPEC §4.1, §9; `docs/api-notes.md`

**Zadania**
- [x] `client.py`: sesja `requests`, nagłówki `Accept: application/vnd.allegro.public.v1+json` i **obowiązkowy `User-Agent`** (SPEC §4.1), token z `auth`, adres bazowy zależny od `ALLEGRO_ENV` (z `docs/api-notes.md`), timeouty (connect 10 s, read 30 s).
- [x] Polityka błędów z tabeli SPEC §9: `401` (odśwież i **powtórz raz**), `422` (`ValidationError`, bez ponowień), `429` (`Retry-After` albo backoff wykładniczy z jitterem, maks. 5 prób), `5xx`/timeout (do 3 ponowień), inne `4xx` → `ApiError`. Odstępstwo: bez `Retry-After` backoff startuje od **60 s** (blokada po `429` trwa ~minutę), nie od 1 s.
- [x] `iter_offers(statuses, limit)` z paginacją i krótką pauzą między stronami (0,2 s). `limit` jawny: domyślnie 100, walidacja 1..1000 (API ma domyślnie 20!).
- [x] Fixtures w `tests/fixtures/` (`offers_page1.json` … `offers_page3.json`, dane fikcyjne, kształt z SPEC §7).
- [x] Testy z SPEC §12 dla `client`: paginacja na 3 stronach, nagłówki `Accept`/`User-Agent`, `429` z `Retry-After`, `429` bez nagłówka, `429` do wyczerpania, `422`, `5xx`, timeout, `401` → odświeżenie i jeden retry. Uśpienia podstawione listą — zero prawdziwych `sleep`.
- [x] Żaden log i żaden komunikat błędu nie zawiera nagłówka `Authorization` (test na `caplog`).

**Bramka**
```bash
ruff check . && pytest -q tests/test_client.py --cov=src/view_tracker_ai_1
```
- Pokrycie `client.py` ≥ 80%, czas testów rozsądny (bez realnych oczekiwań).

**Commit:** `feat(client): HTTP client with retry policy and pagination`
**Dziennik AI:** różnice między założeniami SPEC a rzeczywistym kształtem odpowiedzi.

---

## Etap 4 — Kolektor i podstawowe CLI

**Cel:** działający przepływ „API → baza”. Koniec fazy 1 ze SPEC.
**Zależy od:** 2, 3 · **Czyta:** SPEC §6 FR-1…FR-3, FR-10, §8

**Zadania**
- [x] `collector.py`: `run_once(client, conn, *, statuses, captured_at)` — wspólny `captured_at` (UTC) dla całego przebiegu, aktualizacja `offers`, zapis w jednej transakcji (`storage.save_collection`). Zwraca liczbę **nowych** snapshotów (upserty ofert nie są liczone).
- [x] `cli.py` (`argparse`): opcje globalne `--env`, `--db`, `-v` (działają też po komendzie). Komendy `auth login`, `auth status`, `offers list`, `collect`. Kody wyjścia: 0/1/2/3 (SPEC §8); błędy użycia argparse kończą się kodem 1, nie 2.
- [x] `collect --loop --interval SEC` (domyślnie 3600, minimum 300), czysty Ctrl+C (kod 0), błąd pojedynczego przebiegu logowany bez przerywania pętli, z wyjątkiem `AuthError`.
- [x] Testy: kolektor ze sfałszowanym klientem, `--help` każdej komendy, kody wyjścia, wymuszenie minimum interwału.
- [x] (Opcjonalnie) `scripts/probe_counter.py` z fazy 0 SPEC — skrypt gotowy; uruchomienie (≥ 48 h) należy do człowieka.

**Bramka**
```bash
ruff check . && pytest -q --cov=src/view_tracker_ai_1
python -m view_tracker_ai_1.cli --help
```
- `collect` na mocku zapisuje snapshoty i można je odczytać przez `offers list`.
- **Akceptacja fazy 1 (SPEC §15) spełniona.**

**Commit:** `feat: collector and basic CLI`, następnie `git tag v0.1-phase1`
**Dziennik AI:** podsumowanie fazy 1, w tym wszystkie korekty założeń.

---

## Etap 5 — Analityka

**Cel:** poprawne liczby, na których opierają się wykresy i komentarze AI.
**Zależy od:** 4 · **Czyta:** SPEC §4.2, §6 FR-4

**Zadania**
- [ ] `analytics.py` jako **funkcje czyste** (bez I/O i bez czasu systemowego w środku): wybór przedziału (`24h`, `7d`, `30d`, `90d`, `all`), delty, wykrywanie anomalii `counter_decrease`, agregacja dzienna w `Europe/Warsaw`, `coverage`, trend (OLS, progi jako stałe), struktura `SeriesSummary`.
- [ ] Spadek licznika: do przyrostu wlicz 0, zwiększ licznik anomalii, **nigdy ujemnych przyrostów**.
- [ ] Przy < 3 punktach etykieta trendu `brak danych`.
- [ ] Testy z SPEC §12: seria rosnąca, spadek licznika, luki i `coverage`, agregacja dzienna przez zmianę czasu (**2026-10-25, doba 25-godzinna**), cztery etykiety trendu. Dodaj test na serię z samych zer (zero to poprawna wartość).
- [ ] Poprawka zaległa z etapu 4: `tests/test_cli.py::test_config_error_maps_to_exit_one` zgłasza `ResourceWarning: unclosed database` — ścieżka błędu w CLI zostawia otwarte połączenie SQLite. Zamknąć połączenie i pokryć to testem.

**Bramka**
```bash
ruff check . && pytest -q tests/test_analytics.py --cov=src/view_tracker_ai_1
```
- Pokrycie `analytics.py` ≥ 90%.

**Commit:** `feat(analytics): ranges, deltas, anomalies, trend and coverage`
**Dziennik AI:** jak sprawdzono poprawność trendu (np. ręcznie policzony przykład).

---

## Etap 6 — Dane demo i wykresy

**Cel:** wizualizacje, które można pokazać nawet bez ruchu w Sandboxie, uczciwie oznaczone.
**Zależy od:** 5 · **Czyta:** SPEC §6 FR-5, FR-8, §11

**Zadania**
- [ ] `scripts/seed_demo_data.py`: deterministyczny (`--seed`), kilka ofert, 90 dni snapshotów godzinowych. Wzorce: wzrost, spadek, plateau, oferta z anomalią (spadek licznika), oferta z lukami w danych. Zapis **tylko** do osobnej bazy (domyślnie `data/demo.db`) z `source='synthetic'`. Skrypt odmawia zapisu do bazy zawierającej rekordy `api`.
- [ ] `charts.py`: dwa panele (poziom licznika + dzienny przyrost), markery anomalii, opisy osi po polsku, adnotacja pokrycia, napis **„DANE SYNTETYCZNE”** dla `source='synthetic'`. Backend `Agg`. Zwraca ścieżkę i metadane (`is_synthetic`, `n_points`).
- [ ] CLI: komenda `chart --offer ID --range ... [--metric ...] --out FILE.png`.
- [ ] Testy: plik powstaje, `is_synthetic` ustawione, odmowa zapisu seeda do bazy z danymi `api`.
- [ ] **Kontrola wzrokowa:** wygeneruj wykresy dla każdego przedziału z danych demo i obejrzyj je (narzędziem do podglądu obrazów). Sprawdź czytelność polskich znaków, nakładanie się opisów, obecność znaku wodnego.

**Bramka**
```bash
python scripts/seed_demo_data.py --db data/demo.db --seed 42
python -m view_tracker_ai_1.cli --db data/demo.db chart --offer <ID> --range 30d --out reports/chart.png
ruff check . && pytest -q
```
- Wszystkie 5 przedziałów daje poprawny PNG z napisem „DANE SYNTETYCZNE”.

**Commit:** `feat(charts): demo data generator and chart rendering`
**Dziennik AI:** problemy z czytelnością wykresów znalezione przy kontroli wzrokowej i ich poprawki.

---

## Etap 7 — Moduł AI

**Cel:** komentarz do wyników, który nie zmyśla i jest odporny na złośliwe dane.
**Zależy od:** 5 (6 dla demonstracji) · **Czyta:** SPEC §6 FR-6, §10

**Zadania**
- [ ] `ai_comment.py`: interfejs `CommentGenerator`, `FakeCommentGenerator` (deterministyczny), `AnthropicCommentGenerator` (klient tworzony leniwie, model z `LLM_MODEL`, klucz z `ANTHROPIC_API_KEY`).
- [ ] **Bramka danych:** `n_points < 6` lub `coverage < 0.3` → stały komunikat po polsku, **bez wywołania LLM**.
- [ ] Prompt systemowy z SPEC §10. Wejście wyłącznie z zagregowanych liczb. Nazwa oferty w wydzielonym bloku danych.
- [ ] Walidacja wyjścia (przycięcie do 700 znaków, usunięcie markdownu). Błąd API → komunikat zastępczy, bez przerywania raportu.
- [ ] Cache w `ai_comments` pod kluczem hasha wejścia.
- [ ] CLI: komenda `comment` oraz flaga `--no-ai` (użycie `FakeCommentGenerator` lub pominięcie).
- [ ] Testy z SPEC §12: poniżej progów brak wywołania, prompt zawiera tylko agregaty, **nazwa oferty z próbą wstrzyknięcia instrukcji** (test sprawdza, że trafia do bloku danych), błąd API, cache hit bez drugiego wywołania.

**Bramka**
```bash
ruff check . && pytest -q tests/test_ai_comment.py --cov=src/view_tracker_ai_1
```
- Żadne wywołanie prawdziwego API w testach. Pokrycie ≥ 80%.

**Commit:** `feat(ai): data-grounded comments with gate, cache and injection-safe prompt`
**Dziennik AI:** konkretne przypadki, w których komentarz AI był zbyt pewny siebie albo zmyślał przyczyny, i jak prompt to ograniczył. Jeśli nie testowałeś na żywym modelu, napisz to wprost (to zadanie człowieka, SPEC §16).

---

## Etap 8 — Raport HTML

**Cel:** jeden plik, który pokazuje wszystko razem. Koniec fazy 2 ze SPEC.
**Zależy od:** 6, 7 · **Czyta:** SPEC §6 FR-7, §11

**Zadania**
- [ ] `report.py` + szablon Jinja2 (**autoescape włączony**): nagłówek z badge środowiska (SANDBOX/PROD/DEMO) i czasem generowania, sekcja na ofertę z wykresami wybranych przedziałów (obrazy base64), tabela liczb z FR-4, komentarz AI, stopka z ostrzeżeniem o semantyce licznika (SPEC §4.2).
- [ ] CLI: `report --range ... [--offer ID ...] [--no-ai] --out reports/report.html`.
- [ ] Testy: autoescape (nazwa oferty z `<script>`), badge środowiska, raport z danych demo zawiera napis „DANE SYNTETYCZNE”.

**Bramka**
```bash
python -m view_tracker_ai_1.cli --db data/demo.db report --range 30d --no-ai --out reports/report.html
ruff check . && pytest -q --cov=src/view_tracker_ai_1
```
- Raport tworzy się z danych demo, plik jest samodzielny (brak zewnętrznych zasobów).
- **Akceptacja fazy 2 (SPEC §15) spełniona.**

**Commit:** `feat(report): self-contained HTML report`, następnie `git tag v0.2-phase2`
**Dziennik AI:** podsumowanie fazy 2.

---

## Etap 9 — Zmiana ceny przez API (opcjonalny, decyzja D1)

**Cel:** widoczna „zmiana na koncie” do dokumentacji, bezpiecznie.
**Zależy od:** 3, 4 · **Czyta:** SPEC §6 FR-9, §9; `docs/api-notes.md` pkt 6

Jeśli D1 = „nie”: oznacz etap `[-]`, zapisz decyzję w dzienniku AI i przejdź do etapu 10.

**Zadania**
- [ ] `actions.py`: budowa żądania zmiany ceny **dokładnie wg `api-notes.md`** (wybór `PATCH` albo komend zmiany ceny wynika z dokumentacji, nie z domysłu).
- [ ] **Dry-run domyślnie**: pokazuje, co zostałoby wysłane (bez sekretów). Dopiero `--apply` wysyła żądanie.
- [ ] Na produkcji odmowa, chyba że `ALLOW_PROD_WRITES=1`.
- [ ] Każde wykonanie zapisywane w `actions_log`. Błąd `422` pokazany czytelnie (kod, komunikat, pole).
- [ ] CLI: `act price --offer ID --amount X [--apply]`.
- [ ] Testy z SPEC §12: dry-run niczego nie wysyła, `--apply` na produkcji odmawia, `422`, wpis w `actions_log`.

**Bramka**
```bash
ruff check . && pytest -q tests/test_actions.py
python -m view_tracker_ai_1.cli act price --offer 123 --amount 49.99   # dry-run, nic nie wysyła
```
- Wyjście dry-run nie zawiera tokenów.

**Commit:** `feat(actions): guarded price change with dry-run default`
**Dziennik AI:** rozbieżności między założonym a rzeczywistym formatem żądania i błędów.

---

## Etap 10 — Dokumentacja

**Cel:** komplet materiałów wymaganych do zaliczenia, gotowy do uzupełnienia o zrzuty ekranu.
**Zależy od:** 4–9 · **Czyta:** SPEC §14, §16

**Zadania**
- [ ] `README.md` po polsku, **10 sekcji w kolejności z SPEC §14** (cel; funkcjonalność/endpointy/scope; schemat przepływu; uruchomienie; przykłady; błędy i limity; testy; bezpieczeństwo; dziennik AI; ograniczenia). Tabela „funkcja → endpoint → scope” z wartości zweryfikowanych w `api-notes.md` (niezweryfikowane oznacz wprost).
- [ ] Tabela zmiennych środowiskowych (nazwa, do czego, wymagana?, przykład bez prawdziwej wartości).
- [ ] `docs/data-flow.md` z diagramem Mermaid (SPEC §5).
- [ ] `docs/manual-sandbox-checklist.md`: kroki dla człowieka z dokładnymi komendami (rejestracja aplikacji, `.env`, `auth login`, `collect`, generowanie ruchu, `report`).
- [ ] `docs/screenshots/README.md`: lista zrzutów do wykonania (nazwa pliku, komenda, co ma być widoczne, **co zamaskować**: tokeny, identyfikatory konta, dane osobowe).
- [ ] Sekcja „Przykłady” w README: komendy odtwarzające input → output, z miejscami na zrzuty.
- [ ] `docs/ai-journal.md` uzupełniony o wszystkie etapy. Pole „Refleksja” zostaw człowiekowi.

**Bramka**
- `grep -c '^## ' README.md` pokazuje wszystkie 10 sekcji.
- Wszystkie odnośniki wewnętrzne działają, w dokumentach nie ma żadnych wartości sekretów.
- Każda komenda z README została faktycznie uruchomiona (na mocku lub danych demo) i działa.

**Commit:** `docs: README, data flow, manual checklist, AI journal`

---

## Etap 11 — Domknięcie i kontrola jakości

**Cel:** potwierdzić Definition of Done ze SPEC §15 i przekazać projekt człowiekowi.
**Zależy od:** 10

**Zadania**
- [ ] **Czyste środowisko:** nowe venv, `pip install -r requirements.txt -r requirements-dev.txt`, pełne `pytest --cov` i `ruff check .`.
- [ ] **Skan sekretów:** `gitleaks` (jeśli dostępny) albo przeszukanie repo i historii commitów (`git log -p`) pod kątem wzorców tokenów, kluczy i `client_secret`. Sprawdź też, że `.env`, `data/`, `reports/`, pliki tokenów są w `.gitignore` i nie są śledzone (`git ls-files`).
- [ ] Przejrzyj wszystkie `TODO(verify)`: rozwiąż albo opisz jako ograniczenie w README.
- [ ] Przejdź listę **Definition of Done z SPEC §15** punkt po punkcie i zapisz wynik.
- [ ] Zaktualizuj tabelę statusu w tym pliku.
- [ ] Końcowy raport do człowieka: co działa, odstępstwa od SPEC, znane ograniczenia (semantyka licznika, brak ruchu w Sandboxie), lista zadań człowieka z SPEC §16 (rejestracja aplikacji, zrzuty ekranu, test na żywym API i modelu, decyzja D1, refleksja).

**Bramka:** wszystkie punkty DoD odhaczone. Jeśli któryś nie jest spełniony, napisz który i dlaczego, zamiast go zaznaczać.

**Commit:** `chore: final QA pass`, następnie `git tag v1.0`

---

## Dodatki

### Wznowienie pracy w nowej sesji

1. Przeczytaj `AGENTS.md`, tabelę statusu w tym pliku i ostatnie ~10 wpisów `docs/ai-journal.md`.
2. Uruchom `git status` i `git log --oneline -10`, żeby zobaczyć, gdzie praca stanęła.
3. Uruchom bramkę ostatniego odhaczonego etapu. Jeśli jest czerwona, zacznij od naprawy.
4. Wróć do protokołu pracy i kontynuuj od pierwszego nieodhaczonego etapu.

### Format raportu po etapie (do człowieka)

```
Etap N — <nazwa>: zakończony
Zrobione: <2–4 punkty>
Odstępstwa od SPEC: <brak | lista z uzasadnieniem>
Otwarte pytania / rzeczy dla człowieka: <brak | lista>
Bramka: <wynik komend, pokrycie>
```

### Czego nie robić w żadnym etapie

- Nie scrapuj allegro.pl i nie używaj nieudokumentowanych endpointów.
- Nie komituj sekretów, tokenów, baz danych ani raportów z prawdziwymi danymi.
- Nie mieszaj danych syntetycznych z danymi z API w jednej bazie.
- Nie wykonuj zapisów do API na produkcji.
- Nie odhaczaj bramki, której nie uruchomiłeś.
