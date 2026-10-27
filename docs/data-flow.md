# Przepływ danych

Diagram architektury (źródło: `Project info/SPEC.md` §5).

```mermaid
flowchart LR
    A[Allegro REST API] -->|GET /sale/offers| B[collector]
    B --> C[(SQLite: offers, snapshots)]
    C --> D[analytics: przedziały, delty, trend, anomalie]
    D --> E[charts: PNG]
    D --> F[ai_comment: LLM]
    E --> G[report: HTML]
    F --> G
    H[auth: OAuth device flow + tokeny] --> B
    I[actions: PATCH ceny, faza 3] -->|--apply| A
```

## Przepływ w krokach

1. `auth login` — device flow (SPEC §6 FR-1), tokeny w pliku poza repo (`TOKEN_STORE_PATH`).
2. `collect` — paginacja `GET /sale/offers` (`limit` jawnie, `offset += limit`), wspólny
   `captured_at` w UTC dla całego przebiegu, zapis w jednej transakcji.
3. `analytics` — czyste funkcje na seriach: przedziały, delty, anomalie `counter_decrease`,
   agregacja dzienna w `Europe/Warsaw`, `coverage`, trend OLS.
4. `chart` / `report` — PNG i samodzielny HTML; dane `source='synthetic'` zawsze z napisem
   „DANE SYNTETYCZNE”.
5. `comment` — bramka danych (`n_points < 6` lub `coverage < 0.3` → brak wywołania LLM),
   wejście do modelu wyłącznie jako agregaty.

## Czego ten przepływ nie robi

- Nie scrapuje allegro.pl i nie używa nieudokumentowanych endpointów.
- Nie wysyła do LLM surowych danych konta ani sekretów.
- Nie miesza danych `api` i `synthetic` w jednej bazie.
