# Defect candidates noted during M02 reviews, and where each ended up

Kept separate from the AI-generated tests on purpose: the test generator was run blind (it could not
read `evidence/`), so anything it found was found on its own.

| Candidate (found by human/assistant review in M02) | Outcome in M03 |
|---|---|
| R-10 lodging split can go negative: 0.03 USD over 5 nights → last night −0.01 | **Found independently by the test generator**, which also showed the real impact (another line paid over the cap). Fixed: [defect.md](defect.md) |
| R-10 lodging split: 1.00 USD over 6 nights gives the last night 0.15, less than the others | Resolved by the same fix: shares now round down, so the last night gets 0.20 (the leftover), never less |
| `employee_id` not trimmed: `' E-001 '` bypasses cross-claim duplicate detection | Confirmed in the AI review (S4). Accepted, fixed in M06 |
| amount `'1e2'` accepted and stored/echoed as `'1E+2'` | Generator tested it (`1E+2` = `100.00` for duplicates); AI review P2. Accepted, fixed in M06 |
| Seed claim 3 hand-worked excess said 6.20 (correct 6.00) | Already fixed in M02 (`7fa5aed`); lesson: tests only check what they assert |
