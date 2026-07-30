import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/auth/session_store.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';
import 'package:sakuraplayer_windows/features/auth/domain/auth_session_state.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/movies/data/movie_detail_api.dart';
import 'package:sakuraplayer_windows/features/movies/presentation/movie_detail_controller.dart';

void main() {
  group('movie detail contract', () {
    test('parses shared summary, enrichment, actors and ordered sources', () {
      final detail = MovieDetailDto.fromJson(_detailJson());

      expect(detail.number, 'ABC-123');
      expect(detail.releaseDate, '2026-07-29');
      expect(detail.actors.single.displayName, '测试女优');
      expect(detail.plotImageUrls, <String>[_plotUrl]);
      expect(detail.sources.map((source) => source.availability), <Object?>[
        MovieSourceAvailability.available,
        MovieSourceAvailability.rejected,
      ]);
      expect(detail.sources.first.resourceSizeMb, 2048);
      expect(detail.sources.first.videoFileSizeBytes, isNull);
    });

    test('rejects unknown states, duplicate collections and unsafe images', () {
      expect(
        () => MovieSourceDto.fromJson(_sourceJson()..['availability'] = 'raw'),
        throwsA(isA<ProtocolException>()),
      );
      expect(
        () => MovieDetailDto.fromJson(
          _detailJson()..['tags'] = <Object?>['剧情', '剧情'],
        ),
        throwsA(isA<ProtocolException>()),
      );
      expect(
        () => MovieDetailDto.fromJson(
          _detailJson()
            ..['plot_image_urls'] = <Object?>['https://attacker.test/a.jpg'],
        ),
        throwsA(isA<ProtocolException>()),
      );
      expect(isValidMovieId(movieId), isTrue);
      expect(isValidMovieId('not-a-movie-id'), isFalse);
    });

    test(
      'uses authenticated detail, image and empty favorite requests',
      () async {
        final session = SessionStore(SecureStore(MemorySecureKeyValueStore()));
        await session.setTokens(_tokens());
        final adapter = _MovieDetailAdapter();
        final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
          ..httpClientAdapter = adapter;
        final api = MovieDetailApi(ApiClient(dio: dio, sessionStore: session));

        await api.getMovie(movieId);
        expect(await api.loadCatalogImage(_plotUrl), <int>[1, 2, 3]);
        await api.setFavorite(movieId, enabled: true);
        await api.setFavorite(movieId, enabled: false);

        expect(adapter.requests.map((request) => request.method), <String>[
          'GET',
          'GET',
          'PUT',
          'DELETE',
        ]);
        expect(adapter.requests.first.path, 'movies/$movieId');
        expect(adapter.requests[1].path, 'catalog/images/$plotImageId');
        expect(adapter.requests[2].path, 'movies/$movieId/favorite');
        for (final request in adapter.requests) {
          expect(request.headers['Authorization'], 'Bearer access-token');
        }
      },
    );

    test('rejects a non-204 favorite success response', () async {
      final session = SessionStore(SecureStore(MemorySecureKeyValueStore()));
      await session.setTokens(_tokens());
      final adapter = _MovieDetailAdapter(favoriteStatus: 200);
      final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
        ..httpClientAdapter = adapter;
      final api = MovieDetailApi(ApiClient(dio: dio, sessionStore: session));

      await expectLater(
        api.setFavorite(movieId, enabled: true),
        throwsA(
          isA<ApiException>().having(
            (error) => error.code,
            'code',
            'client_protocol_error',
          ),
        ),
      );
    });

    test('rejects collections beyond the contract limit', () {
      expect(
        () => MovieDetailDto.fromJson(
          _detailJson()
            ..['tags'] = List<Object?>.generate(101, (index) => '标签$index'),
        ),
        throwsA(isA<ProtocolException>()),
      );
    });
  });

  group('movie detail controller', () {
    test('movie changes isolate late detail responses', () async {
      final gateway = _ControlledMovieDetailGateway();
      final container = _container(gateway);
      addTearDown(container.dispose);
      final controller = container.read(movieDetailControllerProvider.notifier);

      final first = controller.load(movieId);
      final second = controller.load(secondMovieId);
      gateway.completeDetail(1, _detail(id: secondMovieId, title: '当前影片'));
      await second;
      gateway.completeDetail(0, _detail(title: '迟到影片'));
      await first;

      final state = container.read(movieDetailControllerProvider);
      expect(state.movieId, secondMovieId);
      expect(state.detail?.title, '当前影片');
      expect(state.status, MovieDetailStatus.ready);
    });

    test('not found is distinct and retry loads the current movie', () async {
      final gateway = _ControlledMovieDetailGateway();
      final container = _container(gateway);
      addTearDown(container.dispose);
      final controller = container.read(movieDetailControllerProvider.notifier);

      final failed = controller.load(movieId);
      gateway.failDetail(
        0,
        const ApiException(
          code: 'resource_not_found',
          message: 'not found',
          statusCode: 404,
        ),
      );
      await failed;
      expect(container.read(movieDetailControllerProvider).isNotFound, isTrue);

      final retry = controller.retry();
      gateway.completeDetail(1, _detail());
      await retry;
      expect(
        container.read(movieDetailControllerProvider).status,
        MovieDetailStatus.ready,
      );
    });

    test(
      'favorite failure preserves value and blocks duplicate mutation',
      () async {
        final gateway = _ControlledMovieDetailGateway();
        final container = _container(gateway);
        addTearDown(container.dispose);
        final controller = container.read(
          movieDetailControllerProvider.notifier,
        );
        final load = controller.load(movieId);
        gateway.completeDetail(0, _detail());
        await load;

        final first = controller.setFavorite(enabled: true);
        final duplicate = controller.setFavorite(enabled: true);
        expect(gateway.favoriteRequests, hasLength(1));
        gateway.failFavorite(
          0,
          const ApiException(code: 'offline', message: 'offline'),
        );
        await Future.wait(<Future<void>>[first, duplicate]);

        final failed = container.read(movieDetailControllerProvider);
        expect(failed.detail?.favorite, isFalse);
        expect(failed.favoriteErrorCode, 'offline');
        expect(failed.isFavoriteInFlight, isFalse);

        final retry = controller.setFavorite(enabled: true);
        gateway.completeFavorite(1);
        await retry;
        expect(
          container.read(movieDetailControllerProvider).detail?.favorite,
          isTrue,
        );
      },
    );

    test(
      'requires explicit non-rejected source and emits only source id',
      () async {
        final gateway = _ControlledMovieDetailGateway();
        final container = _container(gateway);
        addTearDown(container.dispose);
        final controller = container.read(
          movieDetailControllerProvider.notifier,
        );
        final load = controller.load(movieId);
        gateway.completeDetail(0, _detail());
        await load;
        final emitted = <String>[];

        controller.playSelected(emitted.add);
        controller.selectSource(rejectedSourceId);
        controller.playSelected(emitted.add);
        expect(emitted, isEmpty);

        controller.selectSource(sourceId);
        controller.playSelected(emitted.add);
        expect(emitted, <String>[sourceId]);
        expect(
          container.read(movieDetailControllerProvider).selectedSourceId,
          sourceId,
        );
      },
    );

    test('reload clears a selected source that no longer exists', () async {
      final gateway = _ControlledMovieDetailGateway();
      final container = _container(gateway);
      addTearDown(container.dispose);
      final controller = container.read(movieDetailControllerProvider.notifier);
      final first = controller.load(movieId);
      gateway.completeDetail(0, _detail());
      await first;
      controller.selectSource(sourceId);

      final reload = controller.load(movieId);
      gateway.completeDetail(
        1,
        MovieDetailDto.fromJson(
          _detailJson()
            ..['sources'] = <Object?>[
              _sourceJson(
                id: rejectedSourceId,
                availability: 'rejected',
                postId: 2,
              ),
            ],
        ),
      );
      await reload;

      expect(
        container.read(movieDetailControllerProvider).selectedSourceId,
        isNull,
      );
    });

    test(
      'server session change clears state and ignores old response',
      () async {
        final gateway = _ControlledMovieDetailGateway();
        final container = ProviderContainer(
          overrides: [
            movieDetailGatewayProvider.overrideWithValue(gateway),
            authSessionStateProvider.overrideWith(
              (ref) => ref.watch(_mutableAuthProvider),
            ),
          ],
        );
        addTearDown(container.dispose);
        final request = container
            .read(movieDetailControllerProvider.notifier)
            .load(movieId);

        container
            .read(_mutableAuthProvider.notifier)
            .replace(
              AuthSessionState.authenticated(
                serverBaseUri: Uri.parse('https://new-server.test'),
              ),
            );
        await Future<void>.delayed(Duration.zero);
        gateway.completeDetail(0, _detail());
        await request;

        final state = container.read(movieDetailControllerProvider);
        expect(state.status, MovieDetailStatus.idle);
        expect(state.detail, isNull);
        expect(state.selectedSourceId, isNull);
      },
    );
  });
}

const movieId = '00000000-0000-4000-8000-000000000101';
const secondMovieId = '00000000-0000-4000-8000-000000000102';
const sourceId = '00000000-0000-4000-8000-000000000201';
const rejectedSourceId = '00000000-0000-4000-8000-000000000202';
const actorId = '00000000-0000-4000-8000-000000000301';
const plotImageId = '00000000-0000-4000-8000-000000000401';
const _plotUrl = '/api/v1/catalog/images/$plotImageId';

Map<String, Object?> _detailJson({
  String id = movieId,
  String title = '测试影片',
  bool favorite = false,
}) => <String, Object?>{
  'id': id,
  'number': 'ABC-123',
  'title': title,
  'title_original': 'テスト映画',
  'cover_url': '/api/v1/catalog/images/$movieId',
  'publish_date': '2026-07-30',
  'labels': <Object?>['subtitle', '4k'],
  'favorite': favorite,
  'source_count': 2,
  'progress': <String, Object?>{
    'position_seconds': 120,
    'duration_seconds': 600,
    'completed': false,
    'version': 1,
  },
  'release_date': '2026-07-29',
  'maker': '测试厂商',
  'series': '测试系列',
  'director': '测试导演',
  'score': 8.5,
  'description': '中文简介',
  'description_original': '日本語紹介',
  'actors': <Object?>[
    <String, Object?>{
      'id': actorId,
      'display_name': '测试女优',
      'name_ja': 'テスト',
      'name_zh': '测试女优',
      'aliases': <Object?>[],
      'profile_url': null,
      'favorite': false,
    },
  ],
  'tags': <Object?>['剧情', '单体作品'],
  'plot_image_urls': <Object?>[_plotUrl],
  'sources': <Object?>[
    _sourceJson(),
    _sourceJson(id: rejectedSourceId, availability: 'rejected', postId: 2),
  ],
};

Map<String, Object?> _sourceJson({
  String id = sourceId,
  String availability = 'available',
  int postId = 1,
}) => <String, Object?>{
  'id': id,
  'website': 'sehuatang',
  'external_post_id': postId,
  'title': '测试来源 $postId',
  'publish_date': '2026-07-28',
  'category': '中文字幕',
  'labels': <Object?>['subtitle', 'cracked', '4k', 'censored'],
  'resource_size_mb': 2048,
  'video_file_size_bytes': null,
  'availability': availability,
};

MovieDetailDto _detail({String id = movieId, String title = '测试影片'}) =>
    MovieDetailDto.fromJson(_detailJson(id: id, title: title));

TokenPair _tokens() => TokenPair(
  accessToken: 'access-token',
  refreshToken: 'refresh-token',
  accessExpiresAt: DateTime.utc(2026, 7, 30, 12, 15),
  refreshExpiresAt: DateTime.utc(2026, 8, 30, 12),
);

ProviderContainer _container(MovieDetailGateway gateway) => ProviderContainer(
  overrides: [movieDetailGatewayProvider.overrideWithValue(gateway)],
);

final _mutableAuthProvider =
    NotifierProvider<_MutableAuthController, AuthSessionState>(
      _MutableAuthController.new,
    );

class _MutableAuthController extends Notifier<AuthSessionState> {
  @override
  AuthSessionState build() => AuthSessionState.authenticated(
    serverBaseUri: Uri.parse('https://server.test'),
  );

  void replace(AuthSessionState value) => state = value;
}

class _FavoriteRequest {
  const _FavoriteRequest(this.movieId, this.enabled);

  final String movieId;
  final bool enabled;
}

class _ControlledMovieDetailGateway implements MovieDetailGateway {
  final List<Completer<MovieDetailDto>> _detailCompleters =
      <Completer<MovieDetailDto>>[];
  final List<Completer<void>> _favoriteCompleters = <Completer<void>>[];
  final List<_FavoriteRequest> favoriteRequests = <_FavoriteRequest>[];

  @override
  Future<MovieDetailDto> getMovie(String movieId) {
    final completer = Completer<MovieDetailDto>();
    _detailCompleters.add(completer);
    return completer.future;
  }

  void completeDetail(int index, MovieDetailDto detail) =>
      _detailCompleters[index].complete(detail);

  void failDetail(int index, Object error) =>
      _detailCompleters[index].completeError(error);

  @override
  Future<List<int>> loadCatalogImage(String imageUrl) async => <int>[];

  @override
  Future<void> setFavorite(String movieId, {required bool enabled}) {
    favoriteRequests.add(_FavoriteRequest(movieId, enabled));
    final completer = Completer<void>();
    _favoriteCompleters.add(completer);
    return completer.future;
  }

  void completeFavorite(int index) => _favoriteCompleters[index].complete();

  void failFavorite(int index, Object error) =>
      _favoriteCompleters[index].completeError(error);
}

class _MovieDetailAdapter implements HttpClientAdapter {
  _MovieDetailAdapter({this.favoriteStatus = 204});

  final int favoriteStatus;
  final List<RequestOptions> requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (options.method == 'GET' && options.path == 'movies/$movieId') {
      return _jsonResponse(200, _detailJson());
    }
    if (options.method == 'GET' &&
        options.path == 'catalog/images/$plotImageId') {
      return ResponseBody.fromBytes(<int>[1, 2, 3], 200);
    }
    if (options.path == 'movies/$movieId/favorite') {
      return ResponseBody.fromString('', favoriteStatus);
    }
    throw StateError('unexpected request ${options.method} ${options.path}');
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
