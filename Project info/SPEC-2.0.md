# SPEC-2.0.md — view_tracker_ai_1 2.0 (interaktywna aplikacja webowa)

> Wersja 2.0.0 · 2026-11-02 · Dokument dla agenta AI, który implementuje aplikację.
> Język kodu, komentarzy i commitów: **angielski**. UI, komunikaty, README: **polski**.
> Dokument bazowy: `Project info/SPEC.md` (wersja 1.0.0, CLI). Wersja 2.0.0 **zastępuje paradygmat**: zamiast komend i plików — interaktywna aplikacja webowa.

---

## 0. Zasady pracy agenta (przeczytaj najpierw)

1. **Dokumentacja Allegro jest ważniejsza niż ten plik.** Przed użyciem endpointu sprawdź go na developer.allegro.pl. Rozbieżność zapisz w `docs/ai-journal.md` (sekcja „Odstępstwa od SPEC”).
2. **Niczego nie zgaduj.** Rzeczy niezweryfikowane są oznaczone `TODO(verify)`; nie wymyślaj nazw pól, parametrów ani scope'ów.
3. **Testy działają offline.** Zero prawdziwych żądań sieciowych — mocki (`responses`), blokada gniazd w `tests/conftest.py` obowiązuje.
4. **Sekrety tylko w `.env` poza repo.** Nigdy w UI, logach, zrzutach ekranu, przykładach ani w URL.
5. **Rdzeń v1 zostaje.** `analytics.py`, `storage.py`, `client.py`, `auth.py`, `config.py` przechodzą do 2.0 bez zmiany kontraktów (poza `storage` — patrz §7). Nie przepisujemy ich „przy okazji”.
6. **Warstwy.** `ui/` zna tylko `services.py` i `queries.py`; nie importuje `sqlite3`, `storage`, `client` ani `analytics` bezpośrednio. Wyjątek: `models` (typy DTO).
7. **Pracuj etapami** (§15). Po każdym: `ruff check`, `pytest`, commit, wpis w `docs/ai-journal.md`.
8. **Zakaz scrapingu.** Tylko oficjalne REST API Allegro.

---

## 1. Cel i kontekst

**Problem sprzedawcy:** panel Allegro pokazuje tylko bieżące liczniki oferty. Sprzedawca nie widzi trendu, nie wie, czy po zmianie ceny lub tytułu zainteresowanie wzrosło, i nie ma jak porównać ofert między sobą.

**v1.0 (oddane):** CLI + SQLite + wykresy PNG + raport HTML + komentarz AI. Działa, ale każda analiza kończy się plikiem na dysku, a przełączanie ofert i zakresów wymaga wpisywania komend.

**2.0.0:** aplikacja webowa uruchamiana lokalnie, w której **klikając** wybiera się ofertę (lub kilka), zakres czasu i metrykę, a wyniki — wykres, liczby, ranking, porównania, zdarzenia — są widoczne od razu. Część AI zostaje **usunięta** (§10), eksport plików również (§2).

**Kontekst:** projekt zaliczeniowy (integracja z API Allegro), środowisko Sandbox. Interfejs ma być self-service: bez terminala, bez plików pośrednich.

---

## 2. Zakres

**W zakresie 2.0.0:**

- aplikacja Streamlit uruchamiana lokalnie (localhost), UI po polsku,
- logowanie Allegro (device flow) i status tokena **w aplikacji**,
- wybór środowiska/bazy (sandbox / prod / demo) z widocznym oznaczeniem,
- lista ofert: wyszukiwanie, filtr statusu, wybór jednej lub wielu ofert,
- zakres czasu: `24h`, `7d`, `30d`, `90d`, `all` + zakres własny (od–do),
- metryka: wyświetlenia, obserwujący, obie,
- wykres interaktywny: poziom licznika + dzienne przyrosty, markery anomalii, adnotacja pokrycia, znak wodny dla danych syntetycznych,
- karta podsumowania (pola z SPEC v1 §6 FR-4),
- przegląd „ogółem”: kafle zbiorcze, ranking ofert, porównanie z medianą własnego katalogu,
- porównanie okresów (bieżący vs poprzedni) i porównanie ofert (indeks 100),
- warstwa zdarzeń: zdarzenia ofert z API oraz adnotacje ręczne nanoszone na wykres,
- „co nowego od ostatniej wizyty”,
- alerty progowe (reguły w bazie, sygnalizacja w UI),
- jakość danych i świeżość: wiek ostatniego snapshotu, pokrycie, luki, stan kolektora,
- przycisk „Odśwież” (jednorazowy przebieg kolektora) **oraz opcjonalny tryb ciągły** (§9, decyzja D3),
- tryb demo: generator danych syntetycznych i wyraźne oznaczenie,
- strona „Przegląd” jako odpowiednik raportu — **bez pobierania pliku**.

**Poza zakresem 2.0.0:**

- wszelkie funkcje AI: komentarz, digest, `anthropic`, klucze LLM (§10),
- eksport plików: PNG, CSV, HTML, PDF — ani przycisku, ani komendy,
- interfejs CLI dla użytkownika (decyzja D6),
- wielu użytkowników, hosting publiczny, uwierzytelnianie aplikacji, mobile,
- scraping, edycja ofert przez API (etap 9 z v1 pozostaje odłożony),
- powiadomienia e-mail/Slack.

---

## 3. Decyzje (wiążące dla implementacji)

| ID | Decyzja | Wartość | Uzasadnienie |
|---|---|---|---|
| D1 | Framework UI | **Streamlit 1.66.x + Plotly 7.1.x** | najkrótsza droga do interaktywności, gotowe widżety tabel/kart, brak JS |
| D2 | Forma | **aplikacja webowa lokalna** (`localhost`) | wymóg „interaktywny software”, zero deploymentu |
| D3 | Zbieranie danych | przycisk **„Odśwież”** + **opcjonalna pętla w aplikacji** (domyślnie WYŁĄCZONA, §9) | użytkownik chce wszystko w aplikacji; pętla żyje tyle, co proces serwera |
| D4 | AI | **usunięte z projektu** (kod, zależność, zmienne, tabela) | brak potrzeby; upraszcza instalację i bezpieczeństwo |
| D5 | Eksport | **usunięty** | odpowiednikiem jest strona „Przegląd” na ekranie |
| D6 | CLI | **usunięte dla użytkownika**; każda funkcja CLI ma odpowiednik w UI (§4) | „wszystko, co było w CLI, ma być w aplikacji” |
| D7 | Baza | **migracja addytywna v1 → v2**: istniejące bazy otwierają się, dochodzą nowe tabele, `ai_comments` usunięta | nie tracimy zebranej historii |
| D8 | Język | UI i komunikaty po polsku, kod i commity po angielsku | konwencja projektu |
| D9 | SQLite w aplikacji | `journal_mode=WAL`, `busy_timeout`, **połączenie per wątek**, brak długich transakcji | współbieżność pętli kolektora i UI |
| D10 | Użytkownicy | jeden lokalny użytkownik, bez logowania do aplikacji | poza zakresem |

> Uwaga do D7: migracja jest nieodwracalna wstecz (v2 nie otworzy się w v1). Przed migracją aplikacja tworzy kopię pliku bazy (`data/*.db.bak-YYYYMMDD-HHMMSS`).

---

## 4. Parytet funkcji CLI → aplikacja

| CLI 1.0 | 2.0 |
|---|---|
| `auth login` | ekran **Logowanie**: kod, link, status „czekam na zatwierdzenie”, potem „zalogowano, token ważny do…” |
| `auth status` | belka stanu na każdej stronie: token ważny/wygasł + przycisk „Zaloguj ponownie” |
| `offers list` | strona **Oferty**: tabela z wyszukiwaniem, filtrem statusu, wyborem |
| `collect` | przycisk **„Odśwież”** z podsumowaniem (ofert / nowych snapshotów / błąd) |
| `collect --loop` | przełącznik **„Tryb ciągły”** (§9), domyślnie wyłączony |
| `chart` | **Oferta**: wykres Plotly + przełączniki zakresu i metryki |
| `comment` | brak (AI usunięte) |
| `report` | strona **Przegląd**: kafle ogółem, ranking, sekcje ofert — bez pliku |
| `--env`, `--db`, `-v` | selektory środowiska i bazy w panelu bocznym; poziom logów w **Ustawieniach** |
| kody wyjścia 1/2/3 | komunikaty z akcją następną: „zaloguj ponownie”, „limit API — spróbuj za minutę”, „błąd bazy” |

---

## 5. Architektura

```mermaid
flowchart LR
    A[Allegro REST API] -->|GET /sale/offers, /sale/offer-events| B[client + collector]
    B --> C[(SQLite: offers, snapshots, events, annotations, runs)]
    C --> D[queries.py: agregaty SQL]
    C --> E[analytics.py: funkcje czyste]
    D --> F[services.py: przypadki użycia]
    E --> F
    F --> G[ui/: Streamlit + Plotly]
    H[auth: device flow] --> G
    I[pętla kolektora w wątku] --> B
    G -->|"Odśwież" / "Tryb ciągły"| I
```

### Struktura repo (docelowa)

```
view_tracker_ai_1/
├── Project info/                 # SPEC.md (v1), SPEC-2.0.md (ten plik), PLAN, AGENTS
├── README.md                     # po polsku, sekcje §14
├── pyproject.toml
├── requirements.txt              # bez anthropic/matplotlib, z streamlit/plotly
├── requirements-dev.txt
├── .env.example
├── src/view_tracker_ai_1/
│   ├── config.py  errors.py  models.py        # istnieją (bez LLM_*)
│   ├── auth.py  client.py  collector.py       # istnieją
│   ├── analytics.py  storage.py               # istnieją; storage + migracja v2
│   ├── queries.py                              # NOWE: agregaty SQL
│   ├── services.py                             # NOWE: przypadki użycia
│   ├── events.py                               # NOWE: zdarzenia ofert + adnotacje
│   ├── text.py                                 # NOWE: odmiana liczebników, formaty PL
│   └── ui/
│       ├── __init__.py
│       ├── app.py                              # entry: nawigacja, stan, cache
│       ├── runtime.py                          # tryb ciągły (wątek), status kolektora
│       ├── state.py                            # query_params + session_state
│       ├── charts.py                           # figury Plotly
│       └── pages/
│           ├── 1_przeglad.py
│           ├── 2_oferta.py
│           ├── 3_porownanie.py
│           ├── 4_dane.py
│           └── 5_ustawienia.py
├── scripts/
│   └── seed_demo_data.py                       # istnieje
└── tests/
```

**Usuwane w 2.0:** `ai_comment.py`, `charts.py` (matplotlib), `report.py`, `cli.py` oraz ich testy; `anthropic`, `matplotlib` z zależności; `ai_comments` z bazy.

---

## 6. Wymagania funkcjonalne

**FR-1 Uruchomienie.** `python -m view_tracker_ai_1.ui` startuje aplikację na `127.0.0.1:${UI_PORT:-8501}`. Strona główna ładuje się bez sekretów i bez sieci; brak `.env` nie jest błędem (tryb demo działa).

**FR-2 Logowanie.** Ekran pokazuje `verification_uri` i `user_code`, odświeża status co `interval` (polling w tle), po zatwierdzeniu zapisuje tokeny (§13) i pokazuje datę ważności. Anulowanie i wygaśnięcie kodu mają czytelne komunikaty.

**FR-3 Status tokena.** Belka: „Token ważny do DD.MM.YYYY HH:MM”, „Token wygasł — zaloguj się ponownie”, „Brak logowania”. Nigdy nie pokazuje wartości tokenu.

**FR-4 Środowisko i baza.** Selektor: sandbox / prod / demo. Dla `prod` aplikacja jest **tylko do odczytu** (przycisk „Odśwież” i tryb ciągły zablokowane, wyraźny badge). Ścieżka bazy widoczna w Ustawieniach.

**FR-5 Odświeżanie.** Przycisk „Odśwież” woła `collector.run_once` w jednej transakcji, pokazuje wynik (liczba ofert, nowych snapshotów, czas) i zapisuje wpis w `collect_runs`. `AuthError` → komunikat z akcją „Zaloguj ponownie”; `ApiError`/`RateLimitError` → komunikat z powodem, bez utraty ekranu.

**FR-6 Tryb ciągły.** Przełącznik + interwał (domyślnie 3600 s, minimum 300 s). Stan: ostatni przebieg, następny przebieg, liczba przebiegów, liczba zapisanych snapshotów, ostatni błąd. Zatrzymanie natychmiastowe. Szczegóły w §9.

**FR-7 Lista ofert.** Wyszukiwanie po nazwie/ID, filtr statusu, sortowanie po ostatnim snapshocie/przyroście, wybór wielu ofert. Wybór i filtry w `st.query_params` (linkowalne).

**FR-8 Wykres.** Dwa panele Plotly: poziom metryki (linia) i dzienne przyrosty (słupki). Markery anomalii `counter_decrease`, pionowe znaczniki zdarzeń/adnotacji (§FR-15), adnotacja pokrycia, tytuł z nazwą oferty i zakresem, osie po polsku z jednostkami, czas w `Europe/Warsaw`. Zoom i hover wbudowane w Plotly.

**FR-9 Metryki.** Przełącznik: wyświetlenia / obserwujący / obie (dwie osie albo dwa wykresy — wersja z dwiema osiami). Wartości zawsze z etykietami „wyświetlenia” i „obserwujący” (nigdy „polubienia”).

**FR-10 Zakresy.** Presety + zakres własny (od–do, walidacja: od ≤ do, do ≤ dziś). Własny zakres liczony w `Europe/Warsaw`, w bazie UTC.

**FR-11 Karta podsumowania.** `start`, `end`, `min`, `max`, `mean`, `gained_total`, `slope_per_day`, `trend_label`, `coverage`, liczba anomalii, liczba punktów — z etykietami PL i odmianą liczebników.

**FR-12 Przegląd „ogółem”.** Kafle: suma bieżących poziomów (dla ostatniego wspólnego snapshotu), suma przyrostów w przedziale, liczba obserwujących, liczba ofert, liczba ofert ze spadkiem, mediana przyrostu. Ranking ofert po `gained_total` w przedziale. **Definicja „ogółem” jest częścią wymagania:** nie sumujemy poziomów w czasie — suma poziomów dotyczy jednej chwili, przyrosty sumujemy per oferta z pominięciem spadków.

**FR-13 Porównanie okresów.** Dla wybranego zakresu: bieżący vs poprzedni okres tej samej długości; pokazujemy przyrosty i zmianę procentową (z obsługą zera i braku danych).

**FR-14 Porównanie ofert.** Do 5 ofert na jednym wykresie, normalizacja do indeksu 100 w pierwszym punkcie wspólnego okna; tabela przyrostów per oferta.

**FR-15 Zdarzenia i adnotacje.** Warstwa zdarzeń z API (`GET /sale/offer-events`, `TODO(verify)` — §4 dokumentacji v1, `docs/api-notes.md` §9) oraz adnotacje ręczne (data, etykieta, notatka). Nanoszone jako pionowe linie z tooltipem. Lista zdarzeń obok wykresu.

**FR-16 „Co nowego” i alerty.** Po wejściu na ofertę: od ostatniej wizyty (zapis w `app_state`) — zmiana poziomu, nowe anomalie, nowe zdarzenia. Alerty progowe: reguła (`spadek o ≥ X%` albo `≥ Y sztuk` w oknie N dni), oceniana przy każdym odświeżeniu i wejściu; trafienia widoczne jako ostrzeżenie w UI. Bez powiadomień zewnętrznych.

**FR-17 Jakość i świeżość danych.** Wiek ostatniego snapshotu, pokrycie zakresu, liczba luk > 2h, informacja o źródle (`api`/`synthetic`). Gdy `coverage < 0.3` lub `n_points < 6` — widoczna adnotacja „mało danych, trend niepewny” (bez blokowania widoku).

**FR-18 Tryb demo.** Przycisk generujący dane syntetyczne do `data/demo.db` (`scripts/seed_demo_data.py`, deterministyczny `--seed`). Każdy wykres, tabela i kafel z `source='synthetic'` ma znak wodny/plakietkę **„DANE SYNTETYCZNE”**.

**FR-19 Ustawienia.** Ścieżka bazy, środowisko, poziom logów, interwał trybu ciągłego, wersja aplikacji i schematu, informacja o katalogu tokenów (bez zawartości).

### Wymagania niefunkcjonalne

- **NFR-1** Zero sekretów w UI, URL, logach i zrzutach ekranu.
- **NFR-2** Testy offline i deterministyczne; żadnych prawdziwych `sleep` ani sieci.
- **NFR-3** Czasy w bazie UTC, prezentacja `Europe/Warsaw`.
- **NFR-4** `ruff check` bez błędów; `from __future__ import annotations`.
- **NFR-5** Odczyt typowego widoku (50 ofert × 90 dni, jedna oferta) < 2 s po rozgrzaniu cache; start aplikacji < 5 s.
- **NFR-6** Brak globalnego stanu poza `Config` i `st.session_state`; połączenia SQLite zarządzane jawnie.
- **NFR-7** Aplikacja nie może blokować się na żądaniach sieciowych w wątku UI (długie operacje w tle lub z `st.status`).
- **NFR-8** Polskie etykiety z poprawną odmianą (1 oferta / 2 oferty / 5 ofert).

---

## 7. Model danych (SQLite v2)

Zostają tabele v1: `offers`, `snapshots` (+indeks), `actions_log`. **Usuwana:** `ai_comments`. **Nowe:**

```sql
CREATE TABLE collect_runs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at    TEXT NOT NULL,          -- UTC ISO 8601
  finished_at   TEXT,
  status        TEXT NOT NULL CHECK (status IN ('running','ok','error','auth_error')),
  offers_count  INTEGER NOT NULL DEFAULT 0,
  inserted      INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);

CREATE TABLE offer_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_id    TEXT NOT NULL,            -- bez FK: zdarzenie może dotyczyć oferty spoza listy
  occurred_at TEXT NOT NULL,            -- UTC
  type        TEXT NOT NULL,            -- np. OFFER_PRICE_CHANGED
  payload_json TEXT NOT NULL DEFAULT '{}',
  fetched_at  TEXT NOT NULL,
  UNIQUE (offer_id, occurred_at, type)
);

CREATE TABLE annotations (              -- adnotacje ręczne
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_id   TEXT NOT NULL,
  occurred_at TEXT NOT NULL,            -- UTC
  label      TEXT NOT NULL,
  note       TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE alert_rules (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_id    TEXT,                     -- NULL = wszystkie oferty
  kind        TEXT NOT NULL CHECK (kind IN ('pct_drop','abs_drop')),
  threshold   REAL NOT NULL,
  window_days INTEGER NOT NULL CHECK (window_days > 0),
  created_at  TEXT NOT NULL
);

CREATE TABLE app_state (                -- stan UI trwały między sesjami
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

**Migracja (D7):** `SCHEMA_VERSION = 2`. Funkcja `storage.migrate(conn)`:
- wersja 1 → 2: utwórz nowe tabele, `DROP TABLE IF EXISTS ai_comments`, ustaw wersję 2, kopia zapasowa pliku przed migracją;
- wersja 2 → bez zmian (idempotentnie);
- wersja > 2 → `StorageError`;
- pusta baza → od razu schemat v2.

**Zapytania agregujące (`queries.py`)** — muszą liczyć w SQL, nie w Pythonie:
`offers_overview(conn, offer_ids, since, until)` (poziomy ostatniego wspólnego snapshotu, sumy przyrostów per oferta), `ranking(conn, since, until)`, `median_gain(...)`, `freshness(conn)`, `gaps(conn, offer_id, since)`, `snapshots_for(conn, offer_ids, since, until)`.
Przyrosty liczone per oferta (`max(delta,0)`), nigdy przez sumowanie poziomów w czasie.

---

## 8. Ekrany aplikacji

| Strona | Zawartość | Stany |
|---|---|---|
| **Przegląd** | kafle ogółem, ranking ofert, alerty, świeżość, skróty do ofert | pusty start (brak danych), demo, błąd API |
| **Oferta** | wybór oferty, zakres, metryka, wykres, karta podsumowania, zdarzenia/adnotacje, „co nowego”, sekcja AI: **brak** | brak ofert, brak punktów, mało punktów, dane syntetyczne |
| **Porównanie** | wybór 2–5 ofert, indeks 100, tabela przyrostów, porównanie okresów | za mało ofert, brak wspólnego okna |
| **Dane** | stan kolektora: ostatnie przebiegi, świeżość, luki, przycisk „Odśwież”, tryb ciągły | brak uprawnień (prod), błąd auth, błąd limitu |
| **Ustawienia** | środowisko, baza, logi, interwał, wersje, katalog tokenów, akcje demo | — |

Stan w URL: `db`, `env`, `offer` (może wielokrotnie), `range`, `from`, `to`, `metric`, `compare`. Przykład: `/?db=sandbox&offer=123&range=30d&metric=visits`.

---

## 9. Kolektor, pętla i harmonogram

- **Przycisk „Odśwież”** → `collector.run_once` (istnieje) + wpis `collect_runs` (`running` → `ok`/`error`).
- **Tryb ciągły (D3):**
  - wątek daemon uruchamiany raz na proces serwera; uchwyt trzymany w `@st.cache_resource` (`ui/runtime.py`),
  - start/stop z UI, interwał walidowany (≥ 300 s), wartość interwału zapisana w `app_state`,
  - stan włączony **nie** jest odtwarzany po restarcie serwera (świadoma decyzja: brak zaskakującego zbierania w tle),
  - każdy przebieg: `run_once`, wpis `collect_runs`, obsługa błędów: `AppError` → log + status, `AuthError` → stop pętli + baner „zaloguj ponownie”,
  - wątek nie dotyka `st.session_state`; komunikuje się przez obiekt `RuntimeStatus` (lock + pola), który UI tylko odczytuje,
  - połączenie SQLite tworzone **w wątku** kolektora (nie współdzielone z UI), `WAL` + `busy_timeout=5000`,
  - stop: `Event.set()` + `join(timeout=5)`; przy zamykaniu serwera wątek jest daemonem.
- **Ograniczenie wpisane w UI i README:** tryb ciągły działa tylko, gdy proces aplikacji jest uruchomiony; uśpienie laptopa = luka w danych.
- **Poza trybem ciągłym** aplikacja nie wykonuje żadnych żądań w tle.

---

## 10. Usunięcie AI (D4)

| Element | Akcja |
|---|---|
| `ai_comment.py`, `tests/test_ai_comment.py` | usunąć |
| `cli.py` (komendy `comment`, `report`), `tests/test_cli.py` | usunąć (zastąpione testami `services`/UI) |
| `charts.py`, `report.py` + testy | usunąć (eksport wycofany, wykresy w Plotly) |
| `storage.get_cached_comment` / `put_cached_comment` | usunąć |
| tabela `ai_comments` | `DROP` w migracji v2 |
| `requirements.txt`: `anthropic`, `matplotlib` | usunąć |
| `.env.example`, `config.py`: `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `LLM_MODEL`, `require_llm` | usunąć |
| SPEC/README/PLAN wzmianki o AI | oznaczyć jako wycofane w 2.0; `docs/ai-journal.md` zostaje jako zapis historyczny |

Po usunięciu `requirements.txt`: `jinja2` (używany tylko przez `report.py`) **też do usunięcia**, chyba że zostanie użyty w UI (nie jest). Zostają: `requests`, `python-dotenv`, `tzdata`, `streamlit`, `plotly`.

---

## 11. Wykresy i formatowanie

- **Plotly** (`plotly.graph_objects`), jedna figura z dwoma wierszami (`make_subplots`, `row_heights=[0.7, 0.3]`, wspólna oś czasu).
- Kolory i style w jednym miejscu (`ui/charts.py`): linia poziomu, słupki przyrostów dodatnich/ujemnych (spadek pokazany na czerwono w warstwie przyrostów, ale **nie** jako ujemne wyświetlenia — patrz v1 §4.2), markery anomalii, pionowe linie zdarzeń/adnotacji.
- Tytuł: nazwa oferty (przycięta), zakres, metryka; podtytuł: pokrycie i liczba punktów.
- Dla `source='synthetic'`: znak wodny „DANE SYNTETYCZNE” (adnotacja w narożniku) + plakietka w nagłówku.
- Formatowanie liczb: separator tysięcy spacją, przecinek dziesiętny; daty `DD.MM.YYYY HH:MM` w `Europe/Warsaw`; odmiana: „1 punkt / 2 punkty / 5 punktów” (`text.py`, przenieść `_plural` z usuwanego `ai_comment.py` i pokryć testami).
- Hover templates po polsku z jednostkami („wyświetlenia”, „obserwujący”).

---

## 12. Testy

**Bramka każdego etapu:** `ruff check . && pytest -q`.

| Obszar | Przypadki | Cel pokrycia |
|---|---|---|
| `queries.py` | sumy poziomów jednej chwili, przyrosty per oferta z pominięciem spadków, ranking, mediana, świeżość, luki, filtr ofert/okresu | ≥ 90% |
| `services.py` | kompozycja podsumowań, porównanie okresów (w tym poprzedni okres pusty), normalizacja indeksu 100 (dzielenie przez zero), „co nowego”, ocena alertów, błędne zakresy | ≥ 90% |
| `events.py` | parsowanie zdarzeń (mock), deduplikacja `UNIQUE`, adnotacje CRUD, brak zdarzeń = brak warstwy | ≥ 85% |
| `storage` (migracja) | v1 → v2 zachowuje `offers`/`snapshots`, usuwa `ai_comments`, idempotencja, wersja >2 = błąd, kopia zapasowa | ≥ 90% |
| `ui` | `st.testing.v1.AppTest`: aplikacja startuje bez `.env`, pusta baza → empty state, wybór oferty rysuje wykres, przełącznik metryki, „Odśwież” na atrapie klienta, tryb demo | smoke, 6–8 testów |
| rdzeń v1 (bez AI/CLI) | istniejące testy `analytics`, `storage`, `client`, `auth`, `config`, `collector` | bez zmian |

Zasady: żadnych testów opartych na obrazkach; figury Plotly porównujemy jako dane (`fig.data`, `fig.layout`), nie jako PNG. Test pętli: wątek zatrzymuje się w ≤ 5 s, nie startuje bez włączenia, `AuthError` zatrzymuje pętlę. Brak sieci w testach (blokada gniazd).

---

## 13. Bezpieczeństwo

- Sekrety tylko w `.env` poza repo; `.env.example` bez wartości.
- Tokeny: plik `~/.config/view_tracker_ai_1/tokens.json`, katalog 700 / plik 600, zapis atomowy (istnieje w `auth.py`).
- UI nie wyświetla tokenów, nie zapisuje ich w `st.session_state`, nie wstawia do URL ani logów; `config.redact()` obowiązuje w logach.
- Produkcja: tylko odczyt; przycisk odświeżania i tryb ciągły zablokowane, badge PROD.
- Zrzuty ekranu do dokumentacji: bez tokenów, identyfikatorów konta i danych kupujących.

---

## 14. Dokumentacja do dostarczenia

`README.md` (po polsku) — sekcje: cel; zrzut ekranu aplikacji; wymagania i instalacja; konfiguracja `.env`; uruchomienie (`python -m view_tracker_ai_1.ui`); **pierwsze kroki** (login → odśwież → przegląd); wyjaśnienie pojęć (poziom vs przyrost, pokrycie, anomalia, dane syntetyczne); tryb ciągły i jego ograniczenia (tylko przy działającej aplikacji); błędy i limity API; testy; bezpieczeństwo; dziennik AI; ograniczenia (semantyka `visitsCount`, sandbox bez ruchu).

Nowe/aktualizowane dokumenty: `docs/ui-flows.md` (ekrany, stany, parametry URL), `docs/api-notes.md` §9 (zdarzenia ofert, `TODO(verify)`), `docs/manual-sandbox-checklist.md` (login w aplikacji), `docs/screenshots/README.md` (lista zrzutów 2.0), `docs/ai-journal.md` (wpisy etapów 2.0).

---

## 15. Etapy i kryteria akceptacji

**S0 — Porządki i fundament danych.** *(wykonany 2026-11-02 na gałęzi `release/2.0`)* Usunięcie AI/CLI/eksportu (§10), migracja schematu v2 (§7), wydzielenie `services.py`/`queries.py`/`text.py` z logiki dotychczasowego CLI, aktualizacja zależności, zielone testy rdzenia.
*Bramka:* `ruff` + `pytest`; migracja v1→v2 z testem; brak `anthropic`/`matplotlib` w środowisku; istniejące dane czytelne.

**S1 — Szkielet aplikacji.** *(wykonany 2026-11-02)* `ui/app.py` + nawigacja + `state.py` (URL) + belka statusu (token, baza, świeżość) + strona Ustawienia + wybór bazy/środowiska + read-only prod.
*Bramka:* aplikacja startuje bez `.env`; AppTest smoke zielony; URL odtwarza widok.

**S2 — Oferta i wykres.** *(wykonany 2026-11-02)* Lista/wybór oferty, zakresy (presety + własny), metryka, wykres Plotly (poziom + przyrosty + anomalie + pokrycie), karta podsumowania.
*Bramka:* wykres dla każdego z 5 presetów; testy `services`; dane syntetyczne oznaczone.

**S3 — Przegląd i porównania.** *(wykonany 2026-11-02)* Kafle ogółem, ranking, mediana, porównanie okresów, porównanie ofert (indeks 100).
*Bramka:* zgodność liczb z ręcznie policzonym przypadkiem w teście; wydajność < 2 s.

**S4 — Kolektor w aplikacji.** *(wykonany 2026-11-02)* „Odśwież”, `collect_runs`, świeżość, tryb ciągły (domyślnie OFF), obsługa `AuthError`/`ApiError`, WAL.
*Bramka:* testy wątku (start/stop ≤ 5 s, brak startu bez włączenia); brak wyścigów w teście równoległego odczytu i zapisu.

**S5 — Zdarzenia i alerty.** *(wykonany 2026-11-02; endpoint potwierdzony w docs/api-notes.md §9, kształt odpowiedzi i scope nadal TODO(verify)) * `events.py`, weryfikacja `GET /sale/offer-events` w dokumentacji, nanoszenie zdarzeń i adnotacji, „co nowego”, reguły alertów.
*Bramka:* testy parsowania i deduplikacji; dokumentacja potwierdzona w `docs/api-notes.md`; przy braku dostępu do endpointu — adnotacje ręczne działają, a `TODO(verify)` zostaje opisane.

**S6 — Demo, dokumentacja, QA.** Generator demo w UI, dokumenty §14, zrzuty ekranu (człowiek), przegląd DoD, `git tag v2.0.0`.
*Bramka:* aplikacja spełnia §2; README kompletny; brak sekretów w historii; wszystkie `TODO(verify)` rozwiązane albo opisane.

**Definition of Done 2.0.0:** czysta instalacja (`pip install -r requirements-dev.txt`, `pip install -e .`) i start aplikacji na czystej bazie; testy zielone; każda funkcja z §6 działa w UI; brak AI i eksportu; migracja v1→v2 przetestowana; README z instrukcją; tag `v2.0.0`.

---

## 16. Zadania dla człowieka (poza zasięgiem agenta)

1. Zarejestrować/utrzymać aplikację Allegro Sandbox ze scope `allegro:api:sale:offers:read` (oraz dostęp do `offer-events`, jeśli endpoint go wymaga).
2. Wypełnić `.env` kluczami sandboxa i zalogować się w aplikacji (device flow).
3. Wygenerować ruch na ofertach (drugie konto kupującego) albo użyć trybu demo.
4. Zrobić zrzuty ekranu wszystkich stron 2.0 (lista w `docs/screenshots/README.md`).
5. Zdecydować, czy tryb ciągły ma być włączany na stałe w codziennym użyciu (i czy zostawić aplikację uruchomioną).
6. Zaktualizować „Refleksję” w dzienniku AI.

---

## 17. Ryzyka i pułapki

1. **Rerun model Streamlita** — każda interakcja przelicza skrypt; obowiązkowy cache z kluczem `(db, data_version, offer, range, metric)`, gdzie `data_version = max(captured_at) + count`.
2. **Definicja „ogółem”** — najłatwiejszy błąd projektu: sumowanie poziomów w czasie zamiast przyrostów per oferta.
3. **Współbieżność SQLite** — pętla i UI; WAL + połączenie per wątek + `busy_timeout`; test równoległy w S4.
4. **Wątek w Streamlicie** — musi być daemonem, jeden na proces (`cache_resource`), nigdy nie dotyka `st.session_state`.
5. **Uśpienie laptopa** — tryb ciągły przestaje zbierać; UI musi to pokazywać (wiek ostatniego snapshotu), README opisać.
6. **`offer-events` niezweryfikowane** — może wymagać innego scope lub mieć inny kształt; plan B: adnotacje ręczne (FR-15 nie blokuje S5).
7. **Sandbox bez ruchu** — zera w licznikach; bez trybu demo aplikacja wygląda na zepsutą.
8. **Semantyka `visitsCount`** — okno kroczące (hipoteza); UI nie może sugerować, że przyrost = wyświetlenia w okresie, a spadek = błąd.
9. **Zakres własny i strefa** — walidacja i konwersja UTC ↔ `Europe/Warsaw` w jednym miejscu.
10. **Testy UI** — AppTest jest ograniczony; nie uzależniać bramki od przeglądarki, logikę trzymać w `services`/`queries`.

---

## 18. Decyzje przyjęte bez pytania (do ewentualnego veta)

| Temat | Przyjęto | Jeśli chcesz inaczej |
|---|---|---|
| D7 migracja bazy | addytywna v1→v2, `ai_comments` usunięta, kopia zapasowa przed migracją | „czysta karta”: nowa baza `data/v2.db`, brak migracji (trzeba zbierać od nowa) — zmiana §7 i S0 |
| Strona „Przegląd” | zostaje na ekranie, bez pobierania pliku | jeśli chcesz jednak pobieranie HTML — wraca FR „eksport” i zależność `jinja2` |
| Usunięcie AI | kod + zależność + tabela usunięte z projektu, nie tylko ukryte | jeśli AI ma wrócić w 2.x — zostawiamy `ai_comments` i `anthropic` w `requirements-dev` jako opcjonalne |
| Usunięcie CLI | `cli.py` usunięty; wejściem jest `python -m view_tracker_ai_1.ui` | jeśli chcesz zostawić tryb headless — wraca `collect` jako jedna komenda techniczna (bez pozostałych) |
| `charts.py`/`report.py` | usunięte | jeśli chcesz zachować eksport PNG/HTML — zostają, a UI dostaje przyciski pobierania |
