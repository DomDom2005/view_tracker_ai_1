# Zrzuty ekranu do dokumentacji

Pliki wrzuca człowiek. Każdy zrzut: nazwa pliku → komenda, która go wywołuje → co ma być widoczne
→ **co zamaskować**.

| Plik | Komenda / moment | Co ma być widoczne | Zamaskować |
|---|---|---|---|
| `01-auth-login.png` | `python -m view_tracker_ai_1.cli auth login --env sandbox` | kod `user_code` i adres weryfikacji, komunikat o sukcesie | tokeny, `client_secret` |
| `02-auth-status.png` | `... auth status` | data ważności tokena, brak samego tokena | — |
| `03-collect.png` | `... collect --env sandbox` | liczba zapisanych snapshotów | identyfikatory konta |
| `04-offers-list.png` | `... offers list` | id, nazwa, status, ostatni snapshot | dane osobowe w nazwach ofert |
| `05-chart-30d.png` | `... chart --offer <ID> --range 30d --out reports/chart.png` | dwa panele, anomalie, pokrycie | — |
| `06-report.png` | `... report --range 30d --out reports/report.html` | badge środowiska, tabela, komentarz AI | komentarze zawierające dane konta |
| `07-demo-synthetic.png` | `... --db data/demo.db chart ...` | napis „DANE SYNTETYCZNE” | — |
| `08-panel-przed-po.png` | panel sandboxa przed i po `act price --apply` | zmiana ceny oferty | dane konta, adres, zamówienia |
| `09-error-401.png` | wywołanie z unieważnionym tokenem | czytelny komunikat „zaloguj się ponownie” | token |
| `10-error-422.png` | `act price --apply` z niepoprawną kwotą | lista `errors` (code, message, path) | — |

Zasada: na zrzutach nie może być tokenów, `client_secret`, identyfikatorów konta ani danych
kupujących (`Project info/SPEC.md` §13).
