# Freshness of the three TAR models (checked 2026-10-18)

| Model | Newest data | Content check | Verdict |
|---|---|---|---|
| `Dokumentas` (acts) | `paskelbta_tar` 2026-10-16; 1,638 acts published since 2026-10-01 | the ANK amending law of 2026-07 (XV-1142, TAR 2026-11907) is present | **fresh** (lag ≈ 1–2 days) |
| `Suvestine` (consolidations) | `suv_duom_atnaujinimas` max 2025-05; 0 rows ≥ 2025-06-01 | 5 acts: the dump's newest texts lack 1–9 amending laws that e-tar lists, all adopted after May 2025 (`crosscheck_2026-10-18.txt`); 2,527 rows have empty text | **stale since 2025-05** |
| `Priedas` (annex texts) | `atnaujinimo_data` max 2026-03-03 (matches changelog "2026-03-02 annex texts added") | 4 acts published Sep–Oct 2026 with annexes on e-tar: 0 rows in Priedas. Control, 4 acts from Jan–Feb 2026: 1/1, 7/7, 1/1, 1/1 rows | **stale since 2026-03-03** |

The data.gov.lt distributions (Saugyklos API, JSON, JSONL, RDF, and per-model CSV) are formats of the same store, so they share these dates. All of them show "Atnaujinta" with the current date.

**What the "teises_aktai" JSON/JSONL/RDF rows are (checked 2026-10-18):** each portal row's download link redirects (302) to the same store:
- `teises_aktai` JSON/JSONL/RDF → `get.data.gov.lt/datasets/gov/lrsk/teises_aktai/:all/:format/{json,jsonl,rdf}`. That is every model of the namespace in one stream. The namespace has exactly three models (Dokumentas, Priedas, Suvestine), and the stream starts with Dokumentas rows.
- `Suvestine` CSV → `…/teises_aktai/Suvestine/:format/csv`, and likewise for the others.

So there is no separate "teises_aktai" table. Those rows are bulk-format exports of the same three tables.
