# AI Usage Disclosure

This document records how generative AI tools supported the **US-China Relative Orientation Index** project. AI tools were used as development assistants. The project team retained responsibility for all methodological choices, source selection, code, validation, interpretation, documentation and final outputs.

## Microsoft 365 Copilot

**Tool:** [Microsoft 365 Copilot](https://m365.cloud.microsoft/)

### Types of prompts used

Prompts included:

- comparing statistical, index-construction and data-engineering alternatives;
- translating source documentation into reproducible indicator rules;
- reviewing formulas, sign conventions, missing-data rules and temporal-comparability decisions;
- generating and debugging Python collectors, builders, notebooks and tests;
- interpreting tracebacks and isolating the first material implementation error;
- auditing repository paths, generated artefacts and staged Git changes;
- comparing weighting, coverage and sensitivity results;
- drafting decision-register entries, methodological documentation and presentation material; and
- checking outputs against expected keys, ranges, counts and invariants.

### Project design and methodology

Microsoft 365 Copilot supported:

- comparison of candidate source datasets;
- translation of source documentation into reproducible indicator rules;
- development and review of the sign convention, where positive values are US-oriented and negative values are China-oriented;
- formulation of the security, diplomatic, economic, experimental technology and relationship-condition methods;
- comparison of weighting, missing-data and temporal-coverage treatments;
- development of the fixed three-pillar official core index;
- analysis supporting the decision to retain ICT-goods trade orientation as an experimental feature rather than an official pillar;
- security no-ties sensitivity analysis;
- neutral-band comparison and side-specific Jenks classification; and
- drafting of decision-register entries and methodological explanations.

### Data engineering and software development

Microsoft 365 Copilot supported:

- design and debugging of UN Comtrade collection and mirror-data retrieval;
- development of resumable local caching and rate-limit-aware request handling;
- identification and repair of empty-cache, path and test-discovery problems;
- development of processing and integration scripts for trade, diplomatic ties, FDI, security ties, technology trade and the final index;
- drafting and revision of unit tests;
- repository-path and hygiene reviews;
- notebook construction and validation;
- debugging of Streamlit data loading and environment setup; and
- drafting of dashboard handover and presentation materials.

### Documentation and presentation

Microsoft 365 Copilot supported:

- drafting and restructuring of the root README;
- drafting the decision register, findings reports, data-acquisition notes and handover documents;
- preparation of the methodology flow diagram;
- preparation of the three-slide methodology sequence; and
- editing presentation wording for clarity and consistency.

## Claude by Anthropic

**Tool:** [Claude by Anthropic](https://claude.com/)

Claude supported:

- generation of the first skeletal Streamlit implementation from the team's design brief;
- testing of the pipeline and identification of issues involving missing-pillar weighting, technology influence, interpretation of security zeros, unscored key countries and relationship-condition display;
- adaptation of the dashboard to the revised canonical outputs and fixed orientation classes;
- drafting dashboard tests and checking official scores and class counts;
- drafting the dashboard code walkthrough;
- identification and correction of a wrong test expectation, a deprecated Streamlit argument and an unused function; and
- exploratory UN Comtrade technology-import collection, processing, testing and findings documentation that was retained outside the official index.

## Human review and verification

The team did not accept AI-generated code, methods or prose without review. Verification included:

- consulting official source documentation and inspecting original data structures;
- checking source provenance, country mappings, historical eligibility and non-state exclusions;
- reconciling selected API queries with processed outputs;
- confirming cache reuse and monitoring API-call efficiency;
- checking duplicate keys, missing identifiers, score bounds and output counts;
- preserving unsupported observations as missing rather than zero;
- comparing alternative weighting and missing-data treatments;
- validating the technology decision against its empirical influence on the composite;
- testing neutral-band candidates and leave-one-year-out Jenks stability;
- confirming dashboard totals against canonical production outputs; and
- running the complete automated test suite.

At final submission, the complete repository suite reported:

```text
146 passed
```

This result was obtained in the project owner's authorised local environment with both documented local-only inputs available.

A simulated public clone without those two non-redistributed inputs reported:

```text
122 passed, 2 skipped
```

The skipped modules reproduce and validate source-dependent diplomatic and FDI stages. The committed canonical outputs remain sufficient to run the dashboard and reproduce the submitted visualisations. See [`docs/local_data_requirements.md`](docs/local_data_requirements.md).

The team remains accountable for the final submitted work and for explaining and defending every methodological and technical decision.
