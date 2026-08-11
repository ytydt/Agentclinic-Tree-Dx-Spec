# E7b full-results bundle

The complete E7b result tree is published one directory above this folder as
`E7b_registry_selector_FULL_RESULTS.tar.gz`.  Its adjacent `.sha256` file is
the authoritative whole-bundle integrity check.

The archive contains the fully expanded result directory as produced locally:

- 1,200 condition rows over 400 cases and three registry arms;
- case text, gold labels, candidates, evidence snippets, and parsed responses;
- raw concurrent and corrected single-flight analysis surfaces;
- 1,199 semantic-call telemetry rows and all retained response metadata;
- 981 immutable per-payload cache records containing model responses;
- audit queues, the 40-case manual audit, reports, summaries, logs, and the
  preregistration/manifest.

The most useful review files remain expanded beside this README.  To verify and
unpack the complete bundle from `analysis/mechanism_v2/results`:

```bash
sha256sum -c E7b_registry_selector_FULL_RESULTS.tar.gz.sha256
tar -xzf E7b_registry_selector_FULL_RESULTS.tar.gz
```

The expanded raw files are also intentionally retained in the experiment
worktree; only their Git representation is consolidated into the archive.
