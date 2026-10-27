Projekt integracji API allegro, koncepcja na projekt następująca: pobieranie ilości wyświetleń ofert, polubień, notowanie trendów w wyświetleniach. Tworzenie na ich podstawie wykresów (różny przedział czasowy, komentarze AI do wyników)

> **Nota (2026-10-27).** To notatka koncepcyjna sprzed `Project info/SPEC.md`, nie specyfikacja. Nazwa kanoniczna projektu: **`view_tracker_ai_1`**. Gdy notatka przeczy `SPEC.md` (np. ścieżki produkcyjne tutaj vs sandbox-first w SPEC), obowiązuje `SPEC.md`; gdy `SPEC.md` przeczy dokumentacji na developer.allegro.pl, obowiązuje dokumentacja. Fakty zweryfikowane są w `docs/api-notes.md`.


**1. API daje tylko stan bieżący, bez historii.** Liczby są w polu `stats` (`visitsCount`, `watchersCount`) na liście ofert `GET /sale/offers`. Allegro potwierdza, że wyświetlenia oferty zwraca właśnie to pole. Trendy musisz więc budować sam, przez cykliczne snapshoty zapisywane do bazy (np. SQLite). [allegro](https://developer.allegro.pl/documentation)[github](https://github.com/allegro/allegro-api/issues/13039)

**2. Licznik nie jest zwykłą sumą.** Według moderatora społeczności Allegro liczą się tylko unikatowe wyświetlenia, odświeżane co godzinę w cyklu 30-dniowym. Jeśli to okno kroczące, różnica między snapshotami nie jest dziennymi wyświetleniami. Sprawdź to na żywych danych, zanim zbudujesz wykresy, bo komentarze AI oparte na złej interpretacji będą mylące. [allegro](https://spolecznosc.allegro.pl/t5/zaawansowani-sprzedawcy/licznik-wy%C5%9Bwietle%C5%84/m-p/364237)

Jeśli pracujesz na sandboxie, ruchu tam prawie nie ma, więc liczniki będą bliskie zeru (to moje założenie, zweryfikuj). Przyda się tryb z danymi syntetycznymi do demonstracji wykresów albo wejścia na oferty z drugiego konta kupującego.

Twoja lista wymaga też „zmiany na koncie“, a czysty odczyt niczego nie zmienia. Warto zapytać prowadzącego, czy read-only wystarczy. Jeśli nie, możesz dodać akcję: AI sugeruje zmianę (np. ceny), a po Twoim potwierdzeniu `PATCH /sale/product-offers/{offerId}` ją wprowadza. Daje to widoczną zmianę w panelu i realny przypadek `422`.

### Punkty dokumentacji

- **Cel:** sprzedawca widzi tylko bieżące liczniki i nie wie, czy zainteresowanie ofertą rośnie czy spada po zmianie ceny, zdjęć albo tytułu. Narzędzie daje historię, wykresy z różnych okresów i komentarz AI.
- **Endpointy i scope:** `GET /sale/offers` zwraca wiele ofert z `stats` w jednym wywołaniu. To lepsze niż odpytywanie każdej oferty osobno, bo `GET /sale/product-offers/{offerId}` ma dodatkowy limit 3500 zapytań na minutę. Scope do odczytu ofert to prawdopodobnie `allegro:api:sale:offers:read`. Potwierdź to w opisie zasobu, bo nie weryfikowałem. Przy PATCH dojdzie scope do zapisu. [allegro](https://developer.allegro.pl/news/22-pazdziernika-2024-wprowadzimy-dodatkowy-limit-na-zasobie-sale-product-offers-offerid-AgjRKzx1luB)
- **Przepływ danych:** Allegro API → kolektor (cron/harmonogram, co godzinę) → SQLite `(offer_id, ts, visits, watchers)` → agregacja (7/30/90 dni) → wykres + prompt do LLM → raport z komentarzem.
- **Uruchomienie:** `requirements.txt` (`requests`, `python-dotenv`, `matplotlib` lub `plotly`, klient LLM, `pytest`). Zmienne: `ALLEGRO_CLIENT_ID`, `ALLEGRO_CLIENT_SECRET`, `ALLEGRO_ENV` (sandbox/prod), klucz API do LLM i ścieżka do pliku z tokenami. W repo trzymaj tylko `.env.example`. Sandbox wymaga osobnej rejestracji aplikacji (portal ma osobne „Moje aplikacje (sandbox)“). [allegro](https://developer.allegro.pl/search?category=documentation&page=9)
- **Przykłady:** (1) ID ofert → rekordy w bazie; (2) zakres 7 dni → PNG + komentarz AI; (3) opcjonalnie PATCH → zrzut panelu sandboxa przed i po.
- **Błędy:**
    - `401`: token wygasł. Odśwież go refresh tokenem i powtórz żądanie raz. Jeśli odświeżenie się nie uda, poproś o ponowne logowanie.
    - `422`: przy odczycie rzadki (błędne parametry), realny głównie przy PATCH. Pokaż treść `errors` i nie ponawiaj.
    - `429`: główny limit to 9000 zapytań na minutę na Client ID. Przy pollingu co godzinę go nie dotkniesz, więc pokaż obsługę w teście z mockiem. Zastosuj backoff i respektuj `Retry-After`, jeśli jest. [allegro](https://developer.allegro.pl/faq)
- **Testy:** `pytest` z mockowanym HTTP, bez prawdziwego API. Przetestuj logikę delt i okien czasowych, ścieżki 401/422/429 oraz budowanie promptu na stałych danych z zamockowanym LLM.
- **Bezpieczeństwo:** sekrety i tokeny w `.env` lub pliku poza repo (w `.gitignore`), bez logowania tokenów, np. `gitleaks` w pre-commit. Powód jest prosty: wyciek w historii gita oznacza konieczność rotacji sekretu, a token pozwala działać na Twoim koncie sprzedawcy.
- **Dziennik AI:** prowadź go na bieżąco, w formacie data / zadanie / propozycja AI / jak zweryfikowano / wynik. Najczęstsza pomyłka przy API to pola i endpointy, których nie ma w dokumentacji, więc takie przypadki wpisuj w pierwszej kolejności. Sam też weryfikuj moje nazwy scope’ów.