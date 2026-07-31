import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/storage/subtitle_cache.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/playback/data/subtitle_cache.dart';

void main() {
  late Directory temporary;
  late DirectorySubtitleCache cache;

  setUp(() async {
    temporary = await Directory.systemTemp.createTemp('sakura-task211-');
    cache = DirectorySubtitleCache(
      applicationRoot: Directory(
        '${temporary.path}${Platform.pathSeparator}SakuraPlayer',
      ),
    );
  });

  tearDown(() async {
    if (await temporary.exists()) await temporary.delete(recursive: true);
  });

  test('stores only UUID-derived paths and reuses an unexpired copy', () async {
    final expiresAt = DateTime.utc(2026, 8, 1, 12);
    final uri = await cache.store(
      cacheJobId: _jobId,
      subtitleId: _subtitleId,
      format: 'ass',
      bytes: <int>[1, 2, 3],
      expiresAt: expiresAt,
    );

    expect(
      uri.toFilePath(),
      endsWith(
        'subtitles${Platform.pathSeparator}$_jobId${Platform.pathSeparator}$_subtitleId.ass',
      ),
    );
    expect(
      await cache.resolve(
        cacheJobId: _jobId,
        subtitleId: _subtitleId,
        format: 'ass',
        now: DateTime.utc(2026, 8, 1, 11),
      ),
      uri,
    );
    expect(
      () => cache.store(
        cacheJobId: '../outside',
        subtitleId: _subtitleId,
        format: 'ass',
        bytes: <int>[1],
        expiresAt: expiresAt,
      ),
      throwsArgumentError,
    );
  });

  test('rejects oversized bytes and unsupported formats before writing', () {
    expect(
      () => cache.store(
        cacheJobId: _jobId,
        subtitleId: _subtitleId,
        format: 'txt',
        bytes: <int>[1],
        expiresAt: DateTime.utc(2026, 8, 1),
      ),
      throwsArgumentError,
    );
    expect(
      () => cache.store(
        cacheJobId: _jobId,
        subtitleId: _subtitleId,
        format: 'srt',
        bytes: List<int>.filled(8 * 1024 * 1024 + 1, 0),
        expiresAt: DateTime.utc(2026, 8, 1),
      ),
      throwsA(isA<SubtitleCacheException>()),
    );
  });

  test('stores every supported external subtitle format', () async {
    final formats = <String>['srt', 'ass', 'ssa', 'vtt'];
    for (var index = 0; index < formats.length; index++) {
      final format = formats[index];
      final subtitleId =
          '00000000-0000-4000-8000-${(20 + index).toString().padLeft(12, '0')}';
      final uri = await cache.store(
        cacheJobId: _jobId,
        subtitleId: subtitleId,
        format: format,
        bytes: <int>[index],
        expiresAt: DateTime.utc(2026, 8, 1),
      );

      expect(uri.toFilePath(), endsWith('$subtitleId.$format'));
      expect(await File.fromUri(uri).exists(), isTrue);
    }
  });

  test('local expiry and cleaned job remove only matching copies', () async {
    await cache.store(
      cacheJobId: _jobId,
      subtitleId: _subtitleId,
      format: 'srt',
      bytes: <int>[1],
      expiresAt: DateTime.utc(2026, 8, 1, 10),
    );
    await cache.store(
      cacheJobId: _otherJobId,
      subtitleId: _otherSubtitleId,
      format: 'vtt',
      bytes: <int>[2],
      expiresAt: DateTime.utc(2026, 8, 2),
    );

    await cache.removeExpired(now: DateTime.utc(2026, 8, 1, 10));
    expect(await Directory(cache.jobDirectory(_jobId).path).exists(), isFalse);
    expect(
      await cache.resolve(
        cacheJobId: _otherJobId,
        subtitleId: _otherSubtitleId,
        format: 'vtt',
        now: DateTime.utc(2026, 8, 1, 10),
      ),
      isNotNull,
    );

    await cache.removeCacheJob(_otherJobId);
    expect(
      await Directory(cache.jobDirectory(_otherJobId).path).exists(),
      isFalse,
    );
  });

  test(
    'repository uses the authorized media session and reuses cache',
    () async {
      final gateway = _SubtitleGateway();
      final repository = CachedSubtitleRepository(
        gateway: gateway,
        cache: cache,
        now: () => DateTime.utc(2026, 8, 1, 10),
      );
      final manifest = _manifest();
      final subtitle = manifest.subtitles.single;

      final first = await repository.obtain(
        manifest: manifest,
        subtitle: subtitle,
      );
      final second = await repository.obtain(
        manifest: manifest,
        subtitle: subtitle,
      );

      expect(second, first);
      expect(gateway.sessions, <String>[_mediaSessionId]);
      expect(gateway.subtitleIds, <String>[_subtitleId]);
    },
  );

  test(
    'repository rejects options outside the manifest authorization',
    () async {
      final repository = CachedSubtitleRepository(
        gateway: _SubtitleGateway(),
        cache: cache,
        now: () => DateTime.utc(2026, 8, 1, 10),
      );

      await expectLater(
        repository.obtain(
          manifest: _manifest(),
          subtitle: const SubtitleOptionDto(
            id: _otherSubtitleId,
            mediaId: _mediaId,
            name: '../unsafe.ass',
            format: 'ass',
            language: null,
            selectedByDefault: false,
          ),
        ),
        throwsA(
          isA<ApiException>().having(
            (error) => error.code,
            'code',
            'subtitle_not_found',
          ),
        ),
      );
    },
  );

  test('download crossing local expiry is never stored or loaded', () async {
    var now = DateTime.utc(2026, 8, 1, 11, 59);
    final repository = CachedSubtitleRepository(
      gateway: _ExpiringSubtitleGateway(
        () => now = DateTime.utc(2026, 8, 1, 12),
      ),
      cache: cache,
      now: () => now,
    );

    await expectLater(
      repository.obtain(
        manifest: _manifest(),
        subtitle: _manifest().subtitles.single,
      ),
      throwsA(
        isA<ApiException>().having(
          (error) => error.code,
          'code',
          'subtitle_not_found',
        ),
      ),
    );
    expect(await cache.jobDirectory(_jobId).exists(), isFalse);
  });

  test(
    'cleaned lifecycle removes each job without touching other jobs',
    () async {
      await cache.store(
        cacheJobId: _jobId,
        subtitleId: _subtitleId,
        format: 'srt',
        bytes: <int>[1],
        expiresAt: DateTime.utc(2026, 8, 2),
      );
      await cache.store(
        cacheJobId: _otherJobId,
        subtitleId: _otherSubtitleId,
        format: 'vtt',
        bytes: <int>[2],
        expiresAt: DateTime.utc(2026, 8, 2),
      );
      final lifecycle = SubtitleCacheLifecycleCoordinator(cache);

      await lifecycle.reconcileCleanedJobs(<String>[_jobId, _jobId]);

      expect(await cache.jobDirectory(_jobId).exists(), isFalse);
      expect(await cache.jobDirectory(_otherJobId).exists(), isTrue);
    },
  );
}

class _SubtitleGateway implements SubtitleDownloadGateway {
  final List<String> sessions = <String>[];
  final List<String> subtitleIds = <String>[];

  @override
  Future<List<int>> downloadSubtitle({
    required String playbackSessionId,
    required String subtitleId,
  }) async {
    sessions.add(playbackSessionId);
    subtitleIds.add(subtitleId);
    return <int>[1, 2, 3];
  }
}

class _ExpiringSubtitleGateway implements SubtitleDownloadGateway {
  const _ExpiringSubtitleGateway(this.onDownload);

  final void Function() onDownload;

  @override
  Future<List<int>> downloadSubtitle({
    required String playbackSessionId,
    required String subtitleId,
  }) async {
    onDownload();
    return <int>[1, 2, 3];
  }
}

PlaybackManifestDto _manifest() => PlaybackManifestDto(
  sessionId: _sessionId,
  cacheJobId: _jobId,
  mode: PlaybackMode.original,
  streamUri: Uri.parse('https://server.test/stream'),
  expiresAt: DateTime.utc(2026, 8, 1, 12),
  subtitleCacheExpiresAt: DateTime.utc(2026, 8, 1, 12),
  mediaQueue: <PlaybackQueueItemDto>[
    PlaybackQueueItemDto(
      sessionId: _mediaSessionId,
      media: const RemoteMediaDto(
        id: _mediaId,
        candidateId: _candidateId,
        name: 'movie.mkv',
        sizeBytes: 100,
        durationSeconds: 60,
        sequenceNo: 0,
        isValid: true,
      ),
      streamUri: Uri.parse('https://server.test/stream'),
    ),
  ],
  subtitles: const <SubtitleOptionDto>[
    SubtitleOptionDto(
      id: _subtitleId,
      mediaId: _mediaId,
      name: '../unsafe.ass',
      format: 'ass',
      language: 'zh',
      selectedByDefault: true,
    ),
  ],
  progress: null,
);

const _jobId = '00000000-0000-4000-8000-000000000001';
const _subtitleId = '00000000-0000-4000-8000-000000000002';
const _otherJobId = '00000000-0000-4000-8000-000000000003';
const _otherSubtitleId = '00000000-0000-4000-8000-000000000004';
const _mediaId = '00000000-0000-4000-8000-000000000005';
const _candidateId = '00000000-0000-4000-8000-000000000006';
const _sessionId = '00000000-0000-4000-8000-000000000007';
const _mediaSessionId = '00000000-0000-4000-8000-000000000008';
