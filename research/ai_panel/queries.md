# AI answer panel: "before" baseline (built 2026-10-18)

The goal is to measure whether today's assistants give **correct and current** Lithuanian law, and which source they cite. We re-run the same panel after launch (PLAN P4).

**Answer key source:** e-tar.lt current consolidations, fetched 2026-10-18 with `bin/etar_fetch.py` and extracted with `bin/etar_article.py`. The minimum-wage answers come from the resolutions themselves in `Dokumentas`. The "stale" answers come from the open-data dump (`Suvestine`, May 2025).

The questions are chosen so that **a stale source gives a visibly different answer** (Q1–Q7). Q8 is a control: unchanged since 2023, so it should be answered correctly.

| # | Question (ask exactly this) | Correct today (e-tar) | Stale answer looks like | Changed by |
|---|---|---|---|---|
| Q1 | Kokie gyventojų pajamų mokesčio tarifai Lietuvoje 2026 metais darbo pajamoms? | **20 %** up to 36 VDU, **25 %** from 36 to 60 VDU, **32 %** above 60 VDU (GPMĮ Art. 6(1)) | 20 % up to 60 VDU, 32 % above | XV-343 / XV-680, in force 2026-01-01 |
| Q2 | Koks PVM tarifas taikomas knygoms Lietuvoje? | **5 %** (PVMĮ Art. 19(4)(4)) | 9 % | XV-287, in force 2026-01-01 |
| Q3 | Koks PVM tarifas taikomas kultūros renginių bilietams Lietuvoje? | **12 %** (PVMĮ Art. 19(3)(3)) | 9 % | XV-287, in force 2026-01-01 |
| Q4 *(key valid to 2026-10-31; XV-1058 changes Art. 52 from 11-01, re-check)* | Ką darbdavys privalo pateikti darbo tarybai apie nuotolinį darbą pagal Darbo kodekso 52 straipsnį? | At least once a year, at the work council's request: number of remote workers, positions, **and the average pay by position group and gender** where a group has more than two employees (DK Art. 52(8)) | number of workers and positions only (no pay averages) | XV-969, in force 2026-06-07 |
| Q5 | Kas yra „taisomumo įvertis“ pagal Lietuvos civilinį kodeksą? | Defined in **CK Art. 6.228¹(17)**: a score, set under EU law, indicating how repairable a product is. Arts. 6.228¹(16) "gamintojas" and (18) "nemokamas naujinys" are also new | "not defined" / no answer | XV-576, in force 2026-09-27 |
| Q6 | Kas tvirtina privalomo gynybos įgūdžių kurso programą mokyklose? | **The Minister of Education, Science and Sport together with the Minister of National Defence** (Švietimo įstatymas Art. 56(2)(9¹)) | no answer, or a guess | XV-1121 (2026-06-30) |
| Q7 | Kokia minimali mėnesinė alga bus Lietuvoje 2027 metais? | **€1,245** (hourly rate €7.61); Government resolution No. 509 of 2026-07-01 (TAR 2026-11417) | €1,153 (the 2026 figure), or "not yet set" | resolution 2026-11417 |
| Q8 *(control)* | Kokia bausmė už sukčiavimą pagal Baudžiamojo kodekso 182 straipsnį? | Art. 182(1): community service, a fine, restriction of liberty, arrest, or imprisonment up to 3 years. Large value: up to 6 years. Very large value: up to 8 years | unchanged since 2023, so it should be right | – |
| Q9 *(EN)* | What are the personal income tax rates in Lithuania in 2026 for employment income? | same as Q1 | same as Q1 | same as Q1 |
| Q10 *(version)* | Kas pasikeitė Darbo kodekso 52 straipsnyje 2026 metais? | In force: part 8 now requires pay averages by position group and gender (XV-969, in force 2026-06-07). Scheduled: XV-1058 (adopted 2026-06-25) amends Art. 52 again **from 2026-11-01** | "nothing", or 2022 changes | XV-969; XV-1058 pending |

## Scoring (per answer)
- **C**: correct and current. **S**: stale (matches the "stale" column). **W**: wrong in another way. **N**: no answer, or "I can't access".
- **Source:** the domain(s) cited (e-tar.lt, e-seimas, infolex, lrvalstybe, temidy, vmi.lt, news, none).

## Runs
| Run | Date | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude Code WebSearch (retrieval only) | 2026-10-18 | C | **S** | C | **W** | **N** | C | **W** | **N** | C | **W** | 4 C / 1 S / 3 W / 2 N; never cited e-tar; see `baseline_2026-10-18.md` |
| ChatGPT | | | | | | | | | | | | |
| Gemini | | | | | | | | | | | | |
| Copilot / Perplexity (optional) | | | | | | | | | | | | |
