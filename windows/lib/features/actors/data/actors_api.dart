import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/images/gfriends_url.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';

@immutable
class ActorListScope {
  const ActorListScope({this.query, this.favorite = false});

  final String? query;
  final bool favorite;

  String? get normalizedQuery {
    final value = query?.trim();
    return value == null || value.isEmpty ? null : value;
  }

  Map<String, Object?> toQuery({String? cursor}) {
    final value = normalizedQuery;
    if (value != null && value.length > 200) {
      throw ArgumentError.value(
        query,
        'query',
        'must contain at most 200 chars',
      );
    }
    return <String, Object?>{
      if (value != null) 'q': value,
      if (favorite) 'favorite': true,
      'limit': 24,
      if (cursor != null) 'cursor': cursor,
    };
  }

  @override
  bool operator ==(Object other) =>
      other is ActorListScope &&
      other.normalizedQuery == normalizedQuery &&
      other.favorite == favorite;

  @override
  int get hashCode => Object.hash(normalizedQuery, favorite);
}

@immutable
class ActorSummaryDto {
  const ActorSummaryDto({
    required this.id,
    required this.displayName,
    required this.nameJa,
    required this.nameZh,
    required this.aliases,
    required this.profileUrl,
    required this.favorite,
  });

  factory ActorSummaryDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'ActorSummary');
    final aliases = reader.stringList('aliases');
    _validateStringCollection(aliases, 'ActorSummary.aliases');
    final profileUrl =
        json.containsKey('profile_url')
            ? reader.nullableString('profile_url')
            : null;
    if (profileUrl != null && !isAllowedGfriendsUrl(profileUrl)) {
      throw const ProtocolException('ActorSummary.profile_url is invalid');
    }
    return ActorSummaryDto(
      id: reader.uuid('id'),
      displayName: reader.nonEmptyString('display_name'),
      nameJa:
          json.containsKey('name_ja') ? reader.nullableString('name_ja') : null,
      nameZh:
          json.containsKey('name_zh') ? reader.nullableString('name_zh') : null,
      aliases: aliases,
      profileUrl: profileUrl,
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

  ActorSummaryDto copyWith({bool? favorite}) => ActorSummaryDto(
    id: id,
    displayName: displayName,
    nameJa: nameJa,
    nameZh: nameZh,
    aliases: aliases,
    profileUrl: profileUrl,
    favorite: favorite ?? this.favorite,
  );
}

@immutable
class ActorDetailDto extends ActorSummaryDto {
  const ActorDetailDto({
    required super.id,
    required super.displayName,
    required super.nameJa,
    required super.nameZh,
    required super.aliases,
    required super.profileUrl,
    required super.favorite,
    required this.bio,
    required this.bioOriginal,
    required this.galleryUrls,
    required this.movies,
  });

  factory ActorDetailDto.fromJson(Map<String, Object?> json) {
    final summary = ActorSummaryDto.fromJson(json);
    final reader = JsonReader(json, 'ActorDetail');
    final galleryUrls = reader.stringList('gallery_urls');
    _validateStringCollection(galleryUrls, 'ActorDetail.gallery_urls');
    if (galleryUrls.any((url) => !isAllowedGfriendsUrl(url))) {
      throw const ProtocolException('ActorDetail.gallery_urls is invalid');
    }
    final movies = reader.objectList('movies', MovieSummaryDto.fromJson);
    if (movies.length > 100) {
      throw const ProtocolException('ActorDetail.movies exceeds limit');
    }
    return ActorDetailDto(
      id: summary.id,
      displayName: summary.displayName,
      nameJa: summary.nameJa,
      nameZh: summary.nameZh,
      aliases: summary.aliases,
      profileUrl: summary.profileUrl,
      favorite: summary.favorite,
      bio: json.containsKey('bio') ? reader.nullableString('bio') : null,
      bioOriginal:
          json.containsKey('bio_original')
              ? reader.nullableString('bio_original')
              : null,
      galleryUrls: galleryUrls,
      movies: movies,
    );
  }

  final String? bio;
  final String? bioOriginal;
  final List<String> galleryUrls;
  final List<MovieSummaryDto> movies;

  @override
  ActorDetailDto copyWith({bool? favorite}) => ActorDetailDto(
    id: id,
    displayName: displayName,
    nameJa: nameJa,
    nameZh: nameZh,
    aliases: aliases,
    profileUrl: profileUrl,
    favorite: favorite ?? this.favorite,
    bio: bio,
    bioOriginal: bioOriginal,
    galleryUrls: galleryUrls,
    movies: movies,
  );
}

@immutable
class ActorPageDto {
  const ActorPageDto({required this.items, required this.nextCursor});

  factory ActorPageDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'ActorPage');
    final items = reader.objectList('items', ActorSummaryDto.fromJson);
    if (items.length > 100) {
      throw const ProtocolException('ActorPage.items exceeds limit');
    }
    return ActorPageDto(
      items: items,
      nextCursor:
          json.containsKey('next_cursor')
              ? reader.nullableString('next_cursor')
              : null,
    );
  }

  final List<ActorSummaryDto> items;
  final String? nextCursor;
}

abstract interface class ActorsGateway {
  Future<ActorPageDto> listActors({
    required ActorListScope scope,
    String? cursor,
  });

  Future<ActorDetailDto> getActor(String actorId);

  Future<void> setFavorite(String actorId, {required bool enabled});
}

class ActorsApi implements ActorsGateway {
  const ActorsApi(this._client);

  final ApiClient _client;

  @override
  Future<ActorPageDto> listActors({
    required ActorListScope scope,
    String? cursor,
  }) => _client.get<ActorPageDto>(
    'actors',
    query: scope.toQuery(cursor: cursor),
    decode: ActorPageDto.fromJson,
  );

  @override
  Future<ActorDetailDto> getActor(String actorId) {
    requireActorId(actorId);
    return _client.get<ActorDetailDto>(
      'actors/$actorId',
      decode: ActorDetailDto.fromJson,
    );
  }

  @override
  Future<void> setFavorite(String actorId, {required bool enabled}) {
    requireActorId(actorId);
    final path = 'actors/$actorId/favorite';
    return enabled ? _client.putEmpty(path) : _client.deleteEmpty(path);
  }
}

final actorsGatewayProvider = Provider<ActorsGateway>((ref) {
  ref.watch(authSessionStateProvider);
  final client = ref.read(authControllerProvider.notifier).apiClient;
  if (client == null) {
    throw StateError('actors require an authenticated API client');
  }
  return ActorsApi(client);
});

void _validateStringCollection(List<String> values, String context) {
  if (values.length > 100 ||
      values.toSet().length != values.length ||
      values.any((value) => value.isEmpty)) {
    throw ProtocolException('$context is invalid');
  }
}

bool isValidActorId(String value) => isValidUuid(value);

void requireActorId(String value) {
  requireUuid(value, 'actorId');
}
