# Real 115 probes

This directory is excluded from default pytest discovery. Tests here must use the
`real115` marker and require `SAKURAPLAYER_RUN_REAL115=1`,
`SAKURAPLAYER_115_COOKIE`, and `SAKURAPLAYER_115_TEST_ROOT_CID`. The included probe is
read-only. A future destructive probe must prove every target is below that root before
calling delete. Never place credentials, magnets, signed URLs, or captured upstream
bodies in this directory.
