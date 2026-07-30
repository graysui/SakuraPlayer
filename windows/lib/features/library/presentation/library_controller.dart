import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';

enum LibraryStatus { idle, loading, ready, failed, invalid }

@immutable
class LibraryState {
  const LibraryState({
    required this.filters,
    required this.status,
    required this.items,
    required this.nextCursor,
    required this.errorCode,
    required this.isAppending,
    required this.appendErrorCode,
    required this.validationMessage,
  });

  const LibraryState.initial()
    : filters = const MovieFilters(),
      status = LibraryStatus.idle,
      items = const <MovieSummaryDto>[],
      nextCursor = null,
      errorCode = null,
      isAppending = false,
      appendErrorCode = null,
      validationMessage = null;

  final MovieFilters filters;
  final LibraryStatus status;
  final List<MovieSummaryDto> items;
  final String? nextCursor;
  final String? errorCode;
  final bool isAppending;
  final String? appendErrorCode;
  final String? validationMessage;
}

final libraryControllerProvider =
    NotifierProvider<LibraryController, LibraryState>(LibraryController.new);

class LibraryController extends Notifier<LibraryState> {
  int _generation = 0;
  int? _cursorRecoveredGeneration;

  @override
  LibraryState build() {
    ref.watch(authSessionStateProvider);
    _generation++;
    _cursorRecoveredGeneration = null;
    return const LibraryState.initial();
  }

  Future<void> loadInitial() => _loadFirstPage(state.filters);

  Future<void> retryInitial() => _loadFirstPage(state.filters);

  Future<void> applyFilters(MovieFilters filters) async {
    final generation = ++_generation;
    _cursorRecoveredGeneration = null;
    final validation = filters.validationMessage;
    if (validation != null) {
      state = LibraryState(
        filters: filters,
        status: LibraryStatus.invalid,
        items: const <MovieSummaryDto>[],
        nextCursor: null,
        errorCode: null,
        isAppending: false,
        appendErrorCode: null,
        validationMessage: validation,
      );
      return;
    }
    await _requestFirstPage(filters, generation);
  }

  Future<void> _loadFirstPage(MovieFilters filters) async {
    final generation = ++_generation;
    _cursorRecoveredGeneration = null;
    await _requestFirstPage(filters, generation);
  }

  Future<void> _requestFirstPage(MovieFilters filters, int generation) async {
    state = LibraryState(
      filters: filters,
      status: LibraryStatus.loading,
      items: const <MovieSummaryDto>[],
      nextCursor: null,
      errorCode: null,
      isAppending: false,
      appendErrorCode: null,
      validationMessage: null,
    );
    try {
      final page = await ref
          .read(moviesGatewayProvider)
          .listMovies(filters: filters);
      if (generation != _generation) return;
      state = LibraryState(
        filters: filters,
        status: LibraryStatus.ready,
        items: page.items,
        nextCursor: page.nextCursor,
        errorCode: null,
        isAppending: false,
        appendErrorCode: null,
        validationMessage: null,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = LibraryState(
        filters: filters,
        status: LibraryStatus.failed,
        items: const <MovieSummaryDto>[],
        nextCursor: null,
        errorCode: error.code,
        isAppending: false,
        appendErrorCode: null,
        validationMessage: null,
      );
    }
  }

  Future<void> loadMore() => _loadMore(allowRetry: false);

  Future<void> _loadMore({required bool allowRetry}) async {
    final cursor = state.nextCursor;
    if (state.status != LibraryStatus.ready ||
        cursor == null ||
        state.isAppending ||
        (state.appendErrorCode != null && !allowRetry)) {
      return;
    }
    final generation = _generation;
    final previous = state;
    state = LibraryState(
      filters: previous.filters,
      status: LibraryStatus.ready,
      items: previous.items,
      nextCursor: cursor,
      errorCode: null,
      isAppending: true,
      appendErrorCode: null,
      validationMessage: null,
    );
    try {
      final page = await ref
          .read(moviesGatewayProvider)
          .listMovies(filters: previous.filters, cursor: cursor);
      if (generation != _generation) return;
      state = LibraryState(
        filters: previous.filters,
        status: LibraryStatus.ready,
        items: List<MovieSummaryDto>.unmodifiable(<MovieSummaryDto>[
          ...previous.items,
          ...page.items,
        ]),
        nextCursor: page.nextCursor,
        errorCode: null,
        isAppending: false,
        appendErrorCode: null,
        validationMessage: null,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      if (error.code == 'validation_failed' &&
          _cursorRecoveredGeneration != generation) {
        _cursorRecoveredGeneration = generation;
        await _requestFirstPage(previous.filters, generation);
        return;
      }
      state = LibraryState(
        filters: previous.filters,
        status: LibraryStatus.ready,
        items: previous.items,
        nextCursor: cursor,
        errorCode: null,
        isAppending: false,
        appendErrorCode: error.code,
        validationMessage: null,
      );
    }
  }

  Future<void> retryAppend() => _loadMore(allowRetry: true);
}
