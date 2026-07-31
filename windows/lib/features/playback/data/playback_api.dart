import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';

const windowsPlaybackUserAgent = 'SakuraPlayer/1.0 (Windows; x64)';

enum PlaybackMode { original, compatibility }

extension PlaybackModeWireValue on PlaybackMode {
  String get wireValue => switch (this) {
    PlaybackMode.original => 'original',
    PlaybackMode.compatibility => 'compatibility',
  };
}

@immutable
class PlaybackProgressDto {
  const PlaybackProgressDto({
    required this.positionSeconds,
    required this.durationSeconds,
    required this.completed,
    required this.version,
  });

  factory PlaybackProgressDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'PlaybackProgress');
    if (!json.containsKey('duration_seconds')) {
      throw const ProtocolException(
        'PlaybackProgress.duration_seconds is required',
      );
    }
    final position = reader.number('position_seconds');
    final duration =
        json['duration_seconds'] == null
            ? null
            : reader.number('duration_seconds');
    final version = reader.nonNegativeInteger('version');
    if (position < 0 || (duration != null && duration < 0)) {
      throw const ProtocolException('PlaybackProgress values are invalid');
    }
    final completed = reader.boolean('completed');
    if (completed && position != 0) {
      throw const ProtocolException(
        'Completed playback progress must start from zero',
      );
    }
    return PlaybackProgressDto(
      positionSeconds: position.toDouble(),
      durationSeconds: duration?.toDouble(),
      completed: completed,
      version: version,
    );
  }

  final double positionSeconds;
  final double? durationSeconds;
  final bool completed;
  final int version;
}

@immutable
class PlaybackQueueItemDto {
  const PlaybackQueueItemDto({
    required this.sessionId,
    required this.media,
    required this.streamUri,
  });

  final String sessionId;
  final RemoteMediaDto media;
  final Uri streamUri;
}

@immutable
class PlaybackManifestDto {
  const PlaybackManifestDto({
    required this.sessionId,
    required this.cacheJobId,
    required this.mode,
    required this.streamUri,
    required this.expiresAt,
    required this.subtitleCacheExpiresAt,
    required this.mediaQueue,
    required this.subtitles,
    required this.progress,
  });

  factory PlaybackManifestDto.fromJson(
    Map<String, Object?> json, {
    required Uri serverOrigin,
  }) {
    final reader = JsonReader(json, 'PlaybackManifest');
    final mode = switch (reader.enumeration('mode', const {
      'original',
      'compatibility',
    })) {
      'original' => PlaybackMode.original,
      _ => PlaybackMode.compatibility,
    };
    if (reader.enumeration('platform', const {'windows', 'harmonyos'}) !=
            'windows' ||
        reader.nonEmptyString('required_user_agent') !=
            windowsPlaybackUserAgent ||
        reader.nonEmptyString('embedded_tracks_source') != 'client_player') {
      throw const ProtocolException(
        'PlaybackManifest client contract mismatch',
      );
    }
    final queueJson = reader.objectList<Map<String, Object?>>(
      'media_queue',
      (value) => value,
    );
    if (queueJson.isEmpty) {
      throw const ProtocolException('PlaybackManifest.media_queue is empty');
    }
    final queue = queueJson
        .map((item) {
          final itemReader = JsonReader(item, 'PlaybackQueueItem');
          final media = RemoteMediaDto.fromJson(itemReader.object('media'));
          if (!media.isValid) {
            throw const ProtocolException(
              'Playback queue contains invalid media',
            );
          }
          return PlaybackQueueItemDto(
            sessionId: itemReader.uuid('session_id'),
            media: media,
            streamUri: resolvePlaybackCapability(
              serverOrigin,
              itemReader.nonEmptyString('stream_url'),
            ),
          );
        })
        .toList(growable: false);
    if (queue.map((item) => item.sessionId).toSet().length != queue.length ||
        queue.map((item) => item.media.id).toSet().length != queue.length) {
      throw const ProtocolException(
        'PlaybackManifest.media_queue has duplicates',
      );
    }
    final sessionId = reader.uuid('session_id');
    final streamUri = resolvePlaybackCapability(
      serverOrigin,
      reader.nonEmptyString('stream_url'),
    );
    if (!queue.any(
      (item) => item.sessionId == sessionId && item.streamUri == streamUri,
    )) {
      throw const ProtocolException(
        'PlaybackManifest active stream is invalid',
      );
    }
    final subtitles = reader.objectList(
      'subtitles',
      SubtitleOptionDto.fromJson,
    );
    if (!json.containsKey('progress')) {
      throw const ProtocolException('PlaybackManifest.progress is required');
    }
    final progressJson = json['progress'];
    if (progressJson != null && progressJson is! Map) {
      throw const ProtocolException('PlaybackManifest.progress is invalid');
    }
    final PlaybackProgressDto? progress;
    if (progressJson == null) {
      progress = null;
    } else {
      try {
        progress = PlaybackProgressDto.fromJson(
          Map<String, Object?>.from(progressJson as Map),
        );
      } on TypeError {
        throw const ProtocolException('PlaybackManifest.progress is invalid');
      }
    }
    return PlaybackManifestDto(
      sessionId: sessionId,
      cacheJobId: reader.uuid('cache_job_id'),
      mode: mode,
      streamUri: streamUri,
      expiresAt: reader.dateTime('expires_at'),
      subtitleCacheExpiresAt: reader.dateTime('subtitle_cache_expires_at'),
      mediaQueue: List.unmodifiable(queue),
      subtitles: subtitles,
      progress: progress,
    );
  }

  final String sessionId;
  final String cacheJobId;
  final PlaybackMode mode;
  final Uri streamUri;
  final DateTime expiresAt;
  final DateTime subtitleCacheExpiresAt;
  final List<PlaybackQueueItemDto> mediaQueue;
  final List<SubtitleOptionDto> subtitles;
  final PlaybackProgressDto? progress;
}

Uri resolvePlaybackCapability(Uri serverOrigin, String reference) {
  final origin = Uri(
    scheme: serverOrigin.scheme.toLowerCase(),
    host: serverOrigin.host.toLowerCase(),
    port: serverOrigin.hasPort ? serverOrigin.port : null,
  );
  if ((origin.scheme != 'http' && origin.scheme != 'https') ||
      origin.host.isEmpty) {
    throw const ProtocolException('Playback server origin is invalid');
  }
  final parsed = Uri.tryParse(reference);
  if (parsed == null || reference.isEmpty || parsed.userInfo.isNotEmpty) {
    throw const ProtocolException('Playback capability URL is invalid');
  }
  final resolved = origin.resolveUri(parsed);
  final resolvedPort =
      resolved.hasPort
          ? resolved.port
          : (resolved.scheme == 'https' ? 443 : 80);
  final originPort =
      origin.hasPort ? origin.port : (origin.scheme == 'https' ? 443 : 80);
  if ((resolved.scheme != 'http' && resolved.scheme != 'https') ||
      resolved.scheme != origin.scheme ||
      resolved.host.toLowerCase() != origin.host ||
      resolvedPort != originPort ||
      resolved.fragment.isNotEmpty) {
    throw const ProtocolException(
      'Playback capability URL must be same-origin',
    );
  }
  return resolved;
}

abstract interface class PlaybackGateway {
  Future<PlaybackManifestDto> createSession({
    required String cacheJobId,
    required String mediaId,
    required PlaybackMode mode,
  });
}

class PlaybackApi implements PlaybackGateway {
  const PlaybackApi({
    required ApiClient client,
    required Uri serverOrigin,
    required Future<String> Function() clientInstanceId,
  }) : _client = client,
       _serverOrigin = serverOrigin,
       _clientInstanceId = clientInstanceId;

  final ApiClient _client;
  final Uri _serverOrigin;
  final Future<String> Function() _clientInstanceId;

  @override
  Future<PlaybackManifestDto> createSession({
    required String cacheJobId,
    required String mediaId,
    required PlaybackMode mode,
  }) async {
    requireUuid(cacheJobId, 'cacheJobId');
    requireUuid(mediaId, 'mediaId');
    final clientId = await _clientInstanceId();
    requireUuid(clientId, 'clientInstanceId');
    final result = await _client.post<PlaybackManifestDto>(
      'cache-jobs/$cacheJobId/playback-sessions',
      data: <String, Object?>{
        'media_id': mediaId,
        'mode': mode.wireValue,
        'platform': 'windows',
        'client_instance_id': clientId,
      },
      decode:
          (json) =>
              PlaybackManifestDto.fromJson(json, serverOrigin: _serverOrigin),
    );
    if (result.cacheJobId != cacheJobId ||
        !result.mediaQueue.any((item) => item.media.id == mediaId)) {
      throw const ApiException(
        code: 'client_protocol_error',
        message: 'The playback manifest does not match the request.',
      );
    }
    return result;
  }
}

final playbackGatewayProvider = Provider<PlaybackGateway>((ref) {
  final auth = ref.watch(authSessionStateProvider);
  final client = ref.read(authControllerProvider.notifier).apiClient;
  if (!auth.isAuthenticated || auth.serverBaseUri == null || client == null) {
    throw StateError('playback requires an authenticated API client');
  }
  return PlaybackApi(
    client: client,
    serverOrigin: auth.serverBaseUri!,
    clientInstanceId: ref.read(secureStoreProvider).clientInstanceId,
  );
});
