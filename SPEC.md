# Specification: BDC Schedule of Investments Extraction Engine

**Document:** SPEC.md  
**Source status:** Implementation-ready  
**Source version:** 1.0

**Primary objective:** Build and iteratively refine an engine that extracts security-level Schedule of Investments data from BDC SEC filings using XBRL, Inline XBRL, and rendered HTML, with effective-dated company-specific templates.


## Conversion and project notes (added for the MacBook project)

The 26 numbered sections below preserve the attached PDF's requirements. These notes are editorial clarifications, not evidence that the engine has been implemented or validated.

- Source: `Spec BDC 10-Q SOI Extrraction.pdf`, supplied by the user, dated October 6, 2026. Markdown conversion repairs PDF page breaks, directory glyphs, tables, code fences, and YAML indentation.
- Support macOS for this project, in addition to the original Windows requirement. Use Python 3.11 or later and portable paths.
- Claude Code uses the user's Anthropic API credentials for development. Version 1 of the extraction engine has no required LLM/API dependency at runtime; keep extraction deterministic.
- All example accessions (`0000000000-26-000001`), namespace placeholders, company mappings, overrides, and iteration metrics are illustrative. Discover real SEC metadata and validate mappings before use. Never claim the example test counts or accuracy figures as achieved results.
- The section 8.2 YAML is illustrative configuration, not a validated production template. Indentation has been reconstructed so XBRL, HTML, composite rules, normalization, and overrides belong to each effective-dated template. Folded example regexes are written on one line to avoid introducing unintended literal spaces.
- Preserve original example settings while implementing these semantics: section 13.3 governs numeric rate storage (`spread=0.045`); section 8.2's `spread_output_format: percent` is display formatting only. A `%` spread must not pass through the example basis-point parser unchanged.
- Resolve the overlap between example `skip_if_regex` and `total_if_regex` explicitly: classify and retain reported totals for reconciliation before excluding them from holding rows. Reject unresolved contradictory classification rules under section 8.4.
- Exact Clark QNames need real namespace URIs; unqualified local names in the example are controlled fallback mappings, not exact QNames. Never ship the `{issuer-namespace}` placeholder as a supported company mapping.
- Treat `issuer_name` / `security_description` as internal aliases, and export `issuer` / `description`. Normalize override match aliases (`raw_issuer_name` in the example versus `issuer_name_raw` in the output model) explicitly in the validated schema.
- No reviewed golden dataset or complete 25–30-company universe accompanies the PDF. Build the evaluator and annotation workflow, label synthetic fixtures and unreviewed candidates honestly, and report production acceptance as not assessed until reviewed observations exist. Never self-certify reviewer approval.
- Before evaluating current-period totals, filter HTML and XBRL to the chosen reporting date and compatible units/currency. Preserve diagnostics for comparative-period tables and ambiguous totals. Do not combine different currencies into a single reconciliation without a disclosed conversion rule.
- Record additional implementation choices in `docs/decisions.md`; do not silently weaken the numbered requirements.

## 1. Objective

Implement a reproducible extraction engine that:

1. Retrieves the latest eligible Form 10-Q for each configured BDC.
2. Downloads and caches the SEC filing package.
3. Extracts complete XBRL facts, contexts, dimensions, concepts, labels, and presentation roles.
4. Identifies security-level Schedule of Investments, or SOI, records.
5. Reconstructs visible SOI tables from filing HTML.
6. Combines XBRL and HTML data into one normalized holding-level dataset.
7. Splits composite text into fields such as issuer, description, industry, reference index, spread, and maturity date.
8. Validates extracted rows against reported SOI totals.
9. Stores diagnostics and complete source lineage.
10. Supports effective-dated, company-specific extraction templates.
11. Can be iteratively improved by running the engine, evaluating its output, updating templates or generic logic, and rerunning regression tests.

The implementation must favor traceability and correctness over aggressive inference.

## 2. Guiding principles

### 2.1 Source-first extraction

Prefer values explicitly disclosed in the filing. Every output field must be traceable to one or more of:

- an XBRL fact;
- an XBRL dimension member;
- a visible HTML table cell;
- a company-specific parsing rule;
- a reviewed override with provenance.

### 2.2 No unsupported fabrication

The engine must not invent values.

For example, given:

```text
Software Redwood Runway Bidco, LLC Investment Type
First Lien Secured Debt - Term Loan Interest Rate
S+450, 0.50% Floor Maturity Date 12/17/2031
```

the engine can directly infer:

- industry: Software
- issuer: Redwood Runway Bidco LLC
- description: First Lien Secured Debt - Term Loan
- reference index: SOFR, if the company template defines S = SOFR
- spread: 4.50%
- rate floor: 0.50%
- maturity date: 2031-12-17

It cannot infer from that string alone:

- issue date;
- that Redwood should be removed from the issuer;
- that a term loan is a revolving loan;
- that Senior belongs in the description.

Such changes require a separate, documented enrichment or override source.

### 2.3 Generic engine plus company templates

The core engine must contain reusable logic. Company-specific differences must generally be represented in configuration rather than hard-coded conditional statements.

Use application code for:

- SEC retrieval;
- XBRL model processing;
- generic table reconstruction;
- generic normalization;
- generic matching;
- validation;
- diagnostics.

Use templates for:

- company-specific concepts and axes;
- table identification;
- header aliases;
- row formats;
- composite field patterns;
- reference-rate abbreviations;
- scale rules;
- carry-forward rules;
- exclusions;
- reviewed overrides.

### 2.4 Effective dating

A template must be effective-dated because issuers can change:

- taxonomy;
- filing vendor;
- SOI layout;
- dimension structure;
- column labels;
- row formatting;
- reference-rate notation.

A rule that works for one reporting period must not automatically be assumed to work for every historical and future period.

### 2.5 Deterministic behavior

Given the same:

- filing package;
- template version;
- engine version;
- runtime configuration;

the engine must produce the same normalized output.

## 3. Scope

### 3.1 In scope

- SEC Forms 10-Q and optionally 10-Q/A.
- SEC submissions metadata.
- SEC accession-directory discovery.
- Extracted XBRL instance documents.
- Inline XBRL fallback.
- Presentation-role discovery.
- Context and dimension extraction.
- Holding-axis discovery.
- HTML SOI table extraction.
- XBRL/HTML record matching.
- Composite text parsing.
- Effective-dated company templates.
- Reconciliation to reported fair value, cost, and amortized cost.
- Excel, CSV, Parquet, and JSON diagnostics.
- Regression evaluation against reviewed data.

### 3.2 Out of scope for version 1

Unless explicitly added later:

- OCR of scanned filings;
- extraction from image-only PDFs;
- automatic external entity resolution;
- automated determination of issue dates from third-party sources;
- amendment restatement logic beyond choosing whether 10-Q/A is eligible;
- valuation modeling;
- credit analysis;
- downstream ratings decisions.

## 4. Technical constraints

### 4.1 Runtime

- Python 3.11 or later.
- Must run from a command line without a notebook.
- Must support Windows.
- Paths must be configurable and must not be embedded in extraction functions.

### 4.2 Required packages

```text
arelle-release
requests
pandas
openpyxl
beautifulsoup4
lxml
pyyaml
pydantic
pytest
rapidfuzz
pyarrow
```

pydantic is recommended for template validation. rapidfuzz may be used for controlled matching.

### 4.3 SEC access requirements

- Use a descriptive SEC-compliant user agent containing a monitored email.
- Rate-limit requests.
- Retry 429, 500, 502, 503, and 504.
- Cache downloaded files.
- Do not repeatedly download unchanged accession files.
- Log every failed request without exposing credentials.
- The SEC user agent and output paths must be environment or configuration values.

## 5. Proposed repository structure

```text
bdc-soi/
  SPEC.md
  README.md
  pyproject.toml
  config/
    application.yml
    bdc_universe.yml
    template.schema.json
  templates/
    generic.yml
    1379785.yml
    1476765.yml
    ...
  src/
    bdc_soi/
      __init__.py
      cli.py
      config.py
      models.py
      sec_client.py
      filing_discovery.py
      filing_package.py
      xbrl_loader.py
      xbrl_inventory.py
      role_discovery.py
      axis_discovery.py
      xbrl_holdings.py
      html_tables.py
      composite_parser.py
      hybrid_matcher.py
      normalization.py
      validation.py
      evaluation.py
      diagnostics.py
      output.py
  tests/
    unit/
    integration/
    regression/
    fixtures/
  golden/
    manifests/
    expected/
    annotations/
  cache/
  output/
```

Large SEC filing files should not be committed unless licensing, storage, and repository policies permit it. Golden manifests may instead identify accession numbers and checksums.

## 6. Command-line interface

The implementation must provide at least the following commands.

### 6.1 Extract

```bash
python -m bdc_soi extract \
 --cik 1837532 \
 --accession 0000000000-26-000001 \
 --output output/run_001
```

If accession is omitted, use the latest eligible 10-Q.

```bash
python -m bdc_soi extract \
 --cik 1837532 \
 --latest \
 --output output/run_001
```

Run a configured universe:

```bash
python -m bdc_soi extract-universe \
 --universe config/bdc_universe.yml \
 --output output/run_001
```

### 6.2 Evaluate

```bash
python -m bdc_soi evaluate \
 --actual output/run_001 \
 --golden golden \
 --report output/run_001/evaluation
```

### 6.3 Inspect a filing

```bash
python -m bdc_soi inspect \
 --cik 1837532 \
 --accession 0000000000-26-000001 \
 --output output/inspection
```

Inspection output must include:

- presentation roles;
- mapped and unmapped concepts;
- candidate holding axes;
- HTML table scores;
- inferred column mappings;
- example rows;
- reported total candidates.

### 6.4 Validate templates

```bash
python -m bdc_soi validate-templates --templates templates
```

### 6.5 Compare runs

```bash
python -m bdc_soi compare \
 --before output/run_001 \
 --after output/run_002 \
 --output output/comparison
```

## 7. Configuration

### 7.1 Application configuration

Example config/application.yml:

```yaml
sec:
 user_agent: "Organization monitored-mailbox@example.com"
 request_delay_seconds: 0.20
 request_timeout_seconds: 90
 retries: 4

filings:
 months_back: 18
 eligible_forms: ["10-Q"]
 use_amendments: false

paths:
 cache: "./cache"
 templates: "./templates"
 output: "./output"

extraction:
 append_unmatched_html_rows: true
 write_long_xbrl_facts: true
 preserve_raw_values: true

matching:
 minimum_score: 5
 require_unique_best_match: true

validation:
 total_relative_tolerance: 0.005
 total_absolute_tolerance: 1.0
```

### 7.2 BDC universe

Example config/bdc_universe.yml:

```yaml
companies:
 - cik: "1837532"
   enabled: true
 - cik: "1633858"
   enabled: true
```

CIKs should be stored as strings without leading zeros internally and padded only for SEC submissions URLs.

## 8. Company-specific template design

Each CIK should have a separate template file. A file can contain multiple effective-dated template versions.

### 8.1 Template selection

Select a template using:

1. CIK;
2. report date;
3. form type, if specified;
4. optional accession override.

When multiple templates match:

1. accession-specific template wins;
2. narrowest effective-date range wins;
3. higher template priority wins;
4. otherwise fail validation rather than choose unpredictably.

### 8.2 Template schema

Example:

```yaml
schema_version: 1
cik: "1837532"
company_name: "Example BDC"
templates:
  - id: "example-bdc-2025-layout-v1"
    priority: 100
    effective_from: "2025-01-01"
    effective_to: null
    forms: ["10-Q"]
    xbrl:
      role_regex:
        - "Schedule of Investments"
        - "Investment Portfolio"
      row_axes:
        explicit_qnames:
          - "{issuer-namespace}InvestmentIdentifierAxis"
        regex:
          - "Investment.*Identifier"
          - "Portfolio.*Company"
        exclude_regex:
          - "FairValue.*Hierarchy"
          - "Industry"
          - "Geography"
      field_concepts:
        issuer_name:
          - "{issuer-namespace}InvestmentIssuerName"
          - "PortfolioCompanyName"
        security_description:
          - "{issuer-namespace}InvestmentTitle"
        fair_value:
          - "{issuer-namespace}InvestmentOwnedAtFairValue"
        cost:
          - "{issuer-namespace}InvestmentOwnedAtCost"
        principal_amount:
          - "InvestmentPrincipalAmount"
        maturity_date:
          - "InvestmentMaturityDate"
      field_preference:
        fair_value:
          - namespace: "issuer"
            concept: "InvestmentOwnedAtFairValue"
          - namespace: "us-gaap"
            concept: "FairValueOfInvestments"
      context_filters:
        require_report_date: true
        allowed_period_types: ["instant"]
        excluded_axes_regex:
          - "FairValueHierarchy"
          - "AffiliateStatus"
    html:
      table_detection:
        heading_regex:
          - "Schedule of Investments"
          - "Consolidated Schedule of Investments"
        required_terms:
          - "Fair Value"
        optional_terms:
          - "Cost"
          - "Principal"
          - "Maturity"
        excluded_terms:
          - "Fair Value Hierarchy"
          - "Financial Highlights"
        minimum_score: 6
        max_heading_distance: 20
      header_rows:
        min: 1
        max: 4
      header_aliases:
        issuer_name:
          - "^Portfolio Company$"
          - "^Issuer$"
        security_description:
          - "^Investment Type$"
          - "^Description$"
        principal_amount:
          - "Principal"
          - "Par Value"
        cost:
          - "(?<!Amortized )Cost"
        amortized_cost:
          - "Amortized Cost"
        fair_value:
          - "Fair Value"
        maturity_date:
          - "Maturity"
        interest_rate:
          - "Interest Rate"
          - "Coupon"
      scale:
        source: "table_then_document"
        thousands_regex:
          - "amounts? in thousands"
          - '\$ in thousands'
        millions_regex:
          - "amounts? in millions"
        default: 1
      row_rules:
        carry_forward:
          - issuer_name
          - industry
        group_heading_target: industry
        skip_if_regex:
          - "^Total"
          - "^Subtotal"
        total_if_regex:
          - "Total Investments"
          - "Investments at Fair Value"
        require_any_numeric:
          - fair_value
          - cost
          - amortized_cost
          - principal_amount
    composite_fields:
      - id: "member-label-layout-v1"
        source_field: issuer_name
        pattern: '^(?P<header>.+?)\s+Investment Type\s+(?P<description>.+?)\s+Interest Rate\s+(?P<rate>.+?)\s+Maturity Date\s+(?P<maturity>\d{1,2}/\d{1,2}/\d{4})$'
        header_parser:
          known_industries:
            - "Software"
            - "Healthcare"
            - "Business Services"
            - "Financial Services"
          industry_position: "prefix"
          remainder_target: issuer_name
        rate_parser:
          pattern: '(?P<index>SOFR|S|LIBOR|L|PRIME|P)\s*\+\s*(?P<spread_bps>\d+(?:\.\d+)?)'
          floor_pattern: '(?P<floor_pct>\d+(?:\.\d+)?)\s*%\s*Floor'
          index_aliases:
            S: "SOFR"
            SOFR: "SOFR"
            L: "LIBOR"
            LIBOR: "LIBOR"
            P: "Prime"
            PRIME: "Prime"
    normalization:
      legal_suffixes:
        remove_preceding_comma: true
      date_formats:
        - "%m/%d/%Y"
        - "%Y-%m-%d"
      spread_input_unit: "basis_points"
      spread_output_format: "percent"
    overrides: []
```

### 8.3 Reviewed overrides

Overrides must be exceptional and auditable.

```yaml
overrides:
 - id: "reviewed-2025q4-001"
   match:
     report_date: "2025-12-31"
     raw_issuer_name: "Exact original source text"
   set:
     issuer_name: "Reviewed issuer name"
     issue_date: "2024-12-17"
   provenance:
     source_type: "filing_footnote"
     source_url: "https://www.sec.gov/Archives/..."
     source_reference: "Page 84, footnote 7"
     reviewed_by: "reviewer@example.com"
     reviewed_at: "2026-02-10"
     rationale: "Issue date disclosed outside the main SOI table."
```

Every override must include:

- unique ID;
- exact match criteria;
- values being changed;
- source;
- rationale;
- reviewer;
- review date.

An override must not silently change unrelated periods.

### 8.4 Template validation

Reject a template if:

- date ranges overlap ambiguously;
- regexes do not compile;
- an unknown canonical field is referenced;
- an override lacks provenance;
- a percentage or scale unit is unspecified where needed;
- duplicate template IDs exist;
- a row rule conflicts with a total rule;
- explicit XBRL QNames are malformed.

## 9. Canonical output model

### 9.1 Holding identity and filing metadata

| Field | Type | Description |
| --- | --- | --- |
| holding_id | string | Stable deterministic hash of filing and row identity |
| cik | string | Unpadded CIK |
| company_name | string | SEC registrant name |
| accession_number | string | SEC accession |
| filing_date | date | Filing date |
| report_date | date | SOI reporting date |
| form | string | Filing form |
| template_id | string | Applied template |
| engine_version | string | Application version |

### 9.2 Normalized holding fields

| Field | Type | Unit/format |
| --- | --- | --- |
| issuer | string | Normalized issuer name |
| issuer_name_raw | string | Original source value |
| description | string | Security/instrument description |
| description_raw | string | Original source value |
| industry | string | Disclosed industry |
| sector | string | Disclosed sector |
| country | string | Disclosed country |
| investment_type | string | Disclosed investment type |
| reference_index | string | SOFR, LIBOR, Prime, etc. |
| spread | decimal | Decimal rate, e.g. 0.045 |
| spread_bps | decimal | Basis points, e.g. 450 |
| cash_rate | decimal | Decimal rate |
| pik_rate | decimal | Decimal rate |
| rate_floor | decimal | Decimal rate |
| interest_rate | decimal/string | Normalized numeric rate where possible |
| issue_date | date/null | Only when disclosed or sourced |
| maturity_date | date/null | ISO date |
| principal_amount | decimal/null | Filing currency units |
| face_amount | decimal/null | Filing currency units |
| shares | decimal/null | Count |
| cost | decimal/null | Filing currency units |
| amortized_cost | decimal/null | Filing currency units |
| fair_value | decimal/null | Filing currency units |
| percent_of_net_assets | decimal/null | Decimal proportion |
| currency | string/null | ISO currency where known |
| affiliate_status | string/null | Disclosed status |
| controlled_status | string/null | Disclosed status |
| non_accrual_flag | boolean/null | Disclosed or explicitly parsed |
| footnote_markers | string/null | Raw markers |

Internal canonical names may remain issuer_name and security_description, but final output must expose issuer and description consistently. Avoid duplicate fields unless raw and normalized versions are intentionally retained.

### 9.3 Lineage and diagnostics

| Field | Description |
| --- | --- |
| source_method | xbrl, html_only, hybrid_xbrl_html, etc. |
| source_document | Entry document |
| source_table | HTML table/row location |
| source_context_ids | XBRL context IDs |
| source_fact_ids | XBRL fact IDs |
| source_concepts | Concept QNames by field |
| dimension_signature | Complete dimension identity |
| member_labels | XBRL member labels |
| field_lineage | Per-field source and transformation |
| field_conflicts | Conflicting candidates |
| template_rule_ids | Rules that affected the row |
| extraction_confidence | Numeric score from 0 to 1 |
| review_flags | Structured reasons for review |

### 9.4 Field-level lineage

Store field lineage as structured JSON:

```json
{
    "issuer": {
       "source": "xbrl_dimension_member",
       "raw_value": "Software Redwood Runway Bidco, LLC Investment Type ...",
       "rule_id": "member-label-layout-v1",
       "normalized_value": "Redwood Runway Bidco LLC"
    },
    "spread_bps": {
       "source": "parsed_composite_text",
       "raw_value": "S+450",
       "rule_id": "member-label-layout-v1",
       "normalized_value": 450
    }
}
```

## 10. Filing discovery and package retrieval

### 10.1 Filing selection

1. Retrieve CIK##########.json.
2. Include recent submissions and referenced older submission files within the configured lookback.
3. Parse filing and report dates.
4. Keep configured eligible forms.
5. Select the latest filing date, then accession number.
6. Exclude amendments unless enabled.
7. Record why each filing was selected or excluded.

### 10.2 Package retrieval

For the chosen accession:

1. Retrieve index.json.
2. Download:
- primary filing document;
- XML files;
- XSD files;
- relevant HTML files;
- filing summary files;
- JSON metadata.
3. Cache by CIK and accession.
4. Record file size and SHA-256 checksum.
5. Prefer an XML document whose root is {http://www.xbrl.org/2003/instance}xbrl.
6. Prefer _htm.xml among valid instance candidates.
7. Fall back to the primary Inline XBRL document.

Do not identify an instance document only by filename.

## 11. XBRL extraction requirements

### 11.1 Complete fact inventory

For every fact with a context, capture:

- concept Clark QName;
- prefixed QName;
- local name;
- standard label;
- documentation label;
- raw value;
- normalized value;
- numeric value;
- nil status;
- unit;
- decimals;
- context ID;
- period type;
- semantic period start/end;
- complete dimensions;
- fact ID;
- whether the concept appears in a candidate SOI presentation role;
- mapped canonical field.

### 11.2 Date semantics

Arelle may internally represent a date-only XBRL instant as midnight on the following date. Convert it back to the semantic reporting date when appropriate.

Test this behavior explicitly.

### 11.3 Concept mapping

Mapping precedence:

1. exact template QName;
2. template regex;
3. generic exact QName;
4. generic regex over QName, label, and documentation;
5. unmapped.

Record the mapping rule used.

Do not map a broad term such as cost before testing more specific concepts such as amortized cost.

### 11.4 SOI role discovery

Evaluate role URI and role definition. Candidate role patterns include:

- Schedule of Investments;
- Consolidated Schedule of Investments;
- Investment Portfolio;
- Investments Schedule.

Collect concepts reachable through presentation relationships for candidate roles.

### 11.5 Holding-axis discovery

For each dimension axis at the report date, calculate:

- distinct member count;
- fact count;
- context count;
- proportion of facts mapped to holding fields;
- presence in SOI roles;
- positive name indicators;
- negative/classification indicators;
- template match;
- example member labels.

Positive indicators include:

- investment identifier;
- portfolio company;
- issuer;
- borrower;
- security;
- instrument;
- loan identifier.

Negative indicators include:

- fair-value hierarchy;
- level 1, 2, or 3;
- industry;
- sector;
- geography;
- country;
- affiliate status;
- controlled status;
- currency;
- investment type.

Template-specified axes override heuristic selection.

### 11.6 Holding grouping

Group XBRL facts by the selected holding-axis member combination.

Preserve the complete context dimensions separately. This prevents classification dimensions from incorrectly creating separate holdings while retaining lineage.

### 11.7 Duplicate fact selection

Rank fact candidates using:

1. exact company-template concept preference;
2. membership in an SOI presentation role;
3. non-nil status;
4. expected unit;
5. expected period;
6. taxonomy preference;
7. precision/decimals;
8. stable deterministic tiebreaker.

If competing candidates have materially different values:

- select only according to deterministic precedence;
- store all alternatives in field_conflicts;
- reduce confidence;
- add a review flag.
## 12. HTML extraction requirements

### 12.1 Parsing

Parse the primary filing as rendered HTML even if it contains XHTML or Inline XBRL.

### 12.2 Candidate table scoring

Score each table using:

- nearby SOI heading;
- fair-value header;
- cost or amortized-cost header;
- principal or par header;
- maturity header;
- issuer/portfolio-company header;
- exclusion phrases;
- table position;
- template-specific requirements.

Record every scored candidate, including rejected tables and rejection reasons.

### 12.3 Header reconstruction

Support:

- merged cells;
- multi-row headers;
- repeated column names;
- blank or Unnamed header levels;
- split currency-symbol columns;
- repeated headers inside table bodies.

Flatten header levels while preserving meaningful order.

### 12.4 Scale detection

Detect whether monetary values are reported:

- in units;
- in thousands;
- in millions.

Priority:

1. template-fixed rule;
2. table-local text;
3. nearest heading/caption;
4. document-level disclosure;
5. default to one.

Store both raw and scaled values.

### 12.5 Row classification

Classify each row as:

- holding;
- group heading;
- repeated header;
- subtotal;
- total;
- footnote;
- blank;
- unknown.

A holding row generally requires at least one numeric holding field and sufficient descriptive evidence.

### 12.6 Carry-forward behavior

Some tables omit repeated issuer or industry values. Carry-forward behavior must be template-controlled.

Do not carry a value:

- across a new section heading;
- across a total row;
- across a table boundary unless explicitly configured;
- when the template says blanks are meaningful.

### 12.7 Numeric parsing

Support:

- currency symbols;
- commas;
- parentheses as negatives;
- em/en dashes as null;
- footnote suffixes;
- percentages;
- basis points;
- values split across adjacent cells.

Retain the original cell text.

## 13. Composite field parsing

### 13.1 Purpose

Some XBRL dimension labels or HTML cells concatenate multiple logical fields. Templates may define named-capture regexes to split these values.

### 13.2 Required behavior

Given a matching composite pattern:

1. preserve the complete original value in a raw field;
2. apply named captures;
3. normalize each capture according to template rules;
4. record the parser rule ID;
5. do not overwrite a higher-quality direct XBRL or HTML field unless template precedence permits it;
6. flag conflicting direct and parsed values.

### 13.3 Interest-rate parsing

Support examples including:

```text
S+450
S + 450, 0.50% Floor
SOFR + 4.50%
L+600
Prime + 2.25%
S+400 cash / 2.00% PIK
```

Canonical storage:

```text
reference_index = "SOFR"
spread_bps = 450
spread = 0.045
rate_floor = 0.005
```

Display formatting such as 4.50% belongs in the presentation layer. Numeric output should use decimals and/or basis points.

Reference-index aliases must be company/template-specific where ambiguous. Do not globally assume every S means SOFR without a rule or supporting context.

### 13.4 Industry-prefix parsing

Only split a leading industry from an issuer when:

- it matches a configured industry exactly; or
- the industry is independently available in the same row/context.

Do not blindly treat the first word as an industry.

### 13.5 Date parsing

Normalize recognized dates to ISO YYYY-MM-DD.

Invalid or ambiguous dates must remain null and generate a parser diagnostic.

## 14. XBRL and HTML matching

### 14.1 Objective

Use HTML to enrich XBRL-derived records and to provide fallback records where XBRL is incomplete.

### 14.2 Match features

Candidate features include:

- fair value;
- cost;
- amortized cost;
- principal;
- face amount;
- shares;
- issuer;
- description;
- maturity date;
- table sequence.

### 14.3 Matching rules

- Use one-to-one matching.
- Require a minimum score.
- Require the best candidate to be uniquely better than alternatives.
- Do not match solely because one weak text field overlaps.
- Record score and feature contributions.
- Leave ambiguous matches unresolved.
- Append unmatched HTML rows only when enabled.
- Assign lower confidence to unmatched HTML rows.

### 14.4 Match output

For every XBRL row, record:

- matched HTML row ID;
- best score;
- second-best score;
- score margin;
- matched features;
- conflicting fields;
- enrichment fields used.

## 15. Deduplication and identity

### 15.1 Holding ID

Generate a deterministic hash from:

- CIK;
- accession;
- selected holding-axis member key, if available;
- otherwise table and row identity.

Do not use normalized issuer plus fair value alone, because two legitimate instruments may share those values.

### 15.2 Deduplication

Deduplicate only when source identities or strong field combinations indicate the same holding.

Do not collapse separate facilities merely because they have the same:

- issuer;
- maturity date;
- fair value;
- principal amount.

Description, rate, lien, facility type, and source identity must also be considered.

## 16. Validation

### 16.1 Total reconciliation

For each filing, calculate detail sums for:

- fair value;
- cost;
- amortized cost.

Select reported totals from:

1. template-specified total concepts;
2. SOI-role XBRL facts without holding axes;
3. template-identified HTML total rows;
4. generic HTML total candidates.

Store all candidates, not just the selected total.

### 16.2 Reconciliation status

Default tolerance:

max(absolute tolerance, abs(reported total) × relative tolerance)

Recommended defaults:

- absolute tolerance: 1.0 in scaled filing currency;
- relative tolerance: 0.5%.

Statuses:

- pass
- fail
- not_tested
- no_holdings
- ambiguous_total
- review

### 16.3 Additional validation rules

Flag:

- holding rows with no issuer and no description;
- duplicate holding IDs;
- negative fair values unless explicitly allowed;
- maturity date before issue date;
- spread outside configurable bounds;
- percentage values with probable unit errors;
- fair value much larger than principal without explanation;
- unexpected currency;
- excessive unmatched HTML rows;
- excessive XBRL conflicts;
- selected holding axis with very few members;
- material deterioration from the previous run.

Reconciliation is necessary but not sufficient. A wrong set of rows can still reconcile.

## 17. Confidence model

Confidence must be explainable, not merely a number.

Suggested components:

| Evidence | Adjustment |
| --- | --- |
| Direct template-mapped XBRL fact | +0.20 |
| Member from configured holding axis | +0.15 |
| Concept in SOI role | +0.10 |
| Unique XBRL/HTML match | +0.10 |
| Issuer present | +0.05 |
| Description present | +0.05 |
| Monetary value present | +0.10 |
| Composite parser match | +0.05 |
| Conflicting facts | -0.20 |
| Ambiguous HTML match | -0.15 |
| Reviewed override | no automatic increase; mark separately |
| Unmatched HTML-only row | cap at 0.60 |

Store a list of confidence factors for each row.

## 18. Diagnostics and output artifacts

Every run must produce:

```text
run_manifest.json
all_filings.parquet
latest_filings.parquet
holdings.parquet
holdings.csv
long_xbrl_facts.parquet
filing_diagnostics.csv
axis_diagnostics.csv
html_table_diagnostics.csv
matching_diagnostics.csv
validation.csv
template_usage.csv
review_queue.csv
output.xlsx
```

### 18.1 Run manifest

Include:

- run ID;
- start and end timestamps;
- engine version and Git commit;
- configuration checksum;
- template checksums;
- accession checksums;
- Python/package versions;
- selected filings;
- output row counts;
- exceptions.

### 18.2 Review queue

Include rows or filings with:

- failed reconciliation;
- ambiguous matching;
- field conflicts;
- low confidence;
- unknown composite format;
- no selected holding axis;
- no holdings;
- unexpected row-count movement;
- template mismatch.

## 19. Evaluation framework

The agent must not evaluate quality only by visual inspection or total reconciliation.

### 19.1 Golden dataset

Create a reviewed dataset across:

- multiple BDCs;
- multiple reporting periods per BDC;
- old and new filing layouts;
- XBRL-rich filings;
- HTML-heavy filings;
- floating-rate and fixed-rate instruments;
- rows with repeated issuers;
- rows with missing fields;
- affiliated and controlled investments;
- total and subtotal sections.

Each golden holding should contain:

- accession;
- stable annotation ID;
- source table/page/context;
- reviewed canonical values;
- explicit nulls;
- reviewer;
- review date;
- comments.

### 19.2 Train/development/holdout split

Use:

- development filings for template construction;
- regression filings for routine testing;
- holdout filings for unbiased evaluation.

Do not tune templates against holdout expected outputs.

### 19.3 Row alignment for evaluation

Align actual and expected rows using a weighted bipartite match based on:

- issuer;
- description;
- maturity date;
- principal;
- cost;
- fair value;
- source identity where available.

Report unresolved and ambiguous alignments separately.

### 19.4 Metrics

At minimum, calculate:

Row metrics

- row precision;
- row recall;
- row F1;
- duplicate-row rate;
- spurious-total-row rate.

Field metrics

For each canonical field:

- populated precision;
- populated recall;
- exact-match accuracy;
- normalized-text accuracy;
- numeric accuracy within tolerance;
- null accuracy.

Filing metrics

- fair-value reconciliation rate;
- cost reconciliation rate;
- percentage of filings with holdings;
- percentage of filings requiring review;
- unmatched HTML rate;
- field-conflict rate.

Template metrics

- filings using generic template;
- filings using company template;
- unknown-format count;
- regressions by template ID.
### 19.5 Numeric tolerances

Suggested evaluation tolerances:

- monetary values: max of 1 unit or 0.01%;
- percentages: 0.0001 absolute decimal;
- spread basis points: 0.5 basis points;
- dates: exact;
- normalized text: case- and punctuation-normalized exact match, plus a separate raw exact metric.

### 19.6 Acceptance thresholds

Initial production target:

| Metric | Minimum |
| --- | --- |
| Holding row precision | 98% |
| Holding row recall | 97% |
| Fair-value field accuracy | 99% |
| Cost/amortized-cost accuracy | 98% |
| Issuer normalized accuracy | 97% |
| Description normalized accuracy | 95% |
| Maturity-date accuracy | 98% |
| Fair-value reconciliation pass rate | 95% |
| Duplicate-row rate | <0.5% |
| Unexplained runtime failures | 0 |

Company templates should be held to these thresholds individually where enough golden observations exist.

No change may materially reduce aggregate or company-level regression performance without an approved exception.

## 20. Iterative refinement protocol

The coding agent must follow this cycle.

### Step 1: Establish a baseline

1. Implement the generic engine.
2. Run it on the development corpus.
3. Save all output and diagnostics.
4. Evaluate against the golden dataset.
5. Produce a baseline metrics report.

### Step 2: Classify failures

Assign every material failure to one category:

- filing discovery;
- package download;
- Arelle loading;
- concept mapping;
- role discovery;
- holding-axis selection;
- context grouping;
- duplicate fact selection;
- HTML table detection;
- header reconstruction;
- scale detection;
- row classification;
- carry-forward logic;
- composite parsing;
- XBRL/HTML matching;
- normalization;
- deduplication;
- total selection;
- golden-data issue.

Do not make a code change until the failure category is identified.

### Step 3: Choose the narrowest remedy

Use this precedence:

1. fix a genuine generic-engine bug;
2. improve generic logic when supported by multiple companies;
3. add an effective-dated company-template rule;
4. add a reviewed override only when extraction rules cannot represent the fact.

Do not add if cik == ... logic to general application code unless the specification explicitly requires it.

### Step 4: Add a failing test first

Before implementing a fix:

- add a unit or regression test reproducing the failure;
- confirm that it fails;
- implement the change;
- confirm that it passes.

### Step 5: Rerun the affected filing

Compare:

- rows added and removed;
- field changes;
- source lineage changes;
- total reconciliation;
- confidence;
- review flags.

### Step 6: Run the complete regression suite

A company-specific fix must not damage:

- other periods for the same company;
- other companies;
- generic extraction;
- total reconciliation;
- output schemas.

### Step 7: Evaluate holdout data periodically

After a meaningful batch of changes, evaluate against holdout filings without altering their annotations.

### Step 8: Record the result

Every refinement must document:

- failure observed;
- root cause;
- files changed;
- template/rule IDs changed;
- before/after metrics;
- regression result;
- remaining limitations.

## 21. Agent operating instructions

The implementation agent should maintain an iteration log such as:

```markdown
## Iteration 014

### Filing
CIK: 1837532
Accession: 0000000000-26-000001

### Failure
Composite XBRL member label remained entirely in issuer.

### Root cause
The current template did not define the issuer's member-label layout.

### Remedy
Added effective-dated composite parser rule:
`member-label-layout-v2`.

### Before
- issuer accuracy: 42%
- maturity accuracy: 0%
- spread accuracy: 0%

### After
- issuer accuracy: 98%
- maturity accuracy: 100%
- spread accuracy: 100%
### Regression
1,284 tests passed; no metric deterioration.

### Limitations
Issue date remains null because it is not disclosed in the parsed source.
```

The agent must:

- preserve previous run artifacts;
- never modify expected golden values merely to make a test pass without reviewer approval;
- identify assumptions explicitly;
- keep parsing rules narrow enough to avoid false positives;
- attach rule IDs and provenance to transformed values;
- stop and request review when a source value is ambiguous.

## 22. Required tests

### 22.1 Unit tests

At minimum:

- CIK normalization;
- SEC URL construction;
- instance-document detection;
- semantic XBRL date handling;
- QName extraction;
- concept mapping precedence;
- context dimension serialization;
- holding-axis scoring;
- duplicate fact selection;
- HTML monetary parsing;
- percentage parsing;
- scale detection;
- multi-row header flattening;
- total-row detection;
- issuer carry-forward;
- industry-heading handling;
- composite issuer parsing;
- reference-index aliasing;
- spread conversion;
- date normalization;
- XBRL/HTML match scoring;
- ambiguous match rejection;
- reconciliation status;
- deterministic holding ID generation;
- template overlap rejection.

### 22.2 Composite parser example

Input:

```text
Software Redwood Runway Bidco, LLC Investment Type First Lien
Secured Debt - Term Loan Interest Rate S+450, 0.50% Floor
Maturity Date 12/17/2031
```

Expected direct-source output:

```json
{
    "issuer": "Redwood Runway Bidco LLC",
    "description": "First Lien Secured Debt - Term Loan",
    "industry": "Software",
    "reference_index": "SOFR",
    "spread": 0.045,
    "spread_bps": 450,
    "rate_floor": 0.005,
    "issue_date": null,
    "maturity_date": "2031-12-17"
}
```

A separate test may confirm that a reviewed override changes selected fields, but only when its exact accession/report-date criteria and provenance are present.

### 22.3 Integration tests

- Retrieve and cache a known accession.
- Load an extracted XBRL instance with Arelle.
- Fall back to Inline XBRL when no extracted instance exists.
- Extract at least one known SOI table.
- Produce holdings and validation output.
- Rerun entirely from cache.
- Verify deterministic output checksums after excluding run timestamps.

### 22.4 Regression tests

For every supported company template, include at least:

- one filing used to create the template;
- one different-period filing;
- one filing near a template effective-date boundary where possible.

## 23. Error handling

A failure in one extraction method must not unnecessarily stop the other method.

- XBRL failure → continue with HTML.
- HTML failure → retain XBRL results.
- Both fail → emit filing diagnostic and continue with other companies.
- Template validation failure → fail before extraction begins.
- Output-writing failure → retain intermediate Parquet/JSON artifacts where possible.

Do not use broad exception handling without logging:

- exception type;
- message;
- filing identity;
- extraction phase;
- stack trace in the detailed log.

## 24. Performance expectations

For a universe of approximately 25–30 BDCs:

- reuse cached accession files;
- load each Arelle model once per run;
- avoid repeatedly parsing the same HTML;
- avoid quadratic row matching when tables are large by pre-indexing monetary candidates;
- write long facts to Parquet before Excel;
- make Excel long-fact output optional.

Performance optimizations must not weaken deterministic matching or lineage.

## 25. Definition of done

The engine is complete when:

1. All CLI commands are implemented.
2. Templates are validated against a formal schema.
3. Every configured BDC can be processed without terminating the universe run.
4. XBRL and HTML extraction both have independent fallback behavior.
5. Composite SOI labels can be split through template-defined rules.
6. Output conforms to the canonical schema.
7. Every normalized field has lineage.
8. Monetary totals are reconciled or clearly marked as unreconciled.
9. Golden-dataset evaluation is automated.
10. Acceptance thresholds are met.
11. The complete unit, integration, and regression suite passes.
12. Company-specific behavior is stored in effective-dated templates rather than scattered through application code.
13. Overrides are exact, effective-dated, reviewed, and provenance-backed.
14. A run manifest makes every result reproducible.
15. Remaining unsupported formats appear in a review queue rather than being silently misparsed.

## 26. Recommended implementation sequence

The agent should implement in this order:

1. Repository, configuration, and typed models.
2. SEC client and filing discovery.
3. Filing package caching and instance discovery.
4. Arelle model loading and complete fact inventory.
5. Concept and presentation-role mapping.
6. Holding-axis discovery.
7. XBRL holding construction.
8. HTML table discovery and row extraction.
9. Composite field parser.
10. XBRL/HTML matching.
11. Normalization and field-level lineage.
12. Reconciliation and review flags.
13. Parquet, CSV, JSON, and Excel output.
14. Template schema and company-specific templates.
15. Golden-data evaluator.
16. Run comparison tooling.
17. Iterative company-by-company refinement.
18. Holdout evaluation and final regression gate.

The first implementation should favor diagnostic completeness. Once behavior is verified, code may be optimized without changing the output contract.
