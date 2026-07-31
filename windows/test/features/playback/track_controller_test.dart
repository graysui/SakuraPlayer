import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/playback/data/subtitle_cache.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/track_controller.dart';

void main() {
  test('enumerates embedded tracks and selects audio and subtitles', () async {
    final port = _TrackPort();
    final subtitles = _SubtitleRepository();
    final controller = TrackController(port: port, subtitles: subtitles);
    addTearDown(controller.dispose);

    port.catalogs.add(
      const EmbeddedTrackCatalog(
        audio: <EmbeddedTrackOption>[
          EmbeddedTrackOption(id: '1', title: '日语', language: 'ja'),
          EmbeddedTrackOption(id: '2', title: '评论', language: 'zh'),
        ],
        subtitles: <EmbeddedTrackOption>[
          EmbeddedTrackOption(id: '3', title: '内嵌中文', language: 'zh'),
        ],
      ),
    );
    await Future<void>.delayed(Duration.zero);
    await controller.attachManifest(_manifest());

    expect(controller.audioTracks, hasLength(2));
    expect(controller.subtitleChoices, hasLength(3));
    expect(port.externalUris, <Uri>[Uri.file('default.ass')]);
    expect(controller.selectedSubtitleKey, 'external:$_subtitleId');

    await controller.selectAudio('2');
    await controller.selectSubtitle('embedded:3');
    await controller.selectSubtitle('off');

    expect(port.audioSelections, <String>['2']);
    expect(port.subtitleSelections, <String?>['3', null]);
  });

  test('external subtitle failure is isolated from the video', () async {
    final port = _TrackPort();
    final subtitles = _SubtitleRepository(
      error: const ApiException(
        code: 'subtitle_not_found',
        message: 'not found',
      ),
    );
    final controller = TrackController(port: port, subtitles: subtitles);
    addTearDown(controller.dispose);

    await controller.attachManifest(_manifest());

    expect(controller.errorCode, 'subtitle_not_found');
    expect(controller.selectedSubtitleKey, 'off');
    expect(port.externalUris, isEmpty);
  });

  test('a subtitle download from an old manifest is never loaded', () async {
    final port = _TrackPort();
    final subtitles = _DeferredSubtitleRepository();
    final controller = TrackController(port: port, subtitles: subtitles);
    addTearDown(controller.dispose);

    final oldAttach = controller.attachManifest(_manifest());
    await controller.attachManifest(
      _manifest(subtitles: const <SubtitleOptionDto>[]),
    );
    subtitles.complete(Uri.file('stale.ass'));
    await oldAttach;

    expect(port.externalUris, isEmpty);
    expect(controller.selectedSubtitleKey, 'off');
  });
}

class _TrackPort implements TrackPlaybackPort {
  final catalogs = StreamController<EmbeddedTrackCatalog>.broadcast();
  final selections = StreamController<EmbeddedTrackSelection>.broadcast();
  final List<String> audioSelections = <String>[];
  final List<String?> subtitleSelections = <String?>[];
  final List<Uri> externalUris = <Uri>[];

  @override
  Stream<EmbeddedTrackCatalog> get trackCatalogStream => catalogs.stream;

  @override
  Stream<EmbeddedTrackSelection> get trackSelectionStream => selections.stream;

  @override
  Future<void> selectAudioTrack(String id) async => audioSelections.add(id);

  @override
  Future<void> selectEmbeddedSubtitleTrack(String? id) async =>
      subtitleSelections.add(id);

  @override
  Future<void> setExternalSubtitle(
    Uri uri, {
    required String title,
    required String? language,
  }) async => externalUris.add(uri);
}

class _SubtitleRepository implements SubtitleRepository {
  _SubtitleRepository({this.error});

  final ApiException? error;

  @override
  Future<Uri> obtain({
    required PlaybackManifestDto manifest,
    required SubtitleOptionDto subtitle,
  }) async {
    final failure = error;
    if (failure != null) throw failure;
    return Uri.file('default.ass');
  }
}

class _DeferredSubtitleRepository implements SubtitleRepository {
  final Completer<Uri> _result = Completer<Uri>();

  void complete(Uri uri) => _result.complete(uri);

  @override
  Future<Uri> obtain({
    required PlaybackManifestDto manifest,
    required SubtitleOptionDto subtitle,
  }) => _result.future;
}

PlaybackManifestDto _manifest({List<SubtitleOptionDto>? subtitles}) =>
    PlaybackManifestDto(
      sessionId: _sessionId,
      cacheJobId: _jobId,
      mode: PlaybackMode.original,
      streamUri: Uri.parse('https://server.test/stream'),
      expiresAt: DateTime.utc(2026, 8, 1, 12),
      subtitleCacheExpiresAt: DateTime.utc(2026, 8, 1, 12),
      mediaQueue: <PlaybackQueueItemDto>[
        PlaybackQueueItemDto(
          sessionId: _sessionId,
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
      subtitles:
          subtitles ??
          const <SubtitleOptionDto>[
            SubtitleOptionDto(
              id: _subtitleId,
              mediaId: _mediaId,
              name: 'movie.ass',
              format: 'ass',
              language: 'zh',
              selectedByDefault: true,
            ),
          ],
      progress: null,
    );

const _jobId = '00000000-0000-4000-8000-000000000001';
const _mediaId = '00000000-0000-4000-8000-000000000002';
const _candidateId = '00000000-0000-4000-8000-000000000003';
const _sessionId = '00000000-0000-4000-8000-000000000004';
const _subtitleId = '00000000-0000-4000-8000-000000000005';
