Neither is included.

```sh
make engine     # = tools/fetch_engine.sh: clone DMC100-Doom @0cdc78e into .deps/, apply the patch, fetch Freedoom 0.13.0, build E1.img
```

`ports/doomdmc/mkimage.sh` builds the NOR disk image (`E1.img`) from the layout and the WAD; `ports/doomdmc/build.sh` builds `doomd`. Override locations with `DMC`, `IWAD`, `QOS_FREEDOOM_WAD`.
The `engine-patches/` diff holds the QwenOS edits to DMC100-Doom (see `engine-patches/NOTICE`).
