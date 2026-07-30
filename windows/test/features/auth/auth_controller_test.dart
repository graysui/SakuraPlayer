import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/api/server_profile.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';
import 'package:sakuraplayer_windows/core/storage/subtitle_cache.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/server_setup_page.dart';

void main() {
  test(
    'bootstrap token is header-only and neither password nor tokens leak',
    () async {
      final memory = MemorySecureKeyValueStore();
      final subtitle = MemorySubtitleCache();
      RequestOptions? bootstrapRequest;
      final container = _container(
        memory: memory,
        subtitle: subtitle,
        handler: (request) async {
          if (request.path == 'auth/bootstrap') {
            bootstrapRequest = request;
            return _jsonResponse(201, _tokenJson());
          }
          throw StateError('unexpected request ${request.path}');
        },
        initialized: false,
      );
      addTearDown(container.dispose);
      final controller = container.read(authControllerProvider.notifier);
      await controller.configureServer('https://server.test');

      await controller.bootstrap(
        username: 'admin',
        password: 'correct horse battery staple',
        bootstrapToken: 'A' * 43,
      );

      expect(container.read(authControllerProvider).isAuthenticated, isTrue);
      expect(bootstrapRequest!.headers['X-Bootstrap-Token'], 'A' * 43);
      expect(bootstrapRequest!.data, <String, Object?>{
        'username': 'admin',
        'password': 'correct horse battery staple',
        'client_instance_id': memory.values[SecureStore.clientInstanceIdKey],
      });
      expect(memory.values.values, isNot(contains('A' * 43)));
      expect(
        memory.values.values,
        isNot(contains('correct horse battery staple')),
      );
      expect(memory.values.values, isNot(contains('access-token')));
      expect(memory.values[SecureStore.refreshTokenKey], 'refresh-token');
    },
  );

  test(
    'server switch clears local state when old logout is unreachable',
    () async {
      final memory = MemorySecureKeyValueStore();
      final subtitle = MemorySubtitleCache();
      var resetCalls = 0;
      var privateCacheResetCalls = 0;
      final reset =
          RuntimeResetCoordinator()..register(() async {
            resetCalls++;
          });
      final privateCacheReset =
          PrivateCacheResetCoordinator()..register(() async {
            privateCacheResetCalls++;
          });
      final container = _container(
        memory: memory,
        subtitle: subtitle,
        handler: (request) async {
          throw DioException(
            requestOptions: request,
            type: DioExceptionType.connectionError,
            message: 'unreachable',
          );
        },
        initialized: true,
        reset: reset,
        privateCacheReset: privateCacheReset,
      );
      addTearDown(container.dispose);
      final controller = container.read(authControllerProvider.notifier);
      await controller.configureServer('https://old.test');
      await container
          .read(sessionStoreProvider)
          .setTokens(
            TokenPair(
              accessToken: 'old-access',
              refreshToken: 'old-refresh',
              accessExpiresAt: DateTime.utc(2026, 7, 29, 12, 15),
              refreshExpiresAt: DateTime.utc(2026, 8, 29),
            ),
          );

      await controller.configureServer('https://new.test');

      expect(
        container.read(authControllerProvider).serverBaseUri!.host,
        'new.test',
      );
      expect(container.read(sessionStoreProvider).accessToken, isNull);
      expect(memory.values[SecureStore.refreshTokenKey], isNull);
      expect(memory.values[SecureStore.clientInstanceIdKey], isNotNull);
      expect(subtitle.cleared, isTrue);
      expect(resetCalls, 1);
      expect(privateCacheResetCalls, 1);
    },
  );

  testWidgets(
    'failed bootstrap immediately clears password and bootstrap fields',
    (tester) async {
      final memory = MemorySecureKeyValueStore();
      final container = _container(
        memory: memory,
        subtitle: MemorySubtitleCache(),
        handler: (_) async => _errorResponse(401, 'bootstrap_token_invalid'),
        initialized: false,
      );
      addTearDown(container.dispose);
      await container
          .read(authControllerProvider.notifier)
          .configureServer('https://server.test');
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: const MaterialApp(home: ServerSetupPage()),
        ),
      );

      await tester.enterText(find.widgetWithText(TextField, '用户名'), 'admin');
      await tester.enterText(
        find.widgetWithText(TextField, '密码'),
        'correct horse battery staple',
      );
      await tester.enterText(
        find.byKey(const ValueKey('bootstrap-token-field')),
        'B' * 43,
      );
      await tester.ensureVisible(find.text('创建管理员'));
      await tester.tap(find.text('创建管理员'));
      await tester.pumpAndSettle();

      final bootstrap = tester.widget<TextField>(
        find.byKey(const ValueKey('bootstrap-token-field')),
      );
      final password = tester.widget<TextField>(
        find.widgetWithText(TextField, '密码'),
      );
      expect(bootstrap.controller!.text, isEmpty);
      expect(password.controller!.text, isEmpty);
      expect(find.byKey(const ValueKey('auth-error')), findsOneWidget);
      expect(memory.values.values, isNot(contains('B' * 43)));
    },
  );

  test(
    'login, business refresh and logout clear the private client state',
    () async {
      final memory = MemorySecureKeyValueStore();
      final subtitle = MemorySubtitleCache();
      var refreshCalls = 0;
      var businessCalls = 0;
      var logoutCalls = 0;
      final container = _container(
        memory: memory,
        subtitle: subtitle,
        initialized: true,
        handler: (request) async {
          switch (request.path) {
            case 'auth/login':
              return _jsonResponse(200, _tokenJson());
            case 'auth/refresh':
              refreshCalls++;
              return _jsonResponse(
                200,
                _tokenJson(
                  accessToken: 'rotated-access',
                  refreshToken: 'rotated-refresh',
                ),
              );
            case 'movies':
              businessCalls++;
              if (request.headers['Authorization'] == 'Bearer access-token') {
                return _errorResponse(401, 'access_expired');
              }
              expect(request.headers['Authorization'], 'Bearer rotated-access');
              return _jsonResponse(200, <String, Object?>{
                'items': <Object?>[],
              });
            case 'auth/logout':
              logoutCalls++;
              expect(request.headers['Authorization'], 'Bearer rotated-access');
              return ResponseBody.fromString('', 204);
          }
          throw StateError('unexpected request ${request.path}');
        },
      );
      addTearDown(container.dispose);
      final controller = container.read(authControllerProvider.notifier);
      await controller.configureServer('https://server.test');
      await controller.login(
        username: 'admin',
        password: 'correct horse battery staple',
      );

      expect(
        await controller.apiClient!.get('movies', decode: _moviePageCount),
        0,
      );
      await controller.logout();

      expect(refreshCalls, 1);
      expect(businessCalls, 2);
      expect(logoutCalls, 1);
      expect(container.read(sessionStoreProvider).accessToken, isNull);
      expect(memory.values[SecureStore.refreshTokenKey], isNull);
      expect(subtitle.cleared, isTrue);
      expect(container.read(authControllerProvider).isAuthenticated, isFalse);
    },
  );
}

ProviderContainer _container({
  required MemorySecureKeyValueStore memory,
  required MemorySubtitleCache subtitle,
  required Future<ResponseBody> Function(RequestOptions request) handler,
  required bool initialized,
  RuntimeResetCoordinator? reset,
  PrivateCacheResetCoordinator? privateCacheReset,
}) => ProviderContainer(
  overrides: [
    secureKeyValueStoreProvider.overrideWithValue(memory),
    subtitleCacheProvider.overrideWithValue(subtitle),
    serverProbeProvider.overrideWithValue(_Probe(initialized)),
    if (reset != null) runtimeResetProvider.overrideWithValue(reset),
    if (privateCacheReset != null)
      privateCacheResetProvider.overrideWithValue(privateCacheReset),
    apiClientFactoryProvider.overrideWithValue((profile, session) {
      final dio = Dio(BaseOptions(baseUrl: '${profile.baseUri}/api/v1/'))
        ..httpClientAdapter = _Adapter(handler);
      return ApiClient(dio: dio, sessionStore: session);
    }),
  ],
);

class _Probe implements ServerProbe {
  const _Probe(this.initialized);

  final bool initialized;

  @override
  Future<BootstrapStatus> test(ServerProfile profile) async =>
      BootstrapStatus(initialized: initialized, apiVersion: 1);
}

class _Adapter implements HttpClientAdapter {
  const _Adapter(this.handler);

  final Future<ResponseBody> Function(RequestOptions request) handler;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) => handler(options);

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

ResponseBody _errorResponse(int status, String code) =>
    _jsonResponse(status, <String, Object?>{
      'code': code,
      'message': 'Request failed.',
      'request_id': 'request-test',
    });

Map<String, Object?> _tokenJson({
  String accessToken = 'access-token',
  String refreshToken = 'refresh-token',
}) => <String, Object?>{
  'access_token': accessToken,
  'refresh_token': refreshToken,
  'token_type': 'Bearer',
  'access_expires_at': '2026-07-29T12:15:00Z',
  'refresh_expires_at': '2026-08-29T12:00:00Z',
};

int _moviePageCount(Map<String, Object?> json) {
  final items = json['items'];
  if (items is! List) throw const ProtocolException('items must be an array');
  return items.length;
}
