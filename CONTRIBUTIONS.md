# Team Contributions

This document records the principal contributions to the **US-China Relative Orientation Index** project. Contributions were collaborative, and all team members participated in review, discussion, and the final presentation.

## Darren TAY Teck Yong

### Project leadership and methodology

- conceived and led the overall project and index architecture;
- established the project-wide sign convention and country-year orientation framework;
- developed and reviewed the three official pillars: security, diplomatic, and economic;
- led the final decision to retain ICT-goods trade orientation as an experimental feature rather than an official pillar;
- developed the missing-data, effective-weight, temporal-comparability, and canonical-eligibility rules;
- led the neutral-band and side-specific Jenks classification work;
- maintained the decision register and methodological audit trail; and
- led final index validation and interpretation.

### Data pipelines and validation

- established and managed UN Comtrade API access;
- implemented and reviewed merchandise-trade collection, mirror supplementation, and scoring;
- developed and reviewed diplomatic structural ties, treaty ties, economic institutional ties, FDI, technology trade, and final-index integration workflows;
- investigated source coverage, reporter mappings, cache compatibility, and API efficiency;
- developed or reviewed production builders, notebooks, audit outputs, and unit tests;
- conducted technology-influence, security no-ties, and classification-sensitivity analyses; and
- coordinated repository hygiene, branching, merging, and final quality-control checks.

### Documentation and presentation

- authored or consolidated the decision register, findings reports, methodological notes, handovers, and root documentation;
- prepared the methodology flow diagram and presentation sequence; and
- assumed responsibility for presenting the index methodology.

## Aryan Singh

### Security data and processing

- re-extracted and ingested historical SIPRI arms-transfer data for 1996-2025;
- developed the reproducible SIPRI arms-transfer production workflow;
- implemented country-name mapping and non-state-entity filtering;
- established complete five-year rolling windows and validation rules;
- developed the bounded arms-transfer orientation measure;
- added observation-status, volume, and mapping audit outputs; and
- documented SIPRI source parameters, treatments, and limitations.

### Dashboard design and implementation

- designed and built the Streamlit dashboard under `dashboard/`;
- implemented the global map, fixed class colours, year and range views, country profiles, pillar comparison, weight explorer, relationship-condition view, and methodology tab;
- implemented small-state markers, hover and click interactions, and scenario comparisons;
- reviewed the pipeline and identified five issues involving missing-pillar weighting, technology influence, security-zero interpretation, unscored key countries, and over-broad strained labels;
- updated the dashboard to consume the canonical classified output;
- used the production `weighted_index` and `classify_score` functions instead of duplicating official logic;
- implemented official, strict, difference, single-pillar, relationship-condition, and experimental scenario views;
- added dashboard tests confirming that default scenario scores and classes reproduce the official outputs; and
- updated dashboard architecture and usage documentation.

### Presentation

- assumed responsibility for explaining the dashboard construction and software architecture.

## Fazly Effendy Bin Ali

### Technology-trade data and processing

- developed an exploratory technology-goods trade comparison of imports from the United States and China, using UN Comtrade data for HS 8471, 8517, 8541, and 8542;
- assembled 2014-2025 data from four bulk Comtrade batches and 13 Comtrade+ API slices;
- developed a Comtrade+ API collector for slices missing from the bulk download, with caching and a request manifest;
- implemented reporter-code mapping through a Comtrade-to-ISO3 crosswalk;
- implemented duplicate auditing across overlapping batches;
- implemented matched-basket scoring of US-minus-China imports, without treating missing values as zero;
- added data-status flags, coverage and quality-assurance outputs, and unit tests; and
- submitted the pipeline and a proposed decision-register entry for team review on the `technology-pillar-comtrade` branch.

### Technology analysis and findings

- reviewed the score distribution, category decomposition, country examples, time trends, and partial-basket behaviour;
- found that technology-hardware sourcing is strongly China-oriented, with a median score of -0.83;
- showed that close US partners, including Japan, Germany, the United Kingdom, and Australia, also source mainly from China;
- concluded that the measure captures country of manufacture rather than geopolitical alignment;
- identified telecommunications equipment as the main driver and integrated circuits as the only category with substantial US sourcing;
- tested whether solar products, partial baskets, and HS revisions distort the combined score, and found their effect small; and
- documented the analysis in a technology findings review, with recommendations on labelling, partial baskets, and an integrated-circuits sub-indicator.

### Presentation

- participated in team review and coordination of the final dashboard deliverable;
- assumed responsibility for presenting the live dashboard walkthrough and explaining its contents during the final class presentation; and
- supported final presentation integration across the methodology, construction, and demonstration segments.

## Shared responsibilities

The team jointly reviewed:

- the official three-pillar benchmark;
- treatment of technology as experimental;
- fixed orientation classes and central-band interpretation;
- dashboard scenario behaviour and relationship-condition presentation;
- final README, AI disclosure, and presentation narrative; and
- the submitted repository and demonstration flow.
