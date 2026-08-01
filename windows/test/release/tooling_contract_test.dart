import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final projectRoot = Directory.current;

  test('private release tooling is explicit and store-free', () {
    final build = File('${projectRoot.path}/tool/build_private_release.ps1');
    final install = File(
      '${projectRoot.path}/tool/package/Install-SakuraPlayer.ps1',
    );
    final uninstall = File(
      '${projectRoot.path}/tool/package/Uninstall-SakuraPlayer.ps1',
    );

    expect(build.existsSync(), isTrue);
    expect(install.existsSync(), isTrue);
    expect(uninstall.existsSync(), isTrue);

    final buildText = build.readAsStringSync();
    expect(buildText, contains('flutter build windows --release'));
    expect(buildText, contains('Compress-Archive'));
    expect(buildText, contains('CertificateThumbprint'));
    expect(buildText, contains('PROJECT_THIRD_PARTY_NOTICES.md'));
    expect(buildText.toLowerCase(), isNot(contains('microsoft store')));
    expect(buildText.toLowerCase(), isNot(contains('windows store')));
  });

  test('default entrypoint cannot collect the real115 probe', () {
    final runner = File('${projectRoot.path}/tool/run_default_tests.ps1');
    expect(runner.existsSync(), isTrue);

    final text = runner.readAsStringSync().replaceAll('\\', '/');
    expect(text, contains('integration_test/fake_backend_flow_test.dart'));
    expect(text, contains('sakuraplayer-test'));
    expect(text, contains('type=bind'));
    expect(text, contains('readonly'));
    expect(text, isNot(contains('integration_test/real115_probe_test.dart')));
    expect(text, isNot(contains('SAKURAPLAYER_TEST_REAL115')));
    expect(text, isNot(contains('SAKURAPLAYER_115_COOKIE')));
  });

  test('real115 entrypoint requires marker and never names secret values', () {
    final runner = File('${projectRoot.path}/tool/run_real115_probe.ps1');
    expect(runner.existsSync(), isTrue);

    final text = runner.readAsStringSync();
    expect(text, contains("SAKURAPLAYER_TEST_REAL115"));
    expect(text, contains("integration_test/real115_probe_test.dart"));
    expect(text, contains("-d windows"));
    expect(text.toLowerCase(), isNot(contains('cookie=')));
    expect(text.toLowerCase(), isNot(contains('password=')));

    final probe = File(
      '${projectRoot.path}/integration_test/real115_probe_test.dart',
    );
    expect(probe.existsSync(), isTrue);
    final probeText = probe.readAsStringSync();
    expect(probeText, contains('no network attempted'));
    expect(probeText, contains('SAKURAPLAYER_REAL115_CONFIRM_MANAGED_ROOT'));
    expect(probeText, contains('SAKURAPLAYER_REAL115_SKIP_EXTERNAL_SUBTITLES'));
    expect(probeText, contains("'subtitle_external_skipped'"));
    expect(probeText, contains("state: 'operator_approved'"));
    expect(probeText, contains("'srt', 'ass'"));
    expect(probeText, contains('await _probeSubtitles(client, manifest)'));
    expect(probeText, contains('for (final entry in ranges.indexed)'));
    expect(probeText, isNot(contains('final results = await Future.wait')));
    expect(probeText, contains('receiveTimeout: const Duration(seconds: 45)'));
    expect(probeText, isNot(contains('LogInterceptor')));
    expect(probeText.toLowerCase(), isNot(contains('cookie=')));
    expect(probeText.toLowerCase(), isNot(contains('magnet')));

    final runtimeContract =
        File(
          '${projectRoot.parent.path}/docs/specs/001-sakuraplayer-v1/'
          'contracts/runtime-configuration.md',
        ).readAsStringSync();
    for (final variable in <String>[
      'SAKURAPLAYER_REAL115_API_BASE_URL',
      'SAKURAPLAYER_REAL115_USERNAME',
      'SAKURAPLAYER_REAL115_PASSWORD',
      'SAKURAPLAYER_REAL115_MOVIE_ID',
      'SAKURAPLAYER_REAL115_SOURCE_ID',
      'SAKURAPLAYER_REAL115_CONFIRM_MANAGED_ROOT',
    ]) {
      expect(runtimeContract, contains(variable), reason: variable);
    }
  });

  test('TASK-213 acceptance tooling separates fake and real journeys', () {
    final defaultRunner = File(
      '${projectRoot.path}/tool/run_default_tests.ps1',
    );
    final realRunner = File(
      '${projectRoot.path}/tool/run_task213_acceptance.ps1',
    );
    final releaseDriver = File(
      '${projectRoot.path}/test_driver/integration_test.dart',
    );
    final fakeJourney = File(
      '${projectRoot.path}/integration_test/windows_user_journey_test.dart',
    );
    final realJourney = File(
      '${projectRoot.path}/integration_test/windows_real115_e2e_test.dart',
    );
    final checklist = File(
      '${projectRoot.parent.path}/docs/acceptance/'
      'windows-real115-checklist.md',
    );

    expect(fakeJourney.existsSync(), isTrue);
    expect(realJourney.existsSync(), isTrue);
    expect(realRunner.existsSync(), isTrue);
    expect(releaseDriver.existsSync(), isTrue);
    expect(checklist.existsSync(), isTrue);

    final defaultText = defaultRunner.readAsStringSync().replaceAll('\\', '/');
    expect(
      defaultText,
      contains('integration_test/windows_user_journey_test.dart'),
    );
    expect(
      defaultText,
      isNot(contains('integration_test/windows_real115_e2e_test.dart')),
    );

    final realText = realRunner.readAsStringSync().replaceAll('\\', '/');
    expect(realText, contains('SAKURAPLAYER_TEST_REAL115'));
    expect(realText, contains('SAKURAPLAYER_REAL115_SKIP_EXTERNAL_SUBTITLES'));
    expect(realText, contains("\$skipExternalSubtitles -ne '1'"));
    expect(realText, contains('flutter build windows'));
    expect(realText, contains('flutter drive'));
    expect(realText, contains('--release'));
    expect(realText, contains('--profile'));
    expect(realText, contains('Tee-Object'));
    expect(realText, contains('All tests passed!'));
    expect(
      realText,
      contains('integration_test/windows_real115_e2e_test.dart'),
    );
    expect(realText.toLowerCase(), isNot(contains('cookie=')));
    expect(realText.toLowerCase(), isNot(contains('password=')));

    final checklistText = checklist.readAsStringSync();
    expect(checklistText, contains('Range'));
    expect(checklistText, contains('HLS'));
    expect(checklistText, contains('active lease'));
    expect(checklistText, contains('parent/root'));
    expect(checklistText, contains('脱敏'));
    expect(checklistText, contains('subtitle_external_skipped'));
  });
}
