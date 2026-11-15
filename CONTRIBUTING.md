# Contributing

Thank you for helping. The most valuable contribution is a **report of a wrong text or a wrong label**: open an issue with the article URL, what the page says, and what e-tar.lt shows (with the e-tar version dates).

## Project rules
These rules are what makes the site trustworthy. Changes that break them can't be merged.
1. **Never consolidate texts ourselves.** We show the Seimas Chancellery's consolidations unchanged and flag what they don't include yet (D-002, D-016).
2. **Uncertain means flagged.** An article is "Galioja šiandien" only when that can be established. Any new rule must keep `bin/validate_currency.py` at 0 silent errors (D-010).
3. **No machine-generated text on pages.** No LLM summaries or explanations presented next to the law (D-007).
4. **Every word of law is in the HTML.** JavaScript may only add behaviour (D-017).
5. **Normative acts only.** No individual acts that name people.
6. **Be polite to the sources.**
   - data.gov.lt: one request at a time, with backoff; outages are normal.
   - e-tar.lt: only the hand-run validators, rarely (D-004).
7. **Production doesn't depend on anyone's computer** (D-006). Repeatable operations are scripts in `bin/` with `--help`.

## Development
- Python 3.11+, [uv](https://docs.astral.sh/uv/), tests with `uv run pytest -q`.
- For a change to parsing or status rules:
  1. add a test in `tests/`;
  2. rebuild (`uv run bin/nightly.py --no-fetch`);
  3. if the change affects labels, re-run the validators and commit their updated results in `validation/`.
- Design decisions go into `docs/DECISIONS.md` as a new entry; earlier entries are not rewritten.
- New acts: see "Corpus" in `docs/ROADMAP.md`.
