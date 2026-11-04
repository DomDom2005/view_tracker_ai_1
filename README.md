# view_tracker_ai_1

Interaktywna aplikacja webowa do śledzenia historii liczników ofert Allegro: zbiera snapshoty
wyświetleń i obserwujących, liczy trendy, rysuje wykresy i pokazuje zdarzenia ofert.
Projekt zaliczeniowy na studiach AI. Działa w trybie **sandbox-first**, a bez konta Allegro
da się ją uruchomić na **danych syntetycznych** (oznaczonych jako demo).

> **Wersja 2.0.0** zmieniła paradygmat: zamiast komend CLI i plików wynikowych jest aplikacja
Streamlit. Wersja 1.0 (CLI, wykresy PNG, raport HTML, komentarz AI) jest zachowana w historii
gita i na tagu `v1.0`. Funkcje AI oraz eksportu plików zostały **wycofane** (patrz §10).
> **2.0.1** domyka wymagania §6 SPEC: lista ofert z wyszukiwaniem/filtrem/sortowaniem,
> automatyczne odpytywanie logowania, dwie osie dla metryki „oba”, blokada zbierania do bazy
> demo i plakietki „DANE SYNTETYCZNE” w tabelach.
> **2.1.0** to scalenie `release/2.0` z gałęzią `main` (merge commit, tag `v2.1.0`); obie
> gałęzie wskazują ten sam commit.

## 1. Cel

Panel sprzedawcy na Allegro pokazuje tylko **bieżące** liczniki oferty — nie widać, czy
zainteresowanie rośnie, czy spada po zmianie ceny, tytułu albo zdjęć. API Allegro nie udostępnia
historii tych liczb, więc aplikacja buduje ją sama: cyklicznie zapisuje snapshoty do SQLite,
a potem liczy z nich przyrosty, trend, pokrycie i anomalie (spadki licznika).

Efekt dla użytkownika: wybierasz ofertę i zakres, a aplikacja pokazuje wykres, liczby, ranking
ofert, porównanie okresów, zdarzenia oferty i adnotacje — bez terminala i bez plików pośrednich.

## 2. Interfejs

Aplikacja ma pięć widoków (szczegóły w [`docs/ui-flows.md`](docs/ui-flows.md)):

- **Przegląd** — osiem kafli „ogółem” (poziom, przyrost z porównaniem okresów, mediana,
  obserwujący, spadki), banner alertów i ranking ofert z linkami.
- **Oferta** — lista ofert z wyszukiwaniem/filtrem/sortowaniem, wybór 2–5 ofert do porównania,
  wykres Plotly (poziom + dzienne przyrosty, anomalie, znaczniki zdarzeń), karta podsumowania,
  „co nowego”, adnotacje i alerty.
- **Porównanie** — indeks 100 dla 2–5 ofert, tabela i porównanie okresów.
- **Dane** — logowanie device flow, „Odśwież teraz”, przebiegi i tryb ciągły.
- **Ustawienia** — ścieżki, wersje, generowanie danych demo.

Zrzuty ekranu są celowo pominięte — dokumentacja opisuje interfejs tekstowo.

**Motyw:** „warm glass” — ciepły gradient z rozmytymi kulami i pierścieniami rysowanymi w CSS,
szklane panele (`backdrop-filter`), cienkie białe linie i atramentowa typografia. Paleta
widżetów (tabele, inputy) jest w `.streamlit/config.toml`; dekoracje i styl wstrzykuje
`ui/theme.py`. Motyw nie pobiera żadnych obrazów ani fontów z sieci. Zmiana samego CSS działa
po odświeżeniu strony; zmiana palety w `config.toml` wymaga restartu serwera.

## 3. Wymagania i instalacja

- Python **3.11+** (testowane na 3.14.6), Windows / Linux / macOS,
- konto Allegro Sandbox (opcjonalnie — tryb demo działa bez konta).

```bash
pip install -r requirements.txt
pip install -e .            # pakiet z src/ → `python -m view_tracker_ai_1.ui`
```

Instalacja deweloperska (testy, lint):

```bash
pip install -r requirements-dev.txt
pip install -e .
```

## 4. Konfiguracja

Skopiuj `.env.example` do `.env` (poza repo — plik jest w `.gitignore`) i uzupełnij:

| Zmienna | Znaczenie | Wymagana |
|---|---|---|
| `ALLEGRO_CLIENT_ID` / `ALLEGRO_CLIENT_SECRET` | klucze aplikacji sandbox | tak (API) |
| `ALLEGRO_ENV` | `sandbox` albo `prod` | nie (dom. `sandbox`) |
| `ALLEGRO_USER_AGENT` | obowiązkowy nagłówek UA | nie (jest domyślny: `view_tracker_ai_1/2.0.1 (+https://github.com/DomDom2005/view_tracker_ai_1)`) |
| `TOKEN_STORE_PATH` | plik z tokenami | nie (dom. `~/.config/view_tracker_ai_1/tokens.json`) |
| `DB_PATH` | baza SQLite | nie (dom. `data/sandbox.db`) |
| `ALLOW_PROD_WRITES` | zapisy do API na produkcji | nie (dom. zablokowane) |
| `LOG_LEVEL` | `DEBUG`/`INFO`/`WARNING`/`ERROR` | nie (dom. `INFO`) |

Bez `.env` aplikacja **uruchomi się** (tryb demo i podgląd bazy), ale logowanie do API
i zbieranie danych nie będą działać.

## 5. Uruchomienie

Najprościej — launcher w katalogu repo (nie wymaga `pip install -e .`):

```bash
python run.py                          # http://127.0.0.1:8501
python run.py --server.port 8600
```

Na Windows można też **dwuklikiem** uruchomić `start.bat` (woła `run.py` i zostawia okno przy błędzie).

Równoważne wywołania bez launchera:

```bash
python -m view_tracker_ai_1.ui            # http://127.0.0.1:8501
python -m view_tracker_ai_1.ui --server.port 8600
UI_PORT=8600 python -m view_tracker_ai_1.ui   # port z env (Linux/macOS)
$env:UI_PORT=8600; python -m view_tracker_ai_1.ui   # PowerShell
```

Panel boczny wybiera **bazę**: `Sandbox (API)`, `Produkcja (tylko odczyt)` albo
`Dane demo (syntetyczne)`. Wybór trafia do adresu widoku (parametr `db`), więc linki da się
przesłać. Adresy widoków: `/przeglad`, `/oferta`, `/porownanie`, `/dane`, `/ustawienia`.

## 6. Pierwsze kroki

1. **Ustawienia → „Wygeneruj dane demo (90 dni)”**, potem wybierz w panelu bocznym
   „Dane demo (syntetyczne)” — masz pełny obraz bez konta Allegro.
2. Albo: uzupełnij `.env`, wejdź w **Dane → „Rozpocznij logowanie”** (device flow: kod i link do
   zatwierdzenia), potem **„Odśwież teraz”**, a następnie **Przegląd** i **Oferta**.
3. **Oferta**: szukaj po nazwie/ID, filtruj status, sortuj po ostatnim snapshocie albo przyroście;
   wybierz jedną ofertę do szczegółów. Pod wykresem jest karta podsumowania, niżej „Co nowego
   od ostatniej wizyty”, zdarzenia/adnotacje i alerty progowe. Metryka „oba” pokazuje wyświetlenia
   i obserwujących na **dwóch osiach Y**. Wielokrotny wybór ofert jest na stronie **Porównanie** —
   panel Oferta obsługuje jedną ofertę.
4. **Porównanie**: wybierz 2–5 ofert (indeks 100) i porównaj okresy.
5. **Dane**: stan kolektora, przebiegi, tryb ciągły (na bazie demo zablokowany).

## 7. Pojęcia

- **Poziom vs przyrost** — `visitsCount` to licznik (poziom), a nie liczba wyświetleń w danym
  dniu. Aplikacja pokazuje więc poziom i **dzienne przyrosty**; suma przyrostów pomija spadki.
- **Pokrycie** — udział godzin z danymi w wybranym oknie. Poniżej 30% (albo mniej niż 6 punktów)
  trend jest oznaczany jako niepewny.
- **Anomalia** — spadek licznika (`counter_decrease`). Przy oknie kroczącym to normalne zjawisko,
  nie błąd danych.
- **Dane syntetyczne** — generowane lokalnie (`source='synthetic'`), zawsze z plakietką
  „DANE SYNTETYCZNE”; nigdy nie mieszają się z danymi z API w jednej bazie.
- **Indeks 100** — porównanie ofert o różnych skalach: każda linia zaczyna się od 100
  w pierwszym punkcie wspólnego okna.

## 8. Tryb ciągły i ograniczenia

- **„Odśwież teraz”** robi jeden przebieg kolektora i zapisuje wpis w `collect_runs`.
- **Tryb ciągły** (domyślnie wyłączony) uruchamia wątek w procesie aplikacji i zbiera dane
  co interwał ≥ 300 s. Działa **tylko**, gdy aplikacja jest uruchomiona; uśpienie komputera
  oznacza lukę w danych. Po restarcie aplikacji tryb jest zawsze wyłączony (świadoma decyzja).
- Na bazie **PROD** zbieranie i edycja (adnotacje) są zablokowane — tylko odczyt.
- Na bazie **demo** zbieranie z API jest zablokowane, żeby dane syntetyczne nie mieszały się
  z danymi z API (FR-18). Przełącz bazę na Sandbox, żeby zbierać.
- Bez zbierania w tle historia jest tak gęsta, jak często klikasz „Odśwież”.

## 9. Błędy i limity API

| Sytuacja | Zachowanie |
|---|---|
| `401` | token odświeżany raz, potem komunikat „zaloguj się ponownie” |
| `403` | brak scope — komunikat przy zbieraniu/zdarzeniach |
| `422` | czytelna lista błędów, bez ponowień |
| `429` | respektowany `Retry-After`, inaczej backoff od ~60 s (limit blokuje Client ID na minutę) |
| `5xx`/timeout | 3 próby, potem błąd |

Pełne ustalenia i źródła: [`docs/api-notes.md`](docs/api-notes.md).

## 10. Testy i jakość

```bash
ruff check .
pytest -q
pytest -q --cov=src/view_tracker_ai_1 --cov-report=term-missing
```

Testy działają **offline** — sieć jest zablokowana w `tests/conftest.py` (poza loopbackiem
potrzebnym runtime'owi Streamlita), a HTTP mockuje `responses`. Sprawdzane są m.in.: analityka
(przedziały, anomalie, trend, pokrycie), migracja schematu v1→v2, parser zdarzeń i deduplikacja,
alerty, pętla kolektora (start/stop, błędy, brak wyścigów) oraz strony przez `AppTest`.

Wycofane w 2.0: moduł AI (`ai_comment.py`), CLI (`cli.py`), wykresy PNG i raport HTML
(`charts.py`, `report.py`), zależności `anthropic`/`matplotlib`/`jinja2` oraz tabela `ai_comments`.

## 11. Bezpieczeństwo

- Sekrety wyłącznie w `.env` poza repo; w repo jest tylko `.env.example` bez wartości.
- Tokeny: `~/.config/view_tracker_ai_1/tokens.json`, katalog `700`, plik `600`, zapis atomowy.
- Aplikacja nie pokazuje tokenów, nie zapisuje ich w URL ani w stanie sesji; logi przechodzą
  przez filtr maskujący `Authorization`, JWT, `client_secret` i klucze API.
- Nie udostępniaj widoków z tokenami, identyfikatorami konta ani danymi kupujących
  (aplikacja i tak nie pokazuje tokenów).

## 12. Dziennik AI

Przebieg prac, korekty założeń i odstępstwa od SPEC: [`docs/ai-journal.md`](docs/ai-journal.md).
Specyfikacja 2.0: [`Project info/SPEC-2.0.md`](Project%20info/SPEC-2.0.md);
fakty o API: [`docs/api-notes.md`](docs/api-notes.md).

## 13. Ograniczenia

- **Semantyka `visitsCount`** — oficjalna dokumentacja nie potwierdza okna kroczącego ani
  unikalności; to hipoteza z forum. Dlatego zapisujemy poziomy, spadki traktujemy jako anomalie,
  a wnioski o „wyświetleniach w okresie” są przybliżeniem (`scripts/probe_counter.py`).
- **Sandbox bez ruchu** — liczniki mogą stać w miejscu; do prezentacji użyj danych demo.
- **Zdarzenia ofert** — kształt odpowiedzi `GET /sale/offer-events` i wymagany scope są
  niezweryfikowane (`docs/api-notes.md` §9); przy braku dostępu działają adnotacje ręczne.
- **Jedna instancja, jeden użytkownik** — brak logowania do aplikacji i wielodostępu.
