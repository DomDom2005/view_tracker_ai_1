# Dziennik AI

Zapis pracy agenta: co zaproponował, jak to sprawdzono i czy się potwierdziło.
Format wpisu jak w `Project info/SPEC.md` §14. Wpisy są uczciwe — błędy i korekty też.

## Wpisy

|Data|Zadanie|Co zaproponowało/zrobiło AI|Jak zweryfikowano|Wynik (trafne / poprawione / błędne)|
|---|---|---|---|---|
| 2026-10-27 | Uporządkowanie dokumentów projektu (nazwy, ścieżki, bloki kodu) | Ujednolicenie nazwy na `view_tracker_ai_1` w `SPEC.md`, `PLAN.md`, `AGENTS.md`, `Allegro API - Prototyp.md`; poprawa bloków kodu w `AGENTS.md` (niewidzialny znak U+200B w fence); nota o pierwszeństwie dokumentacji Allegro w nocie koncepcyjnej | Porównanie z nazwą repo (`git ls-tree origin/main`), `grep` po `Project info/` | poprawione (dokumenty mówiły „Allegro Trends” / `allegro_trends`) |
| 2026-10-27 | Weryfikacja 6 punktów `SPEC.md` §4.3 w dokumentacji Allegro | Research w developer.allegro.pl (3 niezależne wątki: OAuth, lista ofert, zmiana ceny), wynik w `docs/api-notes.md` | Każdy punkt z URL-em źródła i datą; rzeczy niepotwierdzone oznaczone `NIEZWERYFIKOWANE` | trafne po korektach — 3 ustalenia zmieniły SPEC (patrz „Odstępstwa od SPEC”) |
| 2026-10-27 | Etap 0 — szkielet repo, środowisko, bramka | Struktura `src/view_tracker_ai_1/` + `scripts/` + `tests/` + `docs/`; `pyproject.toml` (src layout, pytest, ruff), przypięte `requirements*.txt`, `.env.example` bez wartości, `tests/conftest.py` z blokadą gniazd, smoke test, root `AGENTS.md` + `CLAUDE.md`, `docs/data-flow.md`, `docs/manual-sandbox-checklist.md`, `docs/screenshots/README.md` | `ruff check .` → All checks passed; `pytest -q` → 15 passed; `python -m view_tracker_ai_1.cli --version` → `view_tracker_ai_1 0.0.1` (z `PYTHONPATH=src`) | trafne, z zastrzeżeniami środowiskowymi (patrz „Notatki z etapu 0”) |
| 2026-10-28 | Etap 1 — config, errors, models, storage | `Config` jako frozen dataclass z `from_env`, walidacją (`ALLEGRO_ENV`, `LLM_PROVIDER`, `LOG_LEVEL`, `ALLOW_PROD_WRITES`), hostami per środowisko i metodami `require_allegro_credentials()`/`require_write_permission()`; `setup_logging()` + `redact()` maskujące Bearer/JWT/`sk-ant-…`/`client_secret`; `AppError` i 5 typów błędów; modele `Offer`/`Snapshot`/`Series`/`SeriesSummary` (+`SeriesPoint`, `DailyGain`, `Anomaly`); `storage.py` ze schematem z SPEC §7, idempotentnym `init_db`, `upsert_offer`, `insert_snapshots`, `get_series`, `list_offers`, `get_last_snapshot`, cache AI, `log_action` | 75 testów; pokrycie: `config.py` 99%, `storage.py` 96%, `errors.py` i `models.py` 100%; `ruff check .` czysty | trafne po dwóch korektach (patrz „Notatki z etapu 1”) |
| 2026-10-28 | Etap 2 — OAuth device flow i magazyn tokenów | `DeviceFlowAuth` (start → polling → tokeny, `slow_down`, `access_denied`, wygaśnięcie kodu), `TokenStore` (katalog 700, plik 600, zapis przez `mkstemp` + `os.replace`), rotacja refresh tokena (nowy zapisywany od razu, stary zachowany, gdy serwer go nie odeśle), `get_valid_token()` z buforem 5 min, `status()` bez ujawniania tokenów; `Tokens`/`DeviceAuthorization` z `repr=False` na sekretach | 101 testów (1 skip na Windows); pokrycie `auth.py` 92%; `ruff check .` czysty; wszystkie żądania przez `responses` | trafne po korektach (patrz „Notatki z etapu 2”) |
| 2026-10-28 | Etap 3 — klient HTTP, retry, błędy, paginacja | `AllegroClient` (`get`, `iter_offers`, `RemoteOffer`): nagłówki `Accept` + `User-Agent`, Bearer z `auth.get_valid_token()`, timeouty 10/30 s, polityka `401` (odśwież + jeden retry), `422` → `ValidationError`, `429` (`Retry-After` jako sekundy albo HTTP-date, fallback 60 s z jitterem, 5 prób), `5xx`/timeout (3 próby), inne `4xx` → `ApiError`; paginacja `offset/limit` z jawnym `limit` (100, zakres 1..1000), stop na `len < limit` lub `offset >= totalCount`, pauza 0,2 s; fixtures `offers_page1..3.json` | 129 testów; pokrycie `client.py` 98%; brak prawdziwych `sleep` (uśpienia to lista); test na `caplog`, że token nie trafia do logów; `ruff check .` czysty | trafne; jedno świadome odstępstwo (start backoffu 60 s, nie 1 s) — patrz „Notatki z etapu 3” |
| 2026-10-28 | Etap 4 — kolektor i CLI (koniec fazy 1) | `collector.run_once` (wspólny `captured_at`, jedna transakcja, zwraca liczbę nowych snapshotów) i `run_forever` (min. 300 s, `AuthError` zatrzymuje pętlę, inne błędy tylko logowane); `storage.save_collection` dla atomowego zapisu ofert + snapshotów; CLI z komendami `auth login`/`auth status`/`offers list`/`collect` oraz opcjami `--env`/`--db`/`-v` także po komendzie; `CommandParser` mapuje błędy użycia na kod 1; `scripts/probe_counter.py` (faza 0) | 164 testy (1 skip); pokrycie `cli.py` 98%, `collector.py` 100%, `storage.py` 94%; bramka PLAN uruchomiona dosłownie, w tym `python -m view_tracker_ai_1.cli --help`; `pip install -e .` i `view_tracker_ai_1 --version` wreszcie zweryfikowane | trafne po jednej realnej korekcie (licznik zapisanych snapshotów) — patrz „Notatki z etapu 4” |
| 2026-10-28 | Reinstalacja środowiska na świeżym klonie (urządzenie **HP_Pavilion**) | `git clone` do pustego workspace; `http.sslBackend=openssl` w lokalnym `.git/config` (schannel dawał `SEC_E_NO_CREDENTIALS`); venv przez `--without-pip` + globalny `pip --python` (padający `ensurepip`); `TMP`/`TEMP` przekierowane do `.tmp/`; zdiagnozowana przyczyna blokady `tempfile.mkdtemp()` — katalog z `mode=0o700` dostaje ACL odcinający zapis i listowanie **także twórcy**; obejście: `sitecustomize.py` maskujący tryb do `0o777` przez `PYTHONPATH`; `pip install -e .` z `--no-build-isolation` | Eksperyment na trzech trybach `os.mkdir`: domyślny i `0o777` → zapis i `listdir` OK, `0o700` → `PermissionError` w obu; `ruff check .` → All checks passed; `pytest -q` → 164 passed, 1 skipped | trafne, ale to **powtórka** problemu z etapu 0; nowe jest to, że obejście działa w `workspace-write`, bez pełnego dostępu — patrz „Notatki ze środowiska — HP_Pavilion” |
| 2026-10-28 | Python 3.14.6 na polecenie człowieka (urządzenie **HP_Pavilion**) | Instalator z python.org (`python-3.14.6-amd64.exe`, SHA-256 zgodny ze stroną wydania) nie uruchomił się — `0x80070005` i brak logu; `uv python install 3.14.6` (build standalone, bez MSI i rejestru) zadziałał po wskazaniu cache i katalogu instalacji w `.tmp`, drzewo skopiowane do `%LOCALAPPDATA%\Programs\Python\Python314`; `.venv` odtworzony na 3.14.6, `pip install -r requirements-dev.txt` i `pip install -e .` bez obejść | Instalator dwa razy `-2147024891` (0x80070005), log nie powstał; `uv` padał na `Failed to create directory ...\uv\cache`; po przełączeniu sesji na pełny dostęp `ruff check .` → All checks passed, `pytest -q` → 164 passed, 1 skipped, bez `PYTHONPATH` i bez `--basetemp`; wcześniej nieusuwalne katalogi z `.tmp` dały się usunąć | trafne po dwóch obejściach; odmowy dotyczyły **uprawnień procesu potomnego**, nie ACL plików — pełny dostęp usuwa problem całkowicie (patrz aktualizacja w „Notatki ze środowiska — HP_Pavilion”) |
| 2026-10-28 | Etap 5 — analityka | `analytics.py` jako funkcje czyste: `range_duration`/`select_points` (`24h`/`7d`/`30d`/`90d`/`all`), `deltas`/`positive_gains`/`gained_total`, `find_anomalies` (`counter_decrease` z ujemną deltą, poza przyrostami), `daily_gains` po dobie `Europe/Warsaw` z DST, `coverage`, `slope_per_day` (OLS) i `label_trend` z progiem 0,02 jako stałą, `summarize` → `SeriesSummary`, `build_series` (snapshoty → seria); przy < 3 punktach nachylenie 0.0 i etykieta `brak danych` | `ruff check .` czysty; `pytest -q` → 205 passed, 1 skipped; pokrycie `analytics.py` **100%**, całości 97%; test na dobę 25-godzinną 2026-10-25 (25 h w UTC kontra 24 h czasu ściennego) oraz na serię samych zer | trafne po korektach (patrz „Notatki z etapu 5”) |
| 2026-10-28 | Etap 6 — dane demo i wykresy | `scripts/seed_demo_data.py` (deterministyczny `--seed` i `--end`, 5 ofert × 90 dni: wzrost, spadek, plateau, anomalia, luki; szum na **przyrostach**, odmowa zapisu do bazy z `source='api'`, zastępowanie poprzednich danych demo); `charts.py` (dwa panele, markery anomalii pod linią, znak wodny tylko w górnym panelu, komunikat zamiast pustej osi przy braku przyrostów, `ChartResult` z metadanymi); komenda `chart` w CLI z wstrzykiwalnym `_now()` i `ChartError` → kod 1; `analytics.to_local()` | `ruff check .` czysty; `pytest -q` → 229 passed, 1 skipped; pokrycie `charts.py` 97%, `cli.py` 98%, całości 97%; bramka z PLAN-u uruchomiona dosłownie (seed → 10 047 snapshotów, `chart` → PNG); **kontrola wzrokowa** 9 wykresów (5 przedziałów + 4 wzorce) i po niej 8 poprawek | trafne po korektach wizualnych (patrz „Notatki z etapu 6”) |
| 2026-10-28 | Etap 7 — moduł AI | `ai_comment.py`: protokół `CommentGenerator`, `FakeCommentGenerator` (deterministyczny, jawnie „komentarz bez AI”), `AnthropicCommentGenerator` (klient leniwie, `client_factory` do testów), `gate_message` (`n_points < 6` lub `coverage < 0.3`), `build_prompt` z blokiem `<dane>` i neutralizacją `<`/`>` w nazwie oferty, `input_hash` (sha256 z agregatów), `clean_comment` (markdown + 700 znaków), `generate_comment` (bramka → cache → model → fallback); `Config.require_llm()`; CLI `comment --offer --range [--metric] [--no-ai]` | `ruff check .` czysty; `pytest -q` → 262 passed, 1 skipped; pokrycie `ai_comment.py` **100%**, `cli.py` i `config.py` 98%, całości 97%; testy: brak wywołania przy bramce, cache hit bez drugiego wołania, próba wstrzyknięcia `</dane>`, brak klucza API w komunikatach błędów, leniwe SDK | trafne po korektach (patrz „Notatki z etapu 7”); **nie testowane na żywym modelu** |
| 2026-10-28 | Etap 10 — dokumentacja; decyzja D1 (etap 9 odłożony) | `README.md` z 10 sekcjami ze SPEC §14 (cel; endpointy + scope z `api-notes.md`; diagram Mermaid; instalacja; tabela zmiennych env; przykłady z **rzeczywistym** wyjściem; błędy/limity; testy; bezpieczeństwo; dziennik AI; ograniczenia); `PLAN.md`: etap 9 → `[-]` z uzasadnieniem, etap 10 → `[x]`; poprawione `docs/screenshots/README.md` i `docs/manual-sandbox-checklist.md`, bo obiecywały komendę `act price` | Bramka uruchomiona dosłownie: `^## ` w README = **10**; wszystkie 6 linków wewnętrznych wskazują istniejące pliki; każda komenda z README wykonana (seed → 10 047 snapshotów, `chart` → 2160 punktów / 100% pokrycia / 1 anomalia, `comment`, `report` → 5 ofert / 10 sekcji, `offers list`, `auth status`); w README brak wartości sekretów; `ruff check .` i `pytest -q` bez zmian (280 passed, 1 skipped) | trafne po dwóch korektach dokumentów |
| 2026-10-28 | Etap 11 — domknięcie i QA | Instalacja `gitleaks` 8.30.1 (binarny release z GitHub → `%LOCALAPPDATA%\Programs\gitleaks`), skan historii (`gitleaks git`, 29 commitów) i drzewa (`gitleaks dir`); `.gitleaks.toml` z wyjątkami na zmyślony JWT w teście redakcji i katalogi lokalne; test czystego środowiska (nowy venv na Pythonie 3.14.6 → instalacja z `requirements*.txt` → pełne `pytest`); przejście Definition of Done ze SPEC §15 punkt po punkcie | Historia: 2 fałszywe alarmy przed konfiguracją → **0 po**; drzewo: 7 → **0**; czysty venv: `pip install` OK, 280 passed, 1 skipped, `ruff` czysty; `git ls-files` nie zawiera `.env`, `*.db`, `tokens*`; `.env.example` bez wartości; README 10/10 sekcji; dziennik: 15 wpisów, 10 sekcji korekt | trafne; **1 punkt DoD** (TODO(verify)) spełniony przez opisanie, nie przez rozwiązanie — uzasadnienie w „Notatki z etapu 11” |
| 2026-10-28 | Etap 8 — raport HTML (koniec fazy 2) | `report.py`: `build_report` (serie → kafle: wykres base64 + tabela FR-4 + komentarz), szablon Jinja2 z autoescape, badge SANDBOX/PROD/DEMO, ostrzeżenie o danych syntetycznych i o semantyce licznika, `write_report` (UTF-8), `series_for_offer`; `charts.render_png` (PNG do pamięci, wspólna figura z `render_chart`); CLI `report --range --range ... [--offer] [--metric] [--no-ai] --out` z lokalnym importem matplotliba | `ruff check .` czysty; `pytest -q` → 280 passed, 1 skipped; pokrycie `report.py` **100%**, `charts.py` **100%**, `cli.py` 98%, całości 97%; bramka z PLAN-u uruchomiona dosłownie: raport 5 ofert / 5 sekcji, 0 odwołań `http(s)://`, 10 osadzonych PNG (sprawdzone: base64 dekoduje się do prawidłowych plików PNG) | trafne po korektach (patrz „Notatki z etapu 8”) |
| 2026-11-02 | Wyrównanie wersji do 1.0.0 + naprawa testu zależnego od zegara | Podniesienie wersji z `0.0.1` na `1.0.0` w `pyproject.toml` i `__version__` (domyślny `User-Agent` bierze wersję z kodu, więc zmienił się sam), aktualizacja literałów UA w `README.md`, `Project info/SPEC.md` §4.1/§13, `docs/api-notes.md` i `.env.example`; ponowna instalacja edytowalna w venv i w systemowym Pythonie, żeby metadane `pip show` też mówiły 1.0.0. Przy okazji: `test_comment_requires_llm_model_when_provider_is_anthropic` padał 5 dni po oddaniu, bo nie podstawiał `cli._now` jak dwa sąsiednie testy `comment` — dodane `monkeypatch.setattr(cli, "_now", lambda: NOW)` | `python -m view_tracker_ai_1.cli --version` → `view_tracker_ai_1 1.0.0` (venv i system), `pip show` → `Version: 1.0.0`, `DEFAULT_USER_AGENT` → `view_tracker_ai_1/1.0.0 (+…)`; `ruff check .` czysty; `pytest -q` → 280 passed, 1 skipped | trafne; wpisy historyczne w dzienniku zachowują `0.0.1`, bo to zapis stanu z tamtych dni |
| 2026-11-02 | S0 2.0 — porządki, schemat v2, warstwa usług | Usunięte z projektu: AI (`ai_comment.py`, test), CLI (`cli.py`, test), eksport (`charts.py`, `report.py`, testy); zależności `anthropic`, `matplotlib`, `jinja2` wycofane, dodane `streamlit==1.66.1` i `plotly==7.1.0`. Nowe moduły: `text.py` (odmiana i formaty PL), `queries.py` (agregaty SQL: poziomy jednej chwili, przyrosty per oferta, mediana, luki, świeżość), `services.py` (przypadki użycia UI + `refresh_once` z wpisem `collect_runs`). Schemat v2: nowe tabele `collect_runs`, `offer_events`, `annotations`, `alert_rules`, `app_state`; `ai_comments` usunięta; migracja v1→v2 z kopią pliku; `connect()` ustawia WAL i `busy_timeout` | `ruff check .` czysty; `pytest -q` → 249 passed, 1 skipped; pokrycie: `queries.py` 100%, `services.py` 97%, `text.py` 100%, `storage.py` 93%, `config.py` 99%, całość 97%; migracja sprawdzona na **kopii prawdziwej bazy** `data/sandbox.db`: wersja 2, 3 oferty i 3 snapshoty zachowane, kopia `.bak-20261102-145248` utworzona; w venv brak `anthropic`/`matplotlib` | trafne; dwie korekty oczekiwań w testach (zakres 24h zawiera punkt z −1 dnia; porównanie okresów obejmuje obie oferty) — kod był poprawny, poprawione asercje |
| 2026-11-02 | S1 2.0 — szkielet aplikacji Streamlit | `ui/state.py` (URL ↔ stan: baza/oferty/zakres/metryka, mapowanie sandbox/prod/demo na ścieżki i env, `config_for`), `ui/components.py` (selektor bazy, belka statusu: token + świeżość + wersje, `connection()` z komunikatem błędu zamiast wywrotki, placeholdery), `ui/app.py` (`st.navigation` z 5 stronami), `ui/__main__.py` (`python -m view_tracker_ai_1.ui` → `streamlit run`), strony: Przegląd (kafle + tabela ofert), Oferta (wybór z URL), Porównanie (placeholder S3), Dane (świeżość, przebiegi), Ustawienia (ścieżki, env, wersje, prod read-only) | `ruff check .` czysty; `pytest -q` → 274 passed, 1 skipped; pokrycie: `ui/app.py` 100%, `ui/state.py` 85%, całość 95%; **serwer uruchomiony z katalogu bez `.env`**: `/_stcore/health` → `ok` po 1 s, strona główna HTTP 200 | trafne po trzech korektach: (1) blokada sieci w `conftest.py` blokowała `socket.socketpair` asyncio i wywalała AppTest — dopuszczono loopback (`127.0.0.1`, `::1`, `localhost`); (2) `use_container_width` jest przestarzałe w Streamlit 1.66 → `width="stretch"`; (3) asercje testów dopasowane do faktycznych etykiet (selectbox pokazuje etykiety, nie wartości) |
| 2026-11-02 | S2 2.0 — oferta, zakresy, metryka, wykres | `analytics`: `select_between`/`coverage_between`/`summarize_between` (addytywnie, istniejące API bez zmian; `summarize` deleguje do wspólnego `_summary`); `services.offer_view` zwraca punkty, agregaty dobowe, podsumowanie i `custom_range`; `ui/charts.py` (Plotly: panel poziomu + słupki dziennych przyrostów, markery anomalii, pokrycie/liczba punktów w podtytule, znak wodny „DANE SYNTETYCZNE”); strona Oferta: wybór oferty, zakresy 24h/7d/30d/90d/all + własny (date_input), metryka wyświetlenia/obserwujący/oba (dwa taby), karta podsumowania (8 kafli), ostrzeżenia o małej ilości danych i danych syntetycznych; stan: `metric="both"`, `from`/`to` | `ruff check .` czysty; `pytest -q` → 291 passed, 1 skipped; pokrycie: `analytics.py` 100%, `ui/charts.py` 100%, `services.py` 95%, `ui/state.py` 95%, strona Oferta 82%, całość 95%; AppTest: każdy z 5 presetów renderuje `plotly_chart`, zakres własny również | trafne po korektach: (1) test pokrycia przekazywał `Series` zamiast punktów; (2) pokrycie okna 7 h przy 4 punktach to 4/7, nie 0,5 (asercja); (3) pozostałości starego testu strony Oferta i brakujący newline po `def` — poprawione |
| 2026-11-02 | S3 2.0 — przegląd i porównania | `services`: `Overview.offers_with_drops`, `compare_offers_indexed` (indeks 100 w pierwszym punkcie okna, pomija oferty bez danych lub z bazą 0, limit 5), `comparison_rows` (start/koniec okna, przyrost, spadki, punkty); `ui/charts.build_comparison_figure` (jedna linia na ofertę, komunikat przy braku danych); Przegląd: wspólne przełączniki zakresu/metryki, 8 kafli (poziom, przyrost z deltą vs poprzedni okres, mediana, oferty z danymi, oferty ze spadkiem, spadki, poprzedni okres, oferty w bazie), ranking z linkami `LinkColumn` do strony Oferty; Porównanie: multiselect 2–5 ofert, wykres indeksu 100, tabela porównawcza, zakładka „Okresy” (bieżący vs poprzedni, cały katalog albo jedna oferta) | `ruff check .` czysty; `pytest -q` → 301 passed, 1 skipped; pokrycie: `ui/charts.py` 100%, `services.py` 95%, Przegląd 92%, Porównanie 85%, całość 94%; **wydajność**: przegląd na 20 ofertach × 720 snapshotów (14 400 wierszy) = **0,10 s** (limit 2 s); ręcznie policzone przypadki w testach (np. poziomy 150+30=180, przyrosty 90+10=100, mediana 50, indeks 150/60=250) | trafne po dwóch korektach: (1) usunięty test placeholdera Porównania (strona już istnieje) zastąpiony testem stanu „za mało ofert”; (2) za długa linia i sortowanie importów — ruff |
| 2026-11-02 | S4 2.0 — kolektor w aplikacji | `ui/runtime.py`: `CollectorRuntime` (wątek daemon, własne połączenie SQLite, status pod lockiem, `AuthError` zatrzymuje pętlę, inne błędy tylko logowane), `shared_runtime` przez `st.cache_resource` (jedna pętla na proces), `stop_for()` przy zmianie bazy; strona Dane: przycisk **„Odśwież teraz”** (zapis `collect_runs`, komunikaty o `AuthError`/`ApiError`), interwał z `app_state` (min. 300 s), przełącznik **trybu ciągłego** (domyślnie OFF, nie odtwarzany po restarcie), panel stanu (przebiegi, zapisane, ostatni start, następny, błąd), blokada na PROD | `ruff check .` czysty; `pytest -q` → 309 passed, 1 skipped; pokrycie: `ui/runtime.py` 92%, ekran Dane 83%, `services.py` 95%, całość 93%; testy: brak auto-startu, start→stop ≤ 5 s, `AuthError` zatrzymuje, `ApiError` kontynuuje, walidacja interwału, idempotentny stop oraz **test równoległego zapisu i odczytu** (50 wstawień w wątku + pętla odczytów) bez `database is locked` | trafne po dwóch korektach: (1) fabryka klienta tworzyła nową atrapę co przebieg, więc błąd powtarzał się w kółko — test użył jednej instancji; (2) pętla czekała 300 s między przebiegami, więc test kontynuacji dostał wstrzykiwany `waiter` (bez realnego czekania) |
| 2026-11-02 | S5 2.0 — zdarzenia, adnotacje, „co nowego”, alerty | `docs/api-notes.md` §9: potwierdzony `GET /sale/offer-events` (parametry `from`/`limit`/`type`, 10 typów zdarzeń); kształt odpowiedzi i scope oznaczone `TODO(verify)`. `events.py`: tolerancyjny parser (`offer.id`/`offerId`, `occurredAt`/`occurred_at`/`time`), `EventError` przy nieznanym kształcie, deduplikacja przez `UNIQUE`, `whats_new` (różnica poziomu, nowe snapshoty/anomalie/zdarzenia), `evaluate_alerts` (spadek od szczytu w oknie). `storage`: CRUD `offer_events`, `annotations`, `alert_rules`. `services`: wrappery dla UI. `ui/charts`: `ChartMarker` — pionowe znaczniki zdarzeń i adnotacji. UI Oferta: sekcja „Co nowego”, „Pobierz zdarzenia”, formularz + lista adnotacji z usuwaniem, alerty (trafienia i reguły). Przegląd: banner alertów | `ruff check .` czysty; `pytest -q` → 325 passed, 1 skipped; pokrycie: `events.py` 95%, `ui/charts.py` 98%, całość 92%; testy: parser (camel/flat/uszkodzone/nieznany kształt), deduplikacja, adnotacje CRUD, `whats_new`, alerty pct/abs/globalny | trafne po trzech korektach: (1) parser nie rzucał przy braku pola `events`; (2) za długa linia w UI; (3) test selectboxów nie uwzględniał nowego selecta „Rodzaj alertu” |
| 2026-11-02 | S6 2.0 — demo, dokumentacja, QA | `demo.py` przeniesiony do pakietu (skrypt to cienkie CLI); `services.seed_demo`; **Ustawienia → generator demo w UI**; **Dane → logowanie device flow w UI** (brakowało FR-2 — kod i link, sprawdzanie zatwierdzenia, anulowanie); README przepisane pod 2.0 (13 sekcji, bez CLI/AI/eksportu); nowy `docs/ui-flows.md`; przepisane `docs/data-flow.md`, `docs/manual-sandbox-checklist.md`, `docs/screenshots/README.md`; wersja **2.0.0** (pakiet, pyproject, UA w `.env.example` i api-notes); metadane editable odświeżone w venv i systemie | `ruff check .` czysty; `pytest -q` → 326 passed, 1 skipped; **gitleaks 8.30.1**: historia 49 commitów — brak sekretów, drzewo robocze — tylko lokalny `.env` (ignorowany); **start na czystej bazie**: `/_stcore/health` → 200 `ok`, strona 200; migracja v1→v2 pokryta testem; brak modułów AI/eksportu | trafne po korektach: (1) testy generatora ładowały skrypt przez `importlib` — przełączone na pakiet; (2) generator w UI odwoływał się do nieistniejącego `state.resolve_db_path` w kontekście configu — użyto `with_overrides`; (3) `.venv` trzymał metadane 1.0.0 z zablokowanym `.pth` — usunięte i przeinstalowane; (4) dołożone logowanie w UI, bo DoD wymaga każdej funkcji z §6 |
| 2026-11-02 | 2.0.1 — domknięcie §6 po przeglądzie DoD | FR-7: `offer_catalog` (szukanie, filtr statusu, sortowanie recent/gain/name) + `q/status/sort/detail` w URL; FR-2: `st.fragment` odpytuje logowanie co 5 s (z anulowaniem); FR-9: metryka „oba” = jedna figura z **dwiema osiami Y** zamiast tabów; FR-12: kafel „Obserwujący (razem)”; FR-18: zbieranie i zdarzenia zablokowane na demo, plakietki syntetycznych na stronie oferty, porównaniu i ekranie Dane; FR-1: `UI_PORT`; FR-17: jawne źródło danych; wersja 2.0.1, SPEC §19 | `ruff check .` czysty; `pytest -q` → 339 passed, 1 skipped; pokrycie 92%; nowe testy: katalog/sortowanie/fallback zakresu, obie osie, filtry w URL, wyszukiwanie w UI, blokady demo, `UI_PORT` | trafne po korektach: (1) przenoszenie kodu przez edycję zjadło newline po `def offer_exists` i `level_totals` — złapane przez `IndentationError`; (2) `offer_catalog` wołał `window_start("custom")` i wywalał stronę przy zakresie własnym; (3) test detail używał klucza `detail` zamiast `detail_offer`; (4) logowanie w AppTest wymagało atrapy `complete_login`, bo fragment od razu odpytuje sieć |
| 2026-11-02 | Decyzja: bez zrzutów ekranu | Właściciel projektu nie chce robić zrzutów, więc usunąłem wymóg z dokumentacji zamiast trzymać otwarty punkt w checklistach: README §2 „Zrzuty ekranu” → „Interfejs” (opis tekstowy pięciu widoków), SPEC §14/§16/§19 bez zrzutów, `docs/manual-sandbox-checklist.md` §6 oznaczone jako niewymagane, usunięty katalog `docs/screenshots/`. Historia w tym dzienniku zostaje bez zmian (to zapis, nie plan) | brak zmian w kodzie; `ruff` czysty; `pytest` 339 passed, 1 skipped | — |
| 2026-11-02 | 2.1.0 — scalenie `release/2.0` do `main` | Wersja podniesiona do **2.1.0** (`__init__`, `pyproject`, UA w `.env.example`/`api-notes`, README, SPEC §20). `main` stał na v1.0 (`f7525f8`), `release/2.0` miał 11 commitów przewagi i **żadnych commitów na main od punktu rozgałęzienia** → scalenie `--no-ff` bez konfliktów. Tag `v2.1.0` na merge commicie; `release/2.0` przewinięty do tego samego commita (obie gałęzie identyczne) | `ruff` czysty; `pytest` 339 passed, 1 skipped; merge bez konfliktów; po scaleniu `main == release/2.0` | — |
| 2026-11-02 | Weryfikacja po scaleniu | Sprawdzone na `main`: wersja 2.1.0 w metadanych (editable reinstalowany w venv i systemie), historia tagów `v1.0 → v2.0.0 → v2.0.1 → v2.1.0`, brak różnicy między `main` a `release/2.0`, brak nieśledzonych sekretów | `git rev-list --count main..release/2.0` = 0 i odwrotnie; `gitleaks` na historii bez zastrzeżeń (jak w S6) | — |
| 2026-11-02 | Motyw „warm glass” | Nowy `ui/theme.py`: ciepły gradient + rozmyte kule i pierścienie w czystym CSS (bez obrazów i sieci), szklane panele (`backdrop-filter`) na kontenerze treści, kaflach, rozwijanych sekcjach i tabelach, pill-buttons z gradientem, szklane taby, cienka linia pod nagłówkiem, brand w pasku bocznym; `.streamlit/config.toml` ustawia jasną ciepłą paletę widżetów; Plotly dostał przezroczyste tło, atramentową typografię i delikatną siatkę (paleta: terakota, amber, fiolet dla obserwujących) | `ruff` czysty; `pytest` → 344 passed, 1 skipped; nowe testy: obecność szkła/gradientu, brak zewnętrznych URL-i w CSS, poprawność `config.toml`, smoke `inject()` w AppTest | trafne: (1) pierwsza wersja `page_header` zdublowała funkcję — usunięta stara; (2) E501 na długich liniach CSS — plik dostał `# ruff: noqa: E501`; (3) nieaktualny podpis „logowanie w etapie S2” poprawiony przy okazji |

**Motyw — decyzje:** ciepła, jasna paleta z ciemnym atramentem zamiast białego tekstu z referencji, bo w tabelach i formularzach liczy się kontrast; tło i „3D” kształty są generowane gradientami (zero binariów), a animacja unoszenia respektuje `prefers-reduced-motion`. Paleta widżetów w `config.toml` wymaga restartu serwera, więc po samej zmianie motywu w kodzie wystarczy odświeżyć stronę.

| 2026-11-02 | Motyw — powrót do pierwszej palety | Na życzenie właściciela cofnięta zmiana „wierniejsza paleta” (`e2f34c0`) przez `git revert` (`3ac30af`): wracają jasny kremowy gradient, szkło 0,42, akcent `#d94f14` i atrament `#3b1b0c`. Sam motyw (szkło, kule, pierścienie, typografia) zostaje — cofnięta jest tylko kolorystyka | `ruff` czysty; `pytest` → 344 passed, 1 skipped (testy palety wróciły do poprzednich oczekiwań razem z revertem) | — |
| 2026-11-02 | Pola wyboru: pomarańczowa ramka | Na prośbę o wyraźniejsze „okienka wyboru”: inputy, selecty, multiselect, pola daty/liczby i textarea mają domyślnie `1px solid var(--vt-accent)` z delikatnym halo; na hover halo rośnie, a na fokus (`:focus-within`) ramka zmienia się na `2px` + mocniejszy pierścień. Otwarty select (`aria-expanded="true"`) dostaje tę samą grubszą ramkę, żeby stan „kliknięte” był widoczny także przy otwartym menu | `ruff` czysty; `pytest` → 345 passed, 1 skipped; nowy test regresyjny pilnuje obu grubości i fokusu | — |
| 2026-11-02 | Panel Oferta: bez multiselectu; kolor słupków przyrostu | Usunięty z panelu Oferta multiselect „Oferty do porównania (2–5)” — wybór wielu ofert należy do strony Porównanie (jedno miejsce zamiast dwóch); na Ofercie zostaje filtr listy i jeden `detail`. Kolor słupków dziennego przyrostu zmieniony na `#9ed914` (limonka) w `charts.GAIN_COLOR`; zaktualizowane README, `docs/ui-flows.md` i wiersz FR-7 w SPEC §19 | `ruff` czysty; `pytest` → 346 passed, 1 skipped; nowy test pilnuje koloru `#9ed914` na śladzie „dzienny przyrost” | — |
| 2026-11-04 | Projekt odtworzony z GitHub + launcher | Lokalny katalog został wyczyszczony (zostało tylko `.dsh`); źródło odtworzone z `origin` (`b956bdf`) — bez konfliktów. Przy okazji usunięte z repo przypadkowe katalogi `pip-uninstall-*` (śledzone od czyszczenia metadanych editable) i przywrócony śledzony plik pamięci projektu `.dsh/storages/memory_project_pdeb90.json`. Dodany **`run.py`** (launcher: dodaje `src/` do `sys.path`, woła `ui.__main__.main`, przekazuje argumenty, np. `--server.port`) oraz **`start.bat`** (dwuklik na Windows). README §5 opisuje oba wejścia | `ruff` czysty; `pytest` → 349 passed, 1 skipped (3 nowe testy launchera); smoke: `python run.py --server.port 8603` → `/_stcore/health` 200 i strona 200; brak `.env` nie blokuje startu | **Uwaga:** razem z katalogiem zniknęły lokalne `data/*.db` i `.env` (ignorowane przez git) — dane demo trzeba wygenerować ponownie, a klucze sandboxa wpisać do nowego `.env` |
| 2026-11-04 | 2.2.0 — wydanie interfejsu i launchera | Podbite **2.2.0**: `__init__`, `pyproject`, UA w `.env.example` i `api-notes`, blok wersji w README, nowy §21 w `SPEC-2.0.md` (tabela commitów po `v2.1.0`), tag `v2.2.0`; `main` przewinięty `--ff-only` do `release/2.0`, więc obie gałęzie stoją na tym samym commicie; metadane editable odświeżone (doinstalowany `setuptools` w `.venv`, instalacja z `--no-build-isolation`, bo izolowany build nie dostaje obejścia `tempfile`). Przy okazji poprawiony README §2: opisywał na stronie Oferta „wybór 2–5 ofert do porównania”, usunięty w `b956bdf` | `ruff check .` → All checks passed; `pytest -q` → 349 passed, 1 skipped; smoke: `run.py --server.port 8606` → `/_stcore/health` 200 `ok` i strona 200; `__version__` z kodu i `pip show` → 2.2.0 | trafne |
| 2026-11-04 | SPEC §20: znaki sterujące z wcześniejszej edycji | Edycja z 2026-11-02 zapisała w `SPEC-2.0.md` §20 znaki CR i VT zamiast liter: „elease/2.0” i „2.1.0” bez `v`. Poprawione na `release/2.0`, `v2.1.0` (2× CR, 5× VT); reszta pliku bez zmian | `python` policzył 0 znaków CR/VT po poprawce; `read` na §20 pokazuje pełne zdania | poprawione — wada była widoczna tylko w bajtach, `read` pokazywał urwany tekst |

## Notatki z wydania 2.2.0

- **Sandbox DSH `workspace-write` znów blokuje `tempfile`** (ten sam objaw co w „Notatki ze środowiska — HP_Pavilion”): `pytest` bez obejścia pada na `mkdtemp` z `mode=0o700` (Streamlit AppTest pisze do takiego katalogu i dostaje `PermissionError`), a katalogi `.tmp/pytest-of-domin` i `pytest-of-domin` w rootcie są nieczytelne (`WinError 5`, `os.scandir`). Lokalne obejście, poza repo (`.tmp/` jest w `.gitignore`): `.tmp/fixlib/sitecustomize.py` wymusza `0o777` w `os.mkdir`, `TEMP`/`TMP` wskazują `.tmp`, a `--basetemp` musi być świeżym katalogiem. Z tym `pytest -q` → 349 passed, 1 skipped (dokładnie jak w opisie 2.1.0).
- **Wniosek:** to ograniczenie procesu w sandboxie, nie kod aplikacji — w zwykłym terminalu bramka przechodzi bez obejść (potwierdzone 2026-10-28). Kodu i testów to nie dotyczy, więc nie zmieniałem repozytorium.
- **Pozostałość do sprzątnięcia przez człowieka:** nieczytelne katalogi cache (`pytest-of-domin` w rootcie, `.tmp/pytest-of-domin`, `.pytest_cache`) — `pytest` zgłasza przez nie `PytestCacheWarning`, a `git status` ostrzega przy `scandir`. Usunięcie wymaga pełnego dostępu do plików.

## Notatki z wydania 2.0.1 (domknięcie §6)

**Dlaczego nowa wersja, a nie poprawka tagu:** `v2.0.0` jest już opublikowany; przepisanie tagu
kłamałoby o tym, co użytkownik może pobrać. 2.0.1 to osobny tag z listą zmian w SPEC §19.

**Decyzje:**

- **FR-7 jako lista + osobny parametr `detail`**: zaznaczenie do porównania (`offer=…`) i oferta otwarta w szczegółach to dwie różne rzeczy, więc nie mogą dzielić jednego parametru. Filtr `status=all` nie trafia do URL, żeby domyślne linki były krótkie.
- **Fallback zakresu w katalogu**: lista ofert pokazuje przyrost w bieżącym oknie, ale `custom` nie ma sensu przy sortowaniu — `offer_catalog` podstawia 30 dni zamiast rzucać wyjątkiem.
- **Blokada demo po stronie UI, nie `services`**: `refresh_once` jest wspólne dla runtime i UI; blokada na poziomie przycisków/togilli jest widoczna dla użytkownika i nie ukrywa logiki w serwisie. Runtime i tak jest zatrzymywany przy zmianie bazy (`stop_for`), a pobieranie zdarzeń dostało własną flagę `allow_sync`.
- **Polling logowania we fragmencie**: `st.fragment(run_every=5)` nie blokuje całej strony; przy sukcesie robi pełny rerun, więc belka statusu od razu pokazuje datę ważności.
- **Dwie osie zamiast tabów**: SPEC FR-9 wprost wybierał wariant „dwie osie”; taby były moim odstępstwem z S2. Teraz jest jedna figura, wspólny hover i czytelny podział skali.

**Korekty:** (1) edycja „usuń pustą linię” zjadła nagłówki dwóch funkcji w `queries.py` — `IndentationError` złapany przy zbieraniu testów; (2) `offer_catalog` wywracał stronę na `range=custom`; (3) AppTest nie widział kodu logowania po kliknięciu, dopóki test nie ustawił `complete_login` na atrapę; (4) test szczegółów używał klucza sesji `detail` zamiast `detail_offer`.

**Co pozostaje człowiekowi:** zrzuty ekranu i przejście na realnym sandboxie (kształt `offer-events`, 429, `count` vs `totalCount`) — bez zmian od 2.0.0.

## Notatki z etapu S6 (2.0 — demo, dokumentacja, QA)

**Decyzje:**

- **Generator przeniesiony z `scripts/` do pakietu** (`view_tracker_ai_1.demo`): UI nie może importować skryptu, a duplikowanie logiki byłoby gorsze. Skrypt został cienkim CLI wołającym ten sam kod.
- **Logowanie w UI dołożone w S6**, choć nie było w planie etapu: bez niego FR-2 i DoD („każda funkcja z §6 działa w UI”) były niespełnione. Device flow: „Rozpocznij logowanie” → kod/link → „Sprawdź zatwierdzenie”; obiekt autoryzacji trzymany w `session_state` do czasu potwierdzenia.
- **Dokumentacja aktualizowana pod 2.0, nie tylko dopisana**: `data-flow.md` i checklista wciąż opisywały CLI, raport HTML i komentarze AI. Nowy `ui-flows.md` opisuje strony, stany i parametry URL — to brakujący dokument z §14.
- **Wersja 2.0.0 w trzech miejscach**: `__version__`, `pyproject.toml` i UA w `.env.example`/`api-notes`; metadane editable w obu interpreterach trzeba było naprawić ręcznie, bo `.venv` blokował stary `.pth` (WinError 5).
- **QA bez udawania**: gitleaks na historii (49 commitów) i drzewie roboczym; start serwera na czystej bazie z `/_stcore/health`; migracja v1→v2 pokryta testem; brak modułów AI/eksportu sprawdzany przez `test_smoke`.

**Korekty:** (1) testy generatora ładowały skrypt przez `importlib.util` — po przeniesieniu do pakietu wystarczy zwykły import; (2) pierwsza wersja przycisku demo używała `state.resolve_db_path` w kontekście configu — poprawione na `config.with_overrides(db_path=...)`; (3) testy AppTest zakładały jeden przycisk na stronie Dane, a doszło logowanie; (4) usunięcie starego edytowalnego `.pth` wymagało ręcznego sprzątania `site-packages`.

**Uwaga:** `.env` z prawdziwym `client_secret` leży lokalnie i jest ignorowany — gitleaks słusznie go widzi w drzewie roboczym, ale historia gita jest czysta.

## Notatki z etapu S5 (2.0 — zdarzenia, adnotacje, alerty)

**Decyzje:**

- **Parser jest tolerancyjny, bo kształt odpowiedzi jest niezweryfikowany.** Akceptuje `offer.id` i `offerId`, `occurredAt`/`occurred_at`/`time`; pojedyncze uszkodzone elementy pomija, ale gdy z listy nie da się rozpoznać **żadnego** — rzuca `EventError` z odesłaniem do `docs/api-notes.md` §9. Dzięki temu pierwsze realne wywołanie od razu powie, co poprawić, a nie policzy zero zdarzeń.
- **Adnotacje ręczne są niezależne od API** — plan B z SPEC, gdy scope okaże się niewystarczający; na bazie PROD formularze są zablokowane.
- **„Co nowego” liczone przed aktualizacją znacznika** i definiowane jako „od poprzedniego odświeżenia strony” (znacznik w `app_state`). To świadome uproszczenie — dokładne „od ostatniego kliknięcia” wymagałoby osobnego zdarzenia sesji.
- **Alerty: spadek liczony od szczytu w oknie**, nie od pierwszego punktu — sprzedawcę interesuje „o ile spadło od najlepszego momentu”. Próg `pct_drop` jest ułamkiem (0,2 = 20%), `abs_drop` liczbą sztuk; reguła bez `offer_id` działa na cały katalog.
- **Etykiety zdarzeń i reguł w `text.py`**, nie w UI — te same nazwy pokazują wykres, tabela zdarzeń i banner alertów.

**Korekty:** (1) brak pola `events` w odpowiedzi nie powodował błędu (parser traktował to jak pustą listę); (2) za długa linia przy budowie etykiet adnotacji; (3) test AppTest zakładał jeden selectbox, a strona Oferty ma teraz także wybór rodzaju alertu.

**Czego jeszcze nie ma:** generatora demo w UI, kompletnej dokumentacji i zrzutów ekranu (S6).

## Notatki z etapu S4 (2.0 — kolektor w aplikacji)

**Decyzje:**

- **Wątek ma własne połączenie SQLite**, tworzone wewnątrz pętli — nie współdzieli go z UI. `connect()` ustawia WAL i `busy_timeout=5000` (z S0), więc odczyt w trakcie zapisu nie kończy się `database is locked`; pokrywa to test równoległy.
- **`st.cache_resource` daje jedną pętlę na proces**, a nie na sesję: dzięki temu zamknięcie karty nie zabija zbierania, a restart procesu zawsze startuje z trybem wyłączonym (świadoma decyzja z SPEC §9).
- **`waiter` wstrzykiwany do runtime'u** — domyślnie `threading.Event.wait`, w testach natychmiastowy. Bez tego test „pętla kontynuuje po błędzie” musiałby czekać 5 minut.
- **Status tylko przez `status()` pod lockiem**; wątek nigdy nie dotyka `st.session_state` ani widgetów.
- **Przy zmianie bazy zatrzymujemy starą pętlę** (`stop_for`), inaczej po przełączeniu na `demo` dane leciałyby dalej do `sandbox`.
- **Komunikat po „Odśwież” przez `session_state` + `st.rerun()`** — inaczej `st.success` znikałby przy natychmiastowym odświeżeniu metryk.

**Korekty:** (1) fabryka klienta w teście tworzyła nową atrapę na każdy przebieg, więc „błąd raz” powtarzał się bez końca — jedna instancja w fabryce; (2) test kontynuacji po `ApiError` czekałby 300 s, więc `waiter` pozwala pominąć oczekiwanie; (3) asercja tekstu blokady PROD („tylko odczyt” vs „tylko do odczytu”).

**Czego jeszcze nie ma:** zdarzeń ofert, adnotacji, alertów progowych i „co nowego” (S5); generatora demo w UI, dokumentacji i zrzutów (S6).

## Notatki z etapu S3 (2.0 — przegląd i porównania)

**Decyzje:**

- **Ranking pokazuje tylko oferty z przyrostami w oknie** — oferta bez danych w przedziale nie ma czego porównywać, więc nie zaśmieca tabeli zerami. Puste okno ma osobny komunikat.
- **Indeks 100 liczony od pierwszego punktu okna, nie od początku historii** — inaczej porównanie zależałoby od tego, jak dawno oferta powstała, a nie od tego, co dzieje się w wybranym zakresie. Oferty z bazą 0 są pomijane (indeks nieokreślony), a UI pokazuje, które i dlaczego.
- **„Oferty ze spadkiem” ≠ „spadki licznika”** — pierwsze to liczba ofert, w których wystąpił choć jeden spadek, drugie to liczba zdarzeń spadku. Kafelki pokazują oba, bo to różne informacje.
- **Porównanie okresów dla „całego katalogu” i dla jednej oferty**, bez osobnej ścieżki w `services` — `compare_periods(offer_id=...)` już to obsługiwał.
- **Linki z rankingu jako `st.column_config.LinkColumn`** z adresem `oferta?db=…&offer=…&range=…&metric=…`; przy `st.navigation` nie ma stron-plików, więc `st.switch_page` nie pasuje, a zwykły link odtwarza widok deterministycznie.
- **Wydajność sprawdzona testem, nie „na oko”**: 20 ofert × 720 snapshotów, przegląd 0,10 s.

**Korekty:** (1) test placeholdera strony Porównania stał się nieaktualny — zastąpiony testem „potrzebne co najmniej 2 oferty”; (2) ruff: za długa linia i sortowanie importów.

**Czego jeszcze nie ma:** „Odśwież”, trybu ciągłego i `collect_runs` w UI (S4); zdarzeń, adnotacji, alertów i „co nowego” (S5).

## Notatki z etapu S2 (2.0 — oferta i wykres)

**Decyzje:**

- **Zakres własny jako funkcje addytywne w `analytics`**, a nie logika w UI: `select_between`, `coverage_between`, `summarize_between`. `summarize` i `summarize_between` korzystają ze wspólnego `_summary(points, nominal_hours)`, więc etykieta trendu, anomalie i przyrosty liczą się identycznie w obu ścieżkach. Pokrycie dla zakresu własnego ma mianownik w długości okna (dla `all` — w rozpiętości danych).
- **Wykres dostaje gotowy `OfferView`** (punkty, dobowe przyrosty, podsumowanie). `ui/charts.py` nie woła analityki poza `daily_gains` już policzonym w services — dzięki temu figura jest testowana bez UI i bez bazy.
- **Metryka „oba” = dwa taby**, nie dwie osie Y na jednym wykresie. Dwie osie przy licznikach o różnych skalach sugerują porównywalność, której nie ma.
- **Brak danych to komunikat w figurze (`Brak danych…`), a nie pusty wykres** — plus `st.info` z podpowiedzią i progiem „mało danych” (`n_points < 6` lub `coverage < 0.3`).
- **Stan w URL rozszerzony o `from`/`to`**, ale daty zapisujemy tylko wtedy, gdy oba pola są ustawione; `range=custom` bez dat pokazuje domyślny ostatni miesiąc.

**Korekty:** (1) test pokrycia przekazywał `Series` do funkcji oczekującej punktów; (2) błędna asercja pokrycia (4 punkty w oknie 7 h = 4/7, nie 0,5); (3) przy edycji testów zostały stare asercje i zniknął newline po `def` — złapane przez `IndentationError`; (4) `plotly_chart` wymaga unikalnego `key` przy dwóch wykresach w tabach.

**Czego jeszcze nie ma:** kafli ogółem, rankingu i porównań (S3), „Odśwież”/trybu ciągłego (S4).

## Notatki z etapu S1 (2.0 — szkielet UI)

**Decyzje:**

- **Stan w URL, ale z fallbackiem na `session_state`.** `AppTest` w Streamlit 1.66 nie ma `query_params`, więc `current_state()` czyta URL, a gdy jest pusty — `session_state`. Dzięki temu ten sam kod jest testowalny bez przeglądarki, a użytkownik nadal może wysłać link do widoku.
- **Baza = trzy nazwy logiczne** (`sandbox`, `prod`, `demo`), a nie dowolna ścieżka. `demo` mapuje się na `data/demo.db`, `prod` na `data/prod.db` i **blokuje zapisy** (badge i ostrzeżenie już w S1, egzekwowanie w S4).
- **Połączenie otwierane na czas jednego rerunu** (`services.database`), nie trzymane globalnie. Koszt jest znikomy, a unikamy problemów z wątkami Streamlita; współbieżność z pętlą kolektora rozwiąże S4 (WAL już włączone w S0).
- **Błędy bazy/konfiguracji nie wywalają aplikacji** — `connection()` pokazuje komunikat, `app.py` łapie `ConfigError` i zatrzymuje render po `st.error`.
- **`AppTest` nie potrafi przełączać stron z `st.navigation`** (oczekuje pliku strony), więc strony testuję przez `AppTest.from_string` z wywołaniem `render()`, a całą aplikację przez `from_file`.

**Korekty:** (1) conftest blokował loopback i asyncio nie mogło utworzyć self-pipe — blokada obejmuje teraz tylko ruch zewnętrzny; (2) `use_container_width` → `width="stretch"` (deprecacja w 1.66); (3) testy sprawdzały surowe wartości selectboxa, a Streamlit zwraca etykiety z `format_func`.

**Czego jeszcze nie ma:** wykresu i wyboru oferty z UI (S2), kafli/rankingu (S3), przycisku „Odśwież” i trybu ciągłego (S4).

## Notatki z etapu S0 (2.0 — fundament)

**Decyzje implementacyjne:**

- **Migracja robi kopię pliku, zanim cokolwiek zmieni.** Kopia trafia obok bazy jako `*.db.bak-YYYYMMDD-HHMMSS`; dla bazy w pamięci jest pomijana. Dzięki temu jednokierunkowa migracja jest odwracalna ręcznie.
- **`init_db` rozróżnia cztery sytuacje:** pusta baza → schemat v2; v2 → dociągnięcie brakujących tabel (`CREATE IF NOT EXISTS`); v1 → migracja; v>2 → `StorageError` (nigdy ciche nadpisanie).
- **`queries.py` liczy przyrosty oknem `LAG`** z filtrem `captured_at <= until`, a dopiero potem `captured_at > since`. Dzięki temu pierwszy punkt przedziału ma punkt odniesienia z przeszłości — bez tego każdy zakres zaczynałby się od zera.
- **`services.refresh_once` zapisuje przebieg także przy błędzie** (`error`/`auth_error`) i dopiero potem podnosi wyjątek; inaczej ekran „Dane” nie wiedziałby, że próba się nie udała.
- **`queries.py` nie ma połączeń z UI ani sieci**, więc pokrycie 100% było osiągalne bez mocków.
- **Systemowy Python też zsynchronizowany** z nowymi zależnościami (użytkownik uruchamia aplikację przez `python -m`), a `jinja2` przywrócony globalnie, bo mógł być używany przez inne projekty — poza zakresem tego repo.

**Czego jeszcze nie ma (świadomie):** UI Streamlit (S1) i pętla w aplikacji (S4). Po S0 repozytorium nie ma interfejsu użytkownika — to stan przejściowy na gałęzi `release/2.0`.

## Notatki z etapu 0 (środowisko)

- Python w PATH nie istnieje (Windows alias), użyty `C:\Users\domin\AppData\Local\Python\pythoncore-3.14-64\python.exe` (3.14.6).
- `python -m venv` nie potrafił doinstalować `pip` — sandboxowy filtr plików blokował zapis do katalogów tworzonych przez `tempfile.mkdtemp`. `pip` w venv doinstalowany przez `uv`; zależności instalowane `uv pip install`.
- `pip install -r requirements-dev.txt` przechodzi (wszystko „already satisfied”), ale kończył się kodem 1, bo pip nie mógł posprzątać swoich katalogów tymczasowych w sandboxie. Na zwykłej maszynie problem nie występuje.
- `pip install -e .` **nie dało się zweryfikować** w trybie `workspace-write` (build wheel używa katalogów tymczasowych). Przy pełnym dostępie do plików instalacja edytowalna i komenda `view_tracker_ai_1 --version` działają — sprawdzone w etapie 4.
- Fixture `tmp_path` nie działał w trybie `workspace-write` (katalogi z prawami 0700 stają się niedostępne). Przy pełnym dostępie do plików problem znika i testy idą standardową bramką, bez obejść.

## Notatki z etapu 1 (decyzje i korekty)

**Decyzje projektowe, których nie było wprost w SPEC:**

- `insert_snapshots` ignoruje duplikat `(offer_id, captured_at)` (`ON CONFLICT DO NOTHING`) i zwraca liczbę *faktycznie* dodanych wierszy — powtórzony `collect` w tej samej sekundzie nie wywraca się na `UNIQUE`, a kolektor dostaje sensowną liczbę do raportu.
- `storage` przyjmuje `sqlite3.Connection` jawnie (bez globalnego stanu), a `connect()` sam tworzy katalog `data/`. Schemat w jednym `executescript`, wersja pilnowana przez `schema_version` — niezgodna wersja to `StorageError`, nie ciche nadpisanie.
- `Config.require_*` sprawdzają wymagania dopiero w miejscu użycia — raport z bazy demo działa bez `ALLEGRO_CLIENT_ID`, zgodnie z PLAN-em.
- Redakcja logów jest funkcją (`redact()`), nie tylko filtrem: te same wzorce da się użyć w raportach i w testach.

**Korekty w trakcie etapu:** (1) pierwsza wersja `from_env` wywalała się na `None.lower()` przy braku zmiennej — poprawione i pokryte testem; (2) `schema_version()` na pustej bazie rzucał `OperationalError` — teraz zwraca `None`.

## Notatki z etapu 2 (decyzje i korekty)

**Decyzje projektowe:**

- **Rotacja refresh tokena:** po każdym odświeżeniu zapisujemy od razu nowy token (stary żyje 60 s), a gdy serwer nie odeśle `refresh_token`, zachowujemy poprzedni — inaczej jedno „puste” odświeżenie wylogowałoby użytkownika.
- **`get_valid_token()` odświeża z buforem 5 min**, żeby token nie wygasł w trakcie żądania; `status()` nigdy nie oddaje wartości tokenów, tylko datę i `expired`.
- **`repr=False`** na `access_token`, `refresh_token` i `device_code` — obiekt może trafić do loga debug bez wycieku.
- **Polling:** `slow_down` zwiększa interwał o 5 s (zgodnie z dokumentacją), `access_denied` i nieznany kod kończą się `AuthError`, wygaśnięcie kodu liczymy od `expires_in`.

**Korekty w trakcie etapu:** (1) pierwsza wersja testów wywoływała `login()` bez zamockowanego `/device` — poprawione przez rozdzielenie testu end-to-end od testów samego `poll()`; (2) bramka w PLAN miała `--cov=src/view_tracker_ai_1/auth`, co nie działa przy `src` layout — zmienione na `--cov=src/view_tracker_ai_1`; (3) `--cov` na ścieżce pliku dawało „no data collected”, więc bramki etapów liczą pokrycie całego pakietu i patrzą na wiersz modułu.

## Notatki z etapu 3 (decyzje i korekty)

**Decyzje projektowe:**

- **Backoff `429` startuje od 60 s, nie od 1 s** (SPEC §9 sugerował 1 s, 2 s, 4 s). Uzasadnienie z dokumentacji: przekroczenie limitu blokuje Client ID na około minutę, więc ponawianie po sekundzie tylko spala próby i tak trafia w blokadę. Gdy API poda `Retry-After`, używamy jego wartości — to zachowanie z tabeli SPEC §9 jest nienaruszone.
- **Koniec paginacji na dwóch warunkach:** `len(items) < limit` **oraz** `offset >= totalCount`. Dokumentacja nie definiuje różnicy `count` vs `totalCount` (`docs/api-notes.md` §8 poz. 5), więc żaden z warunków nie jest jedynym źródłem prawdy.
- **`RemoteOffer` jako DTO klienta** — kolektor nie grzebie w JSON-ie i nie zna kształtu odpowiedzi API; mapowanie na `Offer`/`Snapshot` robi etap 4.
- **Token pobierany na każde żądanie** przez `get_valid_token()` (proaktywne odświeżenie przed wygaśnięciem), a `401` wywołuje wymuszone `refresh()` i dokładnie jeden retry — bez pętli.
- **`limit` zawsze jawny** (domyślnie 100): API ma domyślnie 20, więc „cicha” paginacja gubiłaby oferty.

**Korekty:** (1) ruff zgłosił sortowanie importów w teście — poprawione; (2) po pierwszym zielonym przebiegu dopisałem testy na `Retry-After` w formacie HTTP-date i na śmieciową wartość nagłówka, bo gałąź parsowania daty była nieprzetestowana. Poza tym testy przeszły za pierwszym razem — nie odnotowuję korekt, których nie było.

## Notatki z etapu 4 (decyzje i korekty)

**Decyzje projektowe:**

- **`storage.save_collection()`** robi jedną transakcję na oferty i snapshoty; bez tego dwa osobne `with conn:` commitowały niezależnie i „jedna transakcja” z PLAN-u byłaby fikcją.
- **`run_forever` łapie szeroko** (`except Exception`), bo SPEC FR-3 mówi o błędzie pojedynczego przebiegu; `AuthError` leci dalej, a `KeyboardInterrupt` nie jest `Exception`, więc Ctrl+C naturalnie przerywa pętlę. Nieoczekiwany błąd zostaje w logu z tracebackiem — nie ginie, ale też nie zabija pętli.
- **Opcje globalne działają też po komendzie** (`collect --env sandbox`), tak jak pokazuje `AGENTS.md`; na podkomendach mają `default=argparse.SUPPRESS`, żeby nie nadpisywać wartości podanej przed komendą pustą wartością.
- **`CommandParser.error` → kod 1**, bo argparse domyślnie kończy błędy użycia kodem 2, a w SPEC §8 kod 2 oznacza błąd autoryzacji.
- **`auth status` zawsze zwraca 0** — to komenda informacyjna; brak logowania to normalny stan, nie błąd.
- **`_build_auth`/`_build_client`/`_open_db` jako fabryki** — testy CLI podmieniają je, więc nie trzeba mockować sieci ani prawdziwego device flow.

**Korekta (realna):** pierwsza wersja `save_collection` liczyła wszystkie zmiany w połączeniu, więc `collect` na 2 ofertach meldował „4 nowych snapshotów” (2 upserty ofert + 2 snapshoty). Test to złapał; licznik liczy teraz tylko wstawienia do `snapshots`.

**Faza 1 domknięta:** `collect` na atrapie klienta zapisuje snapshoty, `offers list` je czyta, pokrycie > 80% w każdym module, `pip install -e .` i `view_tracker_ai_1 --version` działają — warunek akceptacji z SPEC §15 spełniony (poza prawdziwym kontem sandbox, które należy do człowieka).

## Notatki ze środowiska — HP_Pavilion (2026-10-28)

Ta sesja powstała na urządzeniu **HP_Pavilion** (konto `hp_pavilion\domin`), po świeżym sklonowaniu repo do pustego katalogu i bez pełnego dostępu do plików (tryb `workspace-write`).

- **Powtórka problemu z etapu 0, ale z węższą diagnozą.** W „Notatki z etapu 0” zapisano, że sandbox blokuje zapis w katalogach tworzonych przez `tempfile.mkdtemp` i że ratunkiem jest pełny dostęp do plików. Dziś udało się to odtworzyć i zawęzić: problemem nie jest `tempfile`, a sam `os.mkdir` z trybem `0o700` — taki katalog dostaje ACL, który odmawia zapisu **i** listowania również procesowi, który go utworzył. `mkdtemp()` zawsze używa `0o700`, dlatego padał pip, a w testach fixture `tmp_path`.
- **Dowód:** trzy katalogi, ten sam proces, ta sama sesja:

  | tryb `os.mkdir` | zapis pliku w środku | `listdir` |
  | --- | --- | --- |
  | domyślny | OK | OK |
  | `0o700` | `PermissionError` | `PermissionError` |
  | `0o777` | OK | OK |

- **Obejście bez pełnego dostępu:** `.tmp/sitelib/sitecustomize.py` podmienia `os.mkdir` tak, by zawsze używał `0o777`; wystarczy wpisać ten katalog na `PYTHONPATH`, a poprawka obejmuje też podprocesy (PEP 517 build backend). Do samej instalacji służy `.tmp/piprun.py`, który robi to wprost przed importem pip. Oba pliki leżą w `.tmp/`, poza repo.
- **Czego to nie naprawia:** katalogi utworzone wcześniej z `0o700` (`.tmp/pytest-of-domin`, część `pip-*`) zostają nieusuwalne — `Remove-Item` również dostaje odmowę. Dlatego `pytest` trzeba wołać z `--basetemp` wskazującym katalog utworzony poza Pythonem.
- **Python 3.13.3, nie 3.14.6.** Interpreter z etapu 0 (`...\pythoncore-3.14-64\python.exe`) już na tej maszynie nie istnieje; `py -0p` pokazuje tylko 3.13.3 i ten trafił do `.venv`. `requires-python = ">=3.11"` jest spełnione, `ruff` i 164 testy są zielone, ale to **inny interpreter** niż ten, na którym pinowano wersje w `requirements*.txt`. Decyzja dla człowieka: doinstalować 3.14 i powtórzyć bramkę albo zaakceptować 3.13 i opisać to jako ograniczenie. **Rozwiązane na polecenie człowieka: 3.14.6 jest zainstalowany — patrz aktualizacja na końcu tej sekcji.**
- **Wpływ na kolejne etapy:** bramki z PLAN-u uruchamiane dosłownie (`pytest -q`) w tym trybie nadal będą zbierać błędy `tmp_path`; trzeba wtedy albo pełnego dostępu do plików, albo `PYTHONPATH=.tmp/sitelib` i `--basetemp`. Kodu aplikacji to nie dotyczy.

**Aktualizacja (ten sam dzień, po przełączeniu sesji na pełny dostęp):**

- **3.14.6 jest zainstalowany:** `%LOCALAPPDATA%\Programs\Python\Python314\python.exe` → `Python 3.14.6`, `.venv` odtworzony na tej wersji, `pip install -r requirements-dev.txt` i `pip install -e .` przeszły bez żadnych obejść, `view_tracker_ai_1 --version` → `0.0.1`.
- **Instalator z python.org nie zadziałał.** `python-3.14.6-amd64.exe` (SHA-256 `14b3e9a7…` zgodny ze stroną wydania) kończył się dwa razy kodem `0x80070005` i nie zapisał nawet logu. Ten sam kod dostawał `uv` przy tworzeniu `%LOCALAPPDATA%\uv\cache` i przy wpisie do rejestru — a PowerShell w tej samej sesji tworzył katalogi w `%LOCALAPPDATA%` bez problemu. Blokada dotyczyła więc **procesów potomnych**, nie samych plików.
- **Obejście:** `uv python install 3.14.6` z `UV_CACHE_DIR` i `UV_PYTHON_INSTALL_DIR` wskazanymi na `.tmp` (build standalone — bez MSI, bez rejestru), a potem `Copy-Item` gotowego drzewa do `%LOCALAPPDATA%\Programs\Python\Python314`.
- **Po przejściu na pełny dostęp problem `0o700` zniknął całkowicie:** bramki przechodzą dosłownie, bez `PYTHONPATH` i bez `--basetemp`, a katalogi uznane wcześniej za nieusuwalne dały się usunąć. Wniosek: to ograniczenie procesu w trybie `workspace-write`, a nie zepsute ACL w repo. Wpisy wyżej zostawiam bez zmian — były prawdziwe w chwili ich zapisania.

## Notatki z etapu 5 (decyzje i korekty)

**Decyzje projektowe:**

- **`start`/`end` w `SeriesSummary` to granice danych, nie okna.** Dzięki temu widać, jak daleko faktycznie sięgają snapshoty; nominalne okno jest nadal używane w mianowniku `coverage`, ale nie udajemy, że dane pokrywają cały przedział.
- **`coverage` sama filtruje punkty** przez `select_points`. Wcześniej zakładała, że dostaje już przyciętą listę — test na starych punktach pokazał, że łatwo o pomyłkę, a filtrowanie jest idempotentne i tanie.
- **Przyrost przypisujemy do dnia późniejszego punktu pary** — czyli do doby, w której wzrost zaobserwowano. Delta na granicy dni nie wpada do poprzedniej doby.
- **Przy mniej niż 3 punktach nachylenie to 0.0, nie „prawdziwy” wynik OLS.** Regresja z dwóch punktów zawsze coś pokaże (test dał 720/dzień) i sugerowałaby pewność, której nie ma; brak trendu ma być widoczny także w liczbach, nie tylko w etykiecie.
- **`build_series` dodane w tym etapie**, bo etap 6 (wykresy) i 8 (raport) potrzebują mapowania snapshotów na serię. Funkcja jest czysta i bez I/O, więc nie łamie zasady z SPEC §5.
- **`COUNTER_DECREASE` jako stała** — `Anomaly` w modelach nie ma pola `kind`, więc stała trzyma słownik nazw na wykresy i raport, zamiast rozsiewać literały.

**Korekty w trakcie etapu:**

1. `deltas` używało `zip(points, points[1:], strict=True)` — to by rzucało `ValueError`, bo listy różnią się długością o 1. Poprawione na `itertools.pairwise`, które dodatkowo nie kłóci się z `ruff format` przy limicie 100 znaków.
2. Pierwsze wersje testów `daily_gains` budowały doby w UTC z założeniem UTC+2 — po 25.10 Warszawa jest na UTC+1, więc doby wypadały o dzień wcześniej. Daty są teraz tworzone jawnie w `Europe/Warsaw`.
3. `coverage` liczyło godziny z punktów spoza okna (wyszło 1/24 zamiast 0) — stąd filtrowanie wewnątrz funkcji.
4. `summarize` liczyło nachylenie również dla 2 punktów — teraz 0.0 plus `brak danych`.
5. **Pułapka PEP 495:** odejmowanie dwóch dat w tej samej strefie daje czas ścienny (24 h), a nie rzeczywisty (25 h). Doba 2026-10-25 jest krótsza o godzinę tylko w UTC; test sprawdza oba wyniki i opisuje różnicę, żeby nikt tego nie „poprawił” z powrotem.
6. **Poprawka zaległa z etapu 4** (`ResourceWarning: unclosed database`): diagnoza w PLAN-ie była niepełna. Ostrzeżenie pojawiało się przy `test_config_error_maps_to_exit_one`, ale winowajcą był `cli._open_db` — wyjątek z `init_db` zostawiał otwarte połączenie, bo `finally` w komendzie nigdy się nie wykonywał (przypisanie `conn = _open_db(...)` kończyło się wyjątkiem). `_open_db` zamyka teraz połączenie przy błędzie i ma osobny test.

## Notatki z etapu 6 (decyzje i korekty)

**Decyzje projektowe:**

- **Szum na przyrostach, nie na poziomie.** Licznik wyświetleń narasta od przyrostów, więc generator dodaje szum do godzinniowego przyrostu i clampuje go do zera. Pierwsza wersja dodawała szum do poziomu i oferta „wzrostowa” miała **204 fałszywe anomalie** — wykres pokazywał 204 „spadki licznika” tam, gdzie ich nie było.
- **`--end` jako parametr.** Deterministyczność wymaga ustalonego końca zakresu, więc skrypt przyjmuje `--end` (domyślnie bieżąca godzina UTC). Ten sam `--seed` i `--end` dają identyczne dane; test to sprawdza.
- **Ponowne uruchomienie zastępuje dane demo** (kasuje wcześniejsze `synthetic` dla tych pięciu ofert), żeby zmiana `--end` nie sklejała dwóch różnych serii w jedną.
- **`render_chart` liczy podsumowanie samo** (`analytics.summarize`) zamiast przyjmować je z zewnątrz — mniej okazji, by wykres i metadane opisywały różne zbiory punktów. `ChartResult` niesie `is_synthetic`, `n_points`, `coverage` i liczbę anomalii, więc testy nie muszą analizować pikseli.
- **Markery anomalii pod linią** (`zorder=1`) i mniejsze: przy serii malejącej jest ich ponad 200 i rysowane na wierzchu zasłaniały cały przebieg poziomu.
- **`ChartError` w `errors.py`** i mapowanie na kod 1 — brak danych w przedziale to błąd użycia, nie awaria.

**Korekty po kontroli wzrokowej (8 poprawek, wszystkie z realnych obrazków):**

1. Adnotacja pokrycia nachodziła na legendę („poziom licznikapokrycie danych…”) → przeniesiona do podtytułu w marginesie figury.
2. Znak wodny „DANE SYNTETYCZNE” leżał na środku figury i zasłaniał słupki przyrostu → teraz tylko w górnym panelu, pod linią.
3. Przy 90 dniach słupki o szerokości 0,8 doby rozpadły się na białe prążki → szerokość 1,0.
4. Oferta „spadek”: 216 markerów tworzyło czerwoną wstęgę bez widocznej linii → markery mniejsze, półprzezroczyste, pod linią.
5. Oferta „plateau” i „spadek”: panel przyrostów miał sam zera i oś od −0,05 do 0,05 (wyglądało jak błąd) → komunikat „brak dodatnich przyrostów w tym przedziale”.
6. Legenda wymieniała „spadek licznika” przed „poziomem licznika” → kolejność rysowania poprawiona.
7. Wykres 24 h miał pokrycie 50%, bo dane demo kończyły się o 00:00, a „teraz” było 13:00 → domyślny koniec seeda to bieżąca godzina.
8. `matplotlib` nie może założyć cache w `%LOCALAPPDATA%\matplotlib` (procesy potomne nie mają tam prawa tworzenia katalogów) i zakładał katalogi `matplotlib-*` w katalogu repo. Cache ustawiony w `tests/conftest.py` (`MPLCONFIGDIR`), a wzorzec dopisany do `.gitignore`. Ten sam mechanizm sprawił, że `pytest` tworzył `pytest-of-domin/` w katalogu repo (systemowy katalog tymczasowy okazał się niezapisywalny, więc `tempfile` spadł do cwd) — `conftest.py` przekierowuje teraz `TMP`/`TEMP` do `.tmp/`, ale tylko gdy temp wypada w repo. **Uwaga dla człowieka:** przy ręcznych uruchomieniach `chart` warto ustawić `MPLCONFIGDIR` samemu, bo inaczej katalog-śmieć pojawi się w repo (jest ignorowany przez git, ale niepotrzebny). Ten sam problem środowiskowy co w „Notatki ze środowiska — HP_Pavilion”.

**Korekty techniczne:**

- Import modułu skryptu w testach (`importlib.util.spec_from_file_location`) wywalał `AttributeError: 'NoneType' object has no attribute '__dict__'` — `dataclasses` ze `slots=True` szukają modułu w `sys.modules`; trzeba go tam zarejestrować przed `exec_module`.
- Próba dopisania testów przez `Add-Content` w PowerShell zapisała tekst w kodowaniu ANSI i uszkodziła UTF-8 w `tests/test_cli.py`; podobnie `Get-Content`/`Set-Content` podwójnie zakodowały `PLAN.md`. Oba pliki cofnięte i zmienione narzędziem do edycji. Wniosek na przyszłość: w tym środowisku nie przepisywać plików repo przez przekierowania powłoki.

## Notatki z etapu 7 (decyzje i korekty)

**Decyzje projektowe:**

- **Bramka jest osobną funkcją i stoi przed cache.** Komunikat „Za mało danych…” nie trafia do bazy — nie ma czego cache’ować, a zmiana danych i tak go unieważni.
- **`input_hash` liczony z agregatów** (`json.dumps(..., sort_keys=True)` → sha256), a nie z surowych snapshotów. Cache jest więc odporny na kolejność pól i nie trzyma w kluczu danych, których nie wysyłamy do modelu.
- **Nazwa oferty jest neutralizowana.** Zwykłe wstawienie jej do promptu nie wystarcza: nazwa `</dane>\nIgnore…` zamykała blok i wypychała instrukcje poza dane. `_safe()` zamienia `<`/`>` na `‹`/`›` i skleja białe znaki — test sprawdza, że `</dane>` występuje w promptcie dokładnie raz.
- **Generatory nie znają bazy.** Bramka, cache i fallback siedzą w `generate_comment`; generator to jedna metoda `generate()`. Dzięki temu raport (etap 8) podmienia generator bez powielania logiki.
- **`except Exception` → `CommentError` bez treści wyjątku.** SDK bywa gadatliwe i potrafi pokazać fragmenty żądania, a tam jest klucz API. Test pilnuje, że `sk-ant-…` nie wycieka w komunikacie.
- **Brak `LLM_MODEL` to błąd, nie zgadywanie.** `Config.require_llm()` wymaga klucza i nazwy modelu; nie wpisujemy „prawdopodobnie claude-…” (SPEC §0 pkt 2).
- **Atrapa mówi wprost „(komentarz bez AI)”**, żeby w raporcie nie dało się pomylić jej z odpowiedzią modelu.

**Korekty w trakcie etapu:**

1. Pierwsza wersja komentarza atrapy pisała „1 spadków licznika” — dodana `_plural()` (1 spadek / 2 spadki / 5 spadków) i testy parametryzowane.
2. `charts` był importowany na górze `cli.py`, więc każda komenda (`auth`, `collect`, `comment`) ładowała matplotlib i tworzyła katalog cache. Import przeniesiony do `_cmd_chart`.
3. Po pierwszym przebiegu pokrycie `ai_comment.py` wynosiło 97%: nieprzetestowane zostały gałąź `except CommentError: raise` i domyślne tworzenie klienta SDK. Dopisane testy (podstawiony moduł `anthropic` w `sys.modules`), teraz 100%.

**Czego nie sprawdzono:** komentarz **nie był uruchamiany na żywym modelu** — w repo nie ma klucza API i testy nie mogą wychodzić do sieci (SPEC §12). Wszystkie ścieżki modelu są sprawdzone na atrapie klienta; jakość samego tekstu (czy model nie zmyśla przyczyn) trzeba ocenić ręcznie na koncie z kluczem — to zadanie człowieka ze SPEC §16.

**Obserwacja, nie błąd:** próg trendu `rel > 0.02` (nachylenie dzielone przez średnią) sprawia, że liniowo rosnąca oferta demo 1004 (151 → 2454 w 90 dni) dostaje etykietę `stabilny` — bo 25 wyświetleń/dzień to 1,9% średniej 1300. To wprost wzór z SPEC §6 FR-4; nie zmieniam go, ale przy czytaniu raportu warto o tym pamiętać.

## Notatki z etapu 8 (decyzje i korekty)

**Decyzje projektowe:**

- **Szablon jako stała w module**, nie plik `.j2`. Plik wymagałby konfiguracji danych pakietu (`package-data`/`MANIFEST`), a raport ma być samodzielny i działać z instalacji edytowalnej oraz z koła. Koszt: HTML jest w Pythonie — zaakceptowany, bo to jeden plik i nie ma go potrzeby edytować poza kodem.
- **`charts.render_png`** zwraca PNG w pamięci i korzysta z tej samej funkcji rysującej co `render_chart`. Bez tego raport musiałby zapisywać pliki tymczasowe, a testy — je sprzątać.
- **Raport nie zna API.** `build_report` dostaje gotowe pary `(Offer, Series)`, więc ten sam kod zbuduje raport z bazy sandbox, produkcyjnej i demo; CLI robi tylko odczyt z bazy.
- **Badge `DEMO`** pojawia się, gdy w danych jest cokolwiek syntetycznego — środowisko jest wtedy nieistotne, bo raport nie pochodzi z API.
- **`--range` i `--offer` można powtarzać**, domyślnie `7d`. Dzięki temu jeden raport może pokazać np. 7d i 30d tej samej oferty.

**Korekty w trakcie etapu:**

1. Pierwsza wersja `build_report` miała typy `dict[str, tuple[object, object]]` z `# type: ignore` — poprawione na `dict[str, tuple[Offer, Series]]`.
2. Szablon miał linię dłuższą niż 100 znaków (ruff E501) — zawinięta.
3. **Dwa razy zepsułem kodowanie pliku, edytując go przez powłokę** (`Set-Content`): `report.py` i wcześniej `PLAN.md` dostały tekst podwójnie zakodowany. Oba pliki przepisane narzędziem do edycji; weryfikacja: `read_bytes().decode("utf-8")` przechodzi, a polskie znaki w raporcie są poprawne. To ten sam błąd, który opisałem w „Notatki z etapu 6” — powtórzony, mimo własnej notatki. Wniosek: w tym środowisku **żadnych** plików repo przez `Set-Content`/`Add-Content`.
4. Testy raportu wpadały w bramkę AI (48-godzinna seria w przedziale 7d to pokrycie 29%) — nie był to błąd kodu, tylko danych testowych; domyślny przedział w testach zmieniony na `24h`, a test bramki dostał osobny przypadek.

**Faza 2 domknięta:** `seed_demo_data` → `chart` → `comment` → `report --range 30d --no-ai` daje jeden samodzielny plik HTML z wykresami, tabelą i komentarzem; pokrycie `report.py` i `charts.py` 100%, całości 97%. Prawdziwe konto sandbox i żywy model nadal należą do człowieka (SPEC §16).

## Notatki z etapu 10 (decyzja D1 i korekty dokumentów)

**Decyzja D1: etap 9 (zmiana ceny) odłożony.** Właściciel projektu zdecydował, że na razie
zostajemy przy odczycie. Konsekwencje, żeby nie były niespodzianką:

- `actions.py` i komenda `act price` **nie istnieją** — aplikacja jest read-only;
- tabela `actions_log` została w schemacie (SPEC §7) i nie jest używana;
- `ALLOW_PROD_WRITES` nadal jest w konfiguracji i nic nie robi, póki nie ma ścieżki zapisu;
- powrót do etapu nie wymaga researchu: endpoint, ciało żądania i obsługa `422` są opisane
  w `docs/api-notes.md` §6;
- `PLAN.md` oznacza etap 9 jako `[-]`, a nie `[ ]`, żeby nikt nie pomylił „odłożony” z „zapomniany”.

**Decyzje przy pisaniu README:**

- Dokładnie **10 nagłówków `##`**, bo bramka liczy `grep -c '^## '`. Podsekcje są `###`, żeby nie
  psuć licznika.
- Tabela endpointów ma **jawną kolumnę statusu**: ✅ potwierdzone, ⚠️ potwierdzone ale
  niezaimplementowane, a `TODO(verify)` są wypisane w README, nie schowane w `docs/`.
- Przykłady zawierają **rzeczywiste wyjście** z przebiegu na danych demo (10 047 snapshotów,
  2160 punktów, 5 ofert / 10 sekcji w raporcie), a nie wyobrażone.

**Korekty (obydwie wymuszone odłożeniem etapu 9):**

1. `docs/screenshots/README.md` obiecywał zrzuty `08-panel-przed-po.png` i `10-error-422.png`
   z komendy `act price --apply`, której nie ma. Oznaczone jako nieaktualne, z notką kiedy wrócą.
2. `docs/manual-sandbox-checklist.md` §5 pytała, czy zmiana ceny działa na sandboxie — punkt
   przekreślony z odesłaniem do decyzji.

Gdyby tego nie poprawić, dokumentacja obiecywałaby funkcję, której użytkownik nie znajdzie —
a to gorsze niż brak dokumentacji.

**Czego nie zweryfikowałem:** `auth login` i `collect` na prawdziwym koncie nie były uruchamiane —
w repo nie ma poświadczeń i testy nie mogą wychodzić do sieci. README opisuje je jako krok
człowieka (SPEC §16), a nie jako coś „sprawdzonego”.

## Notatki z etapu 11 (domknięcie i Definition of Done)

**Czyste środowisko.** Nowy venv na Pythonie 3.14.6, wyłącznie z `requirements.txt`
i `requirements-dev.txt` (bez `pip install -e .`, bez wcześniejszych zależności):

```
pip install -r requirements.txt -r requirements-dev.txt   → OK
pytest -q                                                 → 280 passed, 1 skipped
ruff check .                                              → All checks passed
```

Test przetrwał, bo `pyproject.toml` ma `pythonpath = ["src"]` — testy nie potrzebują instalacji
pakietu. Venv usunięty po przebiegu, żeby nie zajmował miejsca.

**Skan sekretów.** `gitleaks` 8.30.1, binarny release z GitHuba (winget na tej maszynie nie ma).
Bez konfiguracji skan zgłosił:

- w historii 2 trafienia `jwt` — oba to **zmyślony token** w `tests/test_config.py`, użyty
  w teście filtra redakcji logów (`eyJhbGciOiJIUzI1NiJ9.…signature123`); to nie sekret;
- w drzewie roboczym 7 trafień, z czego 6 to pliki testowe `numpy` w `.venv/`, a 1 ten sam JWT.

Dodany `.gitleaks.toml` (reguły domyślne + allowlista) z uzasadnieniem każdego wyjątku. Po nim:
**0 trafień** w historii (29 commitów) i w drzewie. Konfiguracja jest w repo, więc skan jest
powtarzalny.

**Definition of Done (SPEC §15):**

| Punkt | Wynik |
|---|---|
| `pip install -r requirements.txt` + `pytest` na czystym środowisku (Python 3.11+) | ✅ nowy venv na 3.14.6: 280 passed, 1 skipped |
| `ruff check` bez błędów | ✅ All checks passed |
| README: wszystkie 10 sekcji, bez wartości sekretów | ✅ 10/10 `##`; w tabeli env tylko nazwy i przykłady-placeholdery; gitleaks 0 trafień |
| `docs/ai-journal.md`: rzeczywiste wpisy, w tym korekty | ✅ 15 wpisów, 10 sekcji „Korekty…” |
| W repo i w historii commitów brak sekretów | ✅ `gitleaks git` 0/29 commitów, `gitleaks dir` 0; `git ls-files` bez `.env`, `*.db`, `tokens*.json` |
| Wszystkie `TODO(verify)` rozwiązane albo opisane w README jako ograniczenie | ✅ **opisane** (README §10 pkt 5, `docs/api-notes.md` §8) — nie do rozwiązania bez konta sandbox |
| `docs/manual-sandbox-checklist.md` opisuje kroki dla człowieka | ✅ rejestracja aplikacji, `.env`, `auth login`, `collect`, generowanie ruchu, `report`, lista `TODO(verify)`, zrzuty |

**Czego nie da się zamknąć agentowi i dlaczego:** rejestracja aplikacji, konto sandbox, pierwszy
`auth login`/`collect`, zrzuty ekranu, test na żywym modelu i „Refleksja” w dzienniku wymagają
człowieka (SPEC §16). Dla tych punktów DoD nie zgłasza się „zrobione”, tylko wskazuje właściciela.

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
