import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
import 'package:sakuraplayer_windows/features/search/data/search_api.dart';

enum SearchStatus { idle, loading, ready, failed }

@immutable
class SearchState {
  const SearchState({
    required this.query,
    required this.status,
    required this.result,
    required this.errorCode,
  });

  const SearchState.idle()
    : query = '',
      status = SearchStatus.idle,
      result = null,
      errorCode = null;

  final String query;
  final SearchStatus status;
  final SearchResultDto? result;
  final String? errorCode;

  bool get isRefreshing => status == SearchStatus.loading && result != null;

  SearchState copyWith({
    String? query,
    SearchStatus? status,
    SearchResultDto? result,
    bool clearResult = false,
    String? errorCode,
    bool clearError = false,
  }) => SearchState(
    query: query ?? this.query,
    status: status ?? this.status,
    result: clearResult ? null : result ?? this.result,
    errorCode: clearError ? null : errorCode ?? this.errorCode,
  );
}

final searchDebounceDurationProvider = Provider<Duration>(
  (ref) => const Duration(milliseconds: 300),
);

final searchControllerProvider =
    NotifierProvider<SearchController, SearchState>(SearchController.new);

class SearchController extends Notifier<SearchState> {
  Timer? _debounce;
  int _generation = 0;

  @override
  SearchState build() {
    ref.onDispose(() => _debounce?.cancel());
    ref.listen<SnapshotState>(snapshotStateProvider, _onSnapshotChanged);
    return const SearchState.idle();
  }

  void updateQuery(String input) {
    _debounce?.cancel();
    final query = input.trim();
    if (query.isEmpty) {
      _generation++;
      state = const SearchState.idle();
      return;
    }
    state = SearchState(
      query: query,
      status: SearchStatus.idle,
      result: null,
      errorCode: null,
    );
    _debounce = Timer(ref.read(searchDebounceDurationProvider), () {
      unawaited(_runSearch(query));
    });
  }

  void clear() {
    _debounce?.cancel();
    _generation++;
    state = const SearchState.idle();
  }

  Future<void> searchNow(String input) async {
    _debounce?.cancel();
    final query = input.trim();
    if (query.isEmpty) {
      _generation++;
      state = const SearchState.idle();
      return;
    }
    await _runSearch(query);
  }

  Future<void> _runSearch(String query, {bool preserveResult = false}) async {
    final generation = ++_generation;
    state = SearchState(
      query: query,
      status: SearchStatus.loading,
      result: preserveResult ? state.result : null,
      errorCode: null,
    );
    try {
      final result = await ref.read(searchGatewayProvider).search(query);
      if (generation != _generation || state.query != query) return;
      state = SearchState(
        query: query,
        status: SearchStatus.ready,
        result: result,
        errorCode: null,
      );
    } on ApiException catch (error) {
      if (generation != _generation || state.query != query) return;
      state = SearchState(
        query: query,
        status: SearchStatus.failed,
        result: preserveResult ? state.result : null,
        errorCode: error.code,
      );
    }
  }

  void _onSnapshotChanged(SnapshotState? previous, SnapshotState next) {
    final result = state.result;
    if (result == null) return;
    final activePending = result.pendingMetadata.where(
      (item) => item.state != PendingMetadataState.failed,
    );
    if (activePending.isEmpty) return;

    final recovered =
        previous != null && next.recoveryRevision > previous.recoveryRevision;
    final catalogChanged =
        previous != null &&
        next.catalogReadyRevision > previous.catalogReadyRevision;
    final readyNumber = next.lastCatalogMovieReady?.number.toUpperCase();
    final matchesReady =
        catalogChanged &&
        activePending.any((item) => item.number.toUpperCase() == readyNumber);
    if (recovered || matchesReady) {
      unawaited(_runSearch(state.query, preserveResult: true));
    }
  }
}
