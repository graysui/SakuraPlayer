import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/cache/data/cache_api.dart';

enum CachePageStatus { idle, loading, ready, failed }

@immutable
class CachePageState {
  const CachePageState({
    required this.status,
    required this.items,
    required this.capacity,
    required this.nextCursor,
    required this.errorCode,
    required this.isAppending,
    required this.inFlightIds,
    required this.actionErrors,
  });
  const CachePageState.initial()
    : status = CachePageStatus.idle,
      items = const [],
      capacity = null,
      nextCursor = null,
      errorCode = null,
      isAppending = false,
      inFlightIds = const {},
      actionErrors = const {};
  final CachePageStatus status;
  final List<CacheJobDto> items;
  final CacheCapacityDto? capacity;
  final String? nextCursor;
  final String? errorCode;
  final bool isAppending;
  final Set<String> inFlightIds;
  final Map<String, String> actionErrors;
  CachePageState copyWith({
    CachePageStatus? status,
    List<CacheJobDto>? items,
    Object? capacity = _absent,
    Object? nextCursor = _absent,
    Object? errorCode = _absent,
    bool? isAppending,
    Set<String>? inFlightIds,
    Map<String, String>? actionErrors,
  }) => CachePageState(
    status: status ?? this.status,
    items: items ?? this.items,
    capacity:
        identical(capacity, _absent)
            ? this.capacity
            : capacity as CacheCapacityDto?,
    nextCursor:
        identical(nextCursor, _absent)
            ? this.nextCursor
            : nextCursor as String?,
    errorCode:
        identical(errorCode, _absent) ? this.errorCode : errorCode as String?,
    isAppending: isAppending ?? this.isAppending,
    inFlightIds: inFlightIds ?? this.inFlightIds,
    actionErrors: actionErrors ?? this.actionErrors,
  );
}

final cacheControllerProvider =
    NotifierProvider<CacheController, CachePageState>(CacheController.new);

class CacheController extends Notifier<CachePageState> {
  int _generation = 0;
  int _snapshotVersion = -1;
  @override
  CachePageState build() {
    ref.watch(authSessionStateProvider);
    _generation++;
    _snapshotVersion = -1;
    ref.listen<SnapshotState>(snapshotStateProvider, (_, next) {
      if (next.snapshotVersion != _snapshotVersion &&
          state.status == CachePageStatus.ready) {
        _snapshotVersion = next.snapshotVersion;
        unawaited(refresh());
      }
    });
    return const CachePageState.initial();
  }

  Future<void> loadInitial() => _loadFirstPage();
  Future<void> refresh() => _loadFirstPage();
  Future<void> _loadFirstPage() async {
    final generation = ++_generation;
    state = state.copyWith(
      status: CachePageStatus.loading,
      items: const [],
      nextCursor: null,
      errorCode: null,
      isAppending: false,
      actionErrors: const {},
    );
    try {
      final page = await ref.read(cacheGatewayProvider).listJobs();
      if (generation != _generation) return;
      state = state.copyWith(
        status: CachePageStatus.ready,
        items: page.items,
        capacity: page.capacity,
        nextCursor: page.nextCursor,
        errorCode: null,
      );
    } on ApiException catch (error) {
      if (generation == _generation) {
        state = state.copyWith(
          status: CachePageStatus.failed,
          errorCode: error.code,
          items: const [],
          nextCursor: null,
        );
      }
    }
  }

  Future<void> loadMore() async {
    if (state.status != CachePageStatus.ready ||
        state.nextCursor == null ||
        state.isAppending) {
      return;
    }
    final generation = _generation;
    final cursor = state.nextCursor!;
    state = state.copyWith(isAppending: true);
    try {
      final page = await ref
          .read(cacheGatewayProvider)
          .listJobs(cursor: cursor);
      if (generation != _generation) return;
      final byId = <String, CacheJobDto>{
        for (final item in state.items) item.id: item,
      };
      for (final item in page.items) {
        byId[item.id] = item;
      }
      state = state.copyWith(
        items: List.unmodifiable(byId.values),
        capacity: page.capacity,
        nextCursor: page.nextCursor,
        isAppending: false,
      );
    } on ApiException catch (error) {
      if (generation == _generation) {
        state = state.copyWith(
          isAppending: false,
          actionErrors: {...state.actionErrors, '__page__': error.code},
        );
      }
    }
  }

  Future<void> cancel(String jobId, {required bool confirmed}) =>
      _act(jobId, confirmed: confirmed, cleanup: false);
  Future<void> cleanup(String jobId, {required bool confirmed}) =>
      _act(jobId, confirmed: confirmed, cleanup: true);

  Future<CacheJobDto?> selectMedia(
    String jobId,
    MediaCandidateGroup group,
  ) async {
    if (state.inFlightIds.contains(jobId) || group.media.isEmpty) return null;
    CacheJobDto? item;
    for (final value in state.items) {
      if (value.id == jobId) item = value;
    }
    final groups =
        item == null
            ? const <MediaCandidateGroup>[]
            : validMediaCandidateGroups(item);
    if (!groups.any(
      (value) =>
          value.id == group.id &&
          listEquals(
            value.media.map((media) => media.id).toList(),
            group.media.map((media) => media.id).toList(),
          ),
    )) {
      return null;
    }
    final generation = _generation;
    state = state.copyWith(
      inFlightIds: {...state.inFlightIds, jobId},
      actionErrors: {...state.actionErrors}..remove(jobId),
    );
    try {
      final selectedIds = group.media
          .map((media) => media.id)
          .toList(growable: false);
      final updated = await ref
          .read(cacheGatewayProvider)
          .selectMedia(jobId, selectedIds);
      if (generation != _generation) return null;
      if (updated.id != jobId ||
          updated.status != 'ready' ||
          !listEquals(updated.selectedMediaIds, selectedIds)) {
        throw const ApiException(
          code: 'client_protocol_error',
          message: 'Media selection did not return a playable job.',
        );
      }
      state = state.copyWith(
        items: state.items
            .map((value) => value.id == updated.id ? updated : value)
            .toList(growable: false),
        inFlightIds: {...state.inFlightIds}..remove(jobId),
      );
      return updated;
    } on ApiException catch (error) {
      if (generation == _generation) {
        state = state.copyWith(
          inFlightIds: {...state.inFlightIds}..remove(jobId),
          actionErrors: {...state.actionErrors, jobId: error.code},
        );
      }
      return null;
    }
  }

  Future<void> _act(
    String jobId, {
    required bool confirmed,
    required bool cleanup,
  }) async {
    if (!confirmed || state.inFlightIds.contains(jobId)) return;
    CacheJobDto? item;
    for (final candidate in state.items) {
      if (candidate.id == jobId) {
        item = candidate;
        break;
      }
    }
    if (item == null) {
      return;
    }
    if (cleanup
        ? !canCleanupCacheStatus(item.status)
        : !canCancelCacheStatus(item.status)) {
      return;
    }
    final generation = _generation;
    final inFlight = {...state.inFlightIds, jobId};
    state = state.copyWith(
      inFlightIds: inFlight,
      actionErrors: {...state.actionErrors}..remove(jobId),
    );
    try {
      final CacheJobDto updated =
          cleanup
              ? await ref.read(cacheGatewayProvider).cleanup(jobId)
              : await ref.read(cacheGatewayProvider).cancel(jobId);
      if (generation != _generation) return;
      final items = state.items
          .map((value) => value.id == updated.id ? updated : value)
          .toList(growable: false);
      state = state.copyWith(
        items: items,
        inFlightIds: {...state.inFlightIds}..remove(jobId),
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = state.copyWith(
        inFlightIds: {...state.inFlightIds}..remove(jobId),
        actionErrors: {...state.actionErrors, jobId: error.code},
      );
    }
  }
}

const _absent = Object();
