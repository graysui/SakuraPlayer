import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';

enum PlayDisposition {
  ready,
  started,
  queued,
  reused;

  static PlayDisposition parse(String value) {
    for (final disposition in values) {
      if (disposition.name == value) return disposition;
    }
    throw const ProtocolException('PlayRequestResult.disposition is unknown');
  }
}

@immutable
class PlayRequestResultDto {
  const PlayRequestResultDto({
    required this.disposition,
    required this.waitDeadline,
    required this.cacheJob,
  });

  factory PlayRequestResultDto.fromJson(Map<String, Object?> json) {
    const allowedKeys = <String>{'disposition', 'wait_deadline', 'cache_job'};
    const requiredKeys = <String>{'disposition', 'cache_job'};
    if (json.keys.toSet().difference(allowedKeys).isNotEmpty ||
        requiredKeys.difference(json.keys.toSet()).isNotEmpty) {
      throw const ProtocolException('PlayRequestResult has unknown fields');
    }
    final reader = JsonReader(json, 'PlayRequestResult');
    final disposition = PlayDisposition.parse(reader.string('disposition'));
    final deadline = reader.optionalDateTime('wait_deadline');
    final cacheJob = CacheJobDto.fromJson(reader.object('cache_job'));
    if (disposition == PlayDisposition.started) {
      if (deadline == null || cacheJob.status != 'submitting') {
        throw const ProtocolException(
          'PlayRequestResult.started has an invalid deadline or status',
        );
      }
    } else if (deadline != null) {
      throw const ProtocolException(
        'PlayRequestResult deadline is only valid for started',
      );
    }
    if (disposition == PlayDisposition.ready && cacheJob.status != 'ready') {
      throw const ProtocolException(
        'PlayRequestResult.ready must contain a ready job',
      );
    }
    if (disposition == PlayDisposition.queued && cacheJob.status != 'queued') {
      throw const ProtocolException(
        'PlayRequestResult.queued must contain a queued job',
      );
    }
    return PlayRequestResultDto(
      disposition: disposition,
      waitDeadline: deadline,
      cacheJob: cacheJob,
    );
  }

  final PlayDisposition disposition;
  final DateTime? waitDeadline;
  final CacheJobDto cacheJob;
}

abstract interface class PlayRequestGateway {
  Future<PlayRequestResultDto> request({
    required String movieId,
    required String sourceId,
    required String idempotencyKey,
  });

  Future<CacheJobDto> cancel(String jobId, {required bool confirmed});
}

class PlayRequestApi implements PlayRequestGateway {
  const PlayRequestApi(this._client);

  final ApiClient _client;

  @override
  Future<PlayRequestResultDto> request({
    required String movieId,
    required String sourceId,
    required String idempotencyKey,
  }) {
    requireUuid(movieId, 'movieId');
    requireUuid(sourceId, 'sourceId');
    if (!RegExp(r'^[A-Za-z0-9._~-]{16,128}$').hasMatch(idempotencyKey)) {
      throw ArgumentError.value(
        idempotencyKey,
        'idempotencyKey',
        'must be 16..128 safe ASCII characters',
      );
    }
    return _client.post<PlayRequestResultDto>(
      'movies/$movieId/play-requests',
      data: <String, Object?>{'source_id': sourceId},
      headers: <String, Object?>{'Idempotency-Key': idempotencyKey},
      decode: PlayRequestResultDto.fromJson,
    );
  }

  @override
  Future<CacheJobDto> cancel(String jobId, {required bool confirmed}) {
    requireUuid(jobId, 'jobId');
    if (!confirmed) {
      throw ArgumentError.value(confirmed, 'confirmed', 'must be true');
    }
    return _client.post<CacheJobDto>(
      'cache-jobs/$jobId/cancel',
      data: const <String, Object?>{'confirmed': true},
      decode: CacheJobDto.fromJson,
    );
  }
}

final playRequestGatewayProvider = Provider<PlayRequestGateway>((ref) {
  ref.watch(authSessionStateProvider);
  final client = ref.read(authControllerProvider.notifier).apiClient;
  if (client == null) {
    throw StateError('play requests require an authenticated API client');
  }
  return PlayRequestApi(client);
});
