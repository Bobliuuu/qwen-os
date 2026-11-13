`make check`; `tools/doomd_regress.sh` (state/frame goldens in `tests/golden/`); upstream lockstep needs a checkout of qwenputer on `PYTHONPATH` (see [`MERGE_NOTES.md`](MERGE_NOTES.md)).
`tools/model_doom_qwen.py` and `tools/model_doom_chunks.py` drive the real model and need a GPU box plus the Qwen checkpoint; they are not run in CI.
