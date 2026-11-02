# Zrzuty ekranu do dokumentacji (2.0)

Pliki wrzuca człowiek. Każdy zrzut: nazwa pliku → jak go uzyskać → co ma być widoczne
→ **co zamaskować**.

| Plik | Jak uzyskać | Co ma być widoczne | Zamaskować |
|---|---|---|---|
| `01-przeglad.png` | uruchom aplikację, wejdź na **Przegląd** | kafle ogółem, ranking, banner alertów (jeśli jest), belka statusu | identyfikatory konta |
| `02-oferta-wykres.png` | **Oferta** → wybierz ofertę, zakres 30d | dwa panele wykresu, karta podsumowania, podpis o pokryciu | — |
| `03-oferta-zdarzenia.png` | **Oferta** → przewiń do „Zdarzenia i adnotacje” | tabela zdarzeń, adnotacje na wykresie, formularz | dane konta w nazwach zdarzeń |
| `04-porownanie.png` | **Porównanie** → wybierz 3 oferty | wykres indeksu 100, tabela, zakładka „Porównanie okresów” | — |
| `05-dane-kolektor.png` | **Dane** → po „Odśwież teraz” | stan logowania, przebiegi, tryb ciągły (wyłączony) | token (nie jest pokazywany) |
| `06-ustawienia-demo.png` | **Ustawienia** → po „Wygeneruj dane demo” | ścieżki, wersje, komunikat o danych demo | — |
| `07-demo-wykres.png` | wybierz bazę „Dane demo” → **Oferta** | wykres z plakietką **DANE SYNTETYCZNE** | — |
| `08-login.png` | **Dane** → „Rozpocznij logowanie” | kod device flow i link (można zamazać kod) | kod `user_code`, identyfikator klienta |
| `09-blad-auth.png` | wywołanie z unieważnionym tokenem | komunikat „zaloguj się ponownie”, nie stack trace | token |
| `10-migracja.png` | pierwszy start na bazie v1 | komunikat o migracji i kopia `.bak-…` | — |

Zasady: na zrzutach nie może być tokenów, `client_secret`, identyfikatorów konta ani danych
kupujących (`docs/api-notes.md`, README §11). Pliki trzymaj w tym katalogu.
