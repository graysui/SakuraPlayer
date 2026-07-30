import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/auth/session_store.dart';
import 'package:sakuraplayer_windows/core/images/gfriends_url.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';
import 'package:sakuraplayer_windows/features/actors/data/actors_api.dart';
import 'package:sakuraplayer_windows/features/actors/presentation/actors_controller.dart';
import 'package:sakuraplayer_windows/features/auth/domain/auth_session_state.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';

void main() {
  group('actors contract', () {
    test('encodes trimmed query, favorite mode, cursor and fixed limit', () {
      expect(const ActorListScope().toQuery(), <String, Object?>{'limit': 24});
      expect(
        const ActorListScope(
          query: '  樱  ',
          favorite: true,
        ).toQuery(cursor: 'next-page'),
        <String, Object?>{
          'q': '樱',
          'favorite': true,
          'limit': 24,
          'cursor': 'next-page',
        },
      );
      expect(
        () => ActorListScope(query: 'x' * 201).toQuery(),
        throwsArgumentError,
      );
    });

    test('parses strict actor detail and shared movie summaries', () {
      final detail = ActorDetailDto.fromJson(_detailJson());

      expect(detail.displayName, '樱');
      expect(detail.aliases, <String>['桜', 'Sakura']);
      expect(detail.galleryUrls, hasLength(2));
      expect(detail.movies.single.number, 'ABC-123');
      expect(detail.favorite, isFalse);
    });

    test('rejects duplicate aliases, duplicate gallery and unsafe URLs', () {
      expect(
        () => ActorSummaryDto.fromJson(
          _actorJson()..['aliases'] = <Object?>['樱', '樱'],
        ),
        throwsA(isA<ProtocolException>()),
      );
      expect(isValidActorId(actorId), isTrue);
      expect(isValidActorId('not-an-actor-id'), isFalse);
      expect(
        isAllowedGfriendsUrl(
          'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/%2e%2e/avatar.jpg',
        ),
        isFalse,
      );
      expect(
        () => ActorDetailDto.fromJson(
          _detailJson()
            ..['gallery_urls'] = <Object?>[_galleryUrl(1), _galleryUrl(1)],
        ),
        throwsA(isA<ProtocolException>()),
      );
      expect(
        () => ActorSummaryDto.fromJson(
          _actorJson()..['profile_url'] = 'https://attacker.test/avatar.jpg',
        ),
        throwsA(isA<ProtocolException>()),
      );
    });

    test(
      'uses authenticated actor paths and idempotent favorite methods',
      () async {
        final session = SessionStore(SecureStore(MemorySecureKeyValueStore()));
        await session.setTokens(_tokens());
        final adapter = _ActorsAdapter();
        final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
          ..httpClientAdapter = adapter;
        final api = ActorsApi(ApiClient(dio: dio, sessionStore: session));

        await api.listActors(
          scope: const ActorListScope(query: '樱', favorite: true),
          cursor: 'next-page',
        );
        await api.getActor(actorId);
        await api.setFavorite(actorId, enabled: true);
        await api.setFavorite(actorId, enabled: false);

        expect(adapter.requests.map((request) => request.method), <String>[
          'GET',
          'GET',
          'PUT',
          'DELETE',
        ]);
        expect(adapter.requests.first.path, 'actors');
        expect(adapter.requests.first.queryParameters, <String, Object?>{
          'q': '樱',
          'favorite': true,
          'limit': 24,
          'cursor': 'next-page',
        });
        expect(adapter.requests[1].path, 'actors/$actorId');
        expect(adapter.requests[2].path, 'actors/$actorId/favorite');
        for (final request in adapter.requests) {
          expect(request.headers['Authorization'], 'Bearer access-token');
        }
      },
    );
  });

  group('actors controller', () {
    test('scope changes isolate late responses', () async {
      final gateway = _ControlledActorsGateway();
      final container = _container(gateway);
      addTearDown(container.dispose);
      final controller = container.read(actorsControllerProvider.notifier);

      final initial = controller.ensureLoaded();
      final filtered = controller.applyScope(
        const ActorListScope(query: '樱', favorite: true),
      );
      gateway.completeList(1, _page(name: '当前结果'));
      await filtered;
      gateway.completeList(0, _page(name: '迟到结果'));
      await initial;

      final state = container.read(actorsControllerProvider);
      expect(state.scope, const ActorListScope(query: '樱', favorite: true));
      expect(state.items.single.displayName, '当前结果');
    });

    test(
      'duplicate append is ignored and failed cursor retries locally',
      () async {
        final gateway = _ControlledActorsGateway();
        final container = _container(gateway);
        addTearDown(container.dispose);
        final controller = container.read(actorsControllerProvider.notifier);

        final initial = controller.ensureLoaded();
        gateway.completeList(0, _page(nextCursor: 'cursor-2'));
        await initial;

        final append = controller.loadMore();
        final duplicate = controller.loadMore();
        expect(gateway.listRequests, hasLength(2));
        gateway.failList(
          1,
          const ApiException(code: 'offline', message: 'offline'),
        );
        await Future.wait(<Future<void>>[append, duplicate]);
        expect(
          container.read(actorsControllerProvider).appendErrorCode,
          'offline',
        );

        final retry = controller.retryAppend();
        expect(gateway.listRequests[2].cursor, 'cursor-2');
        gateway.completeList(2, _page(name: '第二页'));
        await retry;
        expect(container.read(actorsControllerProvider).items, hasLength(2));
      },
    );

    test('refresh failure preserves the successful page', () async {
      final gateway = _SequenceActorsGateway(<Object>[
        _page(nextCursor: 'cursor-2'),
        const ApiException(code: 'offline', message: 'offline'),
      ]);
      final container = _container(gateway);
      addTearDown(container.dispose);
      final controller = container.read(actorsControllerProvider.notifier);

      await controller.ensureLoaded();
      final before = container.read(actorsControllerProvider);
      await controller.refresh();
      final after = container.read(actorsControllerProvider);

      expect(after.status, ActorsStatus.ready);
      expect(after.items, before.items);
      expect(after.nextCursor, 'cursor-2');
      expect(after.refreshErrorCode, 'offline');
    });

    test(
      'invalid append cursor recovers the current first page once',
      () async {
        final gateway = _SequenceActorsGateway(<Object>[
          _page(nextCursor: 'stale'),
          const ApiException(
            code: 'validation_failed',
            message: 'invalid cursor',
            statusCode: 422,
          ),
          _page(name: '恢复结果'),
        ]);
        final container = _container(gateway);
        addTearDown(container.dispose);
        final controller = container.read(actorsControllerProvider.notifier);

        await controller.ensureLoaded();
        await controller.loadMore();

        final state = container.read(actorsControllerProvider);
        expect(state.items.single.displayName, '恢复结果');
        expect(gateway.listRequests[2].cursor, isNull);
      },
    );

    test(
      'favorite failure preserves state and success removes favorite item',
      () async {
        final gateway = _ControlledActorsGateway();
        final container = _container(gateway);
        addTearDown(container.dispose);
        final controller = container.read(actorsControllerProvider.notifier);

        final load = controller.applyScope(
          const ActorListScope(favorite: true),
        );
        gateway.completeList(0, _page(favorite: true));
        await load;

        final failed = controller.setFavorite(actorId, enabled: false);
        gateway.failFavorite(
          0,
          const ApiException(code: 'offline', message: 'offline'),
        );
        await failed;
        expect(container.read(actorsControllerProvider).items, hasLength(1));
        expect(
          container.read(actorsControllerProvider).favoriteErrorById[actorId],
          'offline',
        );

        final succeeded = controller.setFavorite(actorId, enabled: false);
        gateway.completeFavorite(1);
        await succeeded;
        expect(container.read(actorsControllerProvider).items, isEmpty);
      },
    );

    test(
      'server session change clears state and ignores old response',
      () async {
        final gateway = _ControlledActorsGateway();
        final container = ProviderContainer(
          overrides: [
            actorsGatewayProvider.overrideWithValue(gateway),
            authSessionStateProvider.overrideWith(
              (ref) => ref.watch(_mutableAuthProvider),
            ),
          ],
        );
        addTearDown(container.dispose);
        final request =
            container.read(actorsControllerProvider.notifier).ensureLoaded();

        container
            .read(_mutableAuthProvider.notifier)
            .replace(
              AuthSessionState.authenticated(
                serverBaseUri: Uri.parse('https://new-server.test'),
              ),
            );
        await Future<void>.delayed(Duration.zero);
        gateway.completeList(0, _page());
        await request;

        final state = container.read(actorsControllerProvider);
        expect(state.status, ActorsStatus.idle);
        expect(state.items, isEmpty);
        expect(state.scope, const ActorListScope());
      },
    );
  });

  group('actor detail controller', () {
    test('actor changes isolate late detail responses', () async {
      final gateway = _ControlledActorsGateway();
      final container = _container(gateway);
      addTearDown(container.dispose);
      final controller = container.read(actorDetailControllerProvider.notifier);

      final first = controller.load(actorId);
      final second = controller.load(secondActorId);
      gateway.completeDetail(1, _detail(name: '当前女优', id: secondActorId));
      await second;
      gateway.completeDetail(0, _detail(name: '迟到女优'));
      await first;

      final state = container.read(actorDetailControllerProvider);
      expect(state.actorId, secondActorId);
      expect(state.detail?.displayName, '当前女优');
      expect(state.status, ActorDetailStatus.ready);
    });

    test('detail favorite success synchronizes the loaded list', () async {
      final gateway = _ControlledActorsGateway();
      final container = _container(gateway);
      addTearDown(container.dispose);
      final listController = container.read(actorsControllerProvider.notifier);
      final detailController = container.read(
        actorDetailControllerProvider.notifier,
      );

      final listLoad = listController.ensureLoaded();
      gateway.completeList(0, _page());
      await listLoad;
      final detailLoad = detailController.load(actorId);
      gateway.completeDetail(0, _detail());
      await detailLoad;

      final mutation = detailController.setFavorite(enabled: true);
      gateway.completeFavorite(0);
      await mutation;

      expect(
        container.read(actorDetailControllerProvider).detail?.favorite,
        isTrue,
      );
      expect(
        container.read(actorsControllerProvider).items.single.favorite,
        isTrue,
      );
    });

    test('detail favorite failure preserves the previous value', () async {
      final gateway = _ControlledActorsGateway();
      final container = _container(gateway);
      addTearDown(container.dispose);
      final controller = container.read(actorDetailControllerProvider.notifier);
      final load = controller.load(actorId);
      gateway.completeDetail(0, _detail());
      await load;

      final mutation = controller.setFavorite(enabled: true);
      gateway.failFavorite(
        0,
        const ApiException(code: 'offline', message: 'offline'),
      );
      await mutation;

      final state = container.read(actorDetailControllerProvider);
      expect(state.detail?.favorite, isFalse);
      expect(state.favoriteErrorCode, 'offline');
      expect(state.isFavoriteInFlight, isFalse);
    });
  });
}

const actorId = '00000000-0000-4000-8000-000000000001';
const secondActorId = '00000000-0000-4000-8000-000000000003';

String _galleryUrl(int index) =>
    'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/Sakura/$index.jpg';

Map<String, Object?> _actorJson({String name = '樱', bool favorite = false}) =>
    <String, Object?>{
      'id': actorId,
      'display_name': name,
      'name_ja': '桜',
      'name_zh': '樱',
      'aliases': <Object?>['桜', 'Sakura'],
      'profile_url': _galleryUrl(0),
      'favorite': favorite,
    };

Map<String, Object?> _detailJson() => <String, Object?>{
  ..._actorJson(),
  'bio': '中文简介',
  'bio_original': '日本語紹介',
  'gallery_urls': <Object?>[_galleryUrl(1), _galleryUrl(2)],
  'movies': <Object?>[_movieJson()],
};

Map<String, Object?> _movieJson() => <String, Object?>{
  'id': '00000000-0000-4000-8000-000000000002',
  'number': 'ABC-123',
  'title': '关联影片',
  'title_original': null,
  'cover_url': null,
  'publish_date': '2026-07-30',
  'labels': <Object?>['subtitle'],
  'favorite': false,
  'source_count': 1,
  'progress': null,
};

ActorPageDto _page({
  String name = '樱',
  bool favorite = false,
  String? nextCursor,
}) => ActorPageDto.fromJson(<String, Object?>{
  'items': <Object?>[_actorJson(name: name, favorite: favorite)],
  'next_cursor': nextCursor,
});

ActorDetailDto _detail({String name = '樱', String id = actorId}) =>
    ActorDetailDto.fromJson(<String, Object?>{
      ..._detailJson(),
      'id': id,
      'display_name': name,
    });

TokenPair _tokens() => TokenPair(
  accessToken: 'access-token',
  refreshToken: 'refresh-token',
  accessExpiresAt: DateTime.utc(2026, 7, 30, 12, 15),
  refreshExpiresAt: DateTime.utc(2026, 8, 30, 12),
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

ProviderContainer _container(ActorsGateway gateway) => ProviderContainer(
  overrides: [actorsGatewayProvider.overrideWithValue(gateway)],
);

class _ActorListRequest {
  const _ActorListRequest(this.scope, this.cursor);

  final ActorListScope scope;
  final String? cursor;
}

class _SequenceActorsGateway implements ActorsGateway {
  _SequenceActorsGateway(this.results);

  final List<Object> results;
  final List<_ActorListRequest> listRequests = <_ActorListRequest>[];

  @override
  Future<ActorPageDto> listActors({
    required ActorListScope scope,
    String? cursor,
  }) async {
    listRequests.add(_ActorListRequest(scope, cursor));
    final result = results[listRequests.length - 1];
    if (result is Exception) throw result;
    return result as ActorPageDto;
  }

  @override
  Future<ActorDetailDto> getActor(String actorId) => throw UnimplementedError();

  @override
  Future<void> setFavorite(String actorId, {required bool enabled}) =>
      throw UnimplementedError();
}

class _ControlledActorsGateway implements ActorsGateway {
  final List<_ActorListRequest> listRequests = <_ActorListRequest>[];
  final List<Completer<ActorPageDto>> _listCompleters =
      <Completer<ActorPageDto>>[];
  final List<Completer<void>> _favoriteCompleters = <Completer<void>>[];
  final List<Completer<ActorDetailDto>> _detailCompleters =
      <Completer<ActorDetailDto>>[];

  @override
  Future<ActorPageDto> listActors({
    required ActorListScope scope,
    String? cursor,
  }) {
    listRequests.add(_ActorListRequest(scope, cursor));
    final completer = Completer<ActorPageDto>();
    _listCompleters.add(completer);
    return completer.future;
  }

  void completeList(int index, ActorPageDto page) =>
      _listCompleters[index].complete(page);

  void failList(int index, Object error) =>
      _listCompleters[index].completeError(error);

  @override
  Future<ActorDetailDto> getActor(String actorId) {
    final completer = Completer<ActorDetailDto>();
    _detailCompleters.add(completer);
    return completer.future;
  }

  void completeDetail(int index, ActorDetailDto detail) =>
      _detailCompleters[index].complete(detail);

  @override
  Future<void> setFavorite(String actorId, {required bool enabled}) {
    final completer = Completer<void>();
    _favoriteCompleters.add(completer);
    return completer.future;
  }

  void completeFavorite(int index) => _favoriteCompleters[index].complete();

  void failFavorite(int index, Object error) =>
      _favoriteCompleters[index].completeError(error);
}

class _ActorsAdapter implements HttpClientAdapter {
  final List<RequestOptions> requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (options.method == 'GET' && options.path == 'actors') {
      return _jsonResponse(200, <String, Object?>{
        'items': <Object?>[_actorJson()],
        'next_cursor': null,
      });
    }
    if (options.method == 'GET' && options.path == 'actors/$actorId') {
      return _jsonResponse(200, _detailJson());
    }
    if (options.path == 'actors/$actorId/favorite') {
      return ResponseBody.fromString('', 204);
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
