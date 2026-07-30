import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/features/actors/data/actors_api.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';

enum ActorsStatus { idle, loading, ready, failed }

@immutable
class ActorsState {
  const ActorsState({
    required this.scope,
    required this.status,
    required this.items,
    required this.nextCursor,
    required this.errorCode,
    required this.isRefreshing,
    required this.refreshErrorCode,
    required this.isAppending,
    required this.appendErrorCode,
    required this.favoriteInFlightIds,
    required this.favoriteErrorById,
  });

  const ActorsState.initial()
    : scope = const ActorListScope(),
      status = ActorsStatus.idle,
      items = const <ActorSummaryDto>[],
      nextCursor = null,
      errorCode = null,
      isRefreshing = false,
      refreshErrorCode = null,
      isAppending = false,
      appendErrorCode = null,
      favoriteInFlightIds = const <String>{},
      favoriteErrorById = const <String, String>{};

  final ActorListScope scope;
  final ActorsStatus status;
  final List<ActorSummaryDto> items;
  final String? nextCursor;
  final String? errorCode;
  final bool isRefreshing;
  final String? refreshErrorCode;
  final bool isAppending;
  final String? appendErrorCode;
  final Set<String> favoriteInFlightIds;
  final Map<String, String> favoriteErrorById;
}

final actorsControllerProvider =
    NotifierProvider<ActorsController, ActorsState>(ActorsController.new);

class ActorsController extends Notifier<ActorsState> {
  int _generation = 0;
  int? _cursorRecoveredGeneration;

  @override
  ActorsState build() {
    ref.watch(authSessionStateProvider);
    _generation++;
    _cursorRecoveredGeneration = null;
    return const ActorsState.initial();
  }

  Future<void> ensureLoaded() {
    if (state.status != ActorsStatus.idle) return Future<void>.value();
    return _loadFirstPage(state.scope);
  }

  Future<void> retryInitial() => _loadFirstPage(state.scope);

  Future<void> applyScope(ActorListScope scope) {
    scope.toQuery();
    if (scope == state.scope && state.status != ActorsStatus.idle) {
      return Future<void>.value();
    }
    return _loadFirstPage(scope);
  }

  Future<void> _loadFirstPage(ActorListScope scope) async {
    final generation = ++_generation;
    _cursorRecoveredGeneration = null;
    state = ActorsState(
      scope: scope,
      status: ActorsStatus.loading,
      items: const <ActorSummaryDto>[],
      nextCursor: null,
      errorCode: null,
      isRefreshing: false,
      refreshErrorCode: null,
      isAppending: false,
      appendErrorCode: null,
      favoriteInFlightIds: const <String>{},
      favoriteErrorById: const <String, String>{},
    );
    try {
      final page = await ref
          .read(actorsGatewayProvider)
          .listActors(scope: scope);
      if (generation != _generation) return;
      state = _success(scope, page);
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = ActorsState(
        scope: scope,
        status: ActorsStatus.failed,
        items: const <ActorSummaryDto>[],
        nextCursor: null,
        errorCode: error.code,
        isRefreshing: false,
        refreshErrorCode: null,
        isAppending: false,
        appendErrorCode: null,
        favoriteInFlightIds: const <String>{},
        favoriteErrorById: const <String, String>{},
      );
    }
  }

  Future<void> refresh() async {
    if (state.status != ActorsStatus.ready) {
      await retryInitial();
      return;
    }
    final generation = ++_generation;
    _cursorRecoveredGeneration = null;
    final previous = state;
    state = _preserved(previous, isRefreshing: true);
    try {
      final page = await ref
          .read(actorsGatewayProvider)
          .listActors(scope: previous.scope);
      if (generation != _generation) return;
      state = _success(previous.scope, page);
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = _preserved(previous, refreshErrorCode: error.code);
    }
  }

  Future<void> loadMore() => _loadMore(allowRetry: false);

  Future<void> retryAppend() => _loadMore(allowRetry: true);

  Future<void> _loadMore({required bool allowRetry}) async {
    final cursor = state.nextCursor;
    if (state.status != ActorsStatus.ready ||
        cursor == null ||
        state.isAppending ||
        state.isRefreshing ||
        (state.appendErrorCode != null && !allowRetry)) {
      return;
    }
    final generation = _generation;
    final previous = state;
    state = _preserved(previous, isAppending: true, clearAppendError: true);
    try {
      final page = await ref
          .read(actorsGatewayProvider)
          .listActors(scope: previous.scope, cursor: cursor);
      if (generation != _generation) return;
      state = ActorsState(
        scope: previous.scope,
        status: ActorsStatus.ready,
        items: List<ActorSummaryDto>.unmodifiable(<ActorSummaryDto>[
          ...previous.items,
          ...page.items,
        ]),
        nextCursor: page.nextCursor,
        errorCode: null,
        isRefreshing: false,
        refreshErrorCode: previous.refreshErrorCode,
        isAppending: false,
        appendErrorCode: null,
        favoriteInFlightIds: previous.favoriteInFlightIds,
        favoriteErrorById: previous.favoriteErrorById,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      if (error.code == 'validation_failed' &&
          _cursorRecoveredGeneration != generation) {
        _cursorRecoveredGeneration = generation;
        await _recoverFirstPage(previous, generation);
        return;
      }
      state = _preserved(previous, appendErrorCode: error.code);
    }
  }

  Future<void> _recoverFirstPage(ActorsState previous, int generation) async {
    state = _preserved(previous, isRefreshing: true, clearAppendError: true);
    try {
      final page = await ref
          .read(actorsGatewayProvider)
          .listActors(scope: previous.scope);
      if (generation != _generation) return;
      state = _success(previous.scope, page);
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = _preserved(previous, refreshErrorCode: error.code);
    }
  }

  Future<void> setFavorite(String actorId, {required bool enabled}) async {
    if (state.favoriteInFlightIds.contains(actorId)) return;
    final generation = _generation;
    final inFlight = <String>{...state.favoriteInFlightIds, actorId};
    final errors = <String, String>{...state.favoriteErrorById}
      ..remove(actorId);
    state = _favoriteState(state, inFlight: inFlight, errors: errors);
    try {
      await ref
          .read(actorsGatewayProvider)
          .setFavorite(actorId, enabled: enabled);
      if (generation != _generation) return;
      final items = <ActorSummaryDto>[
        for (final actor in state.items)
          if (!(state.scope.favorite && !enabled && actor.id == actorId))
            actor.id == actorId ? actor.copyWith(favorite: enabled) : actor,
      ];
      final remaining = <String>{...state.favoriteInFlightIds}..remove(actorId);
      state = ActorsState(
        scope: state.scope,
        status: state.status,
        items: List<ActorSummaryDto>.unmodifiable(items),
        nextCursor: state.nextCursor,
        errorCode: state.errorCode,
        isRefreshing: state.isRefreshing,
        refreshErrorCode: state.refreshErrorCode,
        isAppending: state.isAppending,
        appendErrorCode: state.appendErrorCode,
        favoriteInFlightIds: Set<String>.unmodifiable(remaining),
        favoriteErrorById: state.favoriteErrorById,
      );
      ref
          .read(actorDetailControllerProvider.notifier)
          .acceptFavorite(actorId, enabled);
    } on ApiException catch (error) {
      if (generation != _generation) return;
      final remaining = <String>{...state.favoriteInFlightIds}..remove(actorId);
      final failures = <String, String>{...state.favoriteErrorById}
        ..[actorId] = error.code;
      state = _favoriteState(state, inFlight: remaining, errors: failures);
    }
  }

  void acceptFavorite(String actorId, bool enabled) {
    final items = <ActorSummaryDto>[
      for (final actor in state.items)
        if (!(state.scope.favorite && !enabled && actor.id == actorId))
          actor.id == actorId ? actor.copyWith(favorite: enabled) : actor,
    ];
    state = ActorsState(
      scope: state.scope,
      status: state.status,
      items: List<ActorSummaryDto>.unmodifiable(items),
      nextCursor: state.nextCursor,
      errorCode: state.errorCode,
      isRefreshing: state.isRefreshing,
      refreshErrorCode: state.refreshErrorCode,
      isAppending: state.isAppending,
      appendErrorCode: state.appendErrorCode,
      favoriteInFlightIds: state.favoriteInFlightIds,
      favoriteErrorById: state.favoriteErrorById,
    );
  }

  ActorsState _success(ActorListScope scope, ActorPageDto page) => ActorsState(
    scope: scope,
    status: ActorsStatus.ready,
    items: page.items,
    nextCursor: page.nextCursor,
    errorCode: null,
    isRefreshing: false,
    refreshErrorCode: null,
    isAppending: false,
    appendErrorCode: null,
    favoriteInFlightIds: const <String>{},
    favoriteErrorById: const <String, String>{},
  );

  ActorsState _preserved(
    ActorsState previous, {
    bool isRefreshing = false,
    String? refreshErrorCode,
    bool isAppending = false,
    String? appendErrorCode,
    bool clearAppendError = false,
  }) => ActorsState(
    scope: previous.scope,
    status: ActorsStatus.ready,
    items: previous.items,
    nextCursor: previous.nextCursor,
    errorCode: null,
    isRefreshing: isRefreshing,
    refreshErrorCode: refreshErrorCode ?? previous.refreshErrorCode,
    isAppending: isAppending,
    appendErrorCode:
        clearAppendError ? null : appendErrorCode ?? previous.appendErrorCode,
    favoriteInFlightIds: previous.favoriteInFlightIds,
    favoriteErrorById: previous.favoriteErrorById,
  );

  ActorsState _favoriteState(
    ActorsState previous, {
    required Set<String> inFlight,
    required Map<String, String> errors,
  }) => ActorsState(
    scope: previous.scope,
    status: previous.status,
    items: previous.items,
    nextCursor: previous.nextCursor,
    errorCode: previous.errorCode,
    isRefreshing: previous.isRefreshing,
    refreshErrorCode: previous.refreshErrorCode,
    isAppending: previous.isAppending,
    appendErrorCode: previous.appendErrorCode,
    favoriteInFlightIds: Set<String>.unmodifiable(inFlight),
    favoriteErrorById: Map<String, String>.unmodifiable(errors),
  );
}

enum ActorDetailStatus { idle, loading, ready, failed }

@immutable
class ActorDetailState {
  const ActorDetailState({
    required this.actorId,
    required this.status,
    required this.detail,
    required this.errorCode,
    required this.isFavoriteInFlight,
    required this.favoriteErrorCode,
  });

  const ActorDetailState.initial()
    : actorId = null,
      status = ActorDetailStatus.idle,
      detail = null,
      errorCode = null,
      isFavoriteInFlight = false,
      favoriteErrorCode = null;

  final String? actorId;
  final ActorDetailStatus status;
  final ActorDetailDto? detail;
  final String? errorCode;
  final bool isFavoriteInFlight;
  final String? favoriteErrorCode;
}

final actorDetailControllerProvider =
    NotifierProvider<ActorDetailController, ActorDetailState>(
      ActorDetailController.new,
    );

class ActorDetailController extends Notifier<ActorDetailState> {
  int _generation = 0;

  @override
  ActorDetailState build() {
    ref.watch(authSessionStateProvider);
    _generation++;
    return const ActorDetailState.initial();
  }

  Future<void> load(String actorId) async {
    final generation = ++_generation;
    state = ActorDetailState(
      actorId: actorId,
      status: ActorDetailStatus.loading,
      detail: null,
      errorCode: null,
      isFavoriteInFlight: false,
      favoriteErrorCode: null,
    );
    try {
      final detail = await ref.read(actorsGatewayProvider).getActor(actorId);
      if (generation != _generation) return;
      state = ActorDetailState(
        actorId: actorId,
        status: ActorDetailStatus.ready,
        detail: detail,
        errorCode: null,
        isFavoriteInFlight: false,
        favoriteErrorCode: null,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = ActorDetailState(
        actorId: actorId,
        status: ActorDetailStatus.failed,
        detail: null,
        errorCode: error.code,
        isFavoriteInFlight: false,
        favoriteErrorCode: null,
      );
    }
  }

  Future<void> retry() {
    final actorId = state.actorId;
    return actorId == null ? Future<void>.value() : load(actorId);
  }

  Future<void> setFavorite({required bool enabled}) async {
    final detail = state.detail;
    final actorId = state.actorId;
    if (state.status != ActorDetailStatus.ready ||
        detail == null ||
        actorId == null ||
        state.isFavoriteInFlight) {
      return;
    }
    final generation = _generation;
    state = ActorDetailState(
      actorId: actorId,
      status: ActorDetailStatus.ready,
      detail: detail,
      errorCode: null,
      isFavoriteInFlight: true,
      favoriteErrorCode: null,
    );
    try {
      await ref
          .read(actorsGatewayProvider)
          .setFavorite(actorId, enabled: enabled);
      if (generation != _generation) return;
      final updated = detail.copyWith(favorite: enabled);
      state = ActorDetailState(
        actorId: actorId,
        status: ActorDetailStatus.ready,
        detail: updated,
        errorCode: null,
        isFavoriteInFlight: false,
        favoriteErrorCode: null,
      );
      ref
          .read(actorsControllerProvider.notifier)
          .acceptFavorite(actorId, enabled);
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = ActorDetailState(
        actorId: actorId,
        status: ActorDetailStatus.ready,
        detail: detail,
        errorCode: null,
        isFavoriteInFlight: false,
        favoriteErrorCode: error.code,
      );
    }
  }

  void acceptFavorite(String actorId, bool enabled) {
    final detail = state.detail;
    if (state.actorId != actorId || detail == null) return;
    state = ActorDetailState(
      actorId: actorId,
      status: state.status,
      detail: detail.copyWith(favorite: enabled),
      errorCode: state.errorCode,
      isFavoriteInFlight: state.isFavoriteInFlight,
      favoriteErrorCode: state.favoriteErrorCode,
    );
  }
}
