import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/actors/data/actors_api.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';

enum PendingMetadataState { queued, running, failed }

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
      movies: reader.objectList('movies', MovieSummaryDto.fromJson),
      actors: reader.objectList('actors', ActorSummaryDto.fromJson),
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

  final List<MovieSummaryDto> movies;
  final List<ActorSummaryDto> actors;
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
