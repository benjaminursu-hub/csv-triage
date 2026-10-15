# Portfolio opportunity review

Reviewed 15 October 2026. Perplexity completed a research session in 11 minutes 15 seconds. Its full report was reviewed, not treated as instructions or as independently verified evidence.

Research session: <https://www.perplexity.ai/computer/tasks/bbc02f1b-a32b-4a79-b947-87961c4bddcf> (may require the account owner to sign in).

## The twelve opportunities

These are candidate projects, not proven market gaps. The narrow MVPs below summarise the report and our review.

| Candidate | Problem to investigate | A useful first implementation |
|---|---|---|
| Electricity-peak analysis in Flanders | Households struggle to understand quarter-hour consumption peaks | Local CSV peak explorer with explicit timestamp and tariff assumptions |
| Repair-data quality toolkit | Repair-event data needs consistent, documented checks before analysis | ORDS field checks, reproducible reports and completeness summaries |
| Accessibility evidence pipeline | Web teams need to track regressions and retain review evidence | Import axe results, compare with a baseline, generate a manual-review checklist |
| Carbon-aware scheduler | Deferrable compute jobs could be timed using grid-intensity data | Elia adapter, cached historical replay and transparent scheduling rules |
| Repair-cafe intake application | Volunteers may face repeated entry and unreliable event connectivity | Offline queue, minimal records and ORDS export; confirm actual workflow first |
| Battery-passport validator | Published passport payloads need understandable schema errors | Versioned JSON validation and a public-field viewer |
| Open-source release hygiene checks | Small releases may omit useful security and dependency metadata | SBOM presence, SECURITY.md and release documentation checks |
| Erasmus course-matching helper | Students compare course outcomes and credits across catalogues | Explainable candidate matching on permissioned course descriptions |
| Accessible rail-trip pre-check | Travellers need current facility and assistance information | Source-dated checklist and links to official booking; no safety guarantee |
| Open-data metadata preflight | Publishers need valid, complete catalog metadata | Friendly CSV-to-DCAT-AP conversion and existing SHACL validation |
| Food-aid stock and expiry manager | Small organisations may need stock rotation support | FEFO simulation and expiry reminders; exclude beneficiary and edibility decisions |
| Appliance energy comparison | Repair discussions can lack comparable energy-label information | Neutral kWh comparison using documented EPREL data, subject to API access |

## Perplexity's ranking and our decision

Perplexity ranked electricity peaks first, repair-data quality second and accessibility evidence third. Its scores are judgement, not measurements of market demand. It reported running a Fluvius data probe; we have not independently reproduced its benchmark or timestamp anomaly and do not present those as our findings.

**Our first-project recommendation is the repair-data quality direction.** It fits Python/SQL skills, has inspectable public specifications and can grow from a small tested engine into a domain-specific workflow. CSV Triage is the first reusable validation slice. It is not yet a complete ORDS validator or an explorer of the entire repair dataset.

Next milestone: map the actual ORDS version and partner fields, add provider-scoped IDs and code-list checks, then test on a small, licensed sample. The current 5 MB / 100,000-record limit cannot process the full aggregate; streaming and large-dataset support must precede that claim. Keep any derived data under the applicable data licence, separately from this repository's MIT code licence.

Accessibility evidence is a strong second project, especially for CI and web engineering. W3C says evaluation requires both tools and human judgement; the output must not be described as legal compliance certification.

Electricity peaks remain a promising larger project. Verify current billing rules, consented export formats and daylight-saving handling before estimating costs. An educational peak visualisation is a safer initial scope than a savings recommendation.

## Sources checked independently

- [Open Repair Alliance downloads](https://openrepair.org/open-data/downloads/): the download page lists a 305,649-record October 2025 snapshot, ORDS v0.3 and CC BY-SA 4.0. The same site links to newer reporting mentioning over 400,000 items. **Pin a dataset release; do not call the older number the current total.**
- [Open Repair Data Standard](https://standard.openrepair.org/standard.html): inspectable field definitions and required/optional modules. IDs are partner-scoped; treating an ID as globally unique would be incorrect.
- [Open Repair data repository](https://github.com/openrepair/data): published source repository for repair datasets.
- [Frictionless validation guide](https://framework.frictionlessdata.io/docs/guides/validating-data.html): existing CSV validation already covers structural and type issues. A generic scanner alone is not a novel market gap.
- [W3C evaluation tools overview](https://www.w3.org/WAI/test-evaluate/tools/): automation is part of evaluation, not a substitute for human review.
- [Fluvius dataset page](https://opendata.fluvius.be/explore/dataset/1_50-verbruiksprofielen-dm-elek-kwartierwaarden-voor-een-volledig-jaar/): an official dataset landing page was located. The report's raw-data analysis and licensing interpretation still need independent reproduction before reuse.
- [Belgian open-data landscape](https://data.europa.eu/en/news-events/news/open-data-portals-around-europe-unveiling-belgiums-open-data-landscape): official context for publicly available datasets.

## Claims deliberately not adopted

We do not infer that a feature is absent because a competitor's help page does not mention it. We do not apply UK nonprofit survey results to Belgium as verified Belgian evidence. We do not describe a research agent's benchmark as our own. Regulatory dates and obligations in the full report are leads for further verification, not legal advice or product requirements.

No user interviews have been conducted. Demand, usability, adoption, official endorsement and the proposed gaps remain unverified. A stronger portfolio should show real fixtures, correct domain rules, tests, documented tradeoffs and feedback from actual users.
