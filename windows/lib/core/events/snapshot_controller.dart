import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/app_lifecycle.dart';

enum EventApplyResult { applied, ignored, recovered }

@immutable
class SnapshotState {
  const SnapshotState({
    required this.snapshotVersion,
    required this.lastEventId,
    required this.queues,
    required this.cacheJobs,
    required this.metadataJobs,
    required this.cloud115Binding,
    required this.notifications,
    required this.recoveryRevision,
    required this.catalogReadyRevision,
    required this.lastCatalogMovieReady,
  });

  factory SnapshotState.empty() => const SnapshotState(
    snapshotVersion: 0,
    lastEventId: null,
    queues: QueueSnapshot(
      metadataQueued: 0,
      metadataRunning: 0,
      cacheQueued: 0,
      cacheRunning: 0,
      cacheReady: 0,
    ),
    cacheJobs: <String, CacheJobDto>{},
    metadataJobs: <String, MetadataJobDto>{},
    cloud115Binding: Cloud115BindingDto(
      bound: false,
      status: 'unbound',
      displayName: null,
      cacheRootReady: false,
      lastVerifiedAt: null,
    ),
    notifications: <String, NotificationDto>{},
    recoveryRevision: 0,
    catalogReadyRevision: 0,
    lastCatalogMovieReady: null,
  );

  final int snapshotVersion;
  final String? lastEventId;
  final QueueSnapshot queues;
  final Map<String, CacheJobDto> cacheJobs;
  final Map<String, MetadataJobDto> metadataJobs;
  final Cloud115BindingDto cloud115Binding;
  final Map<String, NotificationDto> notifications;
  final int recoveryRevision;
  final int catalogReadyRevision;
  final CatalogMoviePatch? lastCatalogMovieReady;

  SnapshotState copyWith({
    int? snapshotVersion,
    PatchValue<String?> lastEventId = const PatchValue.absent(),
    QueueSnapshot? queues,
    Map<String, CacheJobDto>? cacheJobs,
    Map<String, MetadataJobDto>? metadataJobs,
    Cloud115BindingDto? cloud115Binding,
    Map<String, NotificationDto>? notifications,
    int? recoveryRevision,
    int? catalogReadyRevision,
    PatchValue<CatalogMoviePatch?> lastCatalogMovieReady =
        const PatchValue.absent(),
  }) => SnapshotState(
    snapshotVersion: snapshotVersion ?? this.snapshotVersion,
    lastEventId: lastEventId.isPresent ? lastEventId.value : this.lastEventId,
    queues: queues ?? this.queues,
    cacheJobs: cacheJobs ?? this.cacheJobs,
    metadataJobs: metadataJobs ?? this.metadataJobs,
    cloud115Binding: cloud115Binding ?? this.cloud115Binding,
    notifications: notifications ?? this.notifications,
    recoveryRevision: recoveryRevision ?? this.recoveryRevision,
    catalogReadyRevision: catalogReadyRevision ?? this.catalogReadyRevision,
    lastCatalogMovieReady:
        lastCatalogMovieReady.isPresent
            ? lastCatalogMovieReady.value
            : this.lastCatalogMovieReady,
  );
}

class SnapshotStateNotifier extends Notifier<SnapshotState> {
  @override
  SnapshotState build() => SnapshotState.empty();

  void replace(SnapshotState value) => state = value;

  void clear() => state = SnapshotState.empty();
}

final snapshotStateProvider =
    NotifierProvider<SnapshotStateNotifier, SnapshotState>(
      SnapshotStateNotifier.new,
    );

sealed class EventResourcePatch {
  const EventResourcePatch();

  String get resourceKey;
}

class CacheJobPatch extends EventResourcePatch {
  const CacheJobPatch({
    required this.id,
    this.status,
    this.remotePercent,
    this.errorCode = const PatchValue.absent(),
    this.mediaCandidates,
    this.selectedMediaIds,
    this.subtitles,
    this.readyAt = const PatchValue.absent(),
    this.expiresAt = const PatchValue.absent(),
    this.updatedAt,
  });

  factory CacheJobPatch.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'CacheJobPatch');
    num? remotePercent;
    if (json.containsKey('remote_percent')) {
      remotePercent = reader.number('remote_percent');
      if (remotePercent < 0 || remotePercent > 100) {
        throw const ProtocolException(
          'CacheJobPatch.remote_percent is invalid',
        );
      }
    }
    return CacheJobPatch(
      id: reader.uuid('id'),
      status:
          json.containsKey('status')
              ? reader.enumeration('status', cacheJobStatuses)
              : null,
      remotePercent: remotePercent,
      errorCode: _nullableStringPatch(reader, 'error_code'),
      mediaCandidates:
          json.containsKey('media_candidates')
              ? reader.objectList('media_candidates', RemoteMediaDto.fromJson)
              : null,
      selectedMediaIds:
          json.containsKey('selected_media_ids')
              ? reader.uuidList('selected_media_ids')
              : null,
      subtitles:
          json.containsKey('subtitles')
              ? reader.objectList('subtitles', SubtitleOptionDto.fromJson)
              : null,
      readyAt: _nullableDateTimePatch(reader, 'ready_at'),
      expiresAt: _nullableDateTimePatch(reader, 'expires_at'),
      updatedAt:
          json.containsKey('updated_at') ? reader.dateTime('updated_at') : null,
    );
  }

  final String id;
  final String? status;
  final num? remotePercent;
  final PatchValue<String?> errorCode;
  final List<RemoteMediaDto>? mediaCandidates;
  final List<String>? selectedMediaIds;
  final List<SubtitleOptionDto>? subtitles;
  final PatchValue<DateTime?> readyAt;
  final PatchValue<DateTime?> expiresAt;
  final DateTime? updatedAt;

  @override
  String get resourceKey => 'cache:$id';

  CacheJobDto apply(CacheJobDto current) => current.copyWith(
    status: status,
    remotePercent: remotePercent,
    errorCode: errorCode,
    mediaCandidates: mediaCandidates,
    selectedMediaIds: selectedMediaIds,
    subtitles: subtitles,
    readyAt: readyAt,
    expiresAt: expiresAt,
    updatedAt: updatedAt,
  );
}

class MetadataJobPatch extends EventResourcePatch {
  const MetadataJobPatch({
    required this.id,
    this.movieId = const PatchValue.absent(),
    this.priority,
    this.status,
    this.stage = const PatchValue.absent(),
    this.elapsedMs = const PatchValue.absent(),
    this.errorCode = const PatchValue.absent(),
  });

  factory MetadataJobPatch.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'MetadataJobPatch');
    return MetadataJobPatch(
      id: reader.uuid('id'),
      movieId: _nullableUuidPatch(reader, 'movie_id'),
      priority:
          json.containsKey('priority') ? reader.integer('priority') : null,
      status:
          json.containsKey('status')
              ? reader.enumeration('status', const {
                'queued',
                'running',
                'completed',
                'completed_with_warnings',
                'failed',
              })
              : null,
      stage: _nullableStringPatch(reader, 'stage'),
      elapsedMs: _nullableIntegerPatch(reader, 'elapsed_ms'),
      errorCode: _nullableStringPatch(reader, 'error_code'),
    );
  }

  final String id;
  final PatchValue<String?> movieId;
  final int? priority;
  final String? status;
  final PatchValue<String?> stage;
  final PatchValue<int?> elapsedMs;
  final PatchValue<String?> errorCode;

  @override
  String get resourceKey => 'metadata:$id';

  MetadataJobDto apply(MetadataJobDto current) => current.copyWith(
    movieId: movieId,
    priority: priority,
    status: status,
    stage: stage,
    elapsedMs: elapsedMs,
    errorCode: errorCode,
  );
}

class CredentialPatch extends EventResourcePatch {
  const CredentialPatch({
    this.bound,
    this.status,
    this.displayName = const PatchValue.absent(),
    this.cacheRootReady,
    this.lastVerifiedAt = const PatchValue.absent(),
  });

  factory CredentialPatch.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'CredentialPatch');
    return CredentialPatch(
      bound: json.containsKey('bound') ? reader.boolean('bound') : null,
      status:
          json.containsKey('status')
              ? reader.enumeration('status', const {
                'unbound',
                'active',
                'expired',
                'unavailable',
                'detached',
              })
              : null,
      displayName: _nullableStringPatch(reader, 'display_name'),
      cacheRootReady:
          json.containsKey('cache_root_ready')
              ? reader.boolean('cache_root_ready')
              : null,
      lastVerifiedAt: _nullableDateTimePatch(reader, 'last_verified_at'),
    );
  }

  final bool? bound;
  final String? status;
  final PatchValue<String?> displayName;
  final bool? cacheRootReady;
  final PatchValue<DateTime?> lastVerifiedAt;

  @override
  String get resourceKey => 'credential:cloud115';

  Cloud115BindingDto apply(Cloud115BindingDto current) => current.copyWith(
    bound: bound,
    status: status,
    displayName: displayName,
    cacheRootReady: cacheRootReady,
    lastVerifiedAt: lastVerifiedAt,
  );
}

class NotificationPatch extends EventResourcePatch {
  const NotificationPatch(this.notification);

  final NotificationDto notification;

  @override
  String get resourceKey => 'notification:${notification.id}';
}

class CatalogMoviePatch extends EventResourcePatch {
  const CatalogMoviePatch({required this.movieId, required this.number});

  factory CatalogMoviePatch.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'CatalogMoviePatch');
    return CatalogMoviePatch(
      movieId: reader.uuid('movie_id'),
      number: reader.string('number'),
    );
  }

  final String movieId;
  final String number;

  @override
  String get resourceKey => 'catalog:$movieId';
}

@immutable
class EventEnvelope {
  const EventEnvelope({
    required this.eventId,
    required this.sequence,
    required this.stream,
    required this.streamVersion,
    required this.type,
    required this.occurredAt,
    required this.patch,
  });

  factory EventEnvelope.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'EventEnvelope');
    if (reader.integer('version') != 1) {
      throw const ProtocolException('unknown event envelope version');
    }
    final type = reader.string('type');
    final stream = reader.enumeration('stream', const {
      'metadata',
      'cache',
      'credential',
      'catalog',
      'notification',
    });
    if (!_eventTypes.contains(type) || !type.startsWith('$stream.')) {
      throw const ProtocolException('unknown or mismatched event type');
    }
    final resource = reader.object('resource');
    final patch = switch (stream) {
      'cache' => CacheJobPatch.fromJson(resource),
      'metadata' => MetadataJobPatch.fromJson(resource),
      'credential' => CredentialPatch.fromJson(resource),
      'notification' => NotificationPatch(NotificationDto.fromJson(resource)),
      'catalog' => CatalogMoviePatch.fromJson(resource),
      _ => throw const ProtocolException('unknown event stream'),
    };
    return EventEnvelope(
      eventId: reader.uuid('event_id'),
      sequence: reader.positiveInteger('sequence'),
      stream: stream,
      streamVersion: reader.positiveInteger('stream_version'),
      type: type,
      occurredAt: reader.dateTime('occurred_at'),
      patch: patch,
    );
  }

  final String eventId;
  final int sequence;
  final String stream;
  final int streamVersion;
  final String type;
  final DateTime occurredAt;
  final EventResourcePatch patch;

  static const _eventTypes = <String>{
    'metadata.job.queued.v1',
    'metadata.job.started.v1',
    'metadata.job.stage_changed.v1',
    'metadata.job.completed.v1',
    'metadata.job.failed.v1',
    'cache.job.created.v1',
    'cache.job.updated.v1',
    'cache.job.selection_required.v1',
    'cache.job.ready.v1',
    'cache.job.failed.v1',
    'cache.job.cancelled.v1',
    'cache.job.cleaned.v1',
    'cache.job.cleanup_failed.v1',
    'cache.job.detached.v1',
    'credential.cloud115.changed.v1',
    'notification.created.v1',
    'notification.read.v1',
    'catalog.movie.core_ready.v1',
  };
}

class SnapshotController extends ChangeNotifier {
  SnapshotController({
    required Future<EventSnapshotDto> Function() loadSnapshot,
    NotificationCoordinator? notifications,
  }) : _loadSnapshot = loadSnapshot,
       _notificationCoordinator = notifications;

  final Future<EventSnapshotDto> Function() _loadSnapshot;
  final NotificationCoordinator? _notificationCoordinator;
  final LinkedHashSet<String> _seenEventIds = LinkedHashSet<String>();
  final Map<String, int?> _resourceVersions = <String, int?>{};
  Future<void>? _recoveryInFlight;
  SnapshotState _state = SnapshotState.empty();

  SnapshotState get state => _state;

  Future<void> recover() {
    final active = _recoveryInFlight;
    if (active != null) return active;
    final operation = _recover();
    _recoveryInFlight = operation;
    unawaited(
      operation.then<void>(
        (_) => _clearRecovery(operation),
        onError: (Object _, StackTrace __) => _clearRecovery(operation),
      ),
    );
    return operation;
  }

  Future<void> _recover() async {
    final snapshot = await _loadSnapshot();
    final previous = _state;
    _state = SnapshotState(
      snapshotVersion: snapshot.snapshotVersion,
      lastEventId: snapshot.lastEventId,
      queues: snapshot.queues,
      cacheJobs: Map<String, CacheJobDto>.unmodifiable({
        for (final item in snapshot.cacheJobs) item.id: item,
      }),
      metadataJobs: Map<String, MetadataJobDto>.unmodifiable({
        for (final item in snapshot.metadataJobs) item.id: item,
      }),
      cloud115Binding: snapshot.cloud115Binding,
      notifications: Map<String, NotificationDto>.unmodifiable({
        for (final item in snapshot.notifications) item.id: item,
      }),
      recoveryRevision: previous.recoveryRevision + 1,
      catalogReadyRevision: previous.catalogReadyRevision,
      lastCatalogMovieReady: previous.lastCatalogMovieReady,
    );
    _resourceVersions
      ..clear()
      ..addEntries(
        snapshot.cacheJobs.map((item) => MapEntry('cache:${item.id}', null)),
      )
      ..addEntries(
        snapshot.metadataJobs.map(
          (item) => MapEntry('metadata:${item.id}', null),
        ),
      )
      ..['credential:cloud115'] = null
      ..addEntries(
        snapshot.notifications.map(
          (item) => MapEntry('notification:${item.id}', null),
        ),
      );
    _seenEventIds.clear();
    notifyListeners();
    await _deliverUnread(snapshot.notifications);
  }

  Future<EventApplyResult> apply(EventEnvelope event) async {
    if (_seenEventIds.contains(event.eventId) ||
        event.sequence <= _state.snapshotVersion) {
      return EventApplyResult.ignored;
    }
    if (event.sequence != _state.snapshotVersion + 1) {
      await recover();
      return EventApplyResult.recovered;
    }
    final patch = event.patch;
    final hasResource = _hasResource(patch);
    if (!hasResource) {
      await recover();
      return EventApplyResult.recovered;
    }
    final localVersion = _resourceVersions[patch.resourceKey];
    if (localVersion != null) {
      if (event.streamVersion <= localVersion) {
        _remember(event.eventId);
        _advanceSequence(event.sequence, event.eventId);
        return EventApplyResult.ignored;
      }
      if (event.streamVersion != localVersion + 1) {
        await recover();
        return EventApplyResult.recovered;
      }
    }
    final requiresCapacityRefresh =
        patch is CacheJobPatch &&
        patch.status != null &&
        patch.status != _state.cacheJobs[patch.id]?.status;
    _applyPatch(patch);
    _resourceVersions[patch.resourceKey] = event.streamVersion;
    _remember(event.eventId);
    _advanceSequence(event.sequence, event.eventId);
    notifyListeners();
    if (patch is NotificationPatch) {
      await _deliverUnread(<NotificationDto>[patch.notification]);
    }
    if (requiresCapacityRefresh) {
      await recover();
      return EventApplyResult.recovered;
    }
    return EventApplyResult.applied;
  }

  bool _hasResource(EventResourcePatch patch) => switch (patch) {
    CacheJobPatch() => _state.cacheJobs.containsKey(patch.id),
    MetadataJobPatch() => _state.metadataJobs.containsKey(patch.id),
    CredentialPatch() => true,
    NotificationPatch() => _state.notifications.containsKey(
      patch.notification.id,
    ),
    CatalogMoviePatch() => true,
  };

  void _applyPatch(EventResourcePatch patch) {
    switch (patch) {
      case CacheJobPatch():
        final jobs = Map<String, CacheJobDto>.of(_state.cacheJobs);
        jobs[patch.id] = patch.apply(jobs[patch.id]!);
        _state = _state.copyWith(cacheJobs: Map.unmodifiable(jobs));
      case MetadataJobPatch():
        final jobs = Map<String, MetadataJobDto>.of(_state.metadataJobs);
        jobs[patch.id] = patch.apply(jobs[patch.id]!);
        _state = _state.copyWith(metadataJobs: Map.unmodifiable(jobs));
      case CredentialPatch():
        _state = _state.copyWith(
          cloud115Binding: patch.apply(_state.cloud115Binding),
        );
      case NotificationPatch():
        final notifications = Map<String, NotificationDto>.of(
          _state.notifications,
        );
        notifications[patch.notification.id] = patch.notification;
        _state = _state.copyWith(
          notifications: Map.unmodifiable(notifications),
        );
      case CatalogMoviePatch():
        _state = _state.copyWith(
          catalogReadyRevision: _state.catalogReadyRevision + 1,
          lastCatalogMovieReady: PatchValue.present(patch),
        );
    }
  }

  void _advanceSequence(int sequence, String eventId) {
    _state = _state.copyWith(
      snapshotVersion: sequence,
      lastEventId: PatchValue.present(eventId),
    );
  }

  void _remember(String eventId) {
    _seenEventIds.add(eventId);
    while (_seenEventIds.length > 2048) {
      _seenEventIds.remove(_seenEventIds.first);
    }
  }

  Future<void> _deliverUnread(List<NotificationDto> notifications) async {
    final coordinator = _notificationCoordinator;
    if (coordinator == null) return;
    for (final notification in notifications) {
      final marked = await coordinator.deliver(notification);
      if (marked == null) continue;
      final updated = Map<String, NotificationDto>.of(_state.notifications)
        ..[marked.id] = marked;
      _state = _state.copyWith(notifications: Map.unmodifiable(updated));
      notifyListeners();
    }
  }

  void _clearRecovery(Future<void> operation) {
    if (identical(_recoveryInFlight, operation)) {
      _recoveryInFlight = null;
    }
  }
}

PatchValue<String?> _nullableStringPatch(JsonReader reader, String key) =>
    reader.json.containsKey(key)
        ? PatchValue.present(reader.nullableString(key))
        : const PatchValue.absent();

PatchValue<String?> _nullableUuidPatch(JsonReader reader, String key) =>
    reader.json.containsKey(key)
        ? PatchValue.present(reader.nullableUuid(key))
        : const PatchValue.absent();

PatchValue<int?> _nullableIntegerPatch(JsonReader reader, String key) =>
    reader.json.containsKey(key)
        ? PatchValue.present(reader.nullableInteger(key))
        : const PatchValue.absent();

PatchValue<DateTime?> _nullableDateTimePatch(JsonReader reader, String key) =>
    reader.json.containsKey(key)
        ? PatchValue.present(reader.nullableDateTime(key))
        : const PatchValue.absent();
