# Technology pillar: technology-goods trade orientation (UN Comtrade)

> **Exploratory work, not part of the official index.** This is Fazly's UN Comtrade comparison of
> technology-hardware imports from the US and China (HS 8471, 8517, 8541, 8542; 2014-2025), kept as a record of
> the analysis. It was proposed for team review but not adopted. The production experimental technology feature is
> built separately by `src/data/build_technology_trade.py` (UNCTAD ICT-goods list, TiVA domestic-value-added
> adjustment, 2004-2024). The official index and dashboard do not read any file listed here.

**Indicator:** `technology_goods_trade_orientation` · **Pillar:** `technology`
**Modules:** `src/data/process_comtrade_technology.py` (processing),
`src/data/collect_comtrade_technology_hs4.py` (API collector for missing slices)
**Notebook:** `notebooks/DS608_Technology_Pillar_Comtrade_Full.ipynb`
**Tests:** `tests/test_technology_processing.py`
**Collector renamed:** originally `src/data/collect_technology_trade.py`; renamed so it does not replace the production collector of the same name

> **Status (1 Nov 2026): scored.** 17 ZIPs (4 bulk China batches, 13 API
> slices: US partner 2014–2025 and China 2023), 16,094 rows. 1,949 of 2,256
> country-years are scored (1,719 complete, 230 partial basket). A findings
> review (distribution, category decomposition, partial baskets, options A–D)
> is in `docs/technology_comtrade_findings_review.md`; the diagnostic scripts are in
> `notebooks/technology_review/`.

## Data source

UN Comtrade bulk download (final annual data, `typeCode = C`, `freqCode = A`,
HS classification as originally reported: H1–H6). Four batch ZIPs, one
tab-delimited UTF-8 `.txt` file each:

| Batch ZIP (id) | Years | Rows |
|---|---|---|
| `25642f40…` | 2014, 2015, 2016 | 2,034 |
| `bc622113…` | 2017, 2018, 2019 | 2,084 |
| `717a87a4…` | 2020, 2021, 2022 | 1,990 |
| `e130647f…` | 2021, 2024, 2025 | 1,760 |
| **Total** | 2014–2025 (no 2023) | **7,868** |

The batches contain 47 columns and 190 reporter codes. The ZIPs are kept locally under
`data/raw/un_comtrade/technology/`, which is git-ignored like all of `data/raw/`.

## Filters

| Field | Kept | Meaning |
|---|---|---|
| `flowCode` | `M` | imports only (no exports) |
| `motCode` | `0` | total mode of transport only |
| `partnerCode` | `156`, `842` | China, United States |
| `cmdCode` | `8471`, `8517`, `8541`, `8542` | HS technology basket |

The bulk files had already been restricted to these values at download time,
so the filters keep all 7,868 rows (`outputs/tables/technology_filter_log.csv`).

## HS basket

| HS | `tech_category` |
|---|---|
| 8471 | Computers and data-processing equipment |
| 8517 | Telecommunications equipment |
| 8541 | Semiconductor devices |
| 8542 | Integrated circuits |

## Scoring formula

For reporter *i*, year *t*, using `primaryValue` (US$):

```
TechnologyOrientation_it = (US_it − China_it) / (US_it + China_it)
```

−1 = fully China-sourced; 0 = equal; +1 = fully US-sourced, **within
the bilateral technology-goods comparison only**. This is not a measure of
geopolitical alignment.

* **Category score** (`technology_trade_components.csv`): the formula applied
  to each HS code.
* **Combined score** (`technology_trade_orientation.csv`): the formula applied
  to totals summed over the **matched basket**, meaning the HS codes where *both*
  partners report a value. `n_categories_matched` (0–4) records how many
  categories enter the score.

## Missing-data treatment

* Missing values are **never converted to zero** and never read as neutral.
* A score is calculated only when both partner values are present and
  `US + China > 0`. Otherwise it is `NaN`.
* A category missing for one partner is left out of *both* partners' totals
  (matched basket), so one partner's total never carries an implicit zero.
* `data_complete = True` only when all four categories are matched and scored.
* `data_status` values:

| status | meaning |
|---|---|
| `complete` | all four categories matched, scored |
| `partial_basket` | scored on 1–3 matched categories |
| `missing_us` / `missing_china` | one partner absent in every category |
| `no_matched_category` | both partners present, but never in the same category |
| `zero_denominator` | matched values sum to 0 |
| `no_data` | reporter absent that year |
| `year_not_in_source_pull` | year absent from every batch (currently 2023) |

* The panel grid is every non-anchor reporter × every year 2014–2025, so gaps stay
  visible.
* **Anchors:** China (156) and the US (842) appear as reporters (88 rows) but
  are not scored. This follows the anchor rule of the total-trade pillar.
* **No mirror supplementation.** The accepted methodology uses reporter-side
  imports only. This differs from the total-trade pillar.

## Processing decisions taken on the full pull

1. **Blank labels in the source.** `reporterISO`, `reporterDesc`, `partnerISO` and
   `partnerDesc` are empty in every row. A reusable crosswalk
   (`data/reference/comtrade_country_crosswalk.csv`) resolves codes in this order:
   (a) source fields, when filled in; (b) 6 documented Comtrade M49 exceptions:
   251 France, 490 Other Asia nes (Taiwan, pseudo-ISO `S19`), 579 Norway,
   699 India, 757 Switzerland, 842 USA; (c) ISO 3166-1 numeric via `pycountry`.
   All 190 codes resolve, and none are flagged unresolved.
2. **Duplicate audit.** All 1,346 rows that are duplicated at
   `reporter × year × partner × HS` come from 2021 appearing in two batches. Each
   pair is identical in all 47 columns (customs `C00`, partner2 `0`, MoS `0`,
   MoT `0`, same value), so one copy of each of the 673 pairs was kept
   (7,195 rows remain). No duplicates differ by customs procedure, secondary partner or
   classification. If a future pull has such duplicates, the code keeps only the
   total row. If a duplicate survives even that rule, the run **stops** rather
   than dropping a row.

## Coverage (current pull)

See `outputs/tables/technology_coverage_by_year.csv` for per-year counts.
2,256 country-years: 1,719 complete, 230 partial basket, 282 no data,
21 missing US, 3 missing China, 1 no matched category. 2025 is provisional
(122 scored countries; Taiwan, Vietnam and the UAE have not reported yet).

**QA flags** (`outputs/tables/technology_qa_flags.csv`; flags only, nothing is removed):
55 `large_yoy_change` (|Δ| > 0.5), 321 `near_bound_score` (|score| ≥ 0.95),
348 `small_total_value`, 705 `small_category_value`, 13 `suspicious_gap`,
1 `us_partner_always_missing`.

## Outputs

| File | Grain |
|---|---|
| `data/interim/comtrade_technology_filtered.parquet` | filtered, de-duplicated, labelled rows |
| `data/processed/technology_trade_components.csv` | country × year × HS (9,024 rows) |
| `data/processed/technology_trade_orientation.csv` | country × year (2,256 rows) |
| `data/processed/technology_pillar_long.csv` | long panel: `country_iso3, country, year, pillar, indicator, score, data_status, source` |
| `data/reference/comtrade_country_crosswalk.csv` | Comtrade code → ISO-3, name, method |
| `outputs/tables/technology_*.csv` | inventory, column validation, filter log, duplicate audit, coverage, QA flags |
| `outputs/figures/tech_qa_*.png` | QA charts |

## Reproducing

```bash
pip install -r requirements.txt
cp .env.example .env            # add COMTRADE_API_KEY=<your key>

# 1. Fetch the slices missing from the bulk pull through the Comtrade+ API
#    (US partner 842 for 2014-2025, plus China 156 for 2023):
python -m src.data.collect_comtrade_technology_hs4 --dry-run   # show the plan
python -m src.data.collect_comtrade_technology_hs4             # 13 requests, about 30 s

# 2. Process everything in data/raw/un_comtrade/technology/
python -m src.data.process_comtrade_technology
python -m pytest tests/test_technology_processing.py
```

The collector (`src/data/collect_comtrade_technology_hs4.py`) sends the same query as
the bulk batches, using `comtradeapicall.getFinalData`. The settings are
`typeCode C`, `freqCode A`, `clCode HS`, `flowCode M`,
`cmdCode 8471,8517,8541,8542`, `motCode 0`, `customsCode C00`,
`partner2Code 0`, all reporters, and `breakdownMode classic`. Each slice is
saved as `api_p<partner>_<year>.zip` in bulk-file layout. Saved slices are
cached, and an empty API result is logged in `api_request_manifest.csv`
without writing a file. Use `--partners`/`--years` to fetch other slices,
for example `--partners 156,842 --years 2014-2025` to re-pull both partners
through the API.

The processor loads every ZIP in the folder, bulk or API. Records that appear
in both (same dimensions and value) are kept once. If two copies of a record
disagree on value, the run stops so the conflict can be investigated.

## Known limitations

* **Country of origin, not brand:** US-designed hardware assembled in China counts as Chinese; third-country suppliers (Taiwan, Korea, Malaysia) are outside the comparison.
* **2025 coverage is partial** (123 reporters, against ~170 in earlier years) because reporting lags.
* **Mixed HS vintages (H1–H6).** HS 8541/8542 and 8517 were revised in HS 2017 and
  HS 2022, so category boundaries shift slightly across reporters and years.
* **Reporter-side imports only.** CIF valuation, origin attribution (re-exports
  through Hong Kong or Singapore, assembly in third countries) and confidential
  trade affect values. No mirror data is used.
* **Comtrade estimates and conversions.** After de-duplication, 86% of rows have
  `isReported = False` and 56% have `legacyEstimationFlag ≠ 0`. The flags are kept in
  the interim parquet for sensitivity checks.
* **Taiwan** appears as Comtrade "Other Asia, nes" (`S19`). Check its key against
  other pillars before merging.
* **Small denominators** can push scores toward ±1. They are flagged, not removed.
