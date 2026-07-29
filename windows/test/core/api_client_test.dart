import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/api/server_profile.dart';
import 'package:sakuraplayer_windows/core/auth/session_store.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';
import 'package:sakuraplayer_windows/core/storage/subtitle_cache.dart';

void main() {
  group('secure session', () {
    test('generates one UUID v4 and preserves it while tokens clear', () async {
      final memory = MemorySecureKeyValueStore();
      final secure = SecureStore(memory);
      final session = SessionStore(secure);

      final first = await secure.clientInstanceId();
      await session.setTokens(_tokens('access-old', 'refresh-old'));
      await session.clearTokens();
      final second = await secure.clientInstanceId();

      expect(second, first);
      expect(first[14], '4');
      expect('89ab'.contains(first[19].toLowerCase()), isTrue);
      expect(memory.values[SecureStore.refreshTokenKey], isNull);
      expect(memory.values[SecureStore.clientInstanceIdKey], first);
      expect(memory.values.values, isNot(contains('access-old')));
    });
  });

  group('server address policy', () {
    const policy = ServerAddressPolicy();

    test('normalizes HTTPS and loopback HTTP', () {
      expect(
        policy.normalize(' HTTPS://Example.COM:8443/ ').baseUri.toString(),
        'https://example.com:8443',
      );
      expect(
        policy.normalize('http://127.0.0.1:8000').baseUri.toString(),
        'http://127.0.0.1:8000',
      );
    });

    test('rejects credentials, query, fragment and paths', () {
      for (final input in <String>[
        'https://user@example.com',
        'https://example.com?token=x',
        'https://example.com/#part',
        'https://example.com/api/v1',
        'https://example.com/%2e%2e/api',
      ]) {
        expect(
          () => policy.normalize(input),
          throwsA(isA<ServerAddressException>()),
        );
      }
    });

    test('requires confirmation for private HTTP and rejects public HTTP', () {
      expect(
        () => policy.normalize('http://192.168.1.10:8000'),
        throwsA(
          isA<ServerAddressException>().having(
            (error) => error.code,
            'code',
            'private_http_confirmation_required',
          ),
        ),
      );
      expect(
        policy
            .normalize('http://192.168.1.10:8000', allowPrivateHttp: true)
            .baseUri
            .host,
        '192.168.1.10',
      );
      expect(
        () => policy.normalize('http://8.8.8.8'),
        throwsA(
          isA<ServerAddressException>().having(
            (error) => error.code,
            'code',
            'public_http_forbidden',
          ),
        ),
      );
      expect(
        () => policy.normalize('http://media.home'),
        throwsA(isA<ServerAddressException>()),
      );
      for (final deceptiveHost in <String>[
        'http://127.evil.com.foo',
        'http://fc.example',
        'http://fe80.example',
      ]) {
        expect(
          () => policy.normalize(deceptiveHost, allowPrivateHttp: true),
          throwsA(
            isA<ServerAddressException>().having(
              (error) => error.code,
              'code',
              'public_http_forbidden',
            ),
          ),
        );
      }
      expect(
        policy
            .normalize('http://[fd00::1]:8000', allowPrivateHttp: true)
            .baseUri
            .host,
        'fd00::1',
      );
    });
  });

  group('API client', () {
    test('concurrent 401 responses share one refresh and retry once', () async {
      final secure = SecureStore(MemorySecureKeyValueStore());
      final session = SessionStore(secure);
      await session.setTokens(_tokens('access-old', 'refresh-old'));
      final adapter = _QueueAdapter((request) async {
        if (request.path.endsWith('auth/refresh')) {
          adapterRefreshCalls++;
          await refreshGate.future;
          return _jsonResponse(200, _tokenJson('access-new', 'refresh-new'));
        }
        final authorization = request.headers['Authorization'];
        if (authorization == 'Bearer access-old') {
          return _errorResponse(401, 'access_expired');
        }
        expect(authorization, 'Bearer access-new');
        return _jsonResponse(200, <String, Object?>{'ok': true});
      });
      adapterRefreshCalls = 0;
      refreshGate = Completer<void>();
      final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
        ..httpClientAdapter = adapter;
      final client = ApiClient(dio: dio, sessionStore: session);

      final first = client.get('movies', decode: _okResponse);
      final second = client.get('actors', decode: _okResponse);
      await Future<void>.delayed(Duration.zero);
      refreshGate.complete();

      expect(await first, isTrue);
      expect(await second, isTrue);
      expect(adapterRefreshCalls, 1);
      expect(await secure.readRefreshToken(), 'refresh-new');
    });

    test(
      'a late 401 from the old access token does not refresh again',
      () async {
        final secure = SecureStore(MemorySecureKeyValueStore());
        final session = SessionStore(secure);
        await session.setTokens(_tokens('access-old', 'refresh-old'));
        final releaseLateResponse = Completer<void>();
        var refreshCalls = 0;
        final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
          ..httpClientAdapter = _QueueAdapter((request) async {
            final path = request.path;
            if (path.endsWith('auth/refresh')) {
              refreshCalls++;
              return _jsonResponse(
                200,
                _tokenJson('access-new', 'refresh-new'),
              );
            }
            final authorization = request.headers['Authorization'];
            if (authorization == 'Bearer access-old') {
              if (path.endsWith('actors')) {
                await releaseLateResponse.future;
                await Future<void>.delayed(Duration.zero);
              }
              return _errorResponse(401, 'access_expired');
            }
            expect(authorization, 'Bearer access-new');
            if (path.endsWith('movies') && !releaseLateResponse.isCompleted) {
              releaseLateResponse.complete();
            }
            return _jsonResponse(200, <String, Object?>{'ok': true});
          });
        final client = ApiClient(dio: dio, sessionStore: session);

        final first = client.get('movies', decode: _okResponse);
        final second = client.get('actors', decode: _okResponse);

        expect(await first, isTrue);
        expect(await second, isTrue);
        expect(refreshCalls, 1);
      },
    );

    test('refresh failure clears local tokens and does not loop', () async {
      final secure = SecureStore(MemorySecureKeyValueStore());
      final session = SessionStore(secure);
      await session.setTokens(_tokens('access-old', 'refresh-old'));
      var refreshCalls = 0;
      final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
        ..httpClientAdapter = _QueueAdapter((request) async {
          if (request.path.endsWith('auth/refresh')) {
            refreshCalls++;
            return _errorResponse(401, 'refresh_replayed');
          }
          return _errorResponse(401, 'access_expired');
        });
      final client = ApiClient(dio: dio, sessionStore: session);

      await expectLater(
        client.get('movies', decode: _okResponse),
        throwsA(
          isA<ApiException>().having(
            (error) => error.code,
            'code',
            'refresh_replayed',
          ),
        ),
      );

      expect(refreshCalls, 1);
      expect(session.accessToken, isNull);
      expect(await secure.readRefreshToken(), isNull);
    });

    test(
      'maps structured server errors without exposing response payloads',
      () async {
        final secure = SecureStore(MemorySecureKeyValueStore());
        final session = SessionStore(secure);
        await session.setTokens(_tokens('access', 'refresh'));
        final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
          ..httpClientAdapter = _QueueAdapter(
            (_) async => _errorResponse(409, 'version_conflict'),
          );
        final client = ApiClient(dio: dio, sessionStore: session);

        await expectLater(
          client.post('settings', decode: _okResponse),
          throwsA(
            isA<ApiException>()
                .having((error) => error.code, 'code', 'version_conflict')
                .having((error) => error.statusCode, 'status', 409)
                .having(
                  (error) => error.requestId,
                  'request id',
                  'request-test',
                ),
          ),
        );
      },
    );

    test(
      'rejects absolute and traversal request paths before attaching auth',
      () async {
        final secure = SecureStore(MemorySecureKeyValueStore());
        final session = SessionStore(secure);
        await session.setTokens(_tokens('access', 'refresh'));
        final client = ApiClient(
          dio: Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/')),
          sessionStore: session,
        );

        expect(
          () =>
              client.get('https://attacker.test/collect', decode: _okResponse),
          throwsArgumentError,
        );
        expect(
          () => client.get('../collect', decode: _okResponse),
          throwsArgumentError,
        );
      },
    );

    test('maps certificate failures without a TLS bypass', () async {
      final session = SessionStore(SecureStore(MemorySecureKeyValueStore()));
      final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
        ..httpClientAdapter = _QueueAdapter((request) async {
          throw DioException(
            requestOptions: request,
            type: DioExceptionType.connectionError,
            error: const HandshakeException('CERTIFICATE_VERIFY_FAILED'),
          );
        });
      final client = ApiClient(dio: dio, sessionStore: session);

      await expectLater(
        client.bootstrapStatus(),
        throwsA(
          isA<ApiException>().having(
            (error) => error.code,
            'code',
            'client_tls_error',
          ),
        ),
      );
    });
  });

  group('strict DTO parsing', () {
    test('rejects token type and malformed snapshot fields', () {
      final token = _tokenJson('access', 'refresh')..['token_type'] = 'Basic';
      expect(
        () => TokenPair.fromJson(token),
        throwsA(isA<ProtocolException>()),
      );

      expect(
        () => QueueSnapshot.fromJson(<String, Object?>{
          'metadata_queued': -1,
          'metadata_running': 0,
          'cache_queued': 0,
          'cache_running': 0,
          'cache_ready': 0,
        }),
        throwsA(isA<ProtocolException>()),
      );
    });
  });

  test('subtitle cleanup stays inside the private application root', () async {
    final temporary = await Directory.systemTemp.createTemp('sakura-task202-');
    try {
      final applicationRoot = Directory(
        '${temporary.path}${Platform.pathSeparator}SakuraPlayer',
      );
      final cache = DirectorySubtitleCache(applicationRoot: applicationRoot);
      await cache.directory.create(recursive: true);
      await File(
        '${cache.directory.path}${Platform.pathSeparator}subtitle.ass',
      ).writeAsString('fixture subtitle');
      final sibling = File(
        '${applicationRoot.path}${Platform.pathSeparator}keep.txt',
      );
      await sibling.writeAsString('keep');

      await cache.clear();

      expect(await cache.directory.exists(), isFalse);
      expect(await sibling.exists(), isTrue);
    } finally {
      await temporary.delete(recursive: true);
    }
  });
}

late Completer<void> refreshGate;
int adapterRefreshCalls = 0;

bool _okResponse(Map<String, Object?> json) {
  final value = json['ok'];
  if (value is! bool) throw const ProtocolException('ok must be a boolean');
  return value;
}

TokenPair _tokens(String access, String refresh) => TokenPair(
  accessToken: access,
  refreshToken: refresh,
  accessExpiresAt: DateTime.utc(2026, 7, 29, 12, 15),
  refreshExpiresAt: DateTime.utc(2026, 8, 29, 12),
);

Map<String, Object?> _tokenJson(String access, String refresh) =>
    <String, Object?>{
      'access_token': access,
      'refresh_token': refresh,
      'token_type': 'Bearer',
      'access_expires_at': '2026-07-29T12:15:00Z',
      'refresh_expires_at': '2026-08-29T12:00:00Z',
    };

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

class _QueueAdapter implements HttpClientAdapter {
  _QueueAdapter(this.handler);

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
