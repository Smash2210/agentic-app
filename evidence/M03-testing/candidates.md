# M03 candidates (found during M02 Phase 2 review)
- employee_id not trimmed: ' E-001 ' bypasses cross-claim duplicate detection (spec gap)
- amount '1e2' accepted and stored/echoed as '1E+2'
- R-10 lodging split: 1.00 USD over 6 nights gives last night 0.15 (< other nights)
- R-10 lodging split can go negative: 0.03 USD over 5 nights -> last night -0.01
- Seed claim 3 hand working said excess 6.20 (correct 6.00); tests only assert totals/rules so missed it; caught by the real quickstart run (7fa5aed)
