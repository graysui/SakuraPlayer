import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';

const avdbCategories = <String>['亚洲有码', '亚洲无码', '中文字幕', '4K原版', '素人有码', 'FC2'];

const movieSourceLabels = <String>['subtitle', 'cracked', '4k', 'censored'];

enum MovieSourceWebsite { sehuatang, x1080x }

enum MovieSort {
  publishDateDesc('publish_date_desc'),
  publishDateAsc('publish_date_asc'),
  numberAsc('number_asc');

  const MovieSort(this.apiValue);

  final String apiValue;
}

@immutable
class MovieFilters {
  const MovieFilters({
    this.categories = const <String>{},
    this.labels = const <String>{},
    this.sourceWebsite,
    this.playable,
    this.minResourceSizeMb,
    this.maxResourceSizeMb,
    this.favorite = false,
    this.sort = MovieSort.publishDateDesc,
  });

  final Set<String> categories;
  final Set<String> labels;
  final MovieSourceWebsite? sourceWebsite;
  final bool? playable;
  final int? minResourceSizeMb;
  final int? maxResourceSizeMb;
  final bool favorite;
  final MovieSort sort;

  String? get validationMessage {
    if (categories.any((value) => !avdbCategories.contains(value)) ||
        labels.any((value) => !movieSourceLabels.contains(value))) {
      return '筛选条件无效';
    }
    if ((minResourceSizeMb != null && minResourceSizeMb! < 0) ||
        (maxResourceSizeMb != null && maxResourceSizeMb! < 0)) {
      return '资源大小不能小于 0 MiB';
    }
    if (minResourceSizeMb != null &&
        maxResourceSizeMb != null &&
        minResourceSizeMb! > maxResourceSizeMb!) {
      return '最小资源大小不能大于最大资源大小';
    }
    return null;
  }

  Map<String, Object?> toQuery({String? cursor}) {
    final validation = validationMessage;
    if (validation != null) {
      throw ArgumentError.value(this, 'filters', validation);
    }
    final orderedCategories = avdbCategories
        .where(categories.contains)
        .toList(growable: false);
    final orderedLabels = movieSourceLabels
        .where(labels.contains)
        .toList(growable: false);
    return <String, Object?>{
      'limit': 24,
      'sort': sort.apiValue,
      if (orderedCategories.isNotEmpty)
        'categories': orderedCategories.join(','),
      if (orderedLabels.isNotEmpty) 'labels': orderedLabels.join(','),
      if (sourceWebsite != null) 'source_website': sourceWebsite!.name,
      if (playable != null) 'playable': playable,
      if (minResourceSizeMb != null) 'min_resource_size_mb': minResourceSizeMb,
      if (maxResourceSizeMb != null) 'max_resource_size_mb': maxResourceSizeMb,
      if (favorite) 'favorite': true,
      if (cursor != null) 'cursor': cursor,
    };
  }

  MovieFilters copyWith({
    Set<String>? categories,
    Set<String>? labels,
    Object? sourceWebsite = _absent,
    Object? playable = _absent,
    Object? minResourceSizeMb = _absent,
    Object? maxResourceSizeMb = _absent,
    bool? favorite,
    MovieSort? sort,
  }) => MovieFilters(
    categories: categories ?? this.categories,
    labels: labels ?? this.labels,
    sourceWebsite:
        identical(sourceWebsite, _absent)
            ? this.sourceWebsite
            : sourceWebsite as MovieSourceWebsite?,
    playable: identical(playable, _absent) ? this.playable : playable as bool?,
    minResourceSizeMb:
        identical(minResourceSizeMb, _absent)
            ? this.minResourceSizeMb
            : minResourceSizeMb as int?,
    maxResourceSizeMb:
        identical(maxResourceSizeMb, _absent)
            ? this.maxResourceSizeMb
            : maxResourceSizeMb as int?,
    favorite: favorite ?? this.favorite,
    sort: sort ?? this.sort,
  );

  @override
  bool operator ==(Object other) =>
      other is MovieFilters &&
      setEquals(other.categories, categories) &&
      setEquals(other.labels, labels) &&
      other.sourceWebsite == sourceWebsite &&
      other.playable == playable &&
      other.minResourceSizeMb == minResourceSizeMb &&
      other.maxResourceSizeMb == maxResourceSizeMb &&
      other.favorite == favorite &&
      other.sort == sort;

  @override
  int get hashCode => Object.hash(
    Object.hashAll(avdbCategories.where(categories.contains)),
    Object.hashAll(movieSourceLabels.where(labels.contains)),
    sourceWebsite,
    playable,
    minResourceSizeMb,
    maxResourceSizeMb,
    favorite,
    sort,
  );
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
    final position = reader.number('position_seconds');
    final duration =
        json['duration_seconds'] == null
            ? null
            : reader.number('duration_seconds');
    final version = reader.positiveInteger('version');
    if (position < 0 || (duration != null && duration <= 0)) {
      throw const ProtocolException('PlaybackProgress values are invalid');
    }
    return PlaybackProgressDto(
      positionSeconds: position,
      durationSeconds: duration,
      completed: reader.boolean('completed'),
      version: version,
    );
  }

  final num positionSeconds;
  final num? durationSeconds;
  final bool completed;
  final int version;

  double? get fraction {
    final duration = durationSeconds;
    if (completed || duration == null) return null;
    return (positionSeconds / duration).clamp(0, 1).toDouble();
  }
}

@immutable
class MovieSummaryDto {
  const MovieSummaryDto({
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

  factory MovieSummaryDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'MovieSummary');
    final labels = reader.stringList('labels');
    if (labels.length > 4 ||
        labels.toSet().length != labels.length ||
        labels.any((label) => !movieSourceLabels.contains(label))) {
      throw const ProtocolException('MovieSummary.labels is invalid');
    }
    final publishDate = reader.nullableString('publish_date');
    if (publishDate != null && !_isDate(publishDate)) {
      throw const ProtocolException('MovieSummary.publish_date is invalid');
    }
    final coverUrl = reader.nullableString('cover_url');
    if (coverUrl != null && !_catalogImagePattern.hasMatch(coverUrl)) {
      throw const ProtocolException('MovieSummary.cover_url is invalid');
    }
    return MovieSummaryDto(
      id: reader.uuid('id'),
      number: reader.nonEmptyString('number'),
      title: reader.nonEmptyString('title'),
      titleOriginal: reader.nullableString('title_original'),
      coverUrl: coverUrl,
      publishDate: publishDate,
      labels: labels,
      favorite: reader.boolean('favorite'),
      sourceCount: reader.positiveInteger('source_count'),
      progress:
          json['progress'] == null
              ? null
              : PlaybackProgressDto.fromJson(reader.object('progress')),
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
class MoviePageDto {
  const MoviePageDto({required this.items, required this.nextCursor});

  factory MoviePageDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'MoviePage');
    final items = reader.objectList('items', MovieSummaryDto.fromJson);
    if (items.length > 100) {
      throw const ProtocolException('MoviePage.items exceeds limit');
    }
    return MoviePageDto(
      items: items,
      nextCursor:
          json.containsKey('next_cursor')
              ? reader.nullableString('next_cursor')
              : null,
    );
  }

  final List<MovieSummaryDto> items;
  final String? nextCursor;
}

abstract interface class MoviesGateway {
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  });

  Future<List<int>> loadCover(String coverUrl);
}

class MoviesApi implements MoviesGateway {
  const MoviesApi(this._client);

  final ApiClient _client;

  @override
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  }) => _client.get<MoviePageDto>(
    'movies',
    query: filters.toQuery(cursor: cursor),
    decode: MoviePageDto.fromJson,
  );

  @override
  Future<List<int>> loadCover(String coverUrl) =>
      _client.getBytes(catalogImagePath(coverUrl));

  static String catalogImagePath(String coverUrl) {
    final match = _catalogImagePattern.firstMatch(coverUrl);
    if (match == null) {
      throw ArgumentError.value(
        coverUrl,
        'coverUrl',
        'must be an authenticated catalog image URL',
      );
    }
    return 'catalog/images/${match.group(1)}';
  }
}

final moviesGatewayProvider = Provider<MoviesGateway>((ref) {
  ref.watch(authSessionStateProvider);
  final client = ref.read(authControllerProvider.notifier).apiClient;
  if (client == null) {
    throw StateError('movie library requires an authenticated API client');
  }
  return MoviesApi(client);
});

const _absent = Object();

final _catalogImagePattern = RegExp(
  r'^/api/v1/catalog/images/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})$',
);

bool _isDate(String value) {
  if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(value)) return false;
  final parsed = DateTime.tryParse(value);
  return parsed != null &&
      parsed.year.toString().padLeft(4, '0') == value.substring(0, 4) &&
      parsed.month.toString().padLeft(2, '0') == value.substring(5, 7) &&
      parsed.day.toString().padLeft(2, '0') == value.substring(8, 10);
}
