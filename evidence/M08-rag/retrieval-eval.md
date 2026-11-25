# Retrieval evaluation (16 answerable + 4 unanswerable questions, 44 passages)

| Method | Recall@5 | MRR |
|---|---|---|
| bm25 | 0.875 | 0.802 |
| vector | 1.000 | 0.969 |
| hybrid | 1.000 | 0.969 |

Rank of the first relevant passage per question (— = not in the top 5), and the best embedding similarity of any passage (the refusal signal):

| Question | Answerable | BM25 | Vector | Hybrid | Best similarity |
|---|---|---|---|---|---|
| q01 | yes | — | 1 | 1 | 0.716 |
| q02 | yes | 3 | 2 | 2 | 0.796 |
| q03 | yes | 1 | 1 | 1 | 0.767 |
| q04 | yes | 1 | 1 | 1 | 0.753 |
| q05 | yes | 1 | 1 | 1 | 0.735 |
| q06 | yes | 1 | 1 | 1 | 0.835 |
| q07 | yes | — | 1 | 1 | 0.858 |
| q08 | yes | 1 | 1 | 1 | 0.790 |
| q09 | yes | 1 | 1 | 1 | 0.761 |
| q10 | yes | 2 | 1 | 1 | 0.756 |
| q11 | yes | 1 | 1 | 1 | 0.733 |
| q12 | yes | 1 | 1 | 1 | 0.795 |
| q13 | yes | 1 | 1 | 1 | 0.771 |
| q14 | yes | 1 | 1 | 1 | 0.767 |
| q15 | yes | 1 | 1 | 1 | 0.759 |
| q16 | yes | 1 | 1 | 1 | 0.829 |
| q17 | no | n/a | n/a | n/a | 0.710 |
| q18 | no | n/a | n/a | n/a | 0.680 |
| q19 | no | n/a | n/a | n/a | 0.675 |
| q20 | no | n/a | n/a | n/a | 0.686 |

Lowest best-similarity among answerable questions: **0.716**. Highest among unanswerable: **0.710**.
