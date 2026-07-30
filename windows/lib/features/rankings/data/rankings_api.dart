import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';

enum RankingBoard {
  daily('daily'),
  weekly('weekly'),
  monthly('monthly'),
  top250('top250');

  const RankingBoard(this.apiValue);

  final String apiValue;

  static RankingBoard parse(String value) => switch (value) {
    'daily' => RankingBoard.daily,
    'weekly' => RankingBoard.weekly,
    'monthly' => RankingBoard.monthly,
    'top250' => RankingBoard.top250,
    _ => throw const ProtocolException('RankingPage.board is invalid'),
  };
}

@immutable
class RankingSelection {
  const RankingSelection({required this.board, this.year});

  final RankingBoard board;
  final int? year;

  Map<String, Object?> toQuery({String? cursor}) {
    if (year != null &&
        (board != RankingBoard.top250 || year! < 2008 || year! > 2200)) {
      throw ArgumentError.value(year, 'year', 'is invalid for this board');
    }
    return <String, Object?>{
      'board': board.apiValue,
      if (year != null) 'year': year,
      'limit': 24,
      if (cursor != null) 'cursor': cursor,
    };
  }

  @override
  bool operator ==(Object other) =>
      other is RankingSelection && other.board == board && other.year == year;

  @override
  int get hashCode => Object.hash(board, year);
}

@immutable
class RankingItemDto {
  const RankingItemDto({required this.rank, required this.movie});

  factory RankingItemDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'RankingItem');
    return RankingItemDto(
      rank: reader.positiveInteger('rank'),
      movie: MovieSummaryDto.fromJson(reader.object('movie')),
    );
  }

  final int rank;
  final MovieSummaryDto movie;
}

@immutable
class RankingPageDto {
  const RankingPageDto({
    required this.board,
    required this.year,
    required this.availableYears,
    required this.syncedAt,
    required this.items,
    required this.nextCursor,
  });

  factory RankingPageDto.fromJson(Map<String, Object?> json) {
    final reader = JsonReader(json, 'RankingPage');
    final board = RankingBoard.parse(reader.string('board'));
    final year = reader.nullableInteger('year');
    if (year != null &&
        (board != RankingBoard.top250 || year < 2008 || year > 2200)) {
      throw const ProtocolException('RankingPage.year is invalid');
    }
    final availableYears = _availableYears(reader, board);
    final items = reader.objectList('items', RankingItemDto.fromJson);
    if (items.length > 100) {
      throw const ProtocolException('RankingPage.items exceeds limit');
    }
    return RankingPageDto(
      board: board,
      year: year,
      availableYears: availableYears,
      syncedAt: reader.dateTime('synced_at'),
      items: items,
      nextCursor: reader.nullableString('next_cursor'),
    );
  }

  final RankingBoard board;
  final int? year;
  final List<int> availableYears;
  final DateTime syncedAt;
  final List<RankingItemDto> items;
  final String? nextCursor;

  static List<int> _availableYears(JsonReader reader, RankingBoard board) {
    final raw = reader.json['available_years'];
    if (raw is! List) {
      throw const ProtocolException(
        'RankingPage.available_years must be an array',
      );
    }
    final result = <int>[];
    for (final value in raw) {
      if (value is! int || value < 2008 || value > 2200) {
        throw const ProtocolException(
          'RankingPage.available_years contains an invalid year',
        );
      }
      if (result.contains(value) ||
          (result.isNotEmpty && value >= result.last)) {
        throw const ProtocolException(
          'RankingPage.available_years must be unique and descending',
        );
      }
      result.add(value);
    }
    if (result.length > 100 ||
        (board != RankingBoard.top250 && result.isNotEmpty)) {
      throw const ProtocolException('RankingPage.available_years is invalid');
    }
    return List<int>.unmodifiable(result);
  }
}

enum RankingUnavailableReason {
  credentialsNotConfigured('credentials_not_configured'),
  credentialsInvalid('credentials_invalid'),
  neverSynced('never_synced'),
  syncFailed('sync_failed');

  const RankingUnavailableReason(this.apiValue);

  final String apiValue;

  static RankingUnavailableReason? fromException(ApiException error) {
    if (error.statusCode != 503 ||
        error.code != 'ranking_snapshot_unavailable') {
      return null;
    }
    final reason = error.details?['reason'];
    for (final value in RankingUnavailableReason.values) {
      if (value.apiValue == reason) return value;
    }
    return null;
  }
}

abstract interface class RankingsGateway {
  Future<RankingPageDto> listRanking({
    required RankingSelection selection,
    String? cursor,
  });
}

class RankingsApi implements RankingsGateway {
  const RankingsApi(this._client);

  final ApiClient _client;

  @override
  Future<RankingPageDto> listRanking({
    required RankingSelection selection,
    String? cursor,
  }) => _client.get<RankingPageDto>(
    'rankings',
    query: selection.toQuery(cursor: cursor),
    decode: (json) {
      final page = RankingPageDto.fromJson(json);
      if (page.board != selection.board || page.year != selection.year) {
        throw const ProtocolException(
          'RankingPage scope does not match the request',
        );
      }
      return page;
    },
  );
}

final rankingsGatewayProvider = Provider<RankingsGateway>((ref) {
  ref.watch(authSessionStateProvider);
  final client = ref.read(authControllerProvider.notifier).apiClient;
  if (client == null) {
    throw StateError('rankings require an authenticated API client');
  }
  return RankingsApi(client);
});
