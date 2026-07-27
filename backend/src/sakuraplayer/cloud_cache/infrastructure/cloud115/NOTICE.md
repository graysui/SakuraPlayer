# Cloud115 adapter source notice

This directory contains code adapted from:

- Upstream: <https://github.com/tinypinglite/sakuramediabe.git>
- Revision: `670ca75b2d35b606ffc0caa6fd47fd04c4c95870`
- License: GNU General Public License version 3 only (GPL-3.0-only)
- Upstream files consulted: `src/lib/cloud115/qrlogin.py`, `client.py`,
  `types.py`, `exceptions.py`, and `cipher.py`

Adapted symbols and protocol behavior are limited to QR token/image/status/result,
credential probing and Cookie snapshot merging, directory listing/info/create, recursive
file enumeration, offline add/list/cancel, managed delete, small-file download, original
downurl, HLS metadata, and the downurl `rsa_encode`/`rsa_decode`/XOR helpers.

Rapid upload, upload AES/LZ4, copy/move, raw response models, source URL fields,
MediaLibrary behavior, and external-player paths were not copied or adapted. SakuraPlayer
is itself GPL-3.0-only; the applicable license text is in the repository root `LICENSE`.
