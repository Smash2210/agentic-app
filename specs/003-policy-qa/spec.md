# Feature Specification: Policy Q&A

**Feature Branch**: `003-policy-qa` | **Created**: 2026-11-25 | **Status**: Implemented (M08)

**Input**: An employee asks a question about the travel and expense policy in their own words and
gets an answer, streamed as it is written, that cites the policy sections it comes from. If the
policy does not answer the question, they are told so instead of getting a made-up answer.

## User story (P1): ask the policy

An employee sends a question. The answer streams back in pieces as it is generated, followed by
the list of policy sections it cites, then an end marker.

**Independent test**: with the model and the embeddings replaced by fakes, a question about a
covered topic streams an answer and valid citations; a question the policy does not cover gets the
refusal. Live: the questions in `data/golden/retrieval.jsonl`.

### Acceptance scenarios

1. "Can I claim the minibar from my hotel bill?" → an answer that minibar charges are not
   reimbursable, citing `POL-LODGING#4`.
2. "What is the daily limit for meals?" → 75 USD per calendar day, citing `POL-MEALS#1`.
3. "How many vacation days do I get per year?" → the refusal; no citations.
4. A cited section that was not retrieved for this question is reported as unverified, not as
   a citation.

## Requirements

- **FR-301** Corpus: every document in `data/policies/` (13 documents), split into one passage per
  numbered section, each with a stable ID `<doc_id>#<section>` (e.g. `POL-MEALS#2`), the same
  numbering the policy check already cites.
- **FR-302** Retrieval is **hybrid**: keyword ranking (BM25) and meaning ranking (embeddings),
  combined with Reciprocal Rank Fusion. It returns the top 5 passages with their scores.
- **FR-303** Retrieval is offered to the model **as a tool** (`search_policy(query)`); the model
  decides what to search for. If the model does not search, the question itself is searched.
- **FR-304** **Refusal**: the answer is a fixed refusal ("I can't answer that from the travel and
  expense policy …"), written by code, not the model, when either (a) no passage is similar enough
  to the question (best embedding similarity below a threshold set from the evaluation, FR-308; no
  model is called), or (b) the model judges that the retrieved passages do not answer it. (Amended
  2026-11-25 after the evaluation showed similarity alone cannot separate answerable from
  unanswerable questions safely.)
- **FR-305** **Grounding**: the answer may use only the retrieved passages, and cites them inline as
  `[POL-XXX#n]`. Citations of passages that were not retrieved are reported as `unverified`. An answer
  with no valid citation is marked `grounded: false`.
- **FR-306** **Streaming**: the response is a Server-Sent Events stream: `token` events with text as
  it is generated, one `citations` event (`citations`, `unverified`, `grounded`, `refused`), then
  `done`. An error after streaming has started is sent as an `error` event.
- **FR-307** Input: a question of 1–500 characters. Invalid input is refused with a validation
  error. If the model service is unavailable before streaming starts, the request fails with
  "service unavailable".
- **FR-308** A retrieval evaluation over `data/golden/retrieval.jsonl` (16 answerable + 4
  unanswerable questions) reports recall@5 and MRR for keyword-only, meaning-only and hybrid
  retrieval, and the similarity scores used to choose the refusal threshold.

## Out of scope

Storing questions or answers, conversation history, authentication, documents other than the
policy, a managed vector database (see plan).

## Success criteria

- **SC-301** Hybrid recall@5 is at least as good as either method alone on the golden set, or the
  evidence explains why not.
- **SC-302** All 4 unanswerable golden questions are refused; no answerable one is.
- **SC-303** Every live answer's citations are passages retrieved for that question.
