# Paired boundary property example

This is a task-specific executable oracle for the directory-diff experiment, not
an automatic contract generator or a universal filesystem security check.

Requirement: a root alias resolving to the linked root itself is rejected; an
ancestor link that locates a different ordinary directory remains allowed. Raw
invalid paths are rejected separately. A forbidden input and a nearby permitted
input must not become indistinguishable after a repair.

`check_path_boundary.py` generates dot/dotdot spellings over two fixture layouts,
absolute and relative link targets, three trailing forms and both CLI argument
positions. The OS identifies the endpoint; no candidate path-normalization logic
is copied. Allowed inputs must produce the exact expected file report, not just
exit successfully. Rejected inputs must return an error without a partial report.
Nonempty coverage of both classes and input-file preservation are required.

Freeze this file through `check_inputs` and run it against the compiled CLI through
a declared check. Keep existing tests: invalid roots and symlinks encountered inside
a compared tree are separate obligations. Validate sensitivity on known under-
and over-rejecting implementations before using it to accept a replacement.

The finite domain has stable trees and a single link per generated path. It does
not establish correctness for arbitrary chains, races or all possible inputs.
