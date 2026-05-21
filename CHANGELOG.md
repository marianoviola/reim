# Changelog

All notable changes to this project are documented in this file.

## [Unreleased] — IP hygiene refactor

This release makes the library domain-agnostic by removing residual traces of
the original product-review schema. The product-review use case is now one
example among many, not baked into the core.

### Breaking changes

- Removed legacy field name aliases in `extract_observations_from_reviews`;
  only the canonical names (`observer_id`, `system_id`, `phase_type`,
  `phase_rating`, `criteria_id`) are accepted. The legacy aliases (`user_id`,
  `product_id`, `flow_type`, `experience_rating`, `review_criteria_id`) no
  longer work.
- Removed legacy method/property aliases on `MultiDimensionalREIM`:
  `product_scores_`, `user_reliability_`, `get_product_report`,
  `get_product_detail`, `get_user_report`, `flag_suspicious_users`. Use the
  canonical `system_scores_`, `observer_reliability_`, `get_system_report`,
  `get_system_detail`, `get_observer_report`, `flag_suspicious_observers`
  instead. The `product_id` / `sentiment_score` columns and the `user_id`
  alias column are no longer emitted by the aggregation tables.
- `ReviewInput.phase_type` is now a free string, not a `Literal`. Any
  non-empty phase label is accepted.
- Rating value bounds are now configurable via the `REIM_VALUE_MIN` and
  `REIM_VALUE_MAX` environment variables (defaults: `1.0` and `5.0`),
  replacing the hardcoded `1.0`–`5.0` bounds.
- `DEFAULT_PHASE_TYPES` and `DEFAULT_PHASE_LABELS` moved out of
  `reim.multidim` to `reim.examples.product_review`, renamed to
  `PRODUCT_REVIEW_PHASE_TYPES` and `PRODUCT_REVIEW_PHASE_LABELS`.
  `MultiDimensionalREIM` now defaults `phase_types`/`phase_labels` to `None`,
  accepting any phase string and using it as its own label.
