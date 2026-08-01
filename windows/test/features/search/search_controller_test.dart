import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
import 'package:sakuraplayer_windows/features/search/data/search_api.dart';
import 'package:sakuraplayer_windows/features/search/presentation/search_controller.dart';
import 'package:sakuraplayer_windows/features/search/presentation/search_overlay.dart';

void main() {
  test('strict DTO groups movies, actors and pending metadata', () {
    final result = SearchResultDto.fromJson(
      _searchJson(pendingState: 'queued'),
    );

    expect(result.movies.single.number, 'ABC-123');
    expect(result.actors.single.aliases, contains('小樱'));
    expect(result.pendingMetadata.single.state, PendingMetadataState.queued);
    expect(result.pendingMetadata.single.movieId, movieId);
  });

  testWidgets('failed pending metadata navigates with its movie id', (
    tester,
  ) async {
    final selected = <String>[];
    final gateway = _SequenceSearchGateway(<SearchResultDto>[
      SearchResultDto.fromJson(
        _searchJson(movie: false, pendingState: 'failed'),
      ),
    ]);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          searchGatewayProvider.overrideWithValue(gateway),
          searchDebounceDurationProvider.overrideWithValue(Duration.zero),
        ],
        child: MaterialApp(
          home: Scaffold(body: SearchOverlay(onMovieSelected: selected.add)),
        ),
      ),
    );

    await tester.tap(find.text('搜索番号、影片或女优'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'ABC-123');
    await tester.pumpAndSettle();
    expect(find.text('补全失败'), findsOneWidget);

    await tester.tap(find.widgetWithText(ListTile, 'ABC-123'));
    await tester.pumpAndSettle();
    expect(selected, <String>[movieId]);
  });

  test(
    'late response from an old query cannot replace current results',
    () async {
      final gateway = _ControlledSearchGateway();
      final container = ProviderContainer(
        overrides: [searchGatewayProvider.overrideWithValue(gateway)],
      );
      addTearDown(container.dispose);
      final controller = container.read(searchControllerProvider.notifier);

      final oldRequest = controller.searchNow('OLD-001');
      final newRequest = controller.searchNow('NEW-002');
      gateway.complete(
        'NEW-002',
        SearchResultDto.fromJson(_searchJson(number: 'NEW-002')),
      );
      await newRequest;
      gateway.complete(
        'OLD-001',
        SearchResultDto.fromJson(_searchJson(number: 'OLD-001')),
      );
      await oldRequest;

      expect(
        container.read(searchControllerProvider).result!.movies.single.number,
        'NEW-002',
      );
    },
  );

  test('debounce sends only the latest UI query', () async {
    final gateway = _RecordingSearchGateway();
    final container = ProviderContainer(
      overrides: [
        searchGatewayProvider.overrideWithValue(gateway),
        searchDebounceDurationProvider.overrideWithValue(
          const Duration(milliseconds: 10),
        ),
      ],
    );
    addTearDown(container.dispose);
    final controller = container.read(searchControllerProvider.notifier);

    controller.updateQuery('ABC');
    controller.updateQuery('ABC-123');
    await Future<void>.delayed(const Duration(milliseconds: 30));

    expect(gateway.queries, <String>['ABC-123']);
  });

  test('core-ready refreshes only the current pending search', () async {
    final gateway = _SequenceSearchGateway(<SearchResultDto>[
      SearchResultDto.fromJson(
        _searchJson(movie: false, pendingState: 'running'),
      ),
      SearchResultDto.fromJson(_searchJson()),
    ]);
    final container = ProviderContainer(
      overrides: [searchGatewayProvider.overrideWithValue(gateway)],
    );
    addTearDown(container.dispose);
    final controller = container.read(searchControllerProvider.notifier);
    await controller.searchNow('ABC-123');

    container
        .read(snapshotStateProvider.notifier)
        .replace(
          SnapshotState.empty().copyWith(
            catalogReadyRevision: 1,
            lastCatalogMovieReady: const PatchValue.present(
              CatalogMoviePatch(
                movieId: '00000000-0000-4000-8000-000000000001',
                number: 'ABC-123',
              ),
            ),
          ),
        );
    await Future<void>.delayed(Duration.zero);

    expect(gateway.calls, 2);
    expect(
      container.read(searchControllerProvider).result!.movies.single.number,
      'ABC-123',
    );
    expect(
      container.read(searchControllerProvider).result!.pendingMetadata,
      isEmpty,
    );
  });

  test(
    'failed metadata remains a stable result without automatic retry',
    () async {
      final gateway = _SequenceSearchGateway(<SearchResultDto>[
        SearchResultDto.fromJson(
          _searchJson(movie: false, pendingState: 'failed'),
        ),
      ]);
      final container = ProviderContainer(
        overrides: [searchGatewayProvider.overrideWithValue(gateway)],
      );
      addTearDown(container.dispose);

      await container
          .read(searchControllerProvider.notifier)
          .searchNow('ABC-123');
      container
          .read(snapshotStateProvider.notifier)
          .replace(SnapshotState.empty().copyWith(recoveryRevision: 1));
      await Future<void>.delayed(Duration.zero);

      expect(gateway.calls, 1);
      expect(
        container
            .read(searchControllerProvider)
            .result!
            .pendingMetadata
            .single
            .state,
        PendingMetadataState.failed,
      );
    },
  );

  test('runtime reset does not refresh an old pending search', () async {
    final gateway = _SequenceSearchGateway(<SearchResultDto>[
      SearchResultDto.fromJson(
        _searchJson(movie: false, pendingState: 'running'),
      ),
    ]);
    final container = ProviderContainer(
      overrides: [searchGatewayProvider.overrideWithValue(gateway)],
    );
    addTearDown(container.dispose);
    container
        .read(snapshotStateProvider.notifier)
        .replace(SnapshotState.empty().copyWith(recoveryRevision: 2));
    await container
        .read(searchControllerProvider.notifier)
        .searchNow('ABC-123');

    container.read(snapshotStateProvider.notifier).clear();
    await Future<void>.delayed(Duration.zero);

    expect(gateway.calls, 1);
  });
}

Map<String, Object?> _searchJson({
  String number = 'ABC-123',
  bool movie = true,
  String? pendingState,
}) => <String, Object?>{
  'movies': <Object?>[
    if (movie)
      <String, Object?>{
        'id': '00000000-0000-4000-8000-000000000001',
        'number': number,
        'title': '测试影片',
        'title_original': 'テスト映画',
        'cover_url':
            '/api/v1/catalog/images/00000000-0000-4000-8000-000000000010',
        'publish_date': '2026-07-01',
        'labels': <Object?>['subtitle'],
        'favorite': false,
        'source_count': 1,
        'progress': null,
      },
  ],
  'actors': <Object?>[
    <String, Object?>{
      'id': '00000000-0000-4000-8000-000000000002',
      'display_name': '樱',
      'name_ja': 'さくら',
      'name_zh': '樱',
      'aliases': <Object?>['小樱'],
      'profile_url': null,
      'favorite': true,
    },
  ],
  'pending_metadata': <Object?>[
    if (pendingState != null)
      <String, Object?>{
        'movie_id': movieId,
        'number': number,
        'state': pendingState,
        'metadata_job_id': '00000000-0000-4000-8000-000000000003',
      },
  ],
};

const movieId = '00000000-0000-4000-8000-000000000001';

class _ControlledSearchGateway implements SearchGateway {
  final Map<String, Completer<SearchResultDto>> _requests =
      <String, Completer<SearchResultDto>>{};

  @override
  Future<SearchResultDto> search(String query, {int limit = 10}) {
    final completer = Completer<SearchResultDto>();
    _requests[query] = completer;
    return completer.future;
  }

  void complete(String query, SearchResultDto result) {
    _requests[query]!.complete(result);
  }
}

class _SequenceSearchGateway implements SearchGateway {
  _SequenceSearchGateway(this.results);

  final List<SearchResultDto> results;
  int calls = 0;

  @override
  Future<SearchResultDto> search(String query, {int limit = 10}) async {
    return results[calls++];
  }
}

class _RecordingSearchGateway implements SearchGateway {
  final List<String> queries = <String>[];

  @override
  Future<SearchResultDto> search(String query, {int limit = 10}) async {
    queries.add(query);
    return SearchResultDto.fromJson(_searchJson(number: query));
  }
}
