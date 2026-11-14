### Fixed

- `skill novelty atoms`, `probe` and `analyze` and `skill shorten` stop at the first authentication, permission, unknown-model, unsupported-parameter or no-credentials error (extraction, the faithfulness check, probe wordings, answers and grades, the value and conflict batches, retention adjudication) instead of failing every remaining call and recording each one as failed; the partial result is kept as at the cap, with `reason` `permanent_error`. A refusal, an unparseable reply or a request that is too long is still one failed item. (#708)
