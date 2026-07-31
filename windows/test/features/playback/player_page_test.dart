import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/playback/data/subtitle_cache.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/playback_engine.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/player_controller.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/track_controller.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/player_page.dart';

void main() {
  testWidgets(
    'custom controls fit narrow window and route seek through engine',
    (tester) async {
      tester.view.physicalSize = const Size(420, 720);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final engine = _PageEngine();
      final tracks = TrackController(
        port: engine,
        subtitles: _PageSubtitleRepository(),
      );
      final controller = PlayerController(
        gateway: _PageGateway(),
        engine: engine,
        tracks: tracks,
      );
      addTearDown(controller.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: PlayerPage(
            cacheJobId: _jobId,
            mediaId: _mediaId,
            controller: controller,
          ),
        ),
      );
      await tester.pumpAndSettle();
      engine.durations.add(const Duration(minutes: 1));
      engine.positions.add(const Duration(seconds: 10));
      engine.trackCatalogs.add(
        const EmbeddedTrackCatalog(
          audio: [
            EmbeddedTrackOption(id: 'audio-1', title: '日语', language: 'ja'),
          ],
          subtitles: [
            EmbeddedTrackOption(
              id: 'subtitle-1',
              title: '中文字幕',
              language: 'zh',
            ),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('video-surface')), findsOneWidget);
      expect(find.byKey(const ValueKey('player-controls')), findsOneWidget);
      expect(find.byTooltip('播放'), findsOneWidget);
      expect(find.byTooltip('音轨'), findsOneWidget);
      expect(find.byTooltip('字幕'), findsOneWidget);
      expect(find.byTooltip('播放速度'), findsOneWidget);
      expect(find.byTooltip('全屏'), findsOneWidget);
      expect(find.textContaining('缩略图'), findsNothing);
      expect(tester.takeException(), isNull);

      expect(controller.duration, const Duration(minutes: 1));
      final slider = find.byKey(const ValueKey('player-progress'));
      final sliderRect = tester.getRect(slider);
      await tester.tapAt(
        Offset(sliderRect.left + sliderRect.width * 0.75, sliderRect.center.dy),
      );
      await tester.pump();
      expect(engine.seeks, isNotEmpty);

      await tester.tap(find.byTooltip('音轨'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('日语'));
      await tester.pumpAndSettle();
      expect(engine.selectedAudioTracks, <String>['audio-1']);

      await tester.tap(find.byTooltip('字幕'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('中文字幕'));
      await tester.pumpAndSettle();
      expect(engine.selectedSubtitleTracks, <String?>['subtitle-1']);

      await tester.tap(find.byTooltip('全屏'));
      await tester.pump();
      expect(engine.fullscreenCalls, 1);
    },
  );
}

class _PageGateway implements PlaybackGateway {
  @override
  Future<PlaybackManifestDto> createSession({
    required String cacheJobId,
    required String mediaId,
    required PlaybackMode mode,
  }) async => PlaybackManifestDto(
    sessionId: _sessionId,
    cacheJobId: cacheJobId,
    mode: mode,
    streamUri: Uri.parse(
      'https://server.test/api/v1/playback/streams/$_sessionId',
    ),
    expiresAt: DateTime.utc(2026, 8, 1),
    subtitleCacheExpiresAt: DateTime.utc(2026, 8, 1),
    mediaQueue: [
      PlaybackQueueItemDto(
        sessionId: _sessionId,
        media: const RemoteMediaDto(
          id: _mediaId,
          candidateId: _candidateId,
          name: 'movie.mp4',
          sizeBytes: 1024,
          durationSeconds: 60,
          sequenceNo: 0,
          isValid: true,
        ),
        streamUri: Uri.parse(
          'https://server.test/api/v1/playback/streams/$_sessionId',
        ),
      ),
    ],
    subtitles: const [],
    progress: null,
  );
}

class _PageEngine implements PlaybackEngine {
  final playing = StreamController<bool>.broadcast();
  final completed = StreamController<bool>.broadcast();
  final buffering = StreamController<bool>.broadcast();
  final positions = StreamController<Duration>.broadcast();
  final durations = StreamController<Duration>.broadcast();
  final errors = StreamController<String>.broadcast();
  final trackCatalogs = StreamController<EmbeddedTrackCatalog>.broadcast();
  final trackSelections = StreamController<EmbeddedTrackSelection>.broadcast();
  final seeks = <Duration>[];
  final selectedAudioTracks = <String>[];
  final selectedSubtitleTracks = <String?>[];
  int fullscreenCalls = 0;

  @override
  Stream<bool> get playingStream => playing.stream;
  @override
  Stream<bool> get completedStream => completed.stream;
  @override
  Stream<bool> get bufferingStream => buffering.stream;
  @override
  Stream<Duration> get positionStream => positions.stream;
  @override
  Stream<Duration> get durationStream => durations.stream;
  @override
  Stream<String> get errorStream => errors.stream;
  @override
  Stream<EmbeddedTrackCatalog> get trackCatalogStream => trackCatalogs.stream;
  @override
  Stream<EmbeddedTrackSelection> get trackSelectionStream =>
      trackSelections.stream;
  @override
  Widget buildVideoSurface() => const ColoredBox(color: Colors.black);
  @override
  Future<void> open(PlaybackManifestDto manifest, String mediaId) async {}
  @override
  Future<void> play() async {}
  @override
  Future<void> pause() async {}
  @override
  Future<void> seek(Duration target) async => seeks.add(target);
  @override
  Future<void> setRate(double rate) async {}
  @override
  Future<void> selectAudioTrack(String id) async => selectedAudioTracks.add(id);
  @override
  Future<void> selectEmbeddedSubtitleTrack(String? id) async =>
      selectedSubtitleTracks.add(id);
  @override
  Future<void> setExternalSubtitle(
    Uri uri, {
    required String title,
    required String? language,
  }) async {}
  @override
  Future<void> toggleFullscreen() async => fullscreenCalls++;
  @override
  Future<void> dispose() async {
    await Future.wait([
      playing.close(),
      completed.close(),
      buffering.close(),
      positions.close(),
      durations.close(),
      errors.close(),
      trackCatalogs.close(),
      trackSelections.close(),
    ]);
  }
}

class _PageSubtitleRepository implements SubtitleRepository {
  @override
  Future<Uri> obtain({
    required PlaybackManifestDto manifest,
    required SubtitleOptionDto subtitle,
  }) async => Uri.file('unused.${subtitle.format}');
}

const _jobId = '00000000-0000-4000-8000-000000000001';
const _mediaId = '00000000-0000-4000-8000-000000000002';
const _candidateId = '00000000-0000-4000-8000-000000000003';
const _sessionId = '00000000-0000-4000-8000-000000000004';
