# API notes — zweryfikowane fakty o Allegro REST API

> Data sprawdzenia: **2026-10-27**. Punkty 1–6 odpowiadają sekcji „DO ZWERYFIKOWANIA” w `Project info/SPEC.md` §4.3.
> Metoda: wyłącznie oficjalne strony [developer.allegro.pl](https://developer.allegro.pl). Portal renderuje treść JavaScriptem, więc strony czytano przez proxy renderujące pod tymi samymi oficjalnymi adresami — każde ustalenie ma URL źródła.
> Zasada z `Project info/SPEC.md` §0: **dokumentacja Allegro wygrywa ze SPEC**. Rozbieżności i ich skutki: sekcja 7.

Legenda: ✅ potwierdzone w dokumentacji · ⚠️ potwierdzone, ale inaczej niż zakładał SPEC · ❓ nie potwierdzone (`TODO(verify)` w kodzie)

---

## 1. Scope'y (SPEC §4.3 pkt 1) ✅

| Funkcja projektu | Scope | Status |
|---|---|---|
| Odczyt listy ofert, szczegóły, statystyki | `allegro:api:sale:offers:read` | ✅ istnieje dosłownie |
| Zmiana ceny (edycja oferty, `PATCH`) | `allegro:api:sale:offers:write` | ✅ istnieje dosłownie |

- Osobnego scope'a typu „price” **nie ma** — zmiana ceny to edycja oferty, więc wystarcza `allegro:api:sale:offers:write`.
- Brak wymaganego scope'a w tokenie ⇒ odpowiedź `403`.
- Źródła: [lista dostępnych scope'ów](https://developer.allegro.pl/tutorials/uwierzytelnianie-i-autoryzacja-zlq9e75GdIR#lista-dostepnych-scope-ow), [komunikat o scope w API](https://developer.allegro.pl/news/scope-w-api-allegro-7Gzm9DLXPSX) — 2026-10-27.

### Scope w device flow

- Parametr `scope` jest **opcjonalny**; wartości oddzielane spacją, w URL kodowane jako `%20`.
- Cytat z dokumentacji: „W żądaniu, w zawartości po client_id:client_secret, możesz przekazać dodatkowy parametr scope po znaku & (np. `{client_id}:{client_secret}&scope=allegro:api:sale:offers:write%20allegro:api:orders:read`)”.
- Brak parametru `scope` ⇒ token dostaje wszystkie scope'y zadeklarowane dla aplikacji w panelu.
- ❓ **NIEZWERYFIKOWANE:** czy `scope` idzie w query stringu, czy w ciele żądania — opis w dokumentacji jest niejednoznaczny (`TODO(verify)` w `auth.py`).
- Dla projektu potrzebne: `scope=allegro:api:sale:offers:read%20allegro:api:sale:offers:write`.
- Źródło: ten sam tutorial, sekcja `#device-flow` — 2026-10-27.

---

## 2. Środowiska i hosty (SPEC §4.3 pkt 2) ✅

| Element | Produkcja | Sandbox |
|---|---|---|
| REST API | `https://api.allegro.pl` | `https://api.allegro.pl.allegrosandbox.pl` |
| Autoryzacja (baza) | `https://allegro.pl/auth/oauth/` | `https://allegro.pl.allegrosandbox.pl/auth/oauth/` |
| Token | `POST https://allegro.pl/auth/oauth/token` | `POST https://allegro.pl.allegrosandbox.pl/auth/oauth/token` |
| Device code | `POST https://allegro.pl/auth/oauth/device` | ❓ `https://allegro.pl.allegrosandbox.pl/auth/oauth/device` — **złożenie z bazy sandboxa, nie cytat z docs** |

- Sandbox to **odrębne środowisko**: osobne konto i **osobna rejestracja aplikacji** pod <https://apps.developer.allegro.pl.allegrosandbox.pl/>. Klucze z produkcji nie działają w sandboxie i odwrotnie.
- ❓ Na sandboxie dokumentacja pokazuje jawnie tylko endpoint tokena; ścieżka `/auth/oauth/device` wynika z tej samej bazy. Pierwsze uruchomienie `auth login --env sandbox` musi to potwierdzić (człowiek, SPEC §16).
- Źródła: [informacje podstawowe — środowisko testowe](https://developer.allegro.pl/tutorials/informacje-podstawowe-b21569boAI1#srodowisko-testowe), [pierwsze kroki](https://developer.allegro.pl/tutorials/pierwsze-kroki-MRwYEoOq0im#utworz-aplikacje) — 2026-10-27.

### Nagłówki obowiązkowe ⚠️

- `Accept: application/vnd.allegro.public.v1+json` (wersja beta: `application/vnd.allegro.beta.v1+json`).
- `Content-Type: application/vnd.allegro.public.v1+json` przy `POST`/`PATCH`/`PUT`.
- **`User-Agent: NazwaAplikacji/Wersja (+URL)`** — od **2026-06-30** żądania bez poprawnego UA są odrzucane. To nowy wymóg, którego SPEC nie przewidywał. Nasz UA: `view_tracker_ai_1/0.0.1 (+https://github.com/DomDom2005/view_tracker_ai_1)`, nadpisywalny zmienną `ALLEGRO_USER_AGENT`.
- Źródła: [informacje podstawowe](https://developer.allegro.pl/tutorials/informacje-podstawowe-b21569boAI1), [FAQ](https://developer.allegro.pl/faq) — 2026-10-27.

---

## 3. Device flow: endpointy, parametry, tokeny (SPEC §4.3 pkt 3) ✅

### Krok 1 — żądanie kodu (`device`)

```
POST {auth_base}/device?client_id={client_id}
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded
```

Odpowiedź (przykład z dokumentacji):

```json
{
  "user_code": "cbt3zdu4g",
  "device_code": "645629715",
  "expires_in": "3600",
  "interval": "5",
  "verification_uri": "https://allegro.pl/skojarz-aplikacje",
  "verification_uri_complete": "https://allegro.pl/skojarz-aplikacje?code=cbt3zdu4g"
}
```

- `expires_in` i `interval` przychodzą jako **stringi** — rzutować na `int`, nie zakładać typu liczbowego.
- W terminalu pokazujemy `verification_uri` + `user_code` (albo `verification_uri_complete`).

### Krok 2 — polling (`token`)

```
POST {auth_base}/token
Authorization: Basic base64(client_id:client_secret)   # client_secret NIE w body
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:device_code&device_code={device_code}
```

Odpowiedź przy sukcesie: `access_token`, `token_type` (`bearer`), `refresh_token`, `expires_in` (`43199` w przykładzie) oraz `scope`, `jti`.

### Krok 3 — odświeżanie

```
POST {auth_base}/token
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token={refresh_token}
```

### Czasy życia i rotacja ⚠️

- Access token: **12 h** (`expires_in` ≈ 43199 s).
- Refresh token: **3 miesiące**, **rotowany przy każdym odświeżeniu** — „nowy refresh token jednorazowego użytku”.
- Stary refresh token działa jeszcze **60 s** po odświeżeniu (tolerancja na wyścig), potem jest bezużyteczny.
- Dlatego: po każdym odświeżeniu **natychmiast i atomowo** zapisz nowy `refresh_token` (plik tymczasowy + `os.replace`, SPEC §13). Zgubiony refresh token = ponowne `auth login`.
- ❓ `refresh_token_expires_in` — **nie występuje** w udokumentowanych odpowiedziach; nie parsować tego pola (ani na nim polegać). Czas życia bierzemy z dokumentacji: 3 miesiące.
- Źródło: [uwierzytelnianie i autoryzacja — przedłużenie ważności tokena](https://developer.allegro.pl/tutorials/uwierzytelnianie-i-autoryzacja-zlq9e75GdIR#przedluzenie-waznosci-tokena) — 2026-10-27.

### Błędy pollingu ⚠️

HTTP `400` z ciałem `{"error": ...}`:

| `error` | Znaczenie | Reakcja |
|---|---|---|
| `authorization_pending` | użytkownik jeszcze nie potwierdził | czekaj `interval` i pytaj dalej |
| `slow_down` | pytamy za często | zwiększ interwał (np. +5 s) i pytaj dalej |
| `access_denied` | użytkownik odmówił | `AuthError`, koniec, bez ponowień |
| `Invalid device code` | kod niepoprawny/zużyty | `AuthError` — zacznij od nowa |
| inny kod błędu | „kody straciły ważność” (upłynął `expires_in`) | `AuthError` — zacznij od nowa |

- ❓ `expired_token` jako nazwa kodu **nie jest potwierdzona** w dokumentacji — obsługujemy „każdy inny błąd = restart”, zamiast dopasowywać nieistniejący kod.
- Zalecany interwał pollingu: pole `interval` z odpowiedzi device (**5 s** w przykładzie); częstsze odpytywanie kończy się `slow_down`.
- Źródło: `#device-flow` — 2026-10-27.

---

## 4. `GET /sale/offers`: parametry, `limit`, kształt odpowiedzi (SPEC §4.3 pkt 4) ✅

- Ścieżka poprawna: `GET /sale/offers` (operacja `searchOffersUsingGET`) — lista ofert **zalogowanego sprzedawcy** (nie publiczne wyszukiwanie `GET /offers/listing`, to inny zasób).
- **`stats` z `visitsCount` i `watchersCount` jest w każdej ofercie** — potwierdzone przykładową odpowiedzią w oficjalnym poradniku: `"stats": {"watchersCount": 0, "visitsCount": 0}`.

### Parametry

| Parametr | Wartości | Uwagi |
|---|---|---|
| `limit` | `1..1000`, **domyślnie 20** | ustawiać jawnie; nie zakładać dużej wartości domyślnej |
| `offset` | `0..9999999` | `offset + limit ≤ 10000000` |
| `publication.status` | `INACTIVE`, `ACTIVE`, `ACTIVATING`, `ENDED` | można podać wiele wartości (OR), domyślnie wszystkie statusy |
| `offer.id` | lista stringów | filtr po identyfikatorach |
| `name` | string | szukanie w tytule; min. jedna litera rozpoczynająca dowolny wyraz |
| `sort` | `sellingMode.price.amount`, `stock.sold`, `stock.available` (+ `-` = malejąco) | domyślnie malejąco po ID |

### Odpowiedź i paginacja

```json
{"offers":[{"id":"7610768778","name":"Suszarka do włosów A180 dyfuzor",
            "stats":{"watchersCount":0,"visitsCount":0},
            "stock":{"available":8,"sold":0},
            "publication":{"status":"ACTIVE","startedAt":"2018-10-11T12:16:02Z","endingAt":"2018-10-21T12:16:02Z"}}],
 "count":1,"totalCount":1234}
```

- Pola najwyższego poziomu: `offers`, `count`, `totalCount`.
- ❓ **NIEZWERYFIKOWANE:** dokumentacja nie opisuje wprost różnicy `count` vs `totalCount`. Przyjmujemy: `count` = liczba elementów w tej paczce, `totalCount` = łączna liczba wyników. Kod ma działać poprawnie przy obu interpretacjach: koniec paginacji po `count == 0` **lub** `offset >= totalCount`, i zawsze z bezpiecznym limitem iteracji.
- Paginacja: `offset += limit`, strony po `limit` ofert. Kurs `page.id` (jak w `/sale/products`) **nie dotyczy** tego zasobu.
- Źródła: [dokumentacja referencyjna](https://developer.allegro.pl/documentation), [poradnik „Jak pobrać moje oferty w REST API”](https://developer.allegro.pl/tutorials/jak-zarzadzac-ofertami-7GzB2L37ase#jak-pobrac-moje-oferty-w-rest-api), [informacje podstawowe — stronicowanie](https://developer.allegro.pl/tutorials/informacje-podstawowe-b21569boAI1#stronicowanie) — 2026-10-27.

### Semantyka `visitsCount` ⚠️

- Oficjalna dokumentacja podaje wyłącznie pole `visitsCount` („liczba odwiedzonych”) i `watchersCount` — **bez** opisu unikatowości, okna czasowego i częstotliwości odświeżania.
- Dla kontrastu: `stock.sold` ma wprost udokumentowane okno 30 dni („liczba sprzedanych przedmiotów z ostatnich 30 dni”), a `visitsCount` takiego zapisu **nie ma**.
- Wszystkie twierdzenia o „unikalnych wyświetleniach w oknie 30 dni” pochodzą z forum i GitHub issues, nie z developer.allegro.pl. Dlatego w SPEC §4.2 hipoteza zostaje hipotezą: zapisujemy surowe poziomy, spadek traktujemy jako anomalię, a niepewność opisujemy w README (ograniczenia).
- Źródło: poradnik jw. — 2026-10-27.

---

## 5. Limity zapytań i `429` (SPEC §4.3 pkt 5) ✅

| Limit | Wartość | Zakres |
|---|---|---|
| Główny limit aplikacji | **9000 zapytań/min na Client ID** (dla DCR: Software Statement ID) | produkcja i sandbox |
| `GET /sale/product-offers/{offerId}` | 3500 zapytań/min | na sprzedawcę |
| `PATCH /sale/product-offers/{offerId}` | 2500 zapytań/min | na sprzedawcę |
| Batch modification (poza zakresem) | 250 000 zmian/h lub 9000/min | — |
| Price automation (poza zakresem) | 5 zapytań/s | — |

- Po przekroczeniu głównego limitu: **HTTP `429 Too Many Requests`** i blokada Client ID na **minutę**; potem dostęp wraca automatycznie.
- Osobny mechanizm „leaky bucket” per `user.id`: przy zbyt wielu równoległych żądaniach (nawet poniżej limitu) API odpowiada `429` albo wydłuża czas odpowiedzi.
- ❓ **NIEZWERYFIKOWANE:** czy odpowiedź `429` zawiera nagłówek `Retry-After`. Dokumentacja opisuje „blokadę na minutę” i „po upływie wskazanego czasu”, ale **nie nazywa nagłówka**. Kod: jeśli `Retry-After` jest w odpowiedzi — respektować go; jeśli nie — backoff własny (start ~60 s, bo tyle trwa blokada).
- Polling godzinny (`collect --loop --interval 3600`) jest daleko poniżej limitu; `429` testujemy na mocku, nie wymuszamy na prawdziwym API.
- Źródła: [informacje podstawowe — ograniczenie liczby zapytań](https://developer.allegro.pl/tutorials/informacje-podstawowe-b21569boAI1#ograniczenie-liczby-zapytan-limity), [FAQ](https://developer.allegro.pl/faq), [news o limicie 3500/2500 na `sale/product-offers`](https://developer.allegro.pl/news/22-pazdziernika-2024-wprowadzimy-dodatkowy-limit-na-zasobie-sale-product-offers-offerid-AgjRKzx1luB) — 2026-10-27.

---

## 6. Zmiana ceny i błędy `422` (SPEC §4.3 pkt 6) ⚠️

### Endpoint

- **`PATCH /sale/product-offers/{offerId}`** — edycja pól oferty (partial update, semantyka RFC 7396). Scope: `allegro:api:sale:offers:write` (potwierdzone pośrednio: tabela scope'ów + opis zasobów; strona operacji w portalu jest SPA i nie dała się odczytać).
- Stary `PUT /sale/offers/{offerId}` został **wycofany 2024-01-01** (deprecated od 2023-01-01). Nie używać go i nie trzymać w kodzie jako fallbacku.
- Grupowa zmiana ceny: `PUT /sale/offer-price-change-commands/{commandId}` (`commandId` = UUID), odpowiedź `201 Created` — poza zakresem MVP (faza 3 dotyczy jednej oferty).

### Ciało żądania (minimalne, poprawne)

```json
{"sellingMode": {"price": {"amount": "49.99", "currency": "PLN"}}}
```

- Pole ceny to **`sellingMode.price`**. **Nie** `buyNowPrice`, **nie** `reprice`.
- `amount` podajemy jako **string** (`"49.99"`); dokumentacja w przykładzie odpowiedzi pokazuje liczbę — to niespójność w docs, żądanie budujemy ze stringiem.
- `marketplaceId` (`"allegro-pl"`) występuje tylko w komendzie grupowej, nie w `PATCH`.
- Nagłówki: `Authorization: Bearer {token}`, `Accept: application/vnd.allegro.public.v1+json`, `Content-Type: application/vnd.allegro.public.v1+json`.
- Źródło: [jak zarządzać ofertami — edytuj pola oferty](https://developer.allegro.pl/tutorials/jak-zarzadzac-ofertami-7GzB2L37ase#edytuj-pola-oferty), [wycofanie zasobów `sale/offers`](https://developer.allegro.pl/news/na-poczatku-2024-roku-wylaczymy-zasoby-sale-offers-sluzace-do-tworzenia-i-edycji-ofert-BvqK3XOaEcW) — 2026-10-27.

### Odpowiedź

- `200 OK` — synchronicznie; przy zmianie ceny walidacja pozostałych pól oferty jest pomijana.
- `202 Accepted` — gdy walidacja jest asynchroniczna: wtedy **nie ma** task id w body; są nagłówki `Location` (`GET /sale/product-offers/{offerId}/operations/{operationId}`) i `retry-after`. Polling: `202 IN_PROGRESS` → `303 See Other` → `GET` oferty.
- Źródło: [pierwsze kroki](https://developer.allegro.pl/tutorials/pierwsze-kroki-MRwYEoOq0im) — 2026-10-27.

### Błąd `422`

```json
{"errors": [{"code": "PARAMETER_MISMATCH", "message": "...", "details": "...",
             "path": "productSet[0].product.parameters", "userMessage": "...",
             "metadata": {"productId": "...", "parameterId": "..."}}]}
```

- Obowiązkowe w obsłudze: `code`, `message`, `path`, `userMessage`; `details` / `metadata` pokazujemy, jeśli są.
- CLI wypisuje błędy czytelnie (kod, komunikat, ścieżka pola) i **nie ponawia** żądania.
- Źródło: [komunikat o błędach w ofertach](https://developer.allegro.pl/news/wystawianie-ofert-dzieki-nowym-metadanym-latwiej-obsluzysz-bledy-w-ofertach-lLY0dMDAouj) — 2026-10-27.

### Sandbox

- ❓ Dokumentacja nigdzie nie mówi wprost „zmiana ceny jest dozwolona na sandboxie”. Środowisko testowe „odzwierciedla produkcję”, a konto testowe zakłada się z opcją „Chcę sprzedawać”. Pierwsze `act price --apply --env sandbox` weryfikuje to u człowieka (SPEC §16).
- ❓ Parametr `?pricing` / „change price w tle” **nie występuje** w dokumentacji — nie dodawać go do kodu.

---

## 7. Skutki dla SPEC

Zmiany, które trzeba wprowadzić względem pierwotnego `Project info/SPEC.md`:

1. **`User-Agent` jest obowiązkowy** (od 2026-06-30 bez niego żądania są odrzucane). Trafia do `client.py` jako nagłówek, a do konfiguracji jako `ALLEGRO_USER_AGENT` z sensowną wartością domyślną (§13 SPEC).
2. **`limit` w `GET /sale/offers` ma domyślnie 20, maks. 1000.** Kolektor musi ustawiać `limit` jawnie (np. 100) i paginować `offset += limit`, aż `count == 0` lub `offset >= totalCount`. Inaczej przy >20 ofertach zbiór byłby niepełny.
3. **`count` vs `totalCount`** — dokumentacja nie definiuje różnicy; logika końca paginacji nie może opierać się na niepotwierdzonym znaczeniu `count`.
4. **Semantyka `visitsCount` pozostaje hipotezą** (dokumentacja milczy o unikalności i oknie 30 dni). SPEC §4.2 bez zmian koncepcyjnych, ale README musi to opisać jako ograniczenie, a `scripts/probe_counter.py` jest jedynym sposobem potwierdzenia.
5. **Cena to `sellingMode.price`** (string `amount` + `currency`), a stary `PUT /sale/offers/{offerId}` nie istnieje od 2024-01-01. `actions.py` nie może używać `buyNowPrice`.
6. **`PATCH` może zwrócić `200` albo `202`** — przy `202` obowiązkowa obsługa `Location` + `retry-after` i pollingu `GET .../operations/{operationId}`, a nie odpytywanie oferty.
7. **Scope'y potwierdzone dosłownie**: `allegro:api:sale:offers:read` i `allegro:api:sale:offers:write`.
8. **`Retry-After` niepotwierdzony** — polityka `429` musi działać także bez tego nagłówka (fallback: ~60 s).
9. **Sandbox:** hosty API i auth potwierdzone, ale endpoint `device` na sandboxie i sama zmiana ceny w sandboxie pozostają do sprawdzenia przy pierwszym uruchomieniu z prawdziwym kontem (SPEC §16).

---

## 8. Otwarte `TODO(verify)`

| # | Co | Gdzie w kodzie | Jak domknąć |
|---|---|---|---|
| 1 | Czy `scope` w device flow idzie w query, czy w body | `auth.py` | pierwsze `auth login --env sandbox` u człowieka |
| 2 | Dokładny URL endpointu `device` na sandboxie | `auth.py` (mapa hostów) | jak wyżej; potwierdzić `POST .../auth/oauth/device` |
| 3 | Zachowanie licznika `visitsCount` (czy maleje, czy to okno 30 dni) | `analytics.py` (`scripts/probe_counter.py`) | faza 0 SPEC: ≥ 48 h obserwacji |
| 4 | Czy `429` zawiera nagłówek `Retry-After` | `client.py` (polityka retry) | pierwszy realny `429`; do tego czasu fallback ~60 s |
| 5 | Znaczenie `count` vs `totalCount` | `collector.py` (warunek końca paginacji) | porównanie na koncie sandbox z >1 stroną ofert |
| 6 | Czy zmiana ceny działa na sandboxie | `actions.py` | `act price --apply --env sandbox` u człowieka |
