# Local-only data requirements

The committed canonical outputs are sufficient to run the Streamlit dashboard and reproduce the submitted visualisations. Two source-dependent production and validation stages require local intermediate files that are not redistributed through the public repository because their reuse or redistribution terms do not clearly permit public versioning.

The project-created security-arrangement membership register is version-controlled because it is an original, source-cited analytical input created by the team.

## Local-only inputs

| Required path | Used by | Repository treatment |
|---|---|---|
| `data/interim/relations/drd_anchor_country_year.csv` | Diplomatic structural-ties production and source-level validation | Local only |
| `data/interim/fdi/imf_dip_primary_candidates.csv` | FDI regime assignment, production and source-level validation | Local only |

## Versioned project register

`data/sources/relations/security_arrangement_membership_register.csv` is a project-created, source-cited register of verified security arrangements and membership spells. It records:

- arrangement identifiers and names;
- country and anchor assignment;
- effective start and end years;
- methodological depth;
- relationship type;
- source URL and source note; and
- review status.

The register does not reproduce a proprietary source workbook. It is version-controlled because it is an original analytical input required to reproduce the security-institutional component.

## Expected file placement

Authorised users should place the two local-only files at the exact paths below before rebuilding or validating their respective source-dependent stages:

```text
data/interim/relations/drd_anchor_country_year.csv
data/interim/fdi/imf_dip_primary_candidates.csv
```

Do not rename the files or place copies in the repository root.

## Test behaviour

With both authorised local-only inputs available:

```text
146 passed
```

In a simulated fresh public clone without those two files:

```text
122 passed, 2 skipped
```

The skipped modules are:

```text
tests/test_diplomatic_structural_ties.py
tests/test_fdi_structural_ties.py
```

The module-level skips are intentional. Missing non-redistributed inputs are treated as an expected environment condition rather than a test failure. The final-index, classification and dashboard tests do not require the two local-only files.

## Canonical dashboard input

The dashboard reads the committed classified panel:

```text
outputs/tables/closeness_index/us_china_relative_orientation_index_classified.csv
```

It does not rebuild the restricted upstream stages at runtime and does not write data back to the repository.

## Verification of authorised local inputs

Before running the complete suite, confirm that both files are available:

```bash
for f in \
  data/interim/relations/drd_anchor_country_year.csv \
  data/interim/fdi/imf_dip_primary_candidates.csv
do
  test -f "$f" && echo "FOUND: $f" || echo "MISSING: $f"
done
```

Run the complete suite with:

```bash
python -m pytest -q
```

For an internal integrity record, authorised users may calculate SHA-256 hashes locally:

```bash
shasum -a 256 \
  data/interim/relations/drd_anchor_country_year.csv \
  data/interim/fdi/imf_dip_primary_candidates.csv
```

Do not publish the local-only files merely to make source-level tests runnable.

## Source and reuse notes

### Diplomatic Representation Database

The DRD-derived intermediate is retained locally. The repository versions the production code, audit logic and derived project outputs, while the source-dependent reproduction test is skipped when the local intermediate is unavailable.

### IMF Direct Investment Positions

The IMF DIP candidate panel is retained locally. The repository versions the regime-assignment method, production builder, tests, audit summaries and derived project outputs, but not the source-level candidate extract.

### Security-arrangement register

The security register is the team's own analytical work, assembled from cited public sources and reviewed membership spells. It is committed as a reproducible project input.
