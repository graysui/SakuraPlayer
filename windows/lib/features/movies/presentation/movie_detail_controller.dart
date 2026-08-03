import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/movies/data/movie_detail_api.dart';

enum MovieDetailStatus { idle, loading, ready, failed }

@immutable
class MovieDetailState {
  const MovieDetailState({
    required this.movieId,
    required this.status,
    required this.detail,
    required this.errorCode,
    required this.isFavoriteInFlight,
    required this.favoriteErrorCode,
    required this.isRescrapeInFlight,
    required this.rescrapeState,
    required this.rescrapeErrorCode,
    required this.selectedSourceId,
  });

  const MovieDetailState.initial()
    : movieId = null,
      status = MovieDetailStatus.idle,
      detail = null,
      errorCode = null,
      isFavoriteInFlight = false,
      favoriteErrorCode = null,
      isRescrapeInFlight = false,
      rescrapeState = null,
      rescrapeErrorCode = null,
      selectedSourceId = null;

  final String? movieId;
  final MovieDetailStatus status;
  final MovieDetailDto? detail;
  final String? errorCode;
  final bool isFavoriteInFlight;
  final String? favoriteErrorCode;
  final bool isRescrapeInFlight;
  final MetadataRescrapeState? rescrapeState;
  final String? rescrapeErrorCode;
  final String? selectedSourceId;

  bool get isNotFound => errorCode == 'resource_not_found';
}

final movieDetailControllerProvider =
    NotifierProvider<MovieDetailController, MovieDetailState>(
      MovieDetailController.new,
    );

class MovieDetailController extends Notifier<MovieDetailState> {
  int _generation = 0;

  @override
  MovieDetailState build() {
    ref.watch(authSessionStateProvider);
    _generation++;
    return const MovieDetailState.initial();
  }

  Future<void> load(String movieId) async {
    requireMovieId(movieId);
    final generation = ++_generation;
    final previousSelection =
        state.movieId == movieId ? state.selectedSourceId : null;
    state = MovieDetailState(
      movieId: movieId,
      status: MovieDetailStatus.loading,
      detail: null,
      errorCode: null,
      isFavoriteInFlight: false,
      favoriteErrorCode: null,
      isRescrapeInFlight: false,
      rescrapeState: null,
      rescrapeErrorCode: null,
      selectedSourceId: previousSelection,
    );
    try {
      final detail = await ref
          .read(movieDetailGatewayProvider)
          .getMovie(movieId);
      if (generation != _generation) return;
      final selected =
          detail.sources.any(
                (source) =>
                    source.id == previousSelection && source.isSelectable,
              )
              ? previousSelection
              : null;
      state = MovieDetailState(
        movieId: movieId,
        status: MovieDetailStatus.ready,
        detail: detail,
        errorCode: null,
        isFavoriteInFlight: false,
        favoriteErrorCode: null,
        isRescrapeInFlight: false,
        rescrapeState: null,
        rescrapeErrorCode: null,
        selectedSourceId: selected,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = MovieDetailState(
        movieId: movieId,
        status: MovieDetailStatus.failed,
        detail: null,
        errorCode: error.code,
        isFavoriteInFlight: false,
        favoriteErrorCode: null,
        isRescrapeInFlight: false,
        rescrapeState: null,
        rescrapeErrorCode: null,
        selectedSourceId: null,
      );
    }
  }

  Future<void> retry() {
    final movieId = state.movieId;
    return movieId == null ? Future<void>.value() : load(movieId);
  }

  Future<void> setFavorite({required bool enabled}) async {
    final detail = state.detail;
    final movieId = state.movieId;
    if (state.status != MovieDetailStatus.ready ||
        detail == null ||
        movieId == null ||
        detail.isLimited ||
        state.isFavoriteInFlight) {
      return;
    }
    final generation = _generation;
    state = _copyState(
      detail: detail,
      isFavoriteInFlight: true,
      clearFavoriteError: true,
    );
    try {
      await ref
          .read(movieDetailGatewayProvider)
          .setFavorite(movieId, enabled: enabled);
      if (generation != _generation) return;
      state = _copyState(
        detail: detail.copyWith(favorite: enabled),
        isFavoriteInFlight: false,
        clearFavoriteError: true,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = _copyState(
        detail: detail,
        isFavoriteInFlight: false,
        favoriteErrorCode: error.code,
      );
    }
  }

  Future<void> rescrape() async {
    final detail = state.detail;
    final movieId = state.movieId;
    if (state.status != MovieDetailStatus.ready ||
        detail == null ||
        movieId == null ||
        state.isRescrapeInFlight) {
      return;
    }
    final generation = _generation;
    state = _copyState(
      detail: detail,
      isRescrapeInFlight: true,
      clearRescrapeState: true,
      clearRescrapeError: true,
    );
    try {
      final outcome = await ref
          .read(movieDetailGatewayProvider)
          .rescrapeMovie(movieId);
      if (generation != _generation) return;
      state = _copyState(
        detail: state.detail ?? detail,
        isRescrapeInFlight: false,
        rescrapeState: outcome.state,
        clearRescrapeError: true,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = _copyState(
        detail: state.detail ?? detail,
        isRescrapeInFlight: false,
        rescrapeErrorCode: error.code,
        clearRescrapeState: true,
      );
    }
  }

  void selectSource(String sourceId) {
    final detail = state.detail;
    if (state.status != MovieDetailStatus.ready || detail == null) return;
    final selectable = detail.sources.any(
      (source) => source.id == sourceId && source.isSelectable,
    );
    if (!selectable) return;
    state = _copyState(detail: detail, selectedSourceId: sourceId);
  }

  void playSelected(ValueChanged<String>? sink) {
    final sourceId = state.selectedSourceId;
    final detail = state.detail;
    if (sink == null || sourceId == null || detail == null) return;
    final selectable = detail.sources.any(
      (source) => source.id == sourceId && source.isSelectable,
    );
    if (selectable) sink(sourceId);
  }

  MovieDetailState _copyState({
    required MovieDetailDto detail,
    bool? isFavoriteInFlight,
    String? favoriteErrorCode,
    bool clearFavoriteError = false,
    bool? isRescrapeInFlight,
    MetadataRescrapeState? rescrapeState,
    bool clearRescrapeState = false,
    String? rescrapeErrorCode,
    bool clearRescrapeError = false,
    String? selectedSourceId,
  }) => MovieDetailState(
    movieId: state.movieId,
    status: MovieDetailStatus.ready,
    detail: detail,
    errorCode: null,
    isFavoriteInFlight: isFavoriteInFlight ?? state.isFavoriteInFlight,
    favoriteErrorCode:
        clearFavoriteError
            ? null
            : favoriteErrorCode ?? state.favoriteErrorCode,
    isRescrapeInFlight: isRescrapeInFlight ?? state.isRescrapeInFlight,
    rescrapeState:
        clearRescrapeState ? null : rescrapeState ?? state.rescrapeState,
    rescrapeErrorCode:
        clearRescrapeError
            ? null
            : rescrapeErrorCode ?? state.rescrapeErrorCode,
    selectedSourceId: selectedSourceId ?? state.selectedSourceId,
  );
}
