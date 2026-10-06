# Synthetic fixture (NOT a real SEC filing)

Everything here is hand-written to exercise the engine offline. CIK `999999999`, accession
`0009999999-25-000001`, company "Synthetic Test BDC", and every holding are invented for testing.
The schemas reuse the `http://fasb.org/us-gaap/2024` and `http://xbrl.sec.gov/dei/2024` namespace
URIs only so that the generic namespace-family mapping is exercised; they are not the FASB/SEC
taxonomies. No result on this fixture establishes real-filing accuracy.

Contents
- `package/` mimics an accession directory: `syn-20250630.htm` (primary HTML with a current-period SOI
  table, a comparative December 31, 2024 table that must be rejected, and a fair-value hierarchy table),
  `syn-20250630_htm.xml` (extracted instance), schemas and linkbases.
- `submissions/CIK0999999999.json` mimics the SEC submissions API for discovery.
