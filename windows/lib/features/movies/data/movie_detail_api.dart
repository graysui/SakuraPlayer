import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/actors/data/actors_api.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';

enum MovieMetadataState { coreReady, queued, running, failed }

enum MovieSourceAvailability {
  available,
  queued,
  running,
  ready,
  failed,
  rejected;

  static MovieSourceAvailability parse(String value) => switch (value) {
    'available' => MovieSourceAvailability.available,
    'queued' => MovieSourceAvailability.queued,
    'running' => MovieSourceAvailability.running,
    'ready' => MovieSourceAvailability.ready,
    'failed' => MovieSourceAvailability.failed,
    'rejected' => MovieSourceAvailability.rejected,
    _ =>
      throw const ProtocolException(
        'MovieSource.availability has an unknown value',
      ),
  };
}

@immutable
class MovieSourceDto {
  const MovieSourceDto({
    required this.id,
    required this.website,
    required this.externalPostId,
    required this.title,
    required this.publishDate,
    required this.category,
    required this.labels,
    required this.resourceSizeMb,
    required this.videoFileSizeBytes,
    required this.availability,
  });

  factory MovieSourceDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'MovieSource');
    final publishDate = reader.nullableString('publish_date');
    if (publishDate != null && !isIsoDate(publishDate)) {
      throw const ProtocolException('MovieSource.publish_date is invalid');
    }
    final labels = reader.stringList('labels');
    _requireUniqueStrings(
      labels,
      context: 'MovieSource.labels',
      maxItems: 4,
      allowed: movieSourceLabels.toSet(),
    );
    final resourceSizeMb = reader.nullableInteger('resource_size_mb');
    final videoFileSizeBytes = reader.nullableInteger('video_file_size_bytes');
    if ((resourceSizeMb != null && resourceSizeMb < 0) ||
        (videoFileSizeBytes != null && videoFileSizeBytes < 0)) {
      throw const ProtocolException('MovieSource size is invalid');
    }
    final websiteValue = reader.enumeration('website', const {
      'sehuatang',
      'x1080x',
    });
    return MovieSourceDto(
      id: reader.uuid('id'),
      website: MovieSourceWebsite.values.byName(websiteValue),
      externalPostId: reader.positiveInteger('external_post_id'),
      title: reader.nonEmptyString('title'),
      publishDate: publishDate,
      category: reader.enumeration('category', avdbCategories.toSet()),
      labels: labels,
      resourceSizeMb: resourceSizeMb,
      videoFileSizeBytes: videoFileSizeBytes,
      availability: MovieSourceAvailability.parse(
        reader.string('availability'),
      ),
    );
  }

  final String id;
  final MovieSourceWebsite website;
  final int externalPostId;
  final String title;
  final String? publishDate;
  final String category;
  final List<String> labels;
  final int? resourceSizeMb;
  final int? videoFileSizeBytes;
  final MovieSourceAvailability availability;

  bool get isSelectable => availability != MovieSourceAvailability.rejected;
}

@immutable
class MovieDetailDto extends MovieSummaryDto {
  const MovieDetailDto({
    required super.id,
    required super.number,
    required super.title,
    required super.titleOriginal,
    required super.coverUrl,
    required super.publishDate,
    required super.labels,
    required super.favorite,
    required super.sourceCount,
    required super.progress,
    required this.releaseDate,
    required this.maker,
    required this.series,
    required this.director,
    required this.score,
    required this.description,
    required this.descriptionOriginal,
    required this.actors,
    required this.tags,
    required this.plotImageUrls,
    required this.sources,
    this.metadataState = MovieMetadataState.coreReady,
    this.metadataErrorCode,
  });

  factory MovieDetailDto.fromJson(Map<String, Object?> json) {
    final summary = MovieSummaryDto.fromJson(json);
    final reader = JsonReader(json, 'MovieDetail');
    final releaseDate = reader.nullableString('release_date');
    if (releaseDate != null && !isIsoDate(releaseDate)) {
      throw const ProtocolException('MovieDetail.release_date is invalid');
    }
    final actors = reader.objectList('actors', ActorSummaryDto.fromJson);
    final tags = reader.stringList('tags');
    final plotImageUrls = reader.stringList('plot_image_urls');
    final sources = reader.objectList('sources', MovieSourceDto.fromJson);
    _requireCollectionLimit(actors, 'MovieDetail.actors');
    _requireCollectionLimit(tags, 'MovieDetail.tags');
    _requireCollectionLimit(plotImageUrls, 'MovieDetail.plot_image_urls');
    _requireCollectionLimit(sources, 'MovieDetail.sources');
    _requireUniqueValues(actors.map((actor) => actor.id), 'MovieDetail.actors');
    _requireUniqueStrings(tags, context: 'MovieDetail.tags');
    _requireUniqueStrings(
      plotImageUrls,
      context: 'MovieDetail.plot_image_urls',
    );
    _requireUniqueValues(
      sources.map((source) => source.id),
      'MovieDetail.sources',
    );
    if (plotImageUrls.any((url) => !isCatalogImageUrl(url))) {
      throw const ProtocolException('MovieDetail.plot_image_urls is invalid');
    }
    final score = _nullableFiniteNumber(json, 'score', 'MovieDetail');
    final metadataStateValue = reader.enumeration('metadata_state', const {
      'core_ready',
      'queued',
      'running',
      'failed',
    });
    final metadataState = switch (metadataStateValue) {
      'core_ready' => MovieMetadataState.coreReady,
      'queued' => MovieMetadataState.queued,
      'running' => MovieMetadataState.running,
      'failed' => MovieMetadataState.failed,
      _ =>
        throw const ProtocolException('MovieDetail.metadata_state is invalid'),
    };
    final metadataErrorCode = reader.nullableString('metadata_error_code');
    if (metadataState != MovieMetadataState.failed &&
        metadataErrorCode != null) {
      throw const ProtocolException(
        'MovieDetail.metadata_error_code is invalid',
      );
    }
    return MovieDetailDto(
      id: summary.id,
      number: summary.number,
      title: summary.title,
      titleOriginal: summary.titleOriginal,
      coverUrl: summary.coverUrl,
      publishDate: summary.publishDate,
      labels: summary.labels,
      favorite: summary.favorite,
      sourceCount: summary.sourceCount,
      progress: summary.progress,
      releaseDate: releaseDate,
      maker: reader.nullableString('maker'),
      series: reader.nullableString('series'),
      director: reader.nullableString('director'),
      score: score,
      description: reader.nullableString('description'),
      descriptionOriginal: reader.nullableString('description_original'),
      actors: actors,
      tags: tags,
      plotImageUrls: plotImageUrls,
      sources: sources,
      metadataState: metadataState,
      metadataErrorCode: metadataErrorCode,
    );
  }

  final String? releaseDate;
  final String? maker;
  final String? series;
  final String? director;
  final num? score;
  final String? description;
  final String? descriptionOriginal;
  final List<ActorSummaryDto> actors;
  final List<String> tags;
  final List<String> plotImageUrls;
  final List<MovieSourceDto> sources;
  final MovieMetadataState metadataState;
  final String? metadataErrorCode;

  bool get isLimited => metadataState != MovieMetadataState.coreReady;

  MovieDetailDto copyWith({bool? favorite}) => MovieDetailDto(
    id: id,
    number: number,
    title: title,
    titleOriginal: titleOriginal,
    coverUrl: coverUrl,
    publishDate: publishDate,
    labels: labels,
    favorite: favorite ?? this.favorite,
    sourceCount: sourceCount,
    progress: progress,
    releaseDate: releaseDate,
    maker: maker,
    series: series,
    director: director,
    score: score,
    description: description,
    descriptionOriginal: descriptionOriginal,
    actors: actors,
    tags: tags,
    plotImageUrls: plotImageUrls,
    sources: sources,
    metadataState: metadataState,
    metadataErrorCode: metadataErrorCode,
  );
}

abstract interface class MovieDetailGateway {
  Future<MovieDetailDto> getMovie(String movieId);

  Future<void> setFavorite(String movieId, {required bool enabled});

  Future<List<int>> loadCatalogImage(String imageUrl);
}

class MovieDetailApi implements MovieDetailGateway {
  const MovieDetailApi(this._client);

  final ApiClient _client;

  @override
  Future<MovieDetailDto> getMovie(String movieId) {
    requireMovieId(movieId);
    return _client.get<MovieDetailDto>(
      'movies/$movieId',
      decode: MovieDetailDto.fromJson,
    );
  }

  @override
  Future<void> setFavorite(String movieId, {required bool enabled}) {
    requireMovieId(movieId);
    final path = 'movies/$movieId/favorite';
    return enabled ? _client.putEmpty(path) : _client.deleteEmpty(path);
  }

  @override
  Future<List<int>> loadCatalogImage(String imageUrl) =>
      _client.getBytes(MoviesApi.catalogImagePath(imageUrl));
}

final movieDetailGatewayProvider = Provider<MovieDetailGateway>((ref) {
  ref.watch(authSessionStateProvider);
  final client = ref.read(authControllerProvider.notifier).apiClient;
  if (client == null) {
    throw StateError('movie detail requires an authenticated API client');
  }
  return MovieDetailApi(client);
});

bool isValidMovieId(String value) => isValidUuid(value);

void requireMovieId(String value) => requireUuid(value, 'movieId');

num? _nullableFiniteNumber(
  Map<String, Object?> json,
  String key,
  String context,
) {
  if (!json.containsKey(key)) {
    throw ProtocolException('$context.$key is required');
  }
  final value = json[key];
  if (value == null) return null;
  if (value is! num || !value.isFinite) {
    throw ProtocolException('$context.$key must be a finite number or null');
  }
  return value;
}

void _requireCollectionLimit(List<Object?> values, String context) {
  if (values.length > 100) {
    throw ProtocolException('$context exceeds limit');
  }
}

void _requireUniqueStrings(
  List<String> values, {
  required String context,
  int maxItems = 100,
  Set<String>? allowed,
}) {
  if (values.length > maxItems ||
      values.toSet().length != values.length ||
      values.any((value) => value.isEmpty) ||
      (allowed != null && values.any((value) => !allowed.contains(value)))) {
    throw ProtocolException('$context is invalid');
  }
}

void _requireUniqueValues(Iterable<String> values, String context) {
  final list = values.toList(growable: false);
  if (list.toSet().length != list.length) {
    throw ProtocolException('$context contains duplicates');
  }
}
