import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final projectRoot = Directory.current;

  test('GPL and third-party notices are release inputs', () {
    final license = File('${projectRoot.path}/LICENSE');
    final notices = File('${projectRoot.path}/THIRD_PARTY_NOTICES.md');

    expect(license.existsSync(), isTrue);
    expect(license.readAsStringSync(), contains('GNU GENERAL PUBLIC LICENSE'));
    expect(notices.existsSync(), isTrue);

    final text = notices.readAsStringSync();
    for (final requiredNotice in <String>[
      'GPL-3.0-only',
      'Flutter 3.29.2',
      'flutter_riverpod 3.1.0',
      'dio 5.7.0',
      'flutter_secure_storage 9.2.0',
      'media_kit 1.1.11',
      'media_kit_libs_windows_video 1.0.11',
      'libmpv',
      'flutter_local_notifications',
      '19.5.0',
      'SakuraMedia consultation boundary',
    ]) {
      expect(text, contains(requiredNotice), reason: requiredNotice);
    }
  });

  test('release verifier requires native and license artifacts', () {
    final verifier = File(
      '${projectRoot.path}/tool/verify_release_contents.ps1',
    );

    expect(verifier.existsSync(), isTrue);
    final text = verifier.readAsStringSync();
    for (final artifact in <String>[
      'sakuraplayer_windows.exe',
      'flutter_windows.dll',
      'libmpv-2.dll',
      'data/flutter_assets/NOTICES.Z',
      'BUILD_INFO.txt',
      'LICENSE',
      'THIRD_PARTY_NOTICES.md',
      'PROJECT_THIRD_PARTY_NOTICES.md',
      'SHA256SUMS.txt',
    ]) {
      expect(text, contains(artifact), reason: artifact);
    }
  });
}
