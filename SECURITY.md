# Security

Please report security issues privately, not in public issues. Use GitHub's "Report a vulnerability" button on this repository (Security tab → Advisories), or write to kontaktai@atviri-teises-aktai.lt.

In scope:
- the site and its generated files;
- the nightly workflows and their secrets handling;
- the fetch relay in `worker/`: it must forward only read requests for the Chancellery's two datasets we use, the acts (TAR) and the Seimas votes
  (D-054), and only with its key.

The site is static and has no accounts, forms or user data.
