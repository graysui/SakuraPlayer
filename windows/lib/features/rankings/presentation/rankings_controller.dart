import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/rankings/data/rankings_api.dart';

enum RankingsStatus { idle, loading, ready, failed, unavailable }

@immutable
class RankingsState {
  const RankingsState({
    required this.selection,
    required this.status,
    required this.items,
    required this.availableYears,
    required this.syncedAt,
    required this.nextCursor,
    required this.errorCode,
    required this.unavailableReason,
    required this.isRefreshing,
    required this.refreshErrorCode,
    required this.isAppending,
    required this.appendErrorCode,
  });

  const RankingsState.initial()
    : selection = const RankingSelection(board: RankingBoard.daily),
      status = RankingsStatus.idle,
      items = const <RankingItemDto>[],
      availableYears = const <int>[],
      syncedAt = null,
      nextCursor = null,
      errorCode = null,
      unavailableReason = null,
      isRefreshing = false,
      refreshErrorCode = null,
      isAppending = false,
      appendErrorCode = null;

  final RankingSelection selection;
  final RankingsStatus status;
  final List<RankingItemDto> items;
  final List<int> availableYears;
  final DateTime? syncedAt;
  final String? nextCursor;
  final String? errorCode;
  final RankingUnavailableReason? unavailableReason;
  final bool isRefreshing;
  final String? refreshErrorCode;
  final bool isAppending;
  final String? appendErrorCode;
}

final rankingsControllerProvider =
    NotifierProvider<RankingsController, RankingsState>(RankingsController.new);

class RankingsController extends Notifier<RankingsState> {
  int _generation = 0;
  int? _cursorRecoveredGeneration;

  @override
  RankingsState build() {
    ref.watch(authSessionStateProvider);
    _generation++;
    _cursorRecoveredGeneration = null;
    return const RankingsState.initial();
  }

  Future<void> ensureLoaded() {
    if (state.status != RankingsStatus.idle) return Future<void>.value();
    return _loadFirstPage(state.selection);
  }

  Future<void> retryInitial() => _loadFirstPage(state.selection);

  Future<void> selectBoard(RankingBoard board) {
    final selection = RankingSelection(board: board);
    if (selection == state.selection && state.status != RankingsStatus.idle) {
      return Future<void>.value();
    }
    return _loadFirstPage(selection);
  }

  Future<void> selectYear(int? year) {
    if (state.selection.board != RankingBoard.top250 ||
        (year != null && !state.availableYears.contains(year))) {
      throw ArgumentError.value(year, 'year', 'is not available');
    }
    final selection = RankingSelection(board: RankingBoard.top250, year: year);
    if (selection == state.selection && state.status != RankingsStatus.idle) {
      return Future<void>.value();
    }
    return _loadFirstPage(selection);
  }

  Future<void> _loadFirstPage(RankingSelection selection) async {
    final generation = ++_generation;
    _cursorRecoveredGeneration = null;
    final availableYears = state.availableYears;
    state = RankingsState(
      selection: selection,
      status: RankingsStatus.loading,
      items: const <RankingItemDto>[],
      availableYears: availableYears,
      syncedAt: null,
      nextCursor: null,
      errorCode: null,
      unavailableReason: null,
      isRefreshing: false,
      refreshErrorCode: null,
      isAppending: false,
      appendErrorCode: null,
    );
    try {
      final page = await ref
          .read(rankingsGatewayProvider)
          .listRanking(selection: selection);
      if (generation != _generation) return;
      state = _successState(
        selection: selection,
        page: page,
        fallbackAvailableYears: availableYears,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      final reason = RankingUnavailableReason.fromException(error);
      state = RankingsState(
        selection: selection,
        status:
            reason == null ? RankingsStatus.failed : RankingsStatus.unavailable,
        items: const <RankingItemDto>[],
        availableYears: availableYears,
        syncedAt: null,
        nextCursor: null,
        errorCode: error.code,
        unavailableReason: reason,
        isRefreshing: false,
        refreshErrorCode: null,
        isAppending: false,
        appendErrorCode: null,
      );
    }
  }

  Future<void> refresh() async {
    if (state.status != RankingsStatus.ready) {
      await retryInitial();
      return;
    }
    final generation = ++_generation;
    _cursorRecoveredGeneration = null;
    final previous = state;
    state = RankingsState(
      selection: previous.selection,
      status: RankingsStatus.ready,
      items: previous.items,
      availableYears: previous.availableYears,
      syncedAt: previous.syncedAt,
      nextCursor: previous.nextCursor,
      errorCode: null,
      unavailableReason: null,
      isRefreshing: true,
      refreshErrorCode: null,
      isAppending: false,
      appendErrorCode: null,
    );
    try {
      final page = await ref
          .read(rankingsGatewayProvider)
          .listRanking(selection: previous.selection);
      if (generation != _generation) return;
      state = _successState(
        selection: previous.selection,
        page: page,
        fallbackAvailableYears: previous.availableYears,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = RankingsState(
        selection: previous.selection,
        status: RankingsStatus.ready,
        items: previous.items,
        availableYears: previous.availableYears,
        syncedAt: previous.syncedAt,
        nextCursor: previous.nextCursor,
        errorCode: null,
        unavailableReason: null,
        isRefreshing: false,
        refreshErrorCode: error.code,
        isAppending: false,
        appendErrorCode: previous.appendErrorCode,
      );
    }
  }

  Future<void> loadMore() => _loadMore(allowRetry: false);

  Future<void> retryAppend() => _loadMore(allowRetry: true);

  Future<void> _loadMore({required bool allowRetry}) async {
    final cursor = state.nextCursor;
    if (state.status != RankingsStatus.ready ||
        cursor == null ||
        state.isAppending ||
        state.isRefreshing ||
        (state.appendErrorCode != null && !allowRetry)) {
      return;
    }
    final generation = _generation;
    final previous = state;
    state = RankingsState(
      selection: previous.selection,
      status: RankingsStatus.ready,
      items: previous.items,
      availableYears: previous.availableYears,
      syncedAt: previous.syncedAt,
      nextCursor: cursor,
      errorCode: null,
      unavailableReason: null,
      isRefreshing: false,
      refreshErrorCode: previous.refreshErrorCode,
      isAppending: true,
      appendErrorCode: null,
    );
    try {
      final page = await ref
          .read(rankingsGatewayProvider)
          .listRanking(selection: previous.selection, cursor: cursor);
      if (generation != _generation) return;
      state = RankingsState(
        selection: previous.selection,
        status: RankingsStatus.ready,
        items: List<RankingItemDto>.unmodifiable(<RankingItemDto>[
          ...previous.items,
          ...page.items,
        ]),
        availableYears:
            page.board == RankingBoard.top250
                ? page.availableYears
                : previous.availableYears,
        syncedAt: previous.syncedAt,
        nextCursor: page.nextCursor,
        errorCode: null,
        unavailableReason: null,
        isRefreshing: false,
        refreshErrorCode: previous.refreshErrorCode,
        isAppending: false,
        appendErrorCode: null,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      if (error.code == 'validation_failed' &&
          _cursorRecoveredGeneration != generation) {
        _cursorRecoveredGeneration = generation;
        await _recoverFirstPage(previous, generation);
        return;
      }
      state = RankingsState(
        selection: previous.selection,
        status: RankingsStatus.ready,
        items: previous.items,
        availableYears: previous.availableYears,
        syncedAt: previous.syncedAt,
        nextCursor: cursor,
        errorCode: null,
        unavailableReason: null,
        isRefreshing: false,
        refreshErrorCode: previous.refreshErrorCode,
        isAppending: false,
        appendErrorCode: error.code,
      );
    }
  }

  Future<void> _recoverFirstPage(RankingsState previous, int generation) async {
    state = RankingsState(
      selection: previous.selection,
      status: RankingsStatus.ready,
      items: previous.items,
      availableYears: previous.availableYears,
      syncedAt: previous.syncedAt,
      nextCursor: previous.nextCursor,
      errorCode: null,
      unavailableReason: null,
      isRefreshing: true,
      refreshErrorCode: null,
      isAppending: false,
      appendErrorCode: null,
    );
    try {
      final page = await ref
          .read(rankingsGatewayProvider)
          .listRanking(selection: previous.selection);
      if (generation != _generation) return;
      state = _successState(
        selection: previous.selection,
        page: page,
        fallbackAvailableYears: previous.availableYears,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = RankingsState(
        selection: previous.selection,
        status: RankingsStatus.ready,
        items: previous.items,
        availableYears: previous.availableYears,
        syncedAt: previous.syncedAt,
        nextCursor: previous.nextCursor,
        errorCode: null,
        unavailableReason: null,
        isRefreshing: false,
        refreshErrorCode: error.code,
        isAppending: false,
        appendErrorCode: null,
      );
    }
  }

  RankingsState _successState({
    required RankingSelection selection,
    required RankingPageDto page,
    required List<int> fallbackAvailableYears,
  }) => RankingsState(
    selection: selection,
    status: RankingsStatus.ready,
    items: page.items,
    availableYears:
        page.board == RankingBoard.top250
            ? page.availableYears
            : fallbackAvailableYears,
    syncedAt: page.syncedAt,
    nextCursor: page.nextCursor,
    errorCode: null,
    unavailableReason: null,
    isRefreshing: false,
    refreshErrorCode: null,
    isAppending: false,
    appendErrorCode: null,
  );
}
