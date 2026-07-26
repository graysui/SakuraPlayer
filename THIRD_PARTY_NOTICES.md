# Third-Party Notices

SakuraPlayer is distributed under GPL-3.0-only. Binary distributions must include the applicable license text, this notice, and the source notices for reused code.

## Current Sources

No source code has been copied from the `avmedia/sakuramediabe` reference project through TASK-008.

Future tasks that copy or adapt source must record the component, upstream source URL, upstream revision, files used, and license before the code is committed.

## Pillow

TASK-008 adds Pillow 11.2.1 for complete JPEG, PNG, and WebP decoding and image-dimension validation. Pillow is distributed under the HPND license; its upstream package and license are available at <https://python-pillow.org/> and are included by the locked Python dependency installation.

## defusedxml

TASK-009 adds defusedxml 0.7.1 for rejecting unsafe DTD and entity declarations while parsing Actor Mapping XML. defusedxml is distributed under the Python Software Foundation License; its upstream source and license are available at <https://github.com/tiran/defusedxml> and are included by the locked Python dependency installation.
