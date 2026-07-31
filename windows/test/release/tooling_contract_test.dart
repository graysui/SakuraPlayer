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
}
