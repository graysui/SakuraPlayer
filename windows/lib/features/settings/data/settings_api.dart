import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';

const providerStatuses = <String>{
  'unknown',
  'available',
  'unavailable',
  'credentials_invalid',
  'not_configured',
};
const connectionTargets = <String>{
  'cloud115',
  'javdb',
  'dmm',
  'gfriends',
  'ai',
};
const enrichmentStages = <String>{
  'images',
  'dmm',
  'actor_map',
  'gfriends',
  'translation',
};

@immutable
class QrSessionDto {
  const QrSessionDto({
    required this.id,
    required this.status,
    required this.imageBytes,
    required this.expiresAt,
  });

  factory QrSessionDto.fromJson(Map<String, Object?> json) {
    _rejectSecrets(json, 'QrSession');
    final reader = JsonReader(json, 'QrSession');
    Uint8List? image;
    final encoded = reader.nullableString('qrcode_png_base64');
    if (encoded != null) {
      try {
        image = Uint8List.fromList(base64Decode(encoded));
      } on FormatException {
        throw const ProtocolException('QrSession PNG is invalid');
      }
      const signature = <int>[137, 80, 78, 71, 13, 10, 26, 10];
      if (image.length < signature.length ||
          !listEquals(image.sublist(0, signature.length), signature)) {
        throw const ProtocolException('QrSession PNG is invalid');
      }
    }
    return QrSessionDto(
      id: reader.uuid('id'),
      status: reader.enumeration('status', const {
        'waiting',
        'scanned',
        'confirmed',
        'expired',
        'canceled',
      }),
      imageBytes: image,
      expiresAt: reader.dateTime('expires_at'),
    );
  }

  final String id;
  final String status;
  final Uint8List? imageBytes;
  final DateTime expiresAt;
}

@immutable
class ProviderStateDto {
  const ProviderStateDto({
    required this.configured,
    required this.status,
    required this.lastCheckedAt,
    required this.lastErrorCode,
  });

  factory ProviderStateDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'ProviderState');
    return ProviderStateDto(
      configured: reader.boolean('configured'),
      status: reader.enumeration('status', providerStatuses),
      lastCheckedAt: reader.nullableDateTime('last_checked_at'),
      lastErrorCode: reader.nullableString('last_error_code'),
    );
  }

  final bool configured;
  final String status;
  final DateTime? lastCheckedAt;
  final String? lastErrorCode;
}

@immutable
class JavdbSettingsDto extends ProviderStateDto {
  const JavdbSettingsDto({
    required super.configured,
    required super.status,
    required super.lastCheckedAt,
    required super.lastErrorCode,
    required this.username,
    required this.passwordConfigured,
    required this.version,
  });

  factory JavdbSettingsDto.fromJson(Map<String, Object?> json) {
    final provider = ProviderStateDto.fromJson(json);
    final reader = JsonReader(json, 'JavdbSettings');
    final version = reader.nonNegativeInteger('version');
    return JavdbSettingsDto(
      configured: provider.configured,
      status: provider.status,
      lastCheckedAt: provider.lastCheckedAt,
      lastErrorCode: provider.lastErrorCode,
      username: reader.nullableString('username'),
      passwordConfigured: reader.boolean('password_configured'),
      version: version,
    );
  }

  final String? username;
  final bool passwordConfigured;
  final int version;
}

@immutable
class AiSettingsDto extends ProviderStateDto {
  const AiSettingsDto({
    required super.configured,
    required super.status,
    required super.lastCheckedAt,
    required super.lastErrorCode,
    required this.baseUrl,
    required this.model,
    required this.timeoutSeconds,
    required this.apiKeyConfigured,
    required this.version,
  });

  factory AiSettingsDto.fromJson(Map<String, Object?> json) {
    final provider = ProviderStateDto.fromJson(json);
    final reader = JsonReader(json, 'AiSettings');
    final baseUrl = reader.nullableString('base_url');
    if (baseUrl != null) {
      final uri = Uri.tryParse(baseUrl);
      if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
        throw const ProtocolException('AiSettings.base_url is invalid');
      }
    }
    final timeout = reader.nullableInteger('timeout_seconds');
    if (timeout != null && (timeout < 1 || timeout > 600)) {
      throw const ProtocolException('AiSettings.timeout_seconds is invalid');
    }
    return AiSettingsDto(
      configured: provider.configured,
      status: provider.status,
      lastCheckedAt: provider.lastCheckedAt,
      lastErrorCode: provider.lastErrorCode,
      baseUrl: baseUrl,
      model: reader.nullableString('model'),
      timeoutSeconds: timeout,
      apiKeyConfigured: reader.boolean('api_key_configured'),
      version: reader.nonNegativeInteger('version'),
    );
  }

  final String? baseUrl;
  final String? model;
  final int? timeoutSeconds;
  final bool apiKeyConfigured;
  final int version;
}

@immutable
class SyncRunStateDto {
  const SyncRunStateDto({
    required this.status,
    this.importedCount = 0,
    required this.lastSuccessfulAt,
    required this.nextScheduledAt,
    required this.lastErrorCode,
  });

  factory SyncRunStateDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'SyncRunState');
    return SyncRunStateDto(
      status: reader.enumeration('status', const {
        'never',
        'running',
        'succeeded',
        'failed',
      }),
      importedCount: reader.nonNegativeInteger('imported_count'),
      lastSuccessfulAt: reader.nullableDateTime('last_successful_at'),
      nextScheduledAt: reader.nullableDateTime('next_scheduled_at'),
      lastErrorCode: reader.nullableString('last_error_code'),
    );
  }

  final String status;
  final int importedCount;
  final DateTime? lastSuccessfulAt;
  final DateTime? nextScheduledAt;
  final String? lastErrorCode;
}

@immutable
class SettingsDto {
  const SettingsDto({
    required this.cacheTtlHours,
    required this.readyCacheLimit,
    required this.metadataConcurrency,
    required this.metadataTimeoutSeconds,
    required this.javdb,
    required this.ai,
    required this.providers,
    required this.incrementalSync,
    required this.fullSync,
  });

  factory SettingsDto.fromJson(Map<String, Object?> json) {
    _rejectSecrets(json, 'Settings');
    final reader = JsonReader(json, 'Settings');
    final ttl = reader.integer('cache_ttl_hours');
    final readyLimit = reader.integer('ready_cache_limit');
    final concurrency = reader.integer('metadata_concurrency');
    final timeout = reader.integer('metadata_timeout_seconds');
    if (ttl < 1 ||
        ttl > 168 ||
        readyLimit != 20 ||
        concurrency != 3 ||
        timeout != 600) {
      throw const ProtocolException('Settings constants are invalid');
    }
    final providerJson = reader.object('providers');
    const allowedProviders = {'cloud115', 'dmm', 'gfriends', 'actor_mapping'};
    if (providerJson.keys.toSet().difference(allowedProviders).isNotEmpty ||
        allowedProviders.difference(providerJson.keys.toSet()).isNotEmpty) {
      throw const ProtocolException('Settings.providers is invalid');
    }
    final providers = <String, ProviderStateDto>{};
    for (final entry in providerJson.entries) {
      if (entry.value is! Map) {
        throw const ProtocolException('Settings.providers is invalid');
      }
      providers[entry.key] = ProviderStateDto.fromJson(
        Map<String, Object?>.from(entry.value! as Map),
      );
    }
    final sync = JsonReader(reader.object('avdb_sync'), 'AvdbSyncStatus');
    return SettingsDto(
      cacheTtlHours: ttl,
      readyCacheLimit: readyLimit,
      metadataConcurrency: concurrency,
      metadataTimeoutSeconds: timeout,
      javdb: JavdbSettingsDto.fromJson(reader.object('javdb')),
      ai: AiSettingsDto.fromJson(reader.object('ai')),
      providers: Map<String, ProviderStateDto>.unmodifiable(providers),
      incrementalSync: SyncRunStateDto.fromJson(sync.object('incremental_30d')),
      fullSync: SyncRunStateDto.fromJson(sync.object('full_reconcile')),
    );
  }

  final int cacheTtlHours;
  final int readyCacheLimit;
  final int metadataConcurrency;
  final int metadataTimeoutSeconds;
  final JavdbSettingsDto javdb;
  final AiSettingsDto ai;
  final Map<String, ProviderStateDto> providers;
  final SyncRunStateDto incrementalSync;
  final SyncRunStateDto fullSync;
}

@immutable
class ConnectionTestDto {
  const ConnectionTestDto({
    required this.target,
    required this.status,
    required this.errorCode,
    required this.elapsedMs,
    required this.checkedAt,
  });

  factory ConnectionTestDto.fromJson(Map<String, Object?> json) {
    _rejectSecrets(json, 'ConnectionTest');
    final reader = JsonReader(json, 'ConnectionTest');
    return ConnectionTestDto(
      target: reader.enumeration('target', connectionTargets),
      status: reader.enumeration('status', const {
        'available',
        'unavailable',
        'credentials_invalid',
        'not_configured',
      }),
      errorCode: reader.nullableString('error_code'),
      elapsedMs: reader.nonNegativeInteger('elapsed_ms'),
      checkedAt: reader.dateTime('checked_at'),
    );
  }

  final String target;
  final String status;
  final String? errorCode;
  final int elapsedMs;
  final DateTime checkedAt;
}

@immutable
class ComponentDiagnosticDto {
  const ComponentDiagnosticDto({
    required this.component,
    required this.status,
    required this.errorCode,
    required this.checkedAt,
  });

  factory ComponentDiagnosticDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'ComponentDiagnostic');
    return ComponentDiagnosticDto(
      component: reader.enumeration('component', const {
        'api',
        'scheduler',
        'worker',
        'postgres',
        'avdb',
        'javdb',
        'dmm',
        'gfriends',
        'ai',
        'cloud115',
      }),
      status: reader.enumeration('status', const {
        'healthy',
        'degraded',
        'unavailable',
        'credentials_invalid',
        'unknown',
      }),
      errorCode: reader.nullableString('error_code'),
      checkedAt: reader.dateTime('checked_at'),
    );
  }

  final String component;
  final String status;
  final String? errorCode;
  final DateTime checkedAt;
}

@immutable
class FailureDiagnosticDto {
  const FailureDiagnosticDto({
    required this.taskType,
    required this.taskId,
    required this.stage,
    required this.errorCode,
    required this.elapsedMs,
    required this.attemptNo,
    required this.occurredAt,
  });

  factory FailureDiagnosticDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'FailureDiagnostic');
    final elapsed = reader.nullableInteger('elapsed_ms');
    if (elapsed != null && elapsed < 0) {
      throw const ProtocolException('FailureDiagnostic.elapsed_ms is invalid');
    }
    return FailureDiagnosticDto(
      taskType: reader.enumeration('task_type', const {'metadata', 'cache'}),
      taskId: reader.uuid('task_id'),
      stage: reader.nullableString('stage'),
      errorCode: reader.nonEmptyString('error_code'),
      elapsedMs: elapsed,
      attemptNo: reader.positiveInteger('attempt_no'),
      occurredAt: reader.dateTime('occurred_at'),
    );
  }

  final String taskType;
  final String taskId;
  final String? stage;
  final String errorCode;
  final int? elapsedMs;
  final int attemptNo;
  final DateTime occurredAt;
}

@immutable
class DiagnosticsDto {
  const DiagnosticsDto({
    required this.generatedAt,
    required this.components,
    required this.queues,
    required this.metadataProgress,
    required this.recentFailures,
    required this.connectionTests,
  });

  factory DiagnosticsDto.fromJson(Map<String, Object?> json) {
    _rejectSecrets(json, 'Diagnostics');
    final reader = JsonReader(json, 'Diagnostics');
    final components = reader.objectList(
      'components',
      ComponentDiagnosticDto.fromJson,
    );
    final failures = reader.objectList(
      'recent_failures',
      FailureDiagnosticDto.fromJson,
    );
    final tests = reader.objectList(
      'connection_tests',
      ConnectionTestDto.fromJson,
    );
    if (components.length > 10 ||
        failures.length > 100 ||
        tests.length > 5 ||
        components.map((item) => item.component).toSet().length !=
            components.length ||
        tests.map((item) => item.target).toSet().length != tests.length) {
      throw const ProtocolException('Diagnostics collections are invalid');
    }
    final queuesJson = reader.object('queues');
    if (!queuesJson.containsKey('metadata_paused')) {
      throw const ProtocolException(
        'Diagnostics.queues.metadata_paused is required',
      );
    }
    final queues = QueueSnapshot.fromJson(queuesJson);
    final metadataProgress = MetadataProgressDto.fromJson(
      reader.object('metadata_progress'),
    );
    if (queues.metadataRunning > 3 ||
        queues.cacheQueued > 10 ||
        queues.cacheRunning > 2) {
      throw const ProtocolException('Diagnostics queues are invalid');
    }
    return DiagnosticsDto(
      generatedAt: reader.dateTime('generated_at'),
      components: components,
      queues: queues,
      metadataProgress: metadataProgress,
      recentFailures: failures,
      connectionTests: tests,
    );
  }

  final DateTime generatedAt;
  final List<ComponentDiagnosticDto> components;
  final QueueSnapshot queues;
  final MetadataProgressDto metadataProgress;
  final List<FailureDiagnosticDto> recentFailures;
  final List<ConnectionTestDto> connectionTests;
}

@immutable
class MetadataQueueControlDto {
  const MetadataQueueControlDto({
    required this.paused,
    required this.queued,
    required this.running,
  });

  factory MetadataQueueControlDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'MetadataQueueControl');
    final running = reader.nonNegativeInteger('running');
    if (running > 3) {
      throw const ProtocolException('MetadataQueueControl.running is invalid');
    }
    return MetadataQueueControlDto(
      paused: reader.boolean('paused'),
      queued: reader.nonNegativeInteger('queued'),
      running: running,
    );
  }

  final bool paused;
  final int queued;
  final int running;
}

@immutable
class MetadataProgressDto {
  const MetadataProgressDto({
    required this.total,
    required this.queued,
    required this.running,
    required this.completed,
    required this.failed,
    required this.finished,
    required this.currentNumbers,
  });

  factory MetadataProgressDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'MetadataProgress');
    final total = reader.nonNegativeInteger('total');
    final queued = reader.nonNegativeInteger('queued');
    final running = reader.nonNegativeInteger('running');
    final completed = reader.nonNegativeInteger('completed');
    final failed = reader.nonNegativeInteger('failed');
    final finished = reader.nonNegativeInteger('finished');
    final currentNumbers = reader.stringList('current_numbers');
    if (running > 3 ||
        total != queued + running + completed + failed ||
        finished != completed + failed ||
        currentNumbers.length != running ||
        currentNumbers.length > 3 ||
        currentNumbers.any((number) => number.isEmpty) ||
        currentNumbers.toSet().length != currentNumbers.length) {
      throw const ProtocolException('MetadataProgress is invalid');
    }
    return MetadataProgressDto(
      total: total,
      queued: queued,
      running: running,
      completed: completed,
      failed: failed,
      finished: finished,
      currentNumbers: List.unmodifiable(currentNumbers),
    );
  }

  final int total;
  final int queued;
  final int running;
  final int completed;
  final int failed;
  final int finished;
  final List<String> currentNumbers;

  double get fraction => total == 0 ? 0 : finished / total;
}

@immutable
class MetadataJobPageDto {
  const MetadataJobPageDto({required this.items, required this.nextCursor});

  factory MetadataJobPageDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'MetadataJobPage');
    final items = reader.objectList('items', MetadataJobDto.fromJson);
    if (items.length > 100 ||
        items.map((item) => item.id).toSet().length != items.length ||
        items.any(
          (item) =>
              item.retryableStages
                  .toSet()
                  .difference(enrichmentStages)
                  .isNotEmpty ||
              item.retryableStages.toSet().length !=
                  item.retryableStages.length,
        )) {
      throw const ProtocolException('MetadataJobPage.items is invalid');
    }
    return MetadataJobPageDto(
      items: items,
      nextCursor: reader.nullableString('next_cursor'),
    );
  }

  final List<MetadataJobDto> items;
  final String? nextCursor;
}

Set<String> defaultEnrichmentSelection(List<String> retryableStages) =>
    Set<String>.unmodifiable(
      retryableStages.where(
        (stage) => enrichmentStages.contains(stage) && stage != 'translation',
      ),
    );

List<String> validateEnrichmentSelection({
  required List<String> retryableStages,
  required List<String> selectedStages,
}) {
  final retryable = retryableStages.toSet();
  if (retryable.length != retryableStages.length ||
      retryable.difference(enrichmentStages).isNotEmpty ||
      selectedStages.isEmpty ||
      selectedStages.toSet().length != selectedStages.length ||
      selectedStages.any(
        (stage) =>
            !enrichmentStages.contains(stage) || !retryable.contains(stage),
      )) {
    throw ArgumentError.value(
      selectedStages,
      'selectedStages',
      'must be unique server-provided optional stages',
    );
  }
  return List<String>.unmodifiable(
    enrichmentStages.where(selectedStages.contains),
  );
}

abstract interface class SettingsGateway {
  Future<Cloud115BindingDto> getBinding();
  Future<void> unbind();
  Future<QrSessionDto> createQrSession();
  Future<QrSessionDto> pollQrSession(String sessionId);
  Future<Cloud115BindingDto> confirmQrSession(String sessionId);
  Future<SettingsDto> getSettings();
  Future<SettingsDto> updateTtl(int hours);
  Future<SettingsDto> replaceJavdb({
    required int expectedVersion,
    required String username,
    required String password,
  });
  Future<SettingsDto> clearJavdb(int expectedVersion);
  Future<SettingsDto> replaceAi({
    required int expectedVersion,
    required String baseUrl,
    required String apiKey,
    required String model,
    required int timeoutSeconds,
  });
  Future<SettingsDto> clearAi(int expectedVersion);
  Future<ConnectionTestDto> testConnection(String target);
  Future<DiagnosticsDto> getDiagnostics();
  Future<MetadataQueueControlDto> setMetadataPaused(bool paused);
  Future<MetadataJobPageDto> listMetadataJobs({String? cursor});
  Future<MetadataJobDto> retryMetadataJob(String jobId);
  Future<MetadataJobDto> retryMetadataEnrichment(
    String jobId,
    List<String> stages,
    List<String> retryableStages,
  );
}

class SettingsApi implements SettingsGateway {
  const SettingsApi(this._client);
  final ApiClient _client;

  @override
  Future<Cloud115BindingDto> getBinding() =>
      _client.get('cloud115/binding', decode: Cloud115BindingDto.fromJson);
  @override
  Future<void> unbind() => _client.deleteEmpty('cloud115/binding');
  @override
  Future<QrSessionDto> createQrSession() =>
      _client.post('cloud115/qr-sessions', decode: QrSessionDto.fromJson);
  @override
  Future<QrSessionDto> pollQrSession(String sessionId) {
    requireUuid(sessionId, 'sessionId');
    return _client.get(
      'cloud115/qr-sessions/$sessionId',
      decode: QrSessionDto.fromJson,
    );
  }

  @override
  Future<Cloud115BindingDto> confirmQrSession(String sessionId) {
    requireUuid(sessionId, 'sessionId');
    return _client.post(
      'cloud115/qr-sessions/$sessionId/confirm',
      decode: Cloud115BindingDto.fromJson,
    );
  }

  @override
  Future<SettingsDto> getSettings() =>
      _client.get('settings', decode: SettingsDto.fromJson);
  @override
  Future<SettingsDto> updateTtl(int hours) {
    if (hours < 1 || hours > 168) {
      throw ArgumentError.value(hours, 'hours', 'must be from 1 to 168');
    }
    return _patch(<String, Object?>{'cache_ttl_hours': hours});
  }

  @override
  Future<SettingsDto> replaceJavdb({
    required int expectedVersion,
    required String username,
    required String password,
  }) {
    if (expectedVersion < 0 || username.isEmpty || password.isEmpty) {
      throw ArgumentError('invalid JavDB replacement');
    }
    return _patch(<String, Object?>{
      'javdb': <String, Object?>{
        'action': 'replace',
        'expected_version': expectedVersion,
        'username': username,
        'password': password,
      },
    });
  }

  @override
  Future<SettingsDto> clearJavdb(int expectedVersion) {
    if (expectedVersion < 1) {
      throw ArgumentError.value(expectedVersion, 'expectedVersion');
    }
    return _patch(<String, Object?>{
      'javdb': <String, Object?>{
        'action': 'clear',
        'expected_version': expectedVersion,
      },
    });
  }

  @override
  Future<SettingsDto> replaceAi({
    required int expectedVersion,
    required String baseUrl,
    required String apiKey,
    required String model,
    required int timeoutSeconds,
  }) {
    final uri = Uri.tryParse(baseUrl);
    if (expectedVersion < 0 ||
        uri == null ||
        !uri.hasScheme ||
        uri.host.isEmpty ||
        apiKey.isEmpty ||
        model.isEmpty ||
        timeoutSeconds < 1 ||
        timeoutSeconds > 600) {
      throw ArgumentError('invalid AI replacement');
    }
    return _patch(<String, Object?>{
      'ai': <String, Object?>{
        'action': 'replace',
        'expected_version': expectedVersion,
        'base_url': baseUrl,
        'api_key': apiKey,
        'model': model,
        'timeout_seconds': timeoutSeconds,
      },
    });
  }

  @override
  Future<SettingsDto> clearAi(int expectedVersion) {
    if (expectedVersion < 1) {
      throw ArgumentError.value(expectedVersion, 'expectedVersion');
    }
    return _patch(<String, Object?>{
      'ai': <String, Object?>{
        'action': 'clear',
        'expected_version': expectedVersion,
      },
    });
  }

  Future<SettingsDto> _patch(Map<String, Object?> data) =>
      _client.patch('settings', data: data, decode: SettingsDto.fromJson);
  @override
  Future<ConnectionTestDto> testConnection(String target) {
    if (!connectionTargets.contains(target)) {
      throw ArgumentError.value(target, 'target');
    }
    return _client.post(
      'settings/connection-tests',
      data: <String, Object?>{'target': target},
      decode: ConnectionTestDto.fromJson,
    );
  }

  @override
  Future<DiagnosticsDto> getDiagnostics() =>
      _client.get('admin/diagnostics', decode: DiagnosticsDto.fromJson);
  @override
  Future<MetadataQueueControlDto> setMetadataPaused(bool paused) => _client.put(
    'admin/metadata-queue',
    data: <String, Object?>{'paused': paused},
    decode: MetadataQueueControlDto.fromJson,
  );
  @override
  Future<MetadataJobPageDto> listMetadataJobs({String? cursor}) => _client.get(
    'admin/metadata-jobs',
    query: <String, Object?>{'limit': 24, if (cursor != null) 'cursor': cursor},
    decode: MetadataJobPageDto.fromJson,
  );
  @override
  Future<MetadataJobDto> retryMetadataJob(String jobId) {
    requireUuid(jobId, 'jobId');
    return _client.post(
      'admin/metadata-jobs/$jobId/retry',
      decode: MetadataJobDto.fromJson,
    );
  }

  @override
  Future<MetadataJobDto> retryMetadataEnrichment(
    String jobId,
    List<String> stages,
    List<String> retryableStages,
  ) {
    requireUuid(jobId, 'jobId');
    final validated = validateEnrichmentSelection(
      retryableStages: retryableStages,
      selectedStages: stages,
    );
    return _client.post(
      'admin/metadata-jobs/$jobId/retry-enrichment',
      data: <String, Object?>{'stages': validated},
      decode: MetadataJobDto.fromJson,
    );
  }
}

final settingsGatewayProvider = Provider<SettingsGateway>((ref) {
  ref.watch(authSessionStateProvider);
  final client = ref.read(authControllerProvider.notifier).apiClient;
  if (client == null) {
    throw StateError('settings require an authenticated API client');
  }
  return SettingsApi(client);
});

void _rejectSecrets(Object? value, String context) {
  const forbidden = {
    'cookie',
    'token',
    'uid',
    'sign',
    'cid',
    'account_key',
    'password',
    'api_key',
  };
  if (value is Map) {
    for (final entry in value.entries) {
      if (forbidden.contains(entry.key)) {
        throw ProtocolException('$context contains a secret field');
      }
      _rejectSecrets(entry.value, context);
    }
  } else if (value is List) {
    for (final item in value) {
      _rejectSecrets(item, context);
    }
  }
}
