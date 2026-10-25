# M0 data contract

Every record requires a boolean `is_synthetic`. A dataset cannot mix real and
synthetic records. IDs are opaque, nonempty strings; no VTU ID convention is assumed.

| Record | Fields in addition to `is_synthetic` | Relationship |
| --- | --- | --- |
| Subject | `id`, `name` | Parent of papers and topics. |
| Scheme | `id`, `name`, `year` | Scheme year is separate from paper year. |
| Paper | `id`, `subject_id`, `scheme_id`, `year`, `sitting` | One subject/scheme/year/sitting combination per paper. |
| Question | `id`, `paper_id`, `text`, `marks`, `module`, `number`, `sub_part` | Belongs to one paper. Sub-part may be null. Marks must be finite and positive. |
| Topic | `id`, `subject_id`, `scheme_id`, `name`, `module` | Topic identity is scoped to a subject and scheme. |
| Label | `question_id`, `topic_id` | A unique pair; both references must exist and agree on subject, scheme, and module. |

`Dataset` holds `schema_version`, `is_synthetic`, `provenance`, and arrays for the
record collections above. In Python the record collections are tuples; JSON arrays
are revalidated into tuples on load. Unknown/missing JSON keys are rejected.

A partially labeled dataset is valid, but not automatically evaluation-ready.
Empty collections can represent a newly created corpus. Generated fixtures have
complete labels; future evaluation must explicitly check its own prerequisites.

Synthetic provenance includes the scenario, seed, generator version, configuration
hash, effective configuration, preferred-topic construction details, and an explicit
warning. The accompanying manifest hashes the saved dataset and computes counts.
Do not confuse schema validation with cryptographic provenance verification: the
loader validates records but does not automatically compare a manifest's hash.

Generation exposes no evaluation endpoint and produces no predictions. The future
backtest must separate historical training records from held-out records before
any model or baseline is called.
