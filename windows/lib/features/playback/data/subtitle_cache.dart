import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/storage/subtitle_cache.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';

abstract interface class SubtitleRepository {
  Future<Uri> obtain({
    required PlaybackManifestDto manifest,
    required SubtitleOptionDto subtitle,
  });
}

class SubtitleCacheLifecycleCoordinator {
  SubtitleCacheLifecycleCoordinator(this._cache);

  final SubtitleCache _cache;
  final Set<String> _removedJobs = <String>{};

  Future<void> initialize({required DateTime now}) =>
      _cache.removeExpired(now: now.toUtc());

  Future<void> reconcileCleanedJobs(Iterable<String> cacheJobIds) async {
    for (final id in cacheJobIds) {
      if (_removedJobs.contains(id)) continue;
      await _cache.removeCacheJob(id);
      _removedJobs.add(id);
    }
  }

  void reset() => _removedJobs.clear();
}

class CachedSubtitleRepository implements SubtitleRepository {
  const CachedSubtitleRepository({
    required SubtitleDownloadGateway gateway,
    required SubtitleCache cache,
    DateTime Function()? now,
  }) : _gateway = gateway,
       _cache = cache,
       _now = now ?? _utcNow;

  final SubtitleDownloadGateway _gateway;
  final SubtitleCache _cache;
  final DateTime Function() _now;

  @override
  Future<Uri> obtain({
    required PlaybackManifestDto manifest,
    required SubtitleOptionDto subtitle,
  }) async {
    final authorized = _authorizedOption(manifest, subtitle);
    final now = _now().toUtc();
    if (!now.isBefore(manifest.subtitleCacheExpiresAt.toUtc())) {
      throw const ApiException(
        code: 'subtitle_not_found',
        message: 'The subtitle authorization has expired.',
      );
    }
    final cached = await _cache.resolve(
      cacheJobId: manifest.cacheJobId,
      subtitleId: authorized.id,
      format: authorized.format,
      now: now,
    );
    if (cached != null) return cached;
    final sessionId = _downloadSessionId(manifest, authorized);
    final bytes = await _gateway.downloadSubtitle(
      playbackSessionId: sessionId,
      subtitleId: authorized.id,
    );
    if (!_now().toUtc().isBefore(manifest.subtitleCacheExpiresAt.toUtc())) {
      throw const ApiException(
        code: 'subtitle_not_found',
        message: 'The subtitle authorization has expired.',
      );
    }
    try {
      return await _cache.store(
        cacheJobId: manifest.cacheJobId,
        subtitleId: authorized.id,
        format: authorized.format,
        bytes: bytes,
        expiresAt: manifest.subtitleCacheExpiresAt,
      );
    } on SubtitleCacheException catch (error) {
      throw ApiException(
        code: error.code,
        message: 'The subtitle cannot be stored safely.',
      );
    }
  }

  static SubtitleOptionDto _authorizedOption(
    PlaybackManifestDto manifest,
    SubtitleOptionDto requested,
  ) {
    for (final option in manifest.subtitles) {
      if (option.id == requested.id &&
          option.mediaId == requested.mediaId &&
          option.format == requested.format &&
          option.name == requested.name &&
          option.language == requested.language &&
          option.selectedByDefault == requested.selectedByDefault) {
        return option;
      }
    }
    throw const ApiException(
      code: 'subtitle_not_found',
      message: 'The subtitle is not authorized by this manifest.',
    );
  }

  static String _downloadSessionId(
    PlaybackManifestDto manifest,
    SubtitleOptionDto subtitle,
  ) {
    final mediaId = subtitle.mediaId;
    if (mediaId == null) return manifest.sessionId;
    for (final item in manifest.mediaQueue) {
      if (item.media.id == mediaId) return item.sessionId;
    }
    throw const ApiException(
      code: 'subtitle_not_found',
      message: 'The subtitle media is not in this manifest.',
    );
  }
}

DateTime _utcNow() => DateTime.now().toUtc();

final subtitleRepositoryProvider = Provider<SubtitleRepository>(
  (ref) => CachedSubtitleRepository(
    gateway: ref.watch(subtitleDownloadGatewayProvider),
    cache: ref.watch(subtitleCacheProvider),
  ),
);
