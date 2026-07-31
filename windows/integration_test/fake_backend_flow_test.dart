import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sakuraplayer_windows/app/app.dart';
import 'package:sakuraplayer_windows/features/auth/domain/auth_session_state.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';
import 'package:sakuraplayer_windows/features/rankings/data/rankings_api.dart';
import 'package:sakuraplayer_windows/widgets/shell/desktop_shell.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('offline fake backend opens the native Windows shell', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1280, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionStateProvider.overrideWithValue(
            AuthSessionState.authenticated(
              serverBaseUri: Uri.parse('https://offline.fixture.invalid'),
            ),
          ),
          moviesGatewayProvider.overrideWithValue(const _FakeMoviesGateway()),
          rankingsGatewayProvider.overrideWithValue(
            const _FakeRankingsGateway(),
          ),
        ],
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(DesktopShell), findsOneWidget);
    expect(find.byKey(const ValueKey('library-page')), findsOneWidget);
    expect(find.text('FAKE-001'), findsOneWidget);

    await tester.tap(find.text('排行榜'));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('rankings-page')), findsOneWidget);
    expect(find.text('FAKE-001'), findsOneWidget);
  });
}

class _FakeMoviesGateway implements MoviesGateway {
  const _FakeMoviesGateway();

  @override
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  }) async => MoviePageDto(items: <MovieSummaryDto>[_movie], nextCursor: null);

  @override
  Future<List<int>> loadCover(String coverUrl) async => const <int>[];
}

class _FakeRankingsGateway implements RankingsGateway {
  const _FakeRankingsGateway();

  @override
  Future<RankingPageDto> listRanking({
    required RankingSelection selection,
    String? cursor,
  }) async => RankingPageDto(
    board: selection.board,
    year: selection.year,
    availableYears: const <int>[],
    syncedAt: DateTime.utc(2026, 7, 31),
    items: const <RankingItemDto>[RankingItemDto(rank: 1, movie: _movie)],
    nextCursor: null,
  );
}

const _movie = MovieSummaryDto(
  id: '00000000-0000-4000-8000-000000000001',
  number: 'FAKE-001',
  title: '离线验收影片',
  titleOriginal: null,
  coverUrl: null,
  publishDate: '2026-07-31',
  labels: <String>['subtitle'],
  favorite: false,
  sourceCount: 1,
  progress: null,
);
