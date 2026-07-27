# Third-Party Notices

SakuraPlayer is distributed under GPL-3.0-only. Binary distributions must include the applicable license text, this notice, and the source notices for reused code.

## Cloud115 protocol adapter

TASK-101 adapts selected protocol behavior and the downurl RSA/XOR helpers from
`sakuramediabe`, available at <https://github.com/tinypinglite/sakuramediabe.git>, fixed
at revision `670ca75b2d35b606ffc0caa6fd47fd04c4c95870` under GPL-3.0-only. Consulted files are
`src/lib/cloud115/qrlogin.py`, `client.py`, `types.py`, `exceptions.py`, and `cipher.py`.

The exact retained symbols and explicitly excluded upload/copy/media-library code are
listed in `backend/src/sakuraplayer/cloud_cache/infrastructure/cloud115/NOTICE.md`.

## Pillow

TASK-008 adds Pillow 11.2.1 for complete JPEG, PNG, and WebP decoding and image-dimension validation. Pillow is distributed under the HPND license; its upstream package and license are available at <https://python-pillow.org/> and are included by the locked Python dependency installation.

## defusedxml

TASK-009 adds defusedxml 0.7.1 for rejecting unsafe DTD and entity declarations while parsing Actor Mapping XML. defusedxml is distributed under the Python Software Foundation License; its upstream source and license are available at <https://github.com/tiran/defusedxml> and are included by the locked Python dependency installation.
