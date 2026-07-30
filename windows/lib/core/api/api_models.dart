import 'package:flutter/foundation.dart';

class ProtocolException implements Exception {
  const ProtocolException(this.message);

  final String message;

  @override
  String toString() => 'ProtocolException: $message';
}

@immutable
class BootstrapStatus {
  const BootstrapStatus({required this.initialized, required this.apiVersion});

  factory BootstrapStatus.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'BootstrapStatus');
    final apiVersion = reader.integer('api_version');
    if (apiVersion != 1) {
      throw const ProtocolException('unsupported API version');
    }
    return BootstrapStatus(
      initialized: reader.boolean('initialized'),
      apiVersion: apiVersion,
    );
  }

  final bool initialized;
  final int apiVersion;
}

@immutable
class TokenPair {
  const TokenPair({
    required this.accessToken,
    required this.refreshToken,
    required this.accessExpiresAt,
    required this.refreshExpiresAt,
  });

  factory TokenPair.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'TokenPair');
    if (reader.string('token_type') != 'Bearer') {
      throw const ProtocolException('unsupported token type');
    }
    return TokenPair(
      accessToken: reader.nonEmptyString('access_token'),
      refreshToken: reader.nonEmptyString('refresh_token'),
      accessExpiresAt: reader.dateTime('access_expires_at'),
      refreshExpiresAt: reader.dateTime('refresh_expires_at'),
    );
  }

  final String accessToken;
  final String refreshToken;
  final DateTime accessExpiresAt;
  final DateTime refreshExpiresAt;
}

@immutable
class ApiErrorBody {
  const ApiErrorBody({
    required this.code,
    required this.message,
    required this.requestId,
    this.details,
  });

  factory ApiErrorBody.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'ApiError');
    final code = reader.string('code');
    if (!RegExp(r'^[a-z0-9_]+$').hasMatch(code)) {
      throw const ProtocolException('invalid API error code');
    }
    final rawDetails = json['details'];
    Map<String, Object?>? details;
    if (rawDetails != null) {
      details = Map<String, Object?>.unmodifiable(reader.object('details'));
    }
    return ApiErrorBody(
      code: code,
      message: reader.string('message'),
      requestId: reader.string('request_id'),
      details: details,
    );
  }

  final String code;
  final String message;
  final String requestId;
  final Map<String, Object?>? details;
}

@immutable
class QueueSnapshot {
  const QueueSnapshot({
    required this.metadataQueued,
    required this.metadataRunning,
    required this.cacheQueued,
    required this.cacheRunning,
    required this.cacheReady,
  });

  factory QueueSnapshot.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'QueueSnapshot');
    return QueueSnapshot(
      metadataQueued: reader.nonNegativeInteger('metadata_queued'),
      metadataRunning: reader.nonNegativeInteger('metadata_running'),
      cacheQueued: reader.nonNegativeInteger('cache_queued'),
      cacheRunning: reader.nonNegativeInteger('cache_running'),
      cacheReady: reader.nonNegativeInteger('cache_ready'),
    );
  }

  final int metadataQueued;
  final int metadataRunning;
  final int cacheQueued;
  final int cacheRunning;
  final int cacheReady;
}

const cacheJobStatuses = <String>{
  'queued',
  'submitting',
  'offlining',
  'submit_uncertain',
  'resolving',
  'awaiting_selection',
  'ready',
  'cancelling',
  'cleaning',
  'cleanup_failed',
  'failed',
  'cleaned',
  'detached',
};

@immutable
class RemoteMediaDto {
  const RemoteMediaDto({
    required this.id,
    required this.candidateId,
    required this.name,
    required this.sizeBytes,
    required this.durationSeconds,
    required this.sequenceNo,
    required this.isValid,
  });

  factory RemoteMediaDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'RemoteMedia');
    return RemoteMediaDto(
      id: reader.uuid('id'),
      candidateId: reader.uuid('candidate_id'),
      name: reader.string('name'),
      sizeBytes: reader.nonNegativeInteger('size_bytes'),
      durationSeconds: reader.nullableInteger('duration_seconds'),
      sequenceNo: reader.integer('sequence_no'),
      isValid: reader.boolean('is_valid'),
    );
  }

  final String id;
  final String candidateId;
  final String name;
  final int sizeBytes;
  final int? durationSeconds;
  final int sequenceNo;
  final bool isValid;
}

@immutable
class SubtitleOptionDto {
  const SubtitleOptionDto({
    required this.id,
    required this.mediaId,
    required this.name,
    required this.format,
    required this.language,
    required this.selectedByDefault,
  });

  factory SubtitleOptionDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'SubtitleOption');
    return SubtitleOptionDto(
      id: reader.uuid('id'),
      mediaId: reader.nullableUuid('media_id'),
      name: reader.string('name'),
      format: reader.enumeration('format', const {'srt', 'ass', 'ssa', 'vtt'}),
      language: reader.nullableString('language'),
      selectedByDefault: reader.boolean('selected_by_default'),
    );
  }

  final String id;
  final String? mediaId;
  final String name;
  final String format;
  final String? language;
  final bool selectedByDefault;
}

@immutable
class CacheJobDto {
  const CacheJobDto({
    required this.id,
    required this.movieId,
    required this.sourceId,
    required this.status,
    required this.remotePercent,
    required this.errorCode,
    required this.mediaCandidates,
    required this.selectedMediaIds,
    required this.subtitles,
    required this.readyAt,
    required this.expiresAt,
    required this.createdAt,
    required this.updatedAt,
  });

  factory CacheJobDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'CacheJob');
    final percent = reader.number('remote_percent');
    if (percent < 0 || percent > 100) {
      throw const ProtocolException('CacheJob.remote_percent is out of range');
    }
    return CacheJobDto(
      id: reader.uuid('id'),
      movieId: reader.uuid('movie_id'),
      sourceId: reader.uuid('source_id'),
      status: reader.enumeration('status', cacheJobStatuses),
      remotePercent: percent,
      errorCode: reader.nullableString('error_code'),
      mediaCandidates: reader.objectList(
        'media_candidates',
        RemoteMediaDto.fromJson,
      ),
      selectedMediaIds: reader.uuidList('selected_media_ids'),
      subtitles: reader.objectList('subtitles', SubtitleOptionDto.fromJson),
      readyAt: reader.nullableDateTime('ready_at'),
      expiresAt: reader.nullableDateTime('expires_at'),
      createdAt: reader.dateTime('created_at'),
      updatedAt: reader.dateTime('updated_at'),
    );
  }

  final String id;
  final String movieId;
  final String sourceId;
  final String status;
  final num remotePercent;
  final String? errorCode;
  final List<RemoteMediaDto> mediaCandidates;
  final List<String> selectedMediaIds;
  final List<SubtitleOptionDto> subtitles;
  final DateTime? readyAt;
  final DateTime? expiresAt;
  final DateTime createdAt;
  final DateTime updatedAt;

  CacheJobDto copyWith({
    String? status,
    num? remotePercent,
    PatchValue<String?> errorCode = const PatchValue.absent(),
    List<RemoteMediaDto>? mediaCandidates,
    List<String>? selectedMediaIds,
    List<SubtitleOptionDto>? subtitles,
    PatchValue<DateTime?> readyAt = const PatchValue.absent(),
    PatchValue<DateTime?> expiresAt = const PatchValue.absent(),
    DateTime? updatedAt,
  }) => CacheJobDto(
    id: id,
    movieId: movieId,
    sourceId: sourceId,
    status: status ?? this.status,
    remotePercent: remotePercent ?? this.remotePercent,
    errorCode: errorCode.isPresent ? errorCode.value : this.errorCode,
    mediaCandidates: mediaCandidates ?? this.mediaCandidates,
    selectedMediaIds: selectedMediaIds ?? this.selectedMediaIds,
    subtitles: subtitles ?? this.subtitles,
    readyAt: readyAt.isPresent ? readyAt.value : this.readyAt,
    expiresAt: expiresAt.isPresent ? expiresAt.value : this.expiresAt,
    createdAt: createdAt,
    updatedAt: updatedAt ?? this.updatedAt,
  );
}

@immutable
class MetadataStageDto {
  const MetadataStageDto({
    required this.stage,
    required this.status,
    required this.elapsedMs,
    required this.errorCode,
  });

  factory MetadataStageDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'MetadataStage');
    return MetadataStageDto(
      stage: reader.string('stage'),
      status: reader.string('status'),
      elapsedMs:
          json.containsKey('elapsed_ms')
              ? reader.nullableInteger('elapsed_ms')
              : null,
      errorCode: reader.nullableString('error_code'),
    );
  }

  final String stage;
  final String status;
  final int? elapsedMs;
  final String? errorCode;
}

@immutable
class MetadataJobDto {
  const MetadataJobDto({
    required this.id,
    required this.movieId,
    required this.number,
    required this.priority,
    required this.reason,
    required this.retryMode,
    required this.requestedStages,
    required this.parentJobId,
    required this.status,
    required this.stage,
    required this.attemptNo,
    required this.elapsedMs,
    required this.errorCode,
    required this.stages,
    required this.retryableStages,
    required this.createdAt,
  });

  factory MetadataJobDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'MetadataJob');
    return MetadataJobDto(
      id: reader.uuid('id'),
      movieId: reader.nullableUuid('movie_id'),
      number: reader.string('number'),
      priority: reader.integer('priority'),
      reason: reader.enumeration('reason', const {
        'manual_or_search',
        'ranking',
        'daily',
        'initial',
        'history',
      }),
      retryMode: reader.enumeration('retry_mode', const {
        'full',
        'missing_enrichment',
      }),
      requestedStages: reader.stringList('requested_stages'),
      parentJobId: reader.nullableUuid('parent_job_id'),
      status: reader.enumeration('status', const {
        'queued',
        'running',
        'completed',
        'completed_with_warnings',
        'failed',
      }),
      stage: reader.nullableString('stage'),
      attemptNo: reader.positiveInteger('attempt_no'),
      elapsedMs: reader.nullableInteger('elapsed_ms'),
      errorCode: reader.nullableString('error_code'),
      stages: reader.objectList('stages', MetadataStageDto.fromJson),
      retryableStages: reader.stringList('retryable_stages'),
      createdAt: reader.dateTime('created_at'),
    );
  }

  final String id;
  final String? movieId;
  final String number;
  final int priority;
  final String reason;
  final String retryMode;
  final List<String> requestedStages;
  final String? parentJobId;
  final String status;
  final String? stage;
  final int attemptNo;
  final int? elapsedMs;
  final String? errorCode;
  final List<MetadataStageDto> stages;
  final List<String> retryableStages;
  final DateTime createdAt;

  MetadataJobDto copyWith({
    PatchValue<String?> movieId = const PatchValue.absent(),
    int? priority,
    String? status,
    PatchValue<String?> stage = const PatchValue.absent(),
    PatchValue<int?> elapsedMs = const PatchValue.absent(),
    PatchValue<String?> errorCode = const PatchValue.absent(),
    List<MetadataStageDto>? stages,
    List<String>? retryableStages,
  }) => MetadataJobDto(
    id: id,
    movieId: movieId.isPresent ? movieId.value : this.movieId,
    number: number,
    priority: priority ?? this.priority,
    reason: reason,
    retryMode: retryMode,
    requestedStages: requestedStages,
    parentJobId: parentJobId,
    status: status ?? this.status,
    stage: stage.isPresent ? stage.value : this.stage,
    attemptNo: attemptNo,
    elapsedMs: elapsedMs.isPresent ? elapsedMs.value : this.elapsedMs,
    errorCode: errorCode.isPresent ? errorCode.value : this.errorCode,
    stages: stages ?? this.stages,
    retryableStages: retryableStages ?? this.retryableStages,
    createdAt: createdAt,
  );
}

@immutable
class Cloud115BindingDto {
  const Cloud115BindingDto({
    required this.bound,
    required this.status,
    required this.displayName,
    required this.cacheRootReady,
    required this.lastVerifiedAt,
  });

  factory Cloud115BindingDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'Cloud115Binding');
    return Cloud115BindingDto(
      bound: reader.boolean('bound'),
      status: reader.enumeration('status', const {
        'unbound',
        'active',
        'expired',
        'unavailable',
        'detached',
      }),
      displayName: reader.nullableString('display_name'),
      cacheRootReady: reader.boolean('cache_root_ready'),
      lastVerifiedAt: reader.nullableDateTime('last_verified_at'),
    );
  }

  final bool bound;
  final String status;
  final String? displayName;
  final bool cacheRootReady;
  final DateTime? lastVerifiedAt;

  Cloud115BindingDto copyWith({
    bool? bound,
    String? status,
    PatchValue<String?> displayName = const PatchValue.absent(),
    bool? cacheRootReady,
    PatchValue<DateTime?> lastVerifiedAt = const PatchValue.absent(),
  }) => Cloud115BindingDto(
    bound: bound ?? this.bound,
    status: status ?? this.status,
    displayName: displayName.isPresent ? displayName.value : this.displayName,
    cacheRootReady: cacheRootReady ?? this.cacheRootReady,
    lastVerifiedAt:
        lastVerifiedAt.isPresent ? lastVerifiedAt.value : this.lastVerifiedAt,
  );
}

@immutable
class NotificationDto {
  const NotificationDto({
    required this.id,
    required this.type,
    required this.resourceId,
    required this.errorCode,
    required this.createdAt,
    required this.readAt,
  });

  factory NotificationDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'Notification');
    return NotificationDto(
      id: reader.uuid('id'),
      type: reader.enumeration('type', const {
        'cache_started',
        'cache_ready',
        'cache_failed',
        'credential_expired',
      }),
      resourceId: reader.nullableUuid('resource_id'),
      errorCode: reader.nullableString('error_code'),
      createdAt: reader.dateTime('created_at'),
      readAt: reader.nullableDateTime('read_at'),
    );
  }

  final String id;
  final String type;
  final String? resourceId;
  final String? errorCode;
  final DateTime createdAt;
  final DateTime? readAt;
}

@immutable
class EventSnapshotDto {
  const EventSnapshotDto({
    required this.snapshotVersion,
    required this.lastEventId,
    required this.queues,
    required this.cacheJobs,
    required this.metadataJobs,
    required this.cloud115Binding,
    required this.notifications,
  });

  factory EventSnapshotDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'EventSnapshot');
    return EventSnapshotDto(
      snapshotVersion: reader.nonNegativeInteger('snapshot_version'),
      lastEventId: reader.nullableUuid('last_event_id'),
      queues: QueueSnapshot.fromJson(reader.object('queues')),
      cacheJobs: reader.objectList('cache_jobs', CacheJobDto.fromJson),
      metadataJobs: reader.objectList('metadata_jobs', MetadataJobDto.fromJson),
      cloud115Binding: Cloud115BindingDto.fromJson(
        reader.object('cloud115_binding'),
      ),
      notifications: reader.objectList(
        'notifications',
        NotificationDto.fromJson,
      ),
    );
  }

  final int snapshotVersion;
  final String? lastEventId;
  final QueueSnapshot queues;
  final List<CacheJobDto> cacheJobs;
  final List<MetadataJobDto> metadataJobs;
  final Cloud115BindingDto cloud115Binding;
  final List<NotificationDto> notifications;
}

@immutable
class PatchValue<T> {
  const PatchValue.absent() : isPresent = false, value = null;

  const PatchValue.present(T this.value) : isPresent = true;

  final bool isPresent;
  final T? value;
}

class JsonReader {
  const JsonReader(this.json, this.context);

  final Map<String, Object?> json;
  final String context;

  Object? _required(String key) {
    if (!json.containsKey(key)) {
      throw ProtocolException('$context.$key is required');
    }
    return json[key];
  }

  String string(String key) {
    final value = _required(key);
    if (value is! String) {
      throw ProtocolException('$context.$key must be a string');
    }
    return value;
  }

  String nonEmptyString(String key) {
    final value = string(key);
    if (value.isEmpty) {
      throw ProtocolException('$context.$key must not be empty');
    }
    return value;
  }

  String? nullableString(String key) {
    final value = _required(key);
    if (value == null) return null;
    if (value is! String) {
      throw ProtocolException('$context.$key must be a string or null');
    }
    return value;
  }

  bool boolean(String key) {
    final value = _required(key);
    if (value is! bool) {
      throw ProtocolException('$context.$key must be a boolean');
    }
    return value;
  }

  int integer(String key) {
    final value = _required(key);
    if (value is! int) {
      throw ProtocolException('$context.$key must be an integer');
    }
    return value;
  }

  int nonNegativeInteger(String key) {
    final value = integer(key);
    if (value < 0) {
      throw ProtocolException('$context.$key must be non-negative');
    }
    return value;
  }

  int positiveInteger(String key) {
    final value = integer(key);
    if (value < 1) {
      throw ProtocolException('$context.$key must be positive');
    }
    return value;
  }

  int? nullableInteger(String key) {
    final value = _required(key);
    if (value == null) return null;
    if (value is! int) {
      throw ProtocolException('$context.$key must be an integer or null');
    }
    return value;
  }

  num number(String key) {
    final value = _required(key);
    if (value is! num || !value.isFinite) {
      throw ProtocolException('$context.$key must be a finite number');
    }
    return value;
  }

  DateTime dateTime(String key) {
    final value = DateTime.tryParse(string(key));
    if (value == null) {
      throw ProtocolException('$context.$key must be an RFC 3339 timestamp');
    }
    return value.toUtc();
  }

  DateTime? nullableDateTime(String key) {
    final raw = nullableString(key);
    if (raw == null) return null;
    final value = DateTime.tryParse(raw);
    if (value == null) {
      throw ProtocolException('$context.$key must be an RFC 3339 timestamp');
    }
    return value.toUtc();
  }

  String uuid(String key) {
    final value = string(key);
    if (!_uuidPattern.hasMatch(value)) {
      throw ProtocolException('$context.$key must be a UUID');
    }
    return value;
  }

  String? nullableUuid(String key) {
    final value = nullableString(key);
    if (value != null && !_uuidPattern.hasMatch(value)) {
      throw ProtocolException('$context.$key must be a UUID or null');
    }
    return value;
  }

  String enumeration(String key, Set<String> allowed) {
    final value = string(key);
    if (!allowed.contains(value)) {
      throw ProtocolException('$context.$key has an unknown value');
    }
    return value;
  }

  Map<String, Object?> object(String key) {
    final value = _required(key);
    if (value is! Map) {
      throw ProtocolException('$context.$key must be an object');
    }
    try {
      return Map<String, Object?>.from(value);
    } on TypeError {
      throw ProtocolException('$context.$key has a non-string key');
    }
  }

  List<T> objectList<T>(
    String key,
    T Function(Map<String, Object?> json) parse,
  ) {
    final value = _required(key);
    if (value is! List) {
      throw ProtocolException('$context.$key must be an array');
    }
    return List<T>.unmodifiable(
      value.map((item) {
        if (item is! Map) {
          throw ProtocolException('$context.$key must contain objects');
        }
        try {
          return parse(Map<String, Object?>.from(item));
        } on TypeError {
          throw ProtocolException('$context.$key has a non-string key');
        }
      }),
    );
  }

  List<String> stringList(String key) {
    final value = _required(key);
    if (value is! List || value.any((item) => item is! String)) {
      throw ProtocolException('$context.$key must be a string array');
    }
    return List<String>.unmodifiable(value.cast<String>());
  }

  List<String> uuidList(String key) {
    final values = stringList(key);
    if (values.any((value) => !_uuidPattern.hasMatch(value))) {
      throw ProtocolException('$context.$key must contain UUIDs');
    }
    return values;
  }

  static final RegExp _uuidPattern = RegExp(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$',
  );
}
