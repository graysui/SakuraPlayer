import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';

enum PendingMetadataState { queued, running, failed }

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
    final position = reader.number('position_seconds');
    final duration =
        json['duration_seconds'] == null
            ? null
            : reader.number('duration_seconds');
    if (position < 0 || (duration != null && duration <= 0)) {
      throw const ProtocolException('PlaybackProgress values are invalid');
    }
    return PlaybackProgressDto(
      positionSeconds: position,
      durationSeconds: duration,
      completed: reader.boolean('completed'),
      version: reader.positiveInteger('version'),
    );
  }

  final num positionSeconds;
  final num? durationSeconds;
  final bool completed;
  final int version;
}

@immutable
class MovieSearchResultDto {
  const MovieSearchResultDto({
    required this.id,
    required this.number,
    required this.title,
    required this.titleOriginal,
    required this.coverUrl,
    required this.publishDate,
    required this.labels,
    required this.favorite,
    required this.sourceCount,
    required this.progress,
  });

  factory MovieSearchResultDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'MovieSummary');
    final labels = reader.stringList('labels');
    const allowedLabels = <String>{'subtitle', 'cracked', '4k', 'censored'};
    if (labels.any((label) => !allowedLabels.contains(label))) {
      throw const ProtocolException('MovieSummary.labels is invalid');
    }
    final publishDate =
        json.containsKey('publish_date')
            ? reader.nullableString('publish_date')
            : null;
    if (publishDate != null && DateTime.tryParse(publishDate) == null) {
      throw const ProtocolException('MovieSummary.publish_date is invalid');
    }
    PlaybackProgressDto? progress;
    if (json.containsKey('progress') && json['progress'] != null) {
      progress = PlaybackProgressDto.fromJson(reader.object('progress'));
    }
    return MovieSearchResultDto(
      id: reader.uuid('id'),
      number: reader.nonEmptyString('number'),
      title: reader.nonEmptyString('title'),
      titleOriginal:
          json.containsKey('title_original')
              ? reader.nullableString('title_original')
              : null,
      coverUrl:
          json.containsKey('cover_url')
              ? reader.nullableString('cover_url')
              : null,
      publishDate: publishDate,
      labels: labels,
      favorite: reader.boolean('favorite'),
      sourceCount: reader.positiveInteger('source_count'),
      progress: progress,
    );
  }

  final String id;
  final String number;
  final String title;
  final String? titleOriginal;
  final String? coverUrl;
  final String? publishDate;
  final List<String> labels;
  final bool favorite;
  final int sourceCount;
  final PlaybackProgressDto? progress;
}

@immutable
class ActorSearchResultDto {
  const ActorSearchResultDto({
    required this.id,
    required this.displayName,
    required this.nameJa,
    required this.nameZh,
    required this.aliases,
    required this.profileUrl,
    required this.favorite,
  });

  factory ActorSearchResultDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'ActorSummary');
    return ActorSearchResultDto(
      id: reader.uuid('id'),
      displayName: reader.nonEmptyString('display_name'),
      nameJa:
          json.containsKey('name_ja') ? reader.nullableString('name_ja') : null,
      nameZh:
          json.containsKey('name_zh') ? reader.nullableString('name_zh') : null,
      aliases: reader.stringList('aliases'),
      profileUrl:
          json.containsKey('profile_url')
              ? reader.nullableString('profile_url')
              : null,
      favorite: reader.boolean('favorite'),
    );
  }

  final String id;
  final String displayName;
  final String? nameJa;
  final String? nameZh;
  final List<String> aliases;
  final String? profileUrl;
  final bool favorite;
}

@immutable
class PendingMetadataDto {
  const PendingMetadataDto({
    required this.number,
    required this.state,
    required this.metadataJobId,
  });

  factory PendingMetadataDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'PendingMetadata');
    final state = reader.enumeration('state', const {
      'queued',
      'running',
      'failed',
    });
    return PendingMetadataDto(
      number: reader.nonEmptyString('number'),
      state: PendingMetadataState.values.byName(state),
      metadataJobId: reader.uuid('metadata_job_id'),
    );
  }

  final String number;
  final PendingMetadataState state;
  final String metadataJobId;
}

@immutable
class SearchResultDto {
  const SearchResultDto({
    required this.movies,
    required this.actors,
    required this.pendingMetadata,
  });

  factory SearchResultDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'SearchResult');
    final result = SearchResultDto(
      movies: reader.objectList('movies', MovieSearchResultDto.fromJson),
      actors: reader.objectList('actors', ActorSearchResultDto.fromJson),
      pendingMetadata: reader.objectList(
        'pending_metadata',
        PendingMetadataDto.fromJson,
      ),
    );
    if (result.movies.length > 100 ||
        result.actors.length > 100 ||
        result.pendingMetadata.length > 100) {
      throw const ProtocolException('SearchResult group exceeds limit');
    }
    return result;
  }

  final List<MovieSearchResultDto> movies;
  final List<ActorSearchResultDto> actors;
  final List<PendingMetadataDto> pendingMetadata;
}

abstract interface class SearchGateway {
  Future<SearchResultDto> search(String query, {int limit = 10});
}

class SearchApi implements SearchGateway {
  const SearchApi(this._client);

  final ApiClient _client;

  @override
  Future<SearchResultDto> search(String query, {int limit = 10}) {
    final value = query.trim();
    if (value.isEmpty || value.length > 200) {
      throw ArgumentError.value(query, 'query', 'must contain 1 to 200 chars');
    }
    if (limit < 1 || limit > 100) {
      throw ArgumentError.value(limit, 'limit', 'must be between 1 and 100');
    }
    return _client.get<SearchResultDto>(
      'search',
      query: <String, Object?>{'q': value, 'limit': limit},
      decode: SearchResultDto.fromJson,
    );
  }
}

final searchGatewayProvider = Provider<SearchGateway>((ref) {
  ref.watch(authSessionStateProvider);
  final client = ref.read(authControllerProvider.notifier).apiClient;
  if (client == null) {
    throw StateError('search requires an authenticated API client');
  }
  return SearchApi(client);
});
