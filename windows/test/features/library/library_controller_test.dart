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
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';
import 'package:sakuraplayer_windows/features/library/presentation/library_controller.dart';

void main() {
  group('movies contract', () {
    test(
      'encodes every filter with stable defaults and omits empty values',
      () {
        expect(const MovieFilters().toQuery(), <String, Object?>{
          'limit': 24,
          'sort': 'publish_date_desc',
        });

        final query = MovieFilters(
          categories: avdbCategories.toSet(),
          labels: movieSourceLabels.toSet(),
          sourceWebsite: MovieSourceWebsite.x1080x,
          playable: false,
          minResourceSizeMb: 512,
          maxResourceSizeMb: 4096,
          favorite: true,
          sort: MovieSort.numberAsc,
        ).toQuery(cursor: 'next-page');

        expect(query, <String, Object?>{
          'limit': 24,
          'sort': 'number_asc',
          'categories': '亚洲有码,亚洲无码,中文字幕,4K原版,素人有码,FC2',
          'labels': 'subtitle,cracked,4k,censored',
          'source_website': 'x1080x',
          'playable': false,
          'min_resource_size_mb': 512,
          'max_resource_size_mb': 4096,
          'favorite': true,
          'cursor': 'next-page',
        });
        expect(
          const MovieFilters(
            sourceWebsite: MovieSourceWebsite.sehuatang,
            playable: true,
          ).toQuery(),
          containsPair('playable', true),
        );
      },
    );

    test('parses a strict page and validates progress and cover paths', () {
      final page = MoviePageDto.fromJson(
        _pageJson(
          nextCursor: 'cursor-2',
          progress: <String, Object?>{
            'position_seconds': 300,
            'duration_seconds': 1200,
            'completed': false,
            'version': 2,
          },
        ),
      );

      expect(page.items.single.number, 'ABC-123');
      expect(page.items.single.progress!.fraction, 0.25);
      expect(page.nextCursor, 'cursor-2');
      expect(
        MoviesApi.catalogImagePath(page.items.single.coverUrl!),
        'catalog/images/00000000-0000-4000-8000-000000000010',
      );

      final invalidProgress = _pageJson(
        progress: <String, Object?>{
          'position_seconds': 1,
          'duration_seconds': null,
          'completed': false,
          'version': 0,
        },
      );
      expect(
        () => MoviePageDto.fromJson(invalidProgress),
        throwsA(isA<ProtocolException>()),
      );
      expect(
        () => MoviesApi.catalogImagePath('https://attacker.test/cover.jpg'),
        throwsArgumentError,
      );
    });

    test('rejects unknown labels, invalid dates and oversized pages', () {
      final unknownLabel = _pageJson();
      ((unknownLabel['items']! as List<Object?>).single
          as Map<String, Object?>)['labels'] = <Object?>['unknown'];
      expect(
        () => MoviePageDto.fromJson(unknownLabel),
        throwsA(isA<ProtocolException>()),
      );

      final invalidDate = _pageJson();
      ((invalidDate['items']! as List<Object?>).single
              as Map<String, Object?>)['publish_date'] =
          '2026-07-30T12:00:00Z';
      expect(
        () => MoviePageDto.fromJson(invalidDate),
        throwsA(isA<ProtocolException>()),
      );

      final oversized = _pageJson();
      oversized['items'] = List<Object?>.filled(101, _movieJson());
      expect(
        () => MoviePageDto.fromJson(oversized),
        throwsA(isA<ProtocolException>()),
      );
    });

    test(
      'actual API sends filters and authenticated catalog image requests',
      () async {
        final session = SessionStore(SecureStore(MemorySecureKeyValueStore()));
        await session.setTokens(
          TokenPair(
            accessToken: 'access-token',
            refreshToken: 'refresh-token',
            accessExpiresAt: DateTime.utc(2026, 7, 30, 12, 15),
            refreshExpiresAt: DateTime.utc(2026, 8, 30, 12),
          ),
        );
        final adapter = _RecordingAdapter();
        final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
          ..httpClientAdapter = adapter;
        final api = MoviesApi(ApiClient(dio: dio, sessionStore: session));

        final page = await api.listMovies(
          filters: const MovieFilters(
            categories: <String>{'FC2'},
            favorite: true,
          ),
        );
        final bytes = await api.loadCover(
          '/api/v1/catalog/images/00000000-0000-4000-8000-000000000010',
        );

        expect(page.items.single.number, 'ABC-123');
        expect(bytes, <int>[1, 2, 3]);
        expect(adapter.requests, hasLength(2));
        expect(
          adapter.requests.first.queryParameters,
          containsPair('categories', 'FC2'),
        );
        expect(
          adapter.requests.first.queryParameters,
          containsPair('favorite', true),
        );
        expect(
          adapter.requests.last.path,
          'catalog/images/00000000-0000-4000-8000-000000000010',
        );
        for (final request in adapter.requests) {
          expect(request.headers['Authorization'], 'Bearer access-token');
        }
      },
    );
  });

  group('library controller', () {
    test('loads the default first page and exposes the next cursor', () async {
      final gateway = _SequenceMoviesGateway(<Object>[
        MoviePageDto.fromJson(_pageJson(nextCursor: 'cursor-2')),
      ]);
      final container = _container(gateway);
      addTearDown(container.dispose);

      await container.read(libraryControllerProvider.notifier).loadInitial();

      final state = container.read(libraryControllerProvider);
      expect(state.status, LibraryStatus.ready);
      expect(state.items.single.number, 'ABC-123');
      expect(state.nextCursor, 'cursor-2');
      expect(gateway.requests.single.filters, const MovieFilters());
      expect(gateway.requests.single.cursor, isNull);
    });

    test(
      'late success and failure from an old filter never write back',
      () async {
        final gateway = _ControlledMoviesGateway();
        final container = _container(gateway);
        addTearDown(container.dispose);
        final controller = container.read(libraryControllerProvider.notifier);

        final first = controller.applyFilters(
          const MovieFilters(categories: <String>{'FC2'}),
        );
        final second = controller.applyFilters(
          const MovieFilters(categories: <String>{'中文字幕'}),
        );
        gateway.complete(
          1,
          MoviePageDto.fromJson(_pageJson(number: 'NEW-002')),
        );
        await second;
        gateway.fail(
          0,
          const ApiException(code: 'old_failed', message: 'old failed'),
        );
        await first;

        final state = container.read(libraryControllerProvider);
        expect(state.status, LibraryStatus.ready);
        expect(state.items.single.number, 'NEW-002');
        expect(state.errorCode, isNull);
      },
    );

    test('duplicate bottom triggers share one append request', () async {
      final gateway = _ControlledMoviesGateway();
      final container = _container(gateway);
      addTearDown(container.dispose);
      final controller = container.read(libraryControllerProvider.notifier);

      final firstPage = controller.loadInitial();
      gateway.complete(
        0,
        MoviePageDto.fromJson(_pageJson(nextCursor: 'cursor-2')),
      );
      await firstPage;

      final append = controller.loadMore();
      final duplicate = controller.loadMore();
      expect(gateway.requests, hasLength(2));
      gateway.complete(1, MoviePageDto.fromJson(_pageJson(number: 'DEF-456')));
      await Future.wait(<Future<void>>[append, duplicate]);

      expect(
        container
            .read(libraryControllerProvider)
            .items
            .map((movie) => movie.number),
        <String>['ABC-123', 'DEF-456'],
      );
    });

    test(
      'append failure preserves items and retries the same cursor',
      () async {
        final gateway = _SequenceMoviesGateway(<Object>[
          MoviePageDto.fromJson(_pageJson(nextCursor: 'cursor-2')),
          const ApiException(code: 'upstream_unavailable', message: 'failed'),
          MoviePageDto.fromJson(_pageJson(number: 'DEF-456')),
        ]);
        final container = _container(gateway);
        addTearDown(container.dispose);
        final controller = container.read(libraryControllerProvider.notifier);

        await controller.loadInitial();
        await controller.loadMore();
        var state = container.read(libraryControllerProvider);
        expect(state.items.single.number, 'ABC-123');
        expect(state.nextCursor, 'cursor-2');
        expect(state.appendErrorCode, 'upstream_unavailable');

        await controller.retryAppend();
        state = container.read(libraryControllerProvider);
        expect(state.items, hasLength(2));
        expect(state.appendErrorCode, isNull);
        expect(gateway.requests[1].cursor, 'cursor-2');
        expect(gateway.requests[2].cursor, 'cursor-2');
      },
    );

    test(
      'invalid append cursor recovers the current first page once',
      () async {
        final filters = const MovieFilters(labels: <String>{'subtitle'});
        final gateway = _SequenceMoviesGateway(<Object>[
          MoviePageDto.fromJson(_pageJson(nextCursor: 'stale')),
          const ApiException(
            code: 'validation_failed',
            message: 'invalid cursor',
            statusCode: 422,
          ),
          MoviePageDto.fromJson(_pageJson(number: 'REFRESH-9')),
        ]);
        final container = _container(gateway);
        addTearDown(container.dispose);
        final controller = container.read(libraryControllerProvider.notifier);

        await controller.applyFilters(filters);
        await controller.loadMore();

        final state = container.read(libraryControllerProvider);
        expect(state.items.single.number, 'REFRESH-9');
        expect(state.status, LibraryStatus.ready);
        expect(gateway.requests[2].filters, filters);
        expect(gateway.requests[2].cursor, isNull);
      },
    );

    test('invalid size range stays local and sends no request', () async {
      final gateway = _SequenceMoviesGateway(<Object>[]);
      final container = _container(gateway);
      addTearDown(container.dispose);

      await container
          .read(libraryControllerProvider.notifier)
          .applyFilters(
            const MovieFilters(minResourceSizeMb: 1000, maxResourceSizeMb: 100),
          );

      final state = container.read(libraryControllerProvider);
      expect(state.status, LibraryStatus.invalid);
      expect(state.validationMessage, isNotNull);
      expect(gateway.requests, isEmpty);
    });

    test(
      'server session change clears items and ignores the old response',
      () async {
        final gateway = _ControlledMoviesGateway();
        final container = ProviderContainer(
          overrides: [
            moviesGatewayProvider.overrideWithValue(gateway),
            authSessionStateProvider.overrideWith(
              (ref) => ref.watch(_mutableAuthProvider),
            ),
          ],
        );
        addTearDown(container.dispose);
        final request =
            container.read(libraryControllerProvider.notifier).loadInitial();

        container
            .read(_mutableAuthProvider.notifier)
            .replace(
              AuthSessionState.authenticated(
                serverBaseUri: Uri.parse('https://new-server.test'),
              ),
            );
        await Future<void>.delayed(Duration.zero);
        gateway.complete(0, MoviePageDto.fromJson(_pageJson()));
        await request;

        final state = container.read(libraryControllerProvider);
        expect(state.status, LibraryStatus.idle);
        expect(state.items, isEmpty);
      },
    );
  });
}

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

ProviderContainer _container(MoviesGateway gateway) => ProviderContainer(
  overrides: [moviesGatewayProvider.overrideWithValue(gateway)],
);

Map<String, Object?> _pageJson({
  String number = 'ABC-123',
  String? nextCursor,
  Object? progress,
}) => <String, Object?>{
  'items': <Object?>[_movieJson(number: number, progress: progress)],
  'next_cursor': nextCursor,
};

Map<String, Object?> _movieJson({
  String number = 'ABC-123',
  Object? progress,
}) => <String, Object?>{
  'id':
      number == 'ABC-123'
          ? '00000000-0000-4000-8000-000000000001'
          : '00000000-0000-4000-8000-000000000002',
  'number': number,
  'title': '测试影片 $number',
  'title_original': 'テスト映画',
  'cover_url': '/api/v1/catalog/images/00000000-0000-4000-8000-000000000010',
  'publish_date': '2026-07-30',
  'labels': <Object?>['subtitle', '4k'],
  'favorite': false,
  'source_count': 2,
  'progress': progress,
};

class _MovieRequest {
  const _MovieRequest(this.filters, this.cursor);

  final MovieFilters filters;
  final String? cursor;
}

class _SequenceMoviesGateway implements MoviesGateway {
  _SequenceMoviesGateway(this.results);

  final List<Object> results;
  final List<_MovieRequest> requests = <_MovieRequest>[];

  @override
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  }) async {
    requests.add(_MovieRequest(filters, cursor));
    final result = results[requests.length - 1];
    if (result is Exception) throw result;
    return result as MoviePageDto;
  }

  @override
  Future<List<int>> loadCover(String coverUrl) async => <int>[];
}

class _ControlledMoviesGateway implements MoviesGateway {
  final List<_MovieRequest> requests = <_MovieRequest>[];
  final List<Completer<MoviePageDto>> _completers = <Completer<MoviePageDto>>[];

  @override
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  }) {
    requests.add(_MovieRequest(filters, cursor));
    final completer = Completer<MoviePageDto>();
    _completers.add(completer);
    return completer.future;
  }

  void complete(int index, MoviePageDto page) =>
      _completers[index].complete(page);

  void fail(int index, Object error) => _completers[index].completeError(error);

  @override
  Future<List<int>> loadCover(String coverUrl) async => <int>[];
}

class _RecordingAdapter implements HttpClientAdapter {
  final List<RequestOptions> requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (options.path.endsWith('movies')) {
      return ResponseBody.fromString(
        jsonEncode(_pageJson()),
        200,
        headers: <String, List<String>>{
          Headers.contentTypeHeader: <String>['application/json'],
        },
      );
    }
    return ResponseBody.fromBytes(
      <int>[1, 2, 3],
      200,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>['image/jpeg'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
