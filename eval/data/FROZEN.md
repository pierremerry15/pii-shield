# Frozen test split

`test.txt` was written before any v2 detection code existed, then frozen.

```
sha256  053c7aa9125642106bc52a0f7fa2e4ca54067724619fbcf84da4d5a5f4b89103  eval/data/test.txt
```

`python -m eval.run_eval` checks this hash on every run. It refuses to report test numbers
if the file has changed, so nobody can quietly edit the test set to improve a score.

v2 was developed against `dev.txt` only. Both splits were written by the same author
(me), so this is a guard against tuning, not an independent benchmark. See the README's
"Limitations" section.
