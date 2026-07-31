# Third-Party Notices

SakuraPlayer is distributed under GPL-3.0-only. Binary distributions must
include the applicable GPL text, this notice, and the notices for all packaged
Flutter plugins and native libraries. TASK-212 owns the final artifact audit.

## Flutter 3.29.2 and go_router 16.3.0

Flutter and go_router are Copyright The Flutter Authors and are distributed
under the BSD 3-Clause license. Sources and license text are available from
<https://github.com/flutter/flutter> and
<https://pub.dev/packages/go_router/versions/16.3.0>.

## flutter_riverpod 3.1.0

flutter_riverpod is Copyright 2020 Remi Rousselet and is distributed under the
MIT License. Source and license text are available from
<https://pub.dev/packages/flutter_riverpod/versions/3.1.0>.

## dio 5.7.0

dio is distributed under the MIT License. Source and license text are
available from <https://pub.dev/packages/dio/versions/5.7.0>.

## flutter_secure_storage 9.2.0

flutter_secure_storage is distributed under the BSD 3-Clause License. Source
and license text are available from
<https://pub.dev/packages/flutter_secure_storage/versions/9.2.0>.

## media_kit

media_kit 1.1.11, media_kit_video 1.2.5, media_kit_libs_video 1.0.5 and the
resolved Windows native package media_kit_libs_windows_video 1.0.11 are
Copyright 2021 and onwards Hitesh Kumar Saini and are distributed under the MIT
License. Sources and license text are available from
<https://github.com/media-kit/media-kit>.

The Windows native package uses the libmpv build published by
`media-kit/libmpv-win32-video-build`; version 1.0.11 records mpv revision
`652a1dd90711839acdccc08004056d25514ef2d8`. TASK-212 must retain the exact
licenses and notices emitted for the native binaries in the private package.

## flutter_local_notifications

`flutter_local_notifications` 19.5.0 and its Windows FFI implementation
`flutter_local_notifications_windows` 1.0.3 are distributed under the BSD
3-Clause license. Sources and license text are available from
<https://github.com/MaikuB/flutter_local_notifications> at the corresponding
tags. The plugin is used only for immediate Windows toast display; TASK-212
must retain the resolved transitive notices in the private package.

## SakuraMedia consultation boundary

TASK-201 does not copy application source from SakuraMedia. Later Windows tasks
may consult the feature-first layout and throttled player behavior identified
by the technical plan; any retained source or behavior must add its exact file,
revision, and GPL-3.0-only notice before distribution.
