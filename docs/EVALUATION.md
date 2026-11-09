# Evaluation and release checklist

This workflow applies the locally available Stanford CS230 study notes, particularly L3 (full project lifecycle), L4 (adversarial robustness), L6 (project strategy) and L8 (agents, prompts and RAG). It is an engineering application of those notes, not a claim of Stanford certification.

## Define a baseline and keep test data independent

Specify users, target outputs, unacceptable failures and a simple baseline before tuning. Use dev data to select prompts, thresholds, retrieval settings or model parameters. Freeze a representative, human-reviewed test set for final comparison. Keep related documents, questions, sessions or machine events from leaking across splits. Synthetic data may augment training; it cannot substitute for a realistic production test set.

For sensor forecasting, preserve time order and event independence. Features and imputation must use only information available at prediction time. Report the prediction horizon and event lead time rather than assuming a classifier score means imminent failure.

## Evaluate the components and the complete workflow

| System | Useful evidence |
| --- | --- |
| RAG/support | retrieval recall@k, source correctness, answer correctness, unsupported claims, safe abstention, latency |
| Fine-tuning | base-model comparison, dev loss, held-out task quality, regressions by source/label/role |
| Predictive maintenance | precision/recall, PR-AUC, false alarms, missed failures, event-level results, calibration |
| Meeting workflows | section/item extraction accuracy, omitted/hallucinated actions, correct references, sync behavior |

Accuracy alone is misleading for skewed classes. Report denominators and error costs. A regex guard is a heuristic, not a general hallucination detector. Calibrate LLM judges against human review; judge scores are not independent truth.

## Turn failures into targeted work

Review incorrect examples and record error buckets: bad label, missing source, wrong retrieval, source conflict, unsupported action, malformed input, timeout, duplicate import, subgroup mismatch. Prioritize by frequency and business impact. Improve labels or targeted coverage before assuming a larger model or more agents is necessary.

## Safety, observability and deployment

Treat retrieved documents as untrusted evidence. Include adversarial instructions in the evaluation suite; never allow a document to authorize external actions. Require human confirmation for consequential writes. Store prompts/configuration with version history.

Capture model and dataset versions/hashes, retrieval source/chunk IDs, stage latency and categorized errors. Avoid storing raw sensitive prompts, credentials or customer data in public logs. Verify access controls, backups, rollback and rate limits before shared deployment. Monitor changes in input distributions and observed outcomes; process restarts and missing history must be visible.

## Release evidence

A successful unit test or frontend build does not prove model quality, integration permissions, deployment security or a bug-free application. Record exactly which tests ran, on which versions, and which checks remain manual. Do not publish percentage improvements or latency guarantees without a reproducible benchmark.

Supporting references: [CS230 project guidance](https://cs230.stanford.edu/project/), [scikit-learn evaluation metrics](https://scikit-learn.org/stable/modules/model_evaluation.html), [TRL SFT configuration](https://huggingface.co/docs/trl/en/sft_trainer). Local study-note provenance is recorded in the workspace polish report.
