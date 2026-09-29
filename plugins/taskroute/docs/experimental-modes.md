# Experimental modes

Read only when an experimental mode is explicitly authorized.

Within authorization to delegate to Claude, invoke `deliver` once, or `run RUN`
for an already prepared run.
   For an authorized bounded review-repair experiment, prepare with `--review-repair`
   instead of observer flags. A complete negative first review permits one author
   correction, all unchanged checks, then one fresh independent read-only reviewer.
   First approval ends review; malformed negative or second negative stops. Maximum
   two sequential reviewers, three verifier calls, 24 parent turns / 900 seconds;
   one format correction per reviewer. This is not automatic early-task checkpointing.
   Do not return routine first-review findings to the owner when this mode is enabled;
   the coordinator routes them to implementation inside the reserved run.
   Use `--observe` at preparation only for an explicitly authorized experimental
   observer run: the first live replay failed to detect the known violation, so
   this mode is NOT QUALIFIED for routine semantic supervision.
   The experimental route includes up to two fresh independent Claude
   observer calls before checks, one coordinator correction opportunity and one
   final reviewer. Let the coordinator handle OBSERVER_STOP internally; never
   silently resend after an observer error/unknown result or extend the ceiling.
   Alternative `--probe` generates one frozen executable harness, reused after
   correction without another generation call. Compact mode targets one criterion,
   <=4000 source characters. An integrated run caught and corrected a defect, but final
   semantic acceptance rejected another defect: full delivery remains NOT QUALIFIED.
   Authorized experiments only;
   120-second generation, two 60-second executions maximum, no probe regeneration.
   UNKNOWN probe criteria remain for review, not passed by inference.
   Probe mode validates reviewer completion and allows one same-agent format
   correction. Never spawn a replacement reviewer or infer missing findings.
   Repeated invalid reports stop. Controlled same-reviewer format recovery passed
   live; a fresh integrated implementation route remains unqualified.
   Legacy Python-function mode omits both observer flags. The runner reserves
   before effects, launches one coordinator and one read-only reviewer, and returns
   a packet after independent frozen checks. No auth setup or installation is
   included. Stop on BLOCKED; never automatically retry or resume an unknown result.
