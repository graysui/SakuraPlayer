import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/auth/session_store.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';
import 'package:sakuraplayer_windows/features/settings/data/settings_api.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/qr_binding_controller.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/diagnostics_page.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/settings_labels.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/settings_page.dart';

void main() {
  group('QR and settings DTO contract', () {
    test('decodes PNG in memory and rejects secret response fields', () {
      final qr = QrSessionDto.fromJson(<String, Object?>{
        'id': _qrId,
        'status': 'waiting',
        'qrcode_png_base64': base64Encode(_pngBytes),
        'expires_at': '2026-07-30T13:00:00Z',
      });

      expect(qr.imageBytes, _pngBytes);
      expect(qr.status, 'waiting');
      expect(
        () => QrSessionDto.fromJson(<String, Object?>{
          'id': _qrId,
          'status': 'waiting',
          'qrcode_png_base64': base64Encode(_pngBytes),
          'expires_at': '2026-07-30T13:00:00Z',
          'cookie': 'forbidden',
        }),
        throwsA(isA<ProtocolException>()),
      );
    });

    test('accepts provider not_configured and enforces fixed settings', () {
      final settings = SettingsDto.fromJson(_settingsJson());

      expect(settings.providers['cloud115']?.status, 'not_configured');
      expect(settings.readyCacheLimit, 20);
      expect(settings.metadataConcurrency, 3);
      expect(settings.metadataTimeoutSeconds, 600);

      expect(
        () =>
            SettingsDto.fromJson(_settingsJson()..['metadata_concurrency'] = 4),
        throwsA(isA<ProtocolException>()),
      );
      expect(
        () => SettingsDto.fromJson(_settingsJson()..['api_key'] = 'forbidden'),
        throwsA(isA<ProtocolException>()),
      );
    });

    test('maps binding, QR, provider and unknown errors to Chinese labels', () {
      expect(cloud115BindingStatusLabel('active'), '已绑定');
      expect(qrStatusLabel('waiting'), '等待扫码');
      expect(settingsErrorLabel('dmm_upstream_error'), 'DMM 暂时无法访问');
      expect(settingsErrorLabel('gfriends_upstream_error'), 'GFriends 暂时无法访问');
      expect(
        settingsErrorLabel('translation_credentials_invalid'),
        'AI API key 无效',
      );
      expect(settingsErrorLabel('new_server_error'), '未知错误');
    });

    test('selects only server-provided optional enrichment stages', () {
      expect(
        validateEnrichmentSelection(
          retryableStages: const <String>['images', 'translation'],
          selectedStages: const <String>['images'],
        ),
        const <String>['images'],
      );
      expect(
        () => validateEnrichmentSelection(
          retryableStages: const <String>['images'],
          selectedStages: const <String>['javdb_core'],
        ),
        throwsArgumentError,
      );
      expect(
        defaultEnrichmentSelection(const <String>['images', 'translation']),
        const <String>{'images'},
      );
    });

    test('gateway sends object CAS and explicit enrichment payloads', () async {
      final session = SessionStore(SecureStore(MemorySecureKeyValueStore()));
      await session.setTokens(_tokens());
      final adapter = _SettingsAdapter();
      final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
        ..httpClientAdapter = adapter;
      final api = SettingsApi(ApiClient(dio: dio, sessionStore: session));

      await api.replaceJavdb(
        expectedVersion: 3,
        username: 'admin',
        password: 'secret-value',
      );
      await api.retryMetadataEnrichment(
        _metadataJobId,
        const <String>['translation', 'images'],
        const <String>['images', 'translation'],
      );

      expect(
        adapter.requests.map((item) => '${item.method} ${item.path}'),
        <String>[
          'PATCH settings',
          'POST admin/metadata-jobs/$_metadataJobId/retry-enrichment',
        ],
      );
      expect(adapter.requests.first.data, <String, Object?>{
        'javdb': <String, Object?>{
          'action': 'replace',
          'expected_version': 3,
          'username': 'admin',
          'password': 'secret-value',
        },
      });
      expect(adapter.requests.last.data, <String, Object?>{
        'stages': <String>['images', 'translation'],
      });
      expect(
        adapter.requests.every(
          (item) => item.headers['Authorization'] == 'Bearer access-token',
        ),
        isTrue,
      );
    });

    test('diagnostics retains redacted time fields and queue bounds', () {
      final json = _diagnosticsJson();
      final diagnostics = DiagnosticsDto.fromJson(json);

      expect(
        diagnostics.components.single.checkedAt,
        DateTime.utc(2026, 7, 30, 12),
      );
      expect(diagnostics.recentFailures.single.elapsedMs, 250);
      expect(
        diagnostics.recentFailures.single.occurredAt,
        DateTime.utc(2026, 7, 30, 12, 1),
      );
      expect(diagnostics.connectionTests.single.target, 'cloud115');
      expect(diagnostics.metadataProgress.total, 10);
      expect(diagnostics.metadataProgress.finished, 4);
      expect(diagnostics.metadataProgress.currentNumbers, const ['ABC-123']);
      expect(diagnostics.queues.metadataPaused, isFalse);

      final invalid = _diagnosticsJson();
      (invalid['queues']! as Map<String, Object?>)['cache_running'] = 3;
      expect(
        () => DiagnosticsDto.fromJson(invalid),
        throwsA(isA<ProtocolException>()),
      );
    });
  });

  test('QR confirms once and releases the in-memory image', () async {
    final gateway = _QrGateway();
    final container = ProviderContainer(
      overrides: [settingsGatewayProvider.overrideWithValue(gateway)],
    );
    addTearDown(container.dispose);
    final controller = container.read(qrBindingControllerProvider.notifier);

    await controller.startQr();
    expect(container.read(qrBindingControllerProvider).imageBytes, _pngBytes);
    expect(container.read(qrBindingControllerProvider).isPolling, isTrue);

    await controller.pollOnce();
    await controller.pollOnce();

    final state = container.read(qrBindingControllerProvider);
    expect(gateway.confirmCalls, 1);
    expect(state.status, 'confirmed');
    expect(state.sessionId, isNull);
    expect(state.imageBytes, isNull);
    expect(state.binding?.status, 'active');
  });

  test(
    'temporary QR outage stops polling but keeps the memory session',
    () async {
      final gateway = _UnavailableQrGateway();
      final container = ProviderContainer(
        overrides: [settingsGatewayProvider.overrideWithValue(gateway)],
      );
      addTearDown(container.dispose);
      final controller = container.read(qrBindingControllerProvider.notifier);
      await controller.startQr();

      await controller.pollOnce();

      final state = container.read(qrBindingControllerProvider);
      expect(state.errorCode, 'cloud115_unavailable');
      expect(state.isPolling, isFalse);
      expect(state.sessionId, _qrId);
      expect(state.imageBytes, _pngBytes);
    },
  );

  test('temporary confirm outage keeps the QR and retries confirm', () async {
    final gateway = _UnavailableConfirmQrGateway();
    final container = ProviderContainer(
      overrides: [settingsGatewayProvider.overrideWithValue(gateway)],
    );
    addTearDown(container.dispose);
    final controller = container.read(qrBindingControllerProvider.notifier);
    await controller.startQr();

    await controller.pollOnce();

    var state = container.read(qrBindingControllerProvider);
    expect(gateway.confirmCalls, 1);
    expect(state.errorCode, 'cloud115_unavailable');
    expect(state.status, 'confirmed');
    expect(state.sessionId, _qrId);
    expect(state.imageBytes, _pngBytes);

    await controller.retry();

    state = container.read(qrBindingControllerProvider);
    expect(gateway.confirmCalls, 2);
    expect(state.binding?.status, 'active');
    expect(state.sessionId, isNull);
    expect(state.imageBytes, isNull);
  });

  testWidgets('narrow settings uses tabs and never renders secrets', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(700, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          settingsGatewayProvider.overrideWithValue(_SettingsPageGateway()),
        ],
        child: const MaterialApp(home: Scaffold(body: SettingsPage())),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(TabBar), findsOneWidget);
    expect(find.text('tester · 已绑定'), findsOneWidget);
    await tester.tap(find.text('缓存'));
    await tester.pumpAndSettle();
    expect(find.text('就绪缓存上限：20'), findsOneWidget);
    expect(find.text('元数据并发：3'), findsOneWidget);
    await tester.tap(find.text('服务'));
    await tester.pumpAndSettle();
    final password = tester.widget<TextField>(
      find.byKey(const ValueKey('javdb-password'), skipOffstage: false),
    );
    final apiKey = tester.widget<TextField>(
      find.byKey(const ValueKey('ai-api-key'), skipOffstage: false),
    );
    expect(password.controller?.text, isEmpty);
    expect(apiKey.controller?.text, isEmpty);
    expect(find.text('secret-value'), findsNothing);
    expect(find.text('密码已配置：是'), findsOneWidget);
    expect(find.text('API key 已配置：是'), findsOneWidget);
    expect(find.text('状态：未配置 · 无错误'), findsNWidgets(2));
    final cloud115Button = find.byKey(
      const ValueKey('connection-test-cloud115'),
      skipOffstage: false,
    );
    await tester.ensureVisible(cloud115Button);
    await tester.tap(cloud115Button);
    await tester.pumpAndSettle();
    expect(
      find.textContaining('115 · 不可用 · 115 服务暂时不可用 · 123 ms'),
      findsOneWidget,
    );
  });

  testWidgets(
    'diagnostics shows aggregate metadata progress without job list',
    (tester) async {
      final gateway = _DiagnosticsGateway();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [settingsGatewayProvider.overrideWithValue(gateway)],
          child: const MaterialApp(home: Scaffold(body: DiagnosticsPage())),
        ),
      );
      await tester.pumpAndSettle();

      expect(gateway.diagnosticsCalls, 1);
      expect(gateway.metadataPageCalls, 0);
      expect(find.text('元数据刮削进度'), findsOneWidget);
      expect(find.text('已处理 4 / 10'), findsOneWidget);
      expect(find.text('失败 1'), findsOneWidget);
      expect(find.textContaining('ABC-123'), findsOneWidget);
      expect(find.textContaining('排队 5'), findsNothing);
      expect(find.textContaining('image_failed'), findsNothing);
      expect(find.text('加载更多'), findsNothing);
    },
  );

  testWidgets('diagnostics pauses and resumes metadata claims', (tester) async {
    final gateway = _DiagnosticsGateway();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [settingsGatewayProvider.overrideWithValue(gateway)],
        child: const MaterialApp(home: Scaffold(body: DiagnosticsPage())),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('暂停刮削'));
    await tester.pumpAndSettle();
    expect(gateway.controlRequests, <bool>[true]);
    expect(gateway.diagnosticsCalls, 2);
    expect(find.text('开始刮削'), findsOneWidget);

    await tester.tap(find.text('开始刮削'));
    await tester.pumpAndSettle();
    expect(gateway.controlRequests, <bool>[true, false]);
    expect(find.text('暂停刮削'), findsOneWidget);
  });
}

const _qrId = '00000000-0000-4000-8000-000000000208';
const _metadataJobId = '00000000-0000-4000-8000-000000000209';
const _pngBytes = <int>[137, 80, 78, 71, 13, 10, 26, 10, 0];

Map<String, Object?> _provider({String status = 'unknown'}) =>
    <String, Object?>{
      'configured': false,
      'status': status,
      'last_checked_at': null,
      'last_error_code': null,
    };

Map<String, Object?> _sync() => <String, Object?>{
  'status': 'never',
  'imported_count': 0,
  'release_id': null,
  'started_at': null,
  'completed_at': null,
  'last_successful_at': null,
  'next_scheduled_at': null,
  'last_error_code': null,
};

Map<String, Object?> _settingsJson() => <String, Object?>{
  'cache_ttl_hours': 24,
  'ready_cache_limit': 20,
  'metadata_concurrency': 3,
  'metadata_timeout_seconds': 600,
  'javdb': <String, Object?>{
    ..._provider(status: 'not_configured'),
    'username': null,
    'password_configured': false,
    'version': 0,
  },
  'ai': <String, Object?>{
    ..._provider(status: 'not_configured'),
    'base_url': null,
    'model': null,
    'timeout_seconds': null,
    'api_key_configured': false,
    'version': 0,
  },
  'providers': <String, Object?>{
    'cloud115': _provider(status: 'not_configured'),
    'dmm': _provider(),
    'gfriends': _provider(),
    'actor_mapping': _provider(),
  },
  'avdb_sync': <String, Object?>{
    'incremental_30d': _sync(),
    'full_reconcile': _sync(),
  },
};

class _QrGateway implements SettingsGateway {
  int confirmCalls = 0;

  @override
  Future<QrSessionDto> createQrSession() async =>
      QrSessionDto.fromJson(<String, Object?>{
        'id': _qrId,
        'status': 'waiting',
        'qrcode_png_base64': base64Encode(_pngBytes),
        'expires_at': '2026-07-30T13:00:00Z',
      });

  @override
  Future<QrSessionDto> pollQrSession(String sessionId) async =>
      QrSessionDto.fromJson(<String, Object?>{
        'id': _qrId,
        'status': 'confirmed',
        'qrcode_png_base64': null,
        'expires_at': '2026-07-30T13:00:00Z',
      });

  @override
  Future<Cloud115BindingDto> confirmQrSession(String sessionId) async {
    confirmCalls++;
    return Cloud115BindingDto.fromJson(<String, Object?>{
      'bound': true,
      'status': 'active',
      'display_name': 'tester',
      'cache_root_ready': true,
      'last_verified_at': '2026-07-30T12:00:00Z',
    });
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError(invocation.memberName.toString());
}

class _UnavailableQrGateway extends _QrGateway {
  @override
  Future<QrSessionDto> pollQrSession(String sessionId) => Future.error(
    const ApiException(code: 'cloud115_unavailable', message: 'offline'),
  );
}

class _UnavailableConfirmQrGateway extends _QrGateway {
  @override
  Future<Cloud115BindingDto> confirmQrSession(String sessionId) async {
    confirmCalls++;
    if (confirmCalls == 1) {
      throw const ApiException(
        code: 'cloud115_unavailable',
        message: 'offline',
      );
    }
    return Cloud115BindingDto.fromJson(<String, Object?>{
      'bound': true,
      'status': 'active',
      'display_name': 'tester',
      'cache_root_ready': true,
      'last_verified_at': '2026-07-30T12:00:00Z',
    });
  }
}

class _SettingsPageGateway implements SettingsGateway {
  @override
  Future<SettingsDto> getSettings() async {
    final json = _settingsJson();
    json['javdb'] = <String, Object?>{
      ...(json['javdb']! as Map<String, Object?>),
      'username': 'admin',
      'password_configured': true,
      'version': 1,
    };
    json['ai'] = <String, Object?>{
      ...(json['ai']! as Map<String, Object?>),
      'base_url': 'https://ai.test',
      'model': 'model',
      'timeout_seconds': 60,
      'api_key_configured': true,
      'version': 1,
    };
    return SettingsDto.fromJson(json);
  }

  @override
  Future<Cloud115BindingDto> getBinding() async =>
      Cloud115BindingDto.fromJson(<String, Object?>{
        'bound': true,
        'status': 'active',
        'display_name': 'tester',
        'cache_root_ready': true,
        'last_verified_at': null,
      });

  @override
  Future<ConnectionTestDto> testConnection(String target) async =>
      ConnectionTestDto(
        target: target,
        status: 'unavailable',
        errorCode: 'cloud115_unavailable',
        elapsedMs: 123,
        checkedAt: DateTime.utc(2026, 7, 30, 12),
      );

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError(invocation.memberName.toString());
}

class _DiagnosticsGateway extends _SettingsPageGateway {
  int diagnosticsCalls = 0;
  int metadataPageCalls = 0;
  bool paused = false;
  final List<bool> controlRequests = <bool>[];

  @override
  Future<DiagnosticsDto> getDiagnostics() async {
    diagnosticsCalls++;
    return DiagnosticsDto.fromJson(_diagnosticsJson(paused: paused));
  }

  @override
  Future<MetadataQueueControlDto> setMetadataPaused(bool value) async {
    controlRequests.add(value);
    paused = value;
    return MetadataQueueControlDto(paused: value, queued: 1, running: 1);
  }

  @override
  Future<MetadataJobPageDto> listMetadataJobs({String? cursor}) async {
    metadataPageCalls++;
    return const MetadataJobPageDto(items: [], nextCursor: null);
  }
}

TokenPair _tokens() => TokenPair(
  accessToken: 'access-token',
  refreshToken: 'refresh-token',
  accessExpiresAt: DateTime.utc(2026, 7, 30, 13),
  refreshExpiresAt: DateTime.utc(2026, 8, 30),
);

Map<String, Object?> _metadataJson() => <String, Object?>{
  'id': _metadataJobId,
  'movie_id': '00000000-0000-4000-8000-000000000101',
  'number': 'ABC-123',
  'priority': 10,
  'reason': 'manual_or_search',
  'retry_mode': 'missing_enrichment',
  'requested_stages': <Object?>['images', 'translation'],
  'parent_job_id': '00000000-0000-4000-8000-000000000210',
  'status': 'queued',
  'stage': null,
  'attempt_no': 2,
  'elapsed_ms': null,
  'error_code': null,
  'stages': <Object?>[],
  'retryable_stages': <Object?>[],
  'created_at': '2026-07-30T12:00:00Z',
};

Map<String, Object?> _diagnosticsJson({bool paused = false}) =>
    <String, Object?>{
      'generated_at': '2026-07-30T12:02:00Z',
      'components': <Object?>[
        <String, Object?>{
          'component': 'api',
          'status': 'healthy',
          'error_code': null,
          'checked_at': '2026-07-30T12:00:00Z',
        },
      ],
      'queues': <String, Object?>{
        'metadata_queued': 1,
        'metadata_running': 1,
        'metadata_paused': paused,
        'cache_queued': 1,
        'cache_running': 1,
        'cache_ready': 2,
      },
      'metadata_progress': <String, Object?>{
        'total': 10,
        'queued': 5,
        'running': 1,
        'completed': 3,
        'failed': 1,
        'finished': 4,
        'current_numbers': <Object?>['ABC-123'],
      },
      'recent_failures': <Object?>[
        <String, Object?>{
          'task_type': 'metadata',
          'task_id': _metadataJobId,
          'stage': 'images',
          'error_code': 'image_failed',
          'elapsed_ms': 250,
          'attempt_no': 2,
          'occurred_at': '2026-07-30T12:01:00Z',
        },
      ],
      'connection_tests': <Object?>[
        <String, Object?>{
          'target': 'cloud115',
          'status': 'available',
          'error_code': null,
          'elapsed_ms': 12,
          'checked_at': '2026-07-30T12:00:30Z',
        },
      ],
    };

class _SettingsAdapter implements HttpClientAdapter {
  final requests = <RequestOptions>[];
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (options.method == 'PATCH' && options.path == 'settings') {
      return _jsonResponse(200, _settingsJson());
    }
    if (options.method == 'POST' &&
        options.path.endsWith('/retry-enrichment')) {
      return _jsonResponse(201, _metadataJson());
    }
    throw StateError('unexpected ${options.method} ${options.path}');
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody _jsonResponse(int status, Map<String, Object?> body) =>
    ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>['application/json'],
      },
    );
