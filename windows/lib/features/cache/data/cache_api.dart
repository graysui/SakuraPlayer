import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';

const cacheStatusLabels = <String, String>{
  'queued': '排队中',
  'submitting': '正在提交',
  'offlining': '离线中',
  'submit_uncertain': '提交待确认',
  'resolving': '解析文件',
  'awaiting_selection': '待选文件',
  'ready': '可播放',
  'cancelling': '正在取消',
  'cleaning': '正在清理',
  'cleanup_failed': '清理失败',
  'failed': '任务失败',
  'cleaned': '已清理',
  'detached': '已失联',
};

const _cancellableStatuses = <String>{
  'queued',
  'submitting',
  'offlining',
  'submit_uncertain',
  'resolving',
};

const _cleanupStatuses = <String>{
  'awaiting_selection',
  'ready',
  'cleanup_failed',
};

bool canCancelCacheStatus(String status) =>
    _cancellableStatuses.contains(status);

bool canCleanupCacheStatus(String status) => _cleanupStatuses.contains(status);

@immutable
class CacheCapacityDto {
  const CacheCapacityDto({
    required this.running,
    required this.runningLimit,
    required this.queued,
    required this.queuedLimit,
    required this.ready,
    required this.readyLimit,
  });

  factory CacheCapacityDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'CacheCapacity');
    final running = reader.nonNegativeInteger('running');
    final runningLimit = reader.integer('running_limit');
    final queued = reader.nonNegativeInteger('queued');
    final queuedLimit = reader.integer('queued_limit');
    final ready = reader.nonNegativeInteger('ready');
    final readyLimit = reader.integer('ready_limit');
    if (runningLimit != 2 || queuedLimit != 10 || readyLimit != 20) {
      throw const ProtocolException('CacheCapacity limits are invalid');
    }
    if (running > runningLimit || queued > queuedLimit) {
      throw const ProtocolException('CacheCapacity counts are invalid');
    }
    return CacheCapacityDto(
      running: running,
      runningLimit: runningLimit,
      queued: queued,
      queuedLimit: queuedLimit,
      ready: ready,
      readyLimit: readyLimit,
    );
  }

  final int running;
  final int runningLimit;
  final int queued;
  final int queuedLimit;
  final int ready;
  final int readyLimit;
}

@immutable
class CacheJobPageDto {
  const CacheJobPageDto({
    required this.items,
    required this.capacity,
    required this.nextCursor,
  });

  factory CacheJobPageDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'CacheJobPage');
    final items = reader.objectList('items', CacheJobDto.fromJson);
    if (items.length > 100 ||
        items.map((item) => item.id).toSet().length != items.length) {
      throw const ProtocolException('CacheJobPage.items is invalid');
    }
    return CacheJobPageDto(
      items: items,
      capacity: CacheCapacityDto.fromJson(reader.object('capacity')),
      nextCursor: reader.nullableString('next_cursor'),
    );
  }

  final List<CacheJobDto> items;
  final CacheCapacityDto capacity;
  final String? nextCursor;
}

abstract interface class CacheGateway {
  Future<CacheJobPageDto> listJobs({Set<String> statuses, String? cursor});

  Future<CacheJobDto> cancel(String jobId);

  Future<CacheJobDto> cleanup(String jobId);
}

class CacheApi implements CacheGateway {
  const CacheApi(this._client);

  final ApiClient _client;

  @override
  Future<CacheJobPageDto> listJobs({
    Set<String> statuses = const <String>{},
    String? cursor,
  }) {
    if (statuses.any((status) => !cacheJobStatuses.contains(status))) {
      throw ArgumentError.value(
        statuses,
        'statuses',
        'contains an unknown status',
      );
    }
    if (statuses.length > 12) {
      throw ArgumentError.value(
        statuses,
        'statuses',
        'must contain at most 12 values',
      );
    }
    final ordered = cacheJobStatuses
        .where(statuses.contains)
        .toList(growable: false);
    return _client.get<CacheJobPageDto>(
      'cache-jobs',
      query: <String, Object?>{
        'limit': 24,
        if (ordered.isNotEmpty) 'status': ordered.join(','),
        if (cursor != null) 'cursor': cursor,
      },
      decode: CacheJobPageDto.fromJson,
    );
  }

  @override
  Future<CacheJobDto> cancel(String jobId) {
    requireUuid(jobId, 'jobId');
    return _client.post<CacheJobDto>(
      'cache-jobs/$jobId/cancel',
      data: const <String, Object?>{'confirmed': true},
      decode: CacheJobDto.fromJson,
    );
  }

  @override
  Future<CacheJobDto> cleanup(String jobId) {
    requireUuid(jobId, 'jobId');
    return _client.post<CacheJobDto>(
      'cache-jobs/$jobId/cleanup',
      decode: CacheJobDto.fromJson,
    );
  }
}

final cacheGatewayProvider = Provider<CacheGateway>((ref) {
  ref.watch(authSessionStateProvider);
  final client = ref.read(authControllerProvider.notifier).apiClient;
  if (client == null) {
    throw StateError('cache management requires an authenticated API client');
  }
  return CacheApi(client);
});
