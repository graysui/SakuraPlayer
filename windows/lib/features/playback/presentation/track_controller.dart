import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/playback/data/subtitle_cache.dart';

@immutable
class EmbeddedTrackOption {
  const EmbeddedTrackOption({
    required this.id,
    required this.title,
    required this.language,
  });

  final String id;
  final String? title;
  final String? language;

  String get label =>
      title?.trim().isNotEmpty == true
          ? title!.trim()
          : language?.trim().isNotEmpty == true
          ? language!.trim()
          : '轨道 $id';
}

@immutable
class EmbeddedTrackCatalog {
  const EmbeddedTrackCatalog({
    this.audio = const <EmbeddedTrackOption>[],
    this.subtitles = const <EmbeddedTrackOption>[],
  });

  final List<EmbeddedTrackOption> audio;
  final List<EmbeddedTrackOption> subtitles;
}

@immutable
class EmbeddedTrackSelection {
  const EmbeddedTrackSelection({this.audioId, this.subtitleId});

  final String? audioId;
  final String? subtitleId;
}

@immutable
class SubtitleTrackChoice {
  const SubtitleTrackChoice({
    required this.key,
    required this.label,
    required this.language,
  });

  final String key;
  final String label;
  final String? language;
}

abstract interface class TrackPlaybackPort {
  Stream<EmbeddedTrackCatalog> get trackCatalogStream;
  Stream<EmbeddedTrackSelection> get trackSelectionStream;

  Future<void> selectAudioTrack(String id);
  Future<void> selectEmbeddedSubtitleTrack(String? id);
  Future<void> setExternalSubtitle(
    Uri uri, {
    required String title,
    required String? language,
  });
}

class TrackController extends ChangeNotifier {
  TrackController({
    required TrackPlaybackPort port,
    required SubtitleRepository subtitles,
  }) : _port = port,
       _subtitles = subtitles {
    _subscriptions.addAll(<StreamSubscription<Object?>>[
      port.trackCatalogStream.listen((catalog) {
        if (_disposed) return;
        audioTracks = List<EmbeddedTrackOption>.unmodifiable(catalog.audio);
        embeddedSubtitles = List<EmbeddedTrackOption>.unmodifiable(
          catalog.subtitles,
        );
        notifyListeners();
      }),
      port.trackSelectionStream.listen((selection) {
        if (_disposed) return;
        selectedAudioId = selection.audioId;
        if (selection.subtitleId == null) {
          selectedSubtitleKey = 'off';
        } else if (embeddedSubtitles.any(
          (track) => track.id == selection.subtitleId,
        )) {
          selectedSubtitleKey = 'embedded:${selection.subtitleId}';
        }
        notifyListeners();
      }),
    ]);
  }

  final TrackPlaybackPort _port;
  final SubtitleRepository _subtitles;
  final List<StreamSubscription<Object?>> _subscriptions =
      <StreamSubscription<Object?>>[];

  PlaybackManifestDto? _manifest;
  List<SubtitleOptionDto> externalSubtitles = const <SubtitleOptionDto>[];
  List<EmbeddedTrackOption> audioTracks = const <EmbeddedTrackOption>[];
  List<EmbeddedTrackOption> embeddedSubtitles = const <EmbeddedTrackOption>[];
  String? selectedAudioId;
  String selectedSubtitleKey = 'off';
  String? errorCode;
  bool loadingSubtitle = false;
  bool _disposed = false;

  List<SubtitleTrackChoice> get subtitleChoices => <SubtitleTrackChoice>[
    const SubtitleTrackChoice(key: 'off', label: '关闭字幕', language: null),
    ...embeddedSubtitles.map(
      (track) => SubtitleTrackChoice(
        key: 'embedded:${track.id}',
        label: track.label,
        language: track.language,
      ),
    ),
    ...externalSubtitles.map(
      (subtitle) => SubtitleTrackChoice(
        key: 'external:${subtitle.id}',
        label: subtitle.name,
        language: subtitle.language,
      ),
    ),
  ];

  Future<void> attachManifest(PlaybackManifestDto manifest) async {
    if (_disposed) return;
    _manifest = manifest;
    externalSubtitles = List<SubtitleOptionDto>.unmodifiable(
      manifest.subtitles,
    );
    selectedSubtitleKey = 'off';
    errorCode = null;
    loadingSubtitle = false;
    notifyListeners();
    for (final subtitle in externalSubtitles) {
      if (subtitle.selectedByDefault) {
        await selectSubtitle('external:${subtitle.id}');
        return;
      }
    }
  }

  Future<void> selectAudio(String id) async {
    if (_disposed || !audioTracks.any((track) => track.id == id)) return;
    try {
      await _port.selectAudioTrack(id);
      selectedAudioId = id;
      errorCode = null;
      notifyListeners();
    } on Object {
      errorCode = 'audio_track_load_failed';
      notifyListeners();
    }
  }

  Future<void> selectSubtitle(String key) async {
    if (_disposed || loadingSubtitle) return;
    if (key == 'off') {
      try {
        await _port.selectEmbeddedSubtitleTrack(null);
        selectedSubtitleKey = key;
        errorCode = null;
      } on Object {
        errorCode = 'subtitle_load_failed';
      }
      notifyListeners();
      return;
    }
    if (key.startsWith('embedded:')) {
      final id = key.substring('embedded:'.length);
      if (!embeddedSubtitles.any((track) => track.id == id)) return;
      try {
        await _port.selectEmbeddedSubtitleTrack(id);
        selectedSubtitleKey = key;
        errorCode = null;
      } on Object {
        errorCode = 'subtitle_load_failed';
      }
      notifyListeners();
      return;
    }
    if (!key.startsWith('external:')) return;
    final id = key.substring('external:'.length);
    final matches = externalSubtitles.where((item) => item.id == id).toList();
    if (matches.length != 1) return;
    final manifest = _manifest;
    if (manifest == null) return;
    loadingSubtitle = true;
    errorCode = null;
    notifyListeners();
    try {
      final subtitle = matches.single;
      final uri = await _subtitles.obtain(
        manifest: manifest,
        subtitle: subtitle,
      );
      if (_disposed || !identical(_manifest, manifest)) return;
      await _port.setExternalSubtitle(
        uri,
        title: subtitle.name,
        language: subtitle.language,
      );
      if (_disposed || !identical(_manifest, manifest)) return;
      selectedSubtitleKey = key;
    } on ApiException catch (error) {
      if (!_disposed && identical(_manifest, manifest)) {
        errorCode = error.code;
      }
    } on Object {
      if (!_disposed && identical(_manifest, manifest)) {
        errorCode = 'subtitle_load_failed';
      }
    } finally {
      if (!_disposed && identical(_manifest, manifest)) {
        loadingSubtitle = false;
        notifyListeners();
      }
    }
  }

  @override
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    for (final subscription in _subscriptions) {
      unawaited(subscription.cancel());
    }
    super.dispose();
  }
}
