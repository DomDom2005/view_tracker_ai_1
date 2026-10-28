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
