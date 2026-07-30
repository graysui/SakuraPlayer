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
import 'package:sakuraplayer_windows/features/rankings/data/rankings_api.dart';
import 'package:sakuraplayer_windows/features/rankings/presentation/rankings_controller.dart';

void main() {
  group('rankings contract', () {
    test('encodes board, optional year, cursor and fixed limit', () {
      expect(
        const RankingSelection(board: RankingBoard.daily).toQuery(),
        <String, Object?>{'board': 'daily', 'limit': 24},
      );
      expect(
        const RankingSelection(
          board: RankingBoard.top250,
          year: 2025,
        ).toQuery(cursor: 'next-page'),
        <String, Object?>{
          'board': 'top250',
          'year': 2025,
          'limit': 24,
          'cursor': 'next-page',
        },
      );
      expect(
        () =>
            const RankingSelection(
              board: RankingBoard.weekly,
              year: 2025,
            ).toQuery(),
        throwsArgumentError,
      );
      for (final board in <RankingBoard>[
        RankingBoard.daily,
        RankingBoard.weekly,
        RankingBoard.monthly,
      ]) {
        expect(RankingSelection(board: board).toQuery(), <String, Object?>{
          'board': board.apiValue,
          'limit': 24,
        });
      }
    });

    test('parses rank gaps, UTC sync time and shared movie summaries', () {
      final page = RankingPageDto.fromJson(
        _pageJson(
          board: 'top250',
          year: 2025,
          ranks: <int>[1, 4],
          availableYears: <int>[2026, 2025, 2024],
          nextCursor: 'cursor-2',
        ),
      );

      expect(page.board, RankingBoard.top250);
      expect(page.year, 2025);
      expect(page.items.map((item) => item.rank), <int>[1, 4]);
      expect(page.items.first.movie.number, 'RANK-001');
      expect(page.syncedAt, DateTime.utc(2026, 7, 30, 10, 30));
      expect(page.nextCursor, 'cursor-2');
    });

    test('rejects invalid ranks, year lists and response scopes', () async {
      final invalidRank = _pageJson(ranks: <int>[0]);
      expect(
        () => RankingPageDto.fromJson(invalidRank),
        throwsA(isA<ProtocolException>()),
      );
      final invalidYears = _pageJson(
        board: 'top250',
        availableYears: <int>[2025, 2026],
      );
      expect(
        () => RankingPageDto.fromJson(invalidYears),
        throwsA(isA<ProtocolException>()),
      );

      final session = SessionStore(SecureStore(MemorySecureKeyValueStore()));
      await session.setTokens(_tokens());
      final adapter = _RecordingAdapter(response: _pageJson(board: 'weekly'));
      final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
        ..httpClientAdapter = adapter;
      final api = RankingsApi(ApiClient(dio: dio, sessionStore: session));

      await expectLater(
        api.listRanking(
          selection: const RankingSelection(board: RankingBoard.daily),
        ),
        throwsA(
          isA<ApiException>().having(
            (error) => error.code,
            'code',
            'client_protocol_error',
          ),
        ),
      );
    });

    test(
      'actual API sends only the selected scope with authentication',
      () async {
        final session = SessionStore(SecureStore(MemorySecureKeyValueStore()));
        await session.setTokens(_tokens());
        final adapter = _RecordingAdapter(
          response: _pageJson(board: 'top250', year: 2025),
        );
        final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
          ..httpClientAdapter = adapter;
        final api = RankingsApi(ApiClient(dio: dio, sessionStore: session));

        await api.listRanking(
          selection: const RankingSelection(
            board: RankingBoard.top250,
            year: 2025,
          ),
          cursor: 'cursor-2',
        );

        final request = adapter.requests.single;
        expect(request.path, 'rankings');
        expect(request.queryParameters, <String, Object?>{
          'board': 'top250',
          'year': 2025,
          'limit': 24,
          'cursor': 'cursor-2',
        });
        expect(request.headers['Authorization'], 'Bearer access-token');
      },
    );
  });

  group('rankings controller', () {
    test(
      'loads daily by default and preserves a successful snapshot',
      () async {
        final gateway = _SequenceRankingsGateway(<Object>[
          _page(board: RankingBoard.daily, ranks: <int>[1, 3]),
        ]);
        final container = _container(gateway);
        addTearDown(container.dispose);

        await container
            .read(rankingsControllerProvider.notifier)
            .ensureLoaded();

        final state = container.read(rankingsControllerProvider);
        expect(state.status, RankingsStatus.ready);
        expect(
          state.selection,
          const RankingSelection(board: RankingBoard.daily),
        );
        expect(state.items.map((item) => item.rank), <int>[1, 3]);
        expect(state.syncedAt, isNotNull);
      },
    );

    test(
      'board and year changes isolate late responses and retain selection',
      () async {
        final gateway = _ControlledRankingsGateway();
        final container = _container(gateway);
        addTearDown(container.dispose);
        final controller = container.read(rankingsControllerProvider.notifier);

        final daily = controller.ensureLoaded();
        final top = controller.selectBoard(RankingBoard.top250);
        gateway.complete(
          1,
          _page(board: RankingBoard.top250, availableYears: <int>[2026, 2025]),
        );
        await top;
        gateway.complete(0, _page(board: RankingBoard.daily));
        await daily;

        final yearRequest = controller.selectYear(2025);
        gateway.complete(
          2,
          _page(
            board: RankingBoard.top250,
            year: 2025,
            availableYears: <int>[2026, 2025],
          ),
        );
        await yearRequest;

        final state = container.read(rankingsControllerProvider);
        expect(
          state.selection,
          const RankingSelection(board: RankingBoard.top250, year: 2025),
        );
        expect(state.status, RankingsStatus.ready);
      },
    );

    test(
      'duplicate append is ignored and a failed append retries its cursor',
      () async {
        final gateway = _ControlledRankingsGateway();
        final container = _container(gateway);
        addTearDown(container.dispose);
        final controller = container.read(rankingsControllerProvider.notifier);

        final initial = controller.ensureLoaded();
        gateway.complete(
          0,
          _page(board: RankingBoard.daily, nextCursor: 'cursor-2'),
        );
        await initial;

        final append = controller.loadMore();
        final duplicate = controller.loadMore();
        expect(gateway.requests, hasLength(2));
        gateway.fail(
          1,
          const ApiException(code: 'offline', message: 'offline'),
        );
        await Future.wait(<Future<void>>[append, duplicate]);
        expect(
          container.read(rankingsControllerProvider).appendErrorCode,
          'offline',
        );

        final retry = controller.retryAppend();
        expect(gateway.requests[2].cursor, 'cursor-2');
        gateway.complete(2, _page(board: RankingBoard.daily, ranks: <int>[25]));
        await retry;

        expect(container.read(rankingsControllerProvider).items, hasLength(2));
      },
    );

    test('refresh failure keeps items, cursor and synced time', () async {
      final gateway = _SequenceRankingsGateway(<Object>[
        _page(board: RankingBoard.monthly, nextCursor: 'cursor-2'),
        const ApiException(code: 'offline', message: 'offline'),
      ]);
      final container = _container(gateway);
      addTearDown(container.dispose);
      final controller = container.read(rankingsControllerProvider.notifier);

      await controller.selectBoard(RankingBoard.monthly);
      final before = container.read(rankingsControllerProvider);
      await controller.refresh();
      final after = container.read(rankingsControllerProvider);

      expect(after.status, RankingsStatus.ready);
      expect(after.items, before.items);
      expect(after.nextCursor, 'cursor-2');
      expect(after.syncedAt, before.syncedAt);
      expect(after.refreshErrorCode, 'offline');
    });

    test(
      'invalid append cursor recovers the selected first page once',
      () async {
        final gateway = _SequenceRankingsGateway(<Object>[
          _page(board: RankingBoard.weekly, nextCursor: 'stale'),
          const ApiException(
            code: 'validation_failed',
            message: 'invalid cursor',
            statusCode: 422,
          ),
          _page(board: RankingBoard.weekly, ranks: <int>[9]),
        ]);
        final container = _container(gateway);
        addTearDown(container.dispose);
        final controller = container.read(rankingsControllerProvider.notifier);

        await controller.selectBoard(RankingBoard.weekly);
        await controller.loadMore();

        final state = container.read(rankingsControllerProvider);
        expect(state.status, RankingsStatus.ready);
        expect(state.items.single.rank, 9);
        expect(gateway.requests[2].selection.board, RankingBoard.weekly);
        expect(gateway.requests[2].cursor, isNull);
      },
    );

    test('maps only stable snapshot unavailable reasons', () async {
      final gateway = _SequenceRankingsGateway(<Object>[
        const ApiException(
          code: 'ranking_snapshot_unavailable',
          message: 'unavailable',
          statusCode: 503,
          details: <String, Object?>{'reason': 'credentials_not_configured'},
        ),
        const ApiException(
          code: 'ranking_snapshot_unavailable',
          message: 'unavailable',
          statusCode: 503,
          details: <String, Object?>{'reason': 'unknown'},
        ),
      ]);
      final container = _container(gateway);
      addTearDown(container.dispose);
      final controller = container.read(rankingsControllerProvider.notifier);

      await controller.selectBoard(RankingBoard.top250);
      expect(
        container.read(rankingsControllerProvider).unavailableReason,
        RankingUnavailableReason.credentialsNotConfigured,
      );

      await controller.retryInitial();
      final state = container.read(rankingsControllerProvider);
      expect(state.status, RankingsStatus.failed);
      expect(state.unavailableReason, isNull);
    });

    test(
      'server session change clears state and ignores the old response',
      () async {
        final gateway = _ControlledRankingsGateway();
        final container = ProviderContainer(
          overrides: [
            rankingsGatewayProvider.overrideWithValue(gateway),
            authSessionStateProvider.overrideWith(
              (ref) => ref.watch(_mutableAuthProvider),
            ),
          ],
        );
        addTearDown(container.dispose);
        final request =
            container.read(rankingsControllerProvider.notifier).ensureLoaded();

        container
            .read(_mutableAuthProvider.notifier)
            .replace(
              AuthSessionState.authenticated(
                serverBaseUri: Uri.parse('https://new-server.test'),
              ),
            );
        await Future<void>.delayed(Duration.zero);
        gateway.complete(0, _page(board: RankingBoard.daily));
        await request;

        final state = container.read(rankingsControllerProvider);
        expect(state.status, RankingsStatus.idle);
        expect(state.items, isEmpty);
        expect(
          state.selection,
          const RankingSelection(board: RankingBoard.daily),
        );
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

ProviderContainer _container(RankingsGateway gateway) => ProviderContainer(
  overrides: [rankingsGatewayProvider.overrideWithValue(gateway)],
);

RankingPageDto _page({
  required RankingBoard board,
  int? year,
  List<int> ranks = const <int>[1],
  List<int> availableYears = const <int>[],
  String? nextCursor,
}) => RankingPageDto.fromJson(
  _pageJson(
    board: board.apiValue,
    year: year,
    ranks: ranks,
    availableYears: availableYears,
    nextCursor: nextCursor,
  ),
);

Map<String, Object?> _pageJson({
  String board = 'daily',
  int? year,
  List<int> ranks = const <int>[1],
  List<int> availableYears = const <int>[],
  String? nextCursor,
}) => <String, Object?>{
  'board': board,
  'year': year,
  'available_years': availableYears,
  'synced_at': '2026-07-30T10:30:00Z',
  'items': <Object?>[
    for (var index = 0; index < ranks.length; index++)
      <String, Object?>{'rank': ranks[index], 'movie': _movieJson(index + 1)},
  ],
  'next_cursor': nextCursor,
};

Map<String, Object?> _movieJson(int index) => <String, Object?>{
  'id': '00000000-0000-4000-8000-${index.toString().padLeft(12, '0')}',
  'number': 'RANK-${index.toString().padLeft(3, '0')}',
  'title': '排行榜影片 $index',
  'title_original': null,
  'cover_url': null,
  'publish_date': '2026-07-30',
  'labels': <Object?>['subtitle'],
  'favorite': false,
  'source_count': 1,
  'progress': null,
};

TokenPair _tokens() => TokenPair(
  accessToken: 'access-token',
  refreshToken: 'refresh-token',
  accessExpiresAt: DateTime.utc(2026, 7, 30, 12, 15),
  refreshExpiresAt: DateTime.utc(2026, 8, 30, 12),
);

class _RankingRequest {
  const _RankingRequest(this.selection, this.cursor);

  final RankingSelection selection;
  final String? cursor;
}

class _SequenceRankingsGateway implements RankingsGateway {
  _SequenceRankingsGateway(this.results);

  final List<Object> results;
  final List<_RankingRequest> requests = <_RankingRequest>[];

  @override
  Future<RankingPageDto> listRanking({
    required RankingSelection selection,
    String? cursor,
  }) async {
    requests.add(_RankingRequest(selection, cursor));
    final result = results[requests.length - 1];
    if (result is Exception) throw result;
    return result as RankingPageDto;
  }
}

class _ControlledRankingsGateway implements RankingsGateway {
  final List<_RankingRequest> requests = <_RankingRequest>[];
  final List<Completer<RankingPageDto>> _completers =
      <Completer<RankingPageDto>>[];

  @override
  Future<RankingPageDto> listRanking({
    required RankingSelection selection,
    String? cursor,
  }) {
    requests.add(_RankingRequest(selection, cursor));
    final completer = Completer<RankingPageDto>();
    _completers.add(completer);
    return completer.future;
  }

  void complete(int index, RankingPageDto page) =>
      _completers[index].complete(page);

  void fail(int index, Object error) => _completers[index].completeError(error);
}

class _RecordingAdapter implements HttpClientAdapter {
  _RecordingAdapter({required this.response});

  final Map<String, Object?> response;
  final List<RequestOptions> requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    return ResponseBody.fromString(
      jsonEncode(response),
      200,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
