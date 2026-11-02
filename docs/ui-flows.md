# Ekrany i przepływy UI (2.0)

Stan i przejścia aplikacji Streamlit (SPEC-2.0 §8). Wszystkie strony czytają stan z URL,
więc każdy widok da się zalinkować.

## Parametry URL

| Parametr | Wartości | Znaczenie |
|---|---|---|
| `db` | `sandbox` \| `prod` \| `demo` | wybrana baza (prod = tylko odczyt) |
| `offer` | ID ofert rozdzielone przecinkami | wybór na stronie Oferty; 2–5 ofert na Porównaniu |
| `range` | `24h` \| `7d` \| `30d` \| `90d` \| `all` \| `custom` | zakres czasu |
| `from` / `to` | `YYYY-MM-DD` | granice dla `range=custom` |
| `metric` | `visits` \| `watchers` \| `both` | metryka („oba” = dwie osie Y; na Przeglądzie tylko pierwsze dwie) |
| `q` | tekst | szukanie oferty po nazwie/ID |
| `status` | status albo `all` | filtr statusu listy ofert |
| `sort` | `recent` \| `gain` \| `name` | sortowanie listy ofert |
| `detail` | ID oferty | oferta otwarta w szczegółach |

Przykład: `/?db=demo&offer=1001&range=30d&metric=visits`.

## Strony

### Przegląd (`/przeglad`)

- Przełączniki: zakres, metryka (bez „oba”).
- 8 kafli: poziom metryki, przyrost w oknie z deltą vs poprzedni okres, mediana przyrostu,
  oferty z danymi, oferty ze spadkiem, spadki licznika, poprzedni okres, oferty w bazie.
- Banner alertów progowych (do 3 + „więcej”).
- Ranking ofert z linkiem „pokaż” do strony Oferty z tym samym zakresem.

**Stany:** brak ofert → komunikat z instrukcją; brak przyrostów → komunikat w miejscu rankingu;
błąd bazy → banner, reszta strony nie wywraca się.

### Oferta (`/oferta`)

- Lista ofert: wyszukiwanie po nazwie/ID, filtr statusu, sortowanie (ostatni snapshot / przyrost /
  nazwa), rozwijana tabela z przyrostem. Zaznaczenie 2–5 ofert (multiselect) trafia do Porównania,
  a osobny wybór (`detail`) otwiera szczegóły jednej oferty.
- Wybór zakresu (presety + własny z datami) i metryki (wyświetlenia / obserwujący / **oba —
  dwie osie Y** na jednym wykresie).
- Wykres Plotly: poziom + dzienne przyrosty, markery anomalii, pionowe znaczniki zdarzeń
  i adnotacji, podtytuł z pokryciem i liczbą punktów.
- Karta podsumowania (start/end, min, max, średnia, przyrost, trend, nachylenie, pokrycie,
  punkty), informacja o źródle danych, plakietka „DANE SYNTETYCZNE” przy danych demo.
- „Co nowego od ostatniej wizyty”.
- „Zdarzenia i adnotacje”: pobieranie zdarzeń z API, adnotacje ręczne (dodawanie/usuwanie).
- „Alerty progowe”: trafienia i reguły (dodawanie/usuwanie).

**Stany:** brak ofert; brak ofert po filtrach; brak punktów w przedziale; mało danych
(< 6 punktów lub pokrycie < 30%); dane syntetyczne (plakietka + ostrzeżenie); PROD i demo
(formularze zbierania zablokowane); API bez scope (komunikat, adnotacje działają).

### Porównanie (`/porownanie`)

- Multiselect 2–5 ofert, zakres, metryka (przy „oba” dwa taby).
- Wykres indeksu 100 + tabela (start/koniec okna, przyrost, spadki, punkty).
- Lista ofert pominiętych (brak danych albo poziom startowy 0).
- Zakładka „Porównanie okresów”: bieżący vs poprzedni dla całego katalogu albo jednej oferty.

**Stany:** mniej niż 2 oferty → komunikat; brak danych z poprzedniego okresu → brak delty;
`range=custom` → porównanie okresów niedostępne (komunikat).

### Dane (`/dane`)

- Logowanie Allegro (device flow): kod, link, **automatyczne sprawdzanie zatwierdzenia co 5 s**
  (fragment Streamlita) + anulowanie.
- Kafle: ostatni snapshot, liczba snapshotów, oferty z danymi.
- „Odśwież teraz” (jeden przebieg; komunikat o sukcesie albo `AuthError`/`ApiError`).
- Tryb ciągły: interwał (min. 300 s, zapamiętywany), przełącznik, panel stanu
  (przebiegi, zapisane snapshoty, ostatni start, następny, ostatni błąd).
- Tabela ostatnich przebiegów (`collect_runs`).

**Stany:** PROD → wszystko zablokowane poza odczytem; **demo → zbieranie zablokowane**
(komunikat o niemieszaniu źródeł, plakietka syntetycznych); brak tokena → przycisk logowania;
tryb ciągły wyłączony po restarcie procesu.

### Ustawienia (`/ustawienia`)

- Wybrana baza i jej ścieżka, środowisko API, adresy API/auth.
- Ścieżka tokenów (bez zawartości), poziom logów, wersja aplikacji i schematu.
- Generator danych demo (90 dni) z komunikatem o zapisie.

## Zasady zachowania

- Każda zmiana przełącznika trafia do URL i powoduje rerun; stan jest odtwarzalny z linku.
- Długie operacje (pobranie zdarzeń, odświeżenie, generowanie demo) pokazują wynik komunikatem,
  a błędy domainowe (`AppError`) nie wywalają strony.
- UI nie pokazuje tokenów, nie zapisuje ich w URL ani w `session_state`.
- Cache danych opiera się na `data_version = (max(captured_at), count)` — po zbieraniu widok
  pokazuje świeże dane.
