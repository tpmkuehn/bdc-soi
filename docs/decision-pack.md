# Decision pack: interpretations awaiting the project owner's judgment

Generated 2026-10-06 from the final runs (`output/universe_s3_run17` latest periods, `output/s3i_final_<cik>_<accession>`
prior periods; row ids are stable holding ids). Q5 is affected by D44 (group-level identity): description-less groups
remain unpaired; the proposed representation for them is the same group-level record, which still needs your approval.
Every item below is **not resolved**: the engine applies a documented current treatment, but that treatment depends on
the approval requested here. Implementation fixes (engine behaviour) are marked **[implementation]**; accounting or scope
interpretations are marked **[interpretation]**. SEC URLs point to the primary 10-Q document; locate HTML rows with the
`table_<n>:t<n>r<m>` ids in `html_rows.csv` (row text reproduced) and XBRL facts by fact/context id in
`long_xbrl_facts.parquet` of the run directory.

Summary of what must be answered before further changes:

| # | Question | Kind | Companies | Rows affected | Fair value at stake |
| --- | --- | --- | --- | --- | --- |
| Q1 | Keep the `CO Acquisition Vehicle LLC` one-part member (affiliate roll-forward ending balance of a term loan exported under its schedule member) excluded? | interpretation | Chicago Atlantic | 1 per period | 17.4M (prior), 0 (latest) |
| Q2 | Exclude one-part identifier members that aggregate multi-tranche issuers (affiliate schedule / parent nodes)? | interpretation | Golub Capital BDC | 14 (latest), 13 (prior) | 297.3M / 295.8M |
| Q3 | Accept the documented USD presentation (par-column currency footnote, accounting-policy note, USD total) over CAD/GBP/EUR fair-value units? | interpretation | Apollo, Goldman Sachs BDC, Stellus | Apollo 8 / 8 / 16; GSBD 5 / 3; Stellus 3 | Apollo 407.8M / 483.0M / 841.6M; GSBD 15.4M / 3.8M; Stellus 4.0M |
| Q4 | Treat `Nakdcom One World AB | Hybrid` as a holding from the HTML schedule although its XBRL facts are affiliate roll-forward concepts? | interpretation + implementation | TriplePoint | 1 HTML row + 1 excluded XBRL member | 14.7M |
| Q5 | Record description-less equal-valued groups at group level (D44) instead of leaving both sides unmatched? No row-level pairing is proposed. | implementation (needs approval) | PIMCO, West Bay | PIMCO 8+8 / 10+10; West Bay 2+2 both periods | PIMCO 2.4M / 2.0M; West Bay 3.9M / 3.9M |
| Q6 | Exclude duplicate typed members that differ only by punctuation and carry fair value only; re-admit affiliate-schedule members that appear in the HTML schedule? | implementation (needs approval) | Barings (prior period; latest partly) | 6 duplicate members; 4 JV members per period | 77.8M duplicates; 39.0M / 36.0M JV rows |

---

## Q1. Chicago Atlantic BDC (CIK 1843162): `CO Acquisition Vehicle LLC` one-part member [interpretation]

**Decision required.** Confirm that the one-part identifier member `CO Acquisition Vehicle LLC` is the affiliate
roll-forward's **ending fair value balance** of a position that the schedule already exports under its own schedule
member, so that it stays an excluded candidate (not a second holding). The earlier description of this member as a
"joint-venture interest" was wrong and is withdrawn: the filing describes a **term loan** to a borrower that became a
non-controlled affiliate.

**Exact concept and period semantics of 17,370,481 (prior period 0001193125-26-222738, report date 2026-03-31,
https://www.sec.gov/Archives/edgar/data/1843162/000119312526222738/lien-20260331.htm).**
- Fact F_c6981e7b-5f10-44f7-b1fe-a931faf74745: concept `us-gaap:InvestmentOwnedAtFairValue`, **instant** context
  C_b6dba3c9-309d-4cd8-ad8b-fd907ba45094 (period end 2026-03-31), unit USD, value 17,370,481, typed member
  `CO Acquisition Vehicle LLC` with `InvestmentIssuerAffiliationExtensibleEnumeration` =
  `InvestmentAffiliatedIssuerNoncontrolledMember` (F_edb2e722-7aa5-452a-84ee-550496ed94b1). It is an ending balance,
  not a movement.
- The movements sit on the same member in a **duration** context (C_c496fcaf-5689-447c-bdf1-08b6ee2e4519,
  2026-01-01 to 2026-03-31): `InvestmentsInAndAdvancesToAffiliatesAtFairValueGrossAdditions` 16,310,311
  (F_1bbe9d37-ee12-4578-b296-7b5f5a535e9f), `DebtAndEquitySecuritiesUnrealizedGainLoss` 1,060,170
  (F_26befde6-1b06-4c9e-930f-35b90438553d), `GrossInvestmentIncomeOperating` 825,144. 16,310,311 + 1,060,170 =
  17,370,481: the fact is the roll-forward's ending column.
- The schedule itself tags the same position under the schedule member `US Corporate Debt First Lien Senior Secured
  U.S. Debt Cannabis CO Acquisition Vehicle, LLC Facility Type Term Loan All in Rate 20.00% ... Initial Acquisition Date
  9/30/2025 Maturity 12/31/2029` (context C_27737b6a-1dd8-4c44-b0cb-f091159227a2, in the ScheduleOfInvestments role):
  `InvestmentOwnedAtFairValue` 17,370,000 (F_cd43aedb-f6c4-4f5f-bbca-a21a1c508532), `InvestmentOwnedAtCost`
  16,310,000, principal 16,310,000, percent of net assets 5.7%. That member is exported as a holding and matches the HTML
  schedule row.

**Source excerpts.**
- HTML schedule (in thousands): "CO Acquisition Vehicle LLC Term Loan 20.00 % F 0.00 % 20.00 % 0.00 % 9/30/2025
  12/31/2029 16,310 16,310 17,370 5.7 % (9)(20)".
- Affiliate roll-forward table: "For the Three months ended March 31, 2026 Non-controlled affiliates CO Acquisition
  Vehicle LLC $ - $ 16,310,311 $ - $ - $ 1,060,170 $ 17,370,481 $ 825,144 Total non-controlled affiliates ...".
- Footnote: "On February 26, 2026 the borrower, CO Acquisition Vehicle LLC ("COAV"), was acquired by an affiliate of the
  Company as part of an asset acquisition of cannabis assets. An officer and board member of the acquirer's parent
  company is also a beneficial owner of the Adviser ...".
- Latest period 0001193125-26-347342 (2026-06-30): the one-part member carries `InvestmentOwnedAtFairValue` 0
  (F_d93b973a-900c-41af-995c-dbd7cfd9ceaf) and the roll-forward shows gross additions 17,022,084 and gross reductions
  (17,022,084) for the six months: the position left the affiliate category; the schedule member for the term loan
  is not present at 2026-06-30.

**Current treatment.** The one-part member is an excluded candidate (rule `generic:affiliate_schedule_member`, D32)
because its only report-date fact is the roll-forward ending balance and the position is exported under the
schedule member. The scoped sum equals the reported total (prior period difference 0.0).
**Alternative.** Export the one-part member as a second holding: +17,370,481 and a duplicate of the term loan.
**Recommendation.** Keep excluded; record it as a duplicate representation (roll-forward ending balance) rather
than as a "JV member". Uncertainty: low; the identity of the two representations rests on the equal values
(17,370,481 vs the rounded 17,370,000), the same issuer label and the footnote.

## Q2. Golub Capital BDC (CIK 1476765): one-part identifier members [interpretation]

**Decision required.** Confirm that identifier members carrying only an issuer name (no tranche) are aggregates of the
issuer's tranches that are exported separately, and remain excluded candidates.

**Filings and rows.**
- Latest: 0001476765-26-000048, 2026-06-30, https://www.sec.gov/Archives/edgar/data/1476765/000147676526000048/gbdc-20260630.htm. 11 `affiliate_schedule_member` candidates (fair value 250.7M; e.g. `Chestnut Optical Midco, Inc.` f-10743 / c-1984 107,169,000; `SPF Borrower LLC` f-10799 / c-2008 35,169,000; `Fleet Farm Group LLC` f-10757 / c-1990 31,129,000) and 3 `parent_member_sum_of_children` candidates (46.6M; `Bayside Opco, LLC` f-10729 / c-1978 34,488,000; `Elite Dental Partners LLC` f-10750 / c-1987 9,952,000; `Benetech, Inc.` f-10736 / c-1981 2,126,000).
- Prior: 0001476765-26-000033, 2026-03-31, https://www.sec.gov/Archives/edgar/data/1476765/000147676526000033/gbdc-20260331.htm. 8 affiliate-schedule (195.9M) and 5 parent-node (99.8M) candidates (full list in `excluded_candidates.csv`).

**Source evidence.** Each one-part member carries roll-forward concepts only (no cost/principal/maturity facts) or equals
the sum of >= 2 tranche members of the same issuer that are exported as holdings and that match HTML schedule rows. With
them excluded the complete exported sum equals the reported `InvestmentOwnedAtFairValue` (f-10701 / c-9) within -8,000
(latest) and -12,000 (prior); including them would overstate fair value by 297.3M / 295.8M.

**Current treatment.** Excluded candidates (D32). **Alternative.** Export them as holdings (double counting) or as a
separate "affiliate aggregate" output. **Recommendation.** Keep excluded; optionally emit them in a separate
`affiliate_aggregates` artifact. Uncertainty: low for the sum-of-children rule; moderate for the affiliate-schedule rule,
which relies on the absence of SOI concepts (see Q4/Q6 for its false positives).

## Q3. Apollo Debt Solutions BDC (CIK 1837532): reporting currency of non-USD-tagged facts [interpretation]

**Decision required.** Approve the rule (D33) that a fair-value fact tagged in CAD/GBP/EUR is reported in USD when the
HTML schedule column discloses `$` at or above the row and the HTML cell equals the fact numerically; the XBRL unit,
fact id and value are preserved in a `reporting_currency` conflict.

**Filings and rows.**
- Latest: 0001193125-26-341358, 2026-06-30, https://www.sec.gov/Archives/edgar/data/1837532/000119312526341358/ck0001837532-20260630.htm. 8 rows, fair value 407,788,000: Aryeh Bidco Investment Ltd (3 rows, CAD: 0b620772855a4d597a04937c5d831dcc t32r22 1,677,000; 1f0b80b758293c0e853f92c54f44667d t32r21 69,356,000; f331eb486eadec913187e1a8ae085aeb t32r23 980,000), Pathfinder Bidco Limited (GBP, 537c984933b0fcabf593fbf3bd17f784 t28r3 81,244,000), Investment Company 24 Bidco Limited (GBP, 5612de235f9d327322eb5355d4a404c1 t42r3 8,489,000), Sports Invest Holdings Ltd (GBP, 89501a7cfe48a4e39195e411f59213e4 t37r28 71,189,000), Nottingham Forest Football Club Limited (GBP, f20594f1cca4f151c9271b53447ecd50 t37r10 30,868,000), Joker Holdco 3 S.a r.l (EUR, fca049725f74e5b23554ed4e047d87a2 t37r8 143,985,000).
- Prior period 0001193125-26-215667 (2026-03-31), https://www.sec.gov/Archives/edgar/data/1837532/000119312526215667/ck0001837532-20260331.htm:
  8 rows, 483,008,000 (XBRL units GBP 3, EUR 2, AUD 1 and two filer unit errors AFN 1 and RSD 1; ids in `holdings.csv`).
- Historical period 0000950170-25-105984 (2025-06-30), https://www.sec.gov/Archives/edgar/data/1837532/000095017025105984/ck0001837532-20250630.htm:
  16 rows, 841,561,000 (EUR 5 rows 318.7M, GBP 11 rows 522.9M).
- The same question applies to Goldman Sachs BDC (CIK 1572694: 5 rows / 15,371,000 at 2026-06-30, 3 rows / 3,771,000 at
  2026-03-31) and Stellus (CIK 1901037: 3 EUR-tagged Monitorus rows / 4,033,010 at 2026-06-30); their templates record the
  same kind of evidence (below).

**Source evidence (USD disclosure beyond the `$` symbol).**
- Schedule footnote (3) (ck0001837532-20260630.htm, Consolidated Schedule of Investments notes): "Par amount is
  denominated in USD unless otherwise noted, British Pound ("£"), Australian Dollar ("A$"), Canadian Dollar ("C$"),
  European Euro ("€"), ..." The currency marker is defined for the **par amount** column only; the row prints `C$ 99,924`
  in the par column and `71,286` / `69,356` in the cost and fair-value columns under the `$` column header.
- Note 2 (Significant Accounting Policies, "Foreign Currency Translations"): "The accounting records of the Company are
  maintained in U.S. dollars. All assets and liabilities denominated in foreign currencies are translated into U.S.
  dollars based on the foreign exchange rate on the date of valuation."
- Schedule header: "CONSOLIDATED SCHEDULE OF INVESTMENTS (Unaudited) June 30, 2026 (In thousands, except share data)";
  the schedule's USD total row and the undimensioned `InvestmentOwnedAtFairValue` (F_ad49fec7-28eb-46b0-9c15-eb0e38cb8d51,
  unit USD, 25,367,235,000) include these rows at their printed values.
- Contrary evidence: the filer tagged the fair-value facts with CAD/GBP/EUR units; the principal facts are correctly
  in the facility currency. The XBRL unit therefore conflicts with the filer's own schedule presentation and Note 2.
- Every period: footnote (3) and Note 2 are present verbatim in 0001193125-26-215667 and 0000950170-25-105984 as well
  (the 2026-03-31 footnote adds Swiss Franc; the 2025-06-30 footnote uses "Korean Won" and "kr"); the schedule header
  "(In thousands, except share data)" appears in all three.
- Goldman Sachs BDC (0001193125-26-338331, 0001193125-26-212431): schedule footnote "Par amount is denominated in U.S.
  Dollars ("$" or "USD") unless otherwise noted, Euros ("EUR"), Great British Pounds ("GBP"), Norwegian Kroner ("NOK"),
  Canadian Dollars ("CAD") or Australian Dollars ("AUD")." and Note 2 "The Company's functional currency is USD and these
  consolidated financial statements have been prepared in that currency."
- Stellus (0001104659-26-094771): "Par amount is denominated in U.S. Dollars ("$") unless otherwise noted in Euros ("€")."
  and "The accounting records of the Company are maintained in U.S. dollars."; rows t15r48-t15r50 print `€1,353,050`
  in the par column and USD cost / fair value.
- D33 (revised): the override now applies only where the template records this documented evidence
  (`validation.reporting_currency_evidence`, citing the accession); a `$` column symbol alone leaves the XBRL unit in
  place with the flag `no_documented_reporting_currency_evidence`.

Example row 0b620772855a4d597a04937c5d831dcc: XBRL `InvestmentOwnedAtFairValue` fact
F_625e5d2e-4092-4b5d-8a29-82d2f2a012ff, unit CAD, value 1,677,000 (context C_aa4cfe18-5dd5-40df-af6e-41cdffeeeb96);
HTML table_32 row t32r22 shows 1,677 in the fair-value column whose header cell carries `$` (in thousands). The
`principal_amount` fact of the same row is in CAD (the schedule's "Par Amount" column shows the facility currency). The
schedule total `InvestmentOwnedAtFairValue` (F_ad49fec7-28eb-46b0-9c15-eb0e38cb8d51, USD 25,367,235,000) reconciles with
these rows counted at face value in USD (difference -721,000, tolerance 126.8M).

**Current treatment.** reporting_currency = USD with the conflict and lineage preserved; principal stays in the facility
currency. **Alternatives.** (a) Keep the XBRL unit as the reporting currency (rows become non-USD, the USD reconciliation
would exclude 407.8M / 841.6M and fail); (b) flag only, no currency decision. **Recommendation.** Approve the current
rule. Uncertainty: the HTML `$` is column-level evidence; the filer's own tagging says CAD/GBP/EUR. Numerical equality is
not treated as evidence on its own (rows without a `$` symbol keep their XBRL unit and are flagged
`no_html_currency_evidence`; none in these two periods).

## Q4. TriplePoint Venture Growth (CIK 1580345): `Nakdcom One World AB | Hybrid` [interpretation + implementation]

**Decision required.** Decide whether the Hybrid position is a holding of the schedule (it is printed in the HTML
schedule inside the total) even though its only XBRL facts are affiliate roll-forward concepts, and whether the excluded
XBRL member should be re-admitted and matched to the HTML row.

**Filing and rows.** 0001580345-26-000025, 2026-06-30, https://www.sec.gov/Archives/edgar/data/1580345/000158034526000025/tpvg-20260630.htm.
HTML-only holding 1b86856e14008eb916763c221ca0d384, table_23 row t23r15: `Hybrid(2)(16) 12/30/2025 15,191 14,731`
(issuer carried from the row above, `Nakdcom One World AB(1)(3)(15) Common Stock(2)`). Excluded XBRL candidate
`typed:Nakdcom One World AB | Hybrid | Equity Investments`, facts f-1726, f-1727, f-1971, context c-443, fair value
14,731,000, cost 15,191,000, rule `generic:affiliate_schedule_member`. The prior period (0001580345-26-000021) tags the
same position with SOI concepts and it matches normally (4d0f09a2368cdf2240f540677e919ce6, fair value 14,856,000).

**Source evidence.** Reported total 780,742,000 (f-1932 / c-7) = matched rows 766,011,000 + this HTML row 14,731,000
(difference 0). The money-market row after the grand total (13,582,000) is an after-total row, not in scope.

**Current treatment.** HTML-only holding in the canonical output (flag `unmatched_html_row`); XBRL member kept as an
excluded candidate with its facts. **Alternatives.** (a) Re-admit the XBRL member when an HTML schedule row matches it
(gives one hybrid row with XBRL lineage); (b) drop the HTML row (reconciliation fails by 14.7M). **Recommendation.**
(a), as an implementation change after your approval; it also covers Q6's JV members. Uncertainty: low on the holding's
existence; the open question is the provenance you want (HTML-only vs hybrid with roll-forward facts).

## Q5. PIMCO Capital Solutions (CIK 1905824) and West Bay BDC (CIK 2020354): equal-valued groups without descriptions [implementation, needs approval]

**Decision required.** Decide whether equal-valued, same-issuer groups whose rows carry no distinguishing description on
one side may be recorded at **group level** (D44: `identity_resolution = group`, one HTML row consumed per XBRL row,
lineage pointing at the whole group, flagged `group_level_identity`), or whether both sides stay unmatched (double
counted in the complete sum, scoped reconciliation fails). No row-level pairing by document order is proposed.

**PIMCO.** Latest 0001193125-26-344935, 2026-06-30, https://www.sec.gov/Archives/edgar/data/1905824/000119312526344935/d131047d10q.htm:
8 XBRL-only and 8 HTML-only rows, 2,388,000 each side: `U.S. Treasury Bill` 2 x 99,000 and 4 x 100,000 (HTML table_13
rows t13r39, r41, r42, r45, r49, r51; XBRL ids 228ce6b676724d5ec877117f1011e528, 4a643a8a8aace4f3eea182304c7691ba,
7c02ce9135f4d3693115c2a1cb2bf928, 87bfee50d4c88250c28bb5d9f1075675, f6489a0a5cea301638da6b8d72063677,
f7cad114b585a0d0f1fe1c596739cc97) and `Federal Home Loan Bank Discount Note` 2 x 895,000 (t13r32, t13r33;
57c95eb3507b5de0a56ae778d065801f, c5186cff1cdc5deef398eaa6bb62a84a). Reported total 197,727,000 (ixv-35187), difference
2,388,000, tolerance 988,635. Prior 0001193125-26-224212 (2026-03-31): 10 + 10 Treasury-bill rows, 1,990,000 each side
(ids in `holdings.csv`). (`West Marine/Rising Tide Holdings Inc` 61093480031b007a93d9cca86549bb90 is matched to HTML t13r4 on cost
and issuer and is not part of this question; its XBRL share count 25,000,000 versus the HTML 25,000 is a recorded
numeric conflict.)
**West Bay.** Latest 0001193125-26-344618, 2026-06-30, https://www.sec.gov/Archives/edgar/data/2020354/000119312526344618/ck0002020354-20260630.htm:
`Airwavz Solutions Inc` two identical tranches (fair value 1,940,000, cost 1,951,000, principal 1,960,000) on both sides:
XBRL 95aa19393921a7d4cc3a16fd698b601e and d59140eb6b293397269a8abb9b9c1ad6 (description `1st Lien/Senior Secured Debt`),
HTML t11r16 and t11r17 (no description cell). Reported total 608,548,000, difference 3,880,000, tolerance 3,042,740.
Prior 0001193125-26-219870 (2026-03-31): the same two pairs (578c3d6d9d802479c9c5c9d10fa9b6be, dbade6192539cf1cbe87d30fe4c0a73d
vs 1a618c4a7edf0d46a180ac8a98842ce9, 6508c5bd93bd027bf2038e0bf72bf6bb). The after-total money-market row and a
negative-value revolver are separately flagged and not part of this question.

**Source evidence.** Both sources list the rows in the same order; no field distinguishes the members of a group (the
XBRL typed labels differ only by a sequence suffix). The existing tie-break (D35) requires pairwise description agreement,
which empty HTML descriptions cannot satisfy.

**Current treatment.** Both sides exported and flagged (`ambiguous_html_match`, `unmatched_html_row`); reconciliation
fails by exactly the group sums. **Alternatives.** (a) Record the group at group level (D44 representation:
`identity_resolution = group`, one HTML row consumed per XBRL row, lineage pointing at the whole group, no row-level
pairing claimed), which removes the double count without fabricating pairwise identity; (b) keep as is.
**Recommendation.** None is applied until you decide; the arbitrary document-order pairing recommended in the previous
version of this pack is withdrawn. The PIMCO `West Marine` row is matched and carries a separate share-scale conflict
(25,000 vs 25,000,000).

## Q6. Barings BDC (CIK 1379785), prior period 2026-03-31: duplicate typed members and JV members [implementation, needs approval]

**Decision required.** (a) Approve an exclusion rule for typed members that duplicate another member up to punctuation
and carry only a fair-value fact; (b) approve re-admitting affiliate-schedule members that are printed in the HTML
schedule (same mechanism as Q4).

**Filing.** 0001379785-26-000022, report date 2026-03-31, https://www.sec.gov/Archives/edgar/data/1379785/000137978526000022/bbdc-20260331.htm.
Fair value fails: reported 2,369,989,000 (f-4229 / c-9), difference 77,835,000, tolerance 11,849,945; cost passes.

**(a) Duplicate members, 76.5M of the 77.8M XBRL-only sum.** Six XBRL-only rows `Security Holdings B.V` (no trailing period) each carry only
`InvestmentOwnedAtFairValue` and a PIK-rate fact: 38281e22ec131d53d241afe6dd0a54c5 Bridge Loan f-4570 / c-887 6,997,000;
fbfc31d1b73ce038cf16d0d7e779f13d Revolver c-890 10,600,000; 1d889b6d8c4a3bee8e85b761b829c08c Senior Unsecured Term Loan
c-896 2,961,000; 2d141f0347e900ed0851115d0bf6474d Senior Subordinated Term Loan c-893 11,725,000;
e91b9aa185cbc1b36dfd84bca0e9cb63 Common Stock Series A c-899 469,000; 0d87881f756f36cd5cc275a69e05cd1f Common Stock
Series B c-902 43,745,000 (sum 76,497,000; the remaining 1,338,000 of the XBRL-only sum is `Biolam | First Lien Senior Secured Term Loan`, ddc69cc09f648e99a672dc3c2ae9cedb, a separate unmatched row). The same six positions exist as `Security Holdings B.V.` members with full SOI facts (cost,
rate, maturity) and match the HTML rows t33r38-t33r41, t34r7, t34r8 (e.g. 57bbc71c6e97a39becbfaaf8f5eac810 Bridge Loan
c-766, cost 6,997,000). Both members sit on `us-gaap:InvestmentIdentifierAxis` with the same report-date context period;
the FV-only member is most likely the PIK/non-accrual footnote tagging. The latest period (0001379785-26-000030) tags the
positions once and matches 4 of 6 (two remain XBRL-only for other reasons).
**(b) JV members, 39.0M HTML-only.** `Jocassee Partners LLC | 9.1% Member Interest` (f-4134..f-4136, f-4398 / c-753;
35,248,000), `Thompson Rivers LLC | 16.0% Member Interest` (c-757; 3,059,000), `Waccamaw River LLC | 20% Member Interest`
(c-759; 649,000) and `Sierra Senior Loan Strategy JV I LLC | 89.01% Member Interest` (c-755; cost 11,608,000, fair value 0)
are excluded as affiliate-schedule members although the HTML schedule prints them (table_33 rows t33r21-t33r24, inside
the schedule total); the HTML rows are exported as HTML-only holdings (d5ba89a57481d4ba90df4dfc6cc1a4a7,
b7b3183993eaba5e06abf3c4b44bb97b, 22733e989e66d1df3653f6acf11b2abe, ae200c6c1ae1502822dae37e54490e51). The latest
period shows the same pattern (0410f7b2a123c31337b659be52118367 etc.) but reconciles within tolerance.

**Current treatment.** Duplicates exported as XBRL-only rows (over-count), JV rows exported from HTML only; nothing
removed without a rule. **Alternatives.** (a) rule `duplicate_member_punctuation_variant` (exclude the FV-only twin,
keep its facts in `excluded_candidates.csv`): the prior fair-value difference would fall from 77,835,000 to 1,338,000; (b) re-admit
affiliate-schedule members with an HTML schedule row (Q4 mechanism) so the JV rows become hybrid. **Recommendation.**
Both, after approval; (a) is narrow (identical normalized key, strict fact subset, equal fair value) and would reduce the
prior-period fair-value difference from 77,835,000 to 1,338,000 (within the 11.8M tolerance). Uncertainty: the
footnote-table origin of the twin members is inferred from the fact set, not stated by the filer.

---

## Not decisions (recorded for completeness)
- Investcorp (CIK 1578348) zero-fair-value equity rows: fixed as an implementation change (D41); both periods reconcile and
  all rows match; no approval needed, but the triage batch includes the rows for verification.
- BIP Ventures (CIK 1950572) e6e2ce8c08e96f0136b09e8829ef102c: a filer XBRL inconsistency. The CareSave-labelled member
  (acquisition date 12/12/2024, context C_d2131072-b953-41bb-b362-af9892c15a44) carries the June figures that the HTML
  schedule prints for `Integrative Life Network, LLC Class A Common Stock` (t11r15: 251,152 / 522,718 / 142,480); the
  instance's own `Integrative Life Network, LLC Type Class A Common Stock Acquisition Date 12/12/2024` member holds the
  December facts (224,275 / 522,718 / 251,152 shares) and a June acquisition-date fact. The candidates are NOT merged:
  the HTML row is the canonical candidate by that sibling-member evidence (D46), the XBRL candidate is scoped
  `contradictory_identity_duplicate` outside the sums, both stay in the output and in the blocker inventory, and the
  filing's acceptance is blocked until a reviewer decides (`acceptance = blocked:unresolved_identity_contradiction`).
- Jefferies (CIK 1959604) `Chartwell Cumming Holding Corporation First Lien Revolver` (fair value -2,000) is ambiguous
  between the SOI member and its commitment member; zero sum impact, flagged.
