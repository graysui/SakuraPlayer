import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/cache/data/play_request_api.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/settings/data/settings_api.dart';

const _markerName = 'SAKURAPLAYER_TEST_REAL115';
const _baseUrlName = 'SAKURAPLAYER_REAL115_API_BASE_URL';
const _usernameName = 'SAKURAPLAYER_REAL115_USERNAME';
const _passwordName = 'SAKURAPLAYER_REAL115_PASSWORD';
const _movieIdName = 'SAKURAPLAYER_REAL115_MOVIE_ID';
const _sourceIdName = 'SAKURAPLAYER_REAL115_SOURCE_ID';
const _managedRootName = 'SAKURAPLAYER_REAL115_CONFIRM_MANAGED_ROOT';
const _reuseBindingName = 'SAKURAPLAYER_REAL115_REUSE_BINDING';
const _skipExternalSubtitlesName =
    'SAKURAPLAYER_REAL115_SKIP_EXTERNAL_SUBTITLES';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  final enabled = Platform.environment[_markerName] == '1';

  testWidgets(
    'HLS master selects the highest bandwidth variant without network',
    (_) async {
      final document = _parseHlsDocument(
        '#EXTM3U\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\n'
        'low.m3u8\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=4200000,RESOLUTION=1920x1080\n'
        'high.m3u8\n',
        Uri.parse('https://media.example/master.m3u8'),
        stage: 'hls_manifest',
      );

      expect(document.firstReference, 'high.m3u8');
      expect(_reuseConfirmedBinding(const <String, String>{}), isFalse);
      expect(
        _reuseConfirmedBinding(const <String, String>{_reuseBindingName: '1'}),
        isTrue,
      );
      expect(_skipExternalSubtitles(const <String, String>{}), isFalse);
      expect(
        _skipExternalSubtitles(const <String, String>{
          _skipExternalSubtitlesName: '1',
        }),
        isTrue,
      );
    },
  );

  testWidgets(
    'explicit QR and AC-130 playback journey emits only redacted evidence',
    (_) async {
      final environment = Platform.environment;
      if (environment[_managedRootName] != '1') {
        throw const ProbeFailure('managed_root_not_confirmed');
      }
      final baseUri = _normalizeBaseUri(_required(environment, _baseUrlName));
      final username = _required(environment, _usernameName);
      final password = _required(environment, _passwordName);
      final movieId = _requiredUuid(environment, _movieIdName);
      final sourceId = _requiredUuid(environment, _sourceIdName);
      final clientId = _uuidV4();
      final client = Dio(
        BaseOptions(
          baseUrl: baseUri.toString(),
          connectTimeout: const Duration(seconds: 15),
          receiveTimeout: const Duration(seconds: 45),
          sendTimeout: const Duration(seconds: 15),
          validateStatus: (status) => status != null && status < 500,
        ),
      );

      File? qrImage;
      String? jobId;
      PlaybackManifestDto? manifest;
      try {
        final login = await _requestJson(
          () => client.post<Object?>(
            'auth/login',
            data: <String, Object?>{
              'username': username,
              'password': password,
              'client_instance_id': clientId,
            },
          ),
          stage: 'login',
        );
        final accessToken = login.data['access_token'];
        if (accessToken is! String || accessToken.isEmpty) {
          throw const ProbeFailure('login_protocol_error');
        }
        client.options.headers['Authorization'] = 'Bearer $accessToken';
        _evidence('login', statusCode: login.statusCode);

        if (_reuseConfirmedBinding(environment)) {
          final current = await _requestJson(
            () => client.get<Object?>('cloud115/binding'),
            stage: 'binding_reuse',
          );
          final binding = Cloud115BindingDto.fromJson(current.data);
          if (!binding.bound ||
              binding.status != 'active' ||
              !binding.cacheRootReady) {
            throw const ProbeFailure('binding_reuse_not_active');
          }
          _evidence(
            'binding_reused',
            statusCode: current.statusCode,
            state: binding.status,
          );
        } else {
          final createdQr = await _requestJson(
            () => client.post<Object?>('cloud115/qr-sessions'),
            stage: 'qr_create',
          );
          var qr = QrSessionDto.fromJson(createdQr.data);
          final imageBytes = qr.imageBytes;
          if (imageBytes == null) {
            throw const ProbeFailure('qr_image_missing');
          }
          qrImage = File(
            '${Directory.systemTemp.path}${Platform.pathSeparator}'
            'sakuraplayer-real115-${qr.id}.png',
          );
          await qrImage.writeAsBytes(imageBytes, flush: true);
          _evidence(
            'qr_ready',
            statusCode: createdQr.statusCode,
            sessionId: qr.id,
            localFile: qrImage.path,
          );

          final qrDeadline = DateTime.now().toUtc().add(
            const Duration(minutes: 5),
          );
          while (qr.status == 'waiting' || qr.status == 'scanned') {
            if (DateTime.now().toUtc().isAfter(qr.expiresAt) ||
                DateTime.now().toUtc().isAfter(qrDeadline)) {
              throw const ProbeFailure('qr_scan_timeout');
            }
            await Future<void>.delayed(const Duration(seconds: 2));
            final polled = await _requestJson(
              () => client.get<Object?>('cloud115/qr-sessions/${qr.id}'),
              stage: 'qr_poll',
            );
            qr = QrSessionDto.fromJson(polled.data);
          }
          if (qr.status != 'confirmed') {
            throw ProbeFailure('qr_${qr.status}');
          }
          final confirmed = await _requestJson(
            () => client.post<Object?>('cloud115/qr-sessions/${qr.id}/confirm'),
            stage: 'qr_confirm',
          );
          final binding = Cloud115BindingDto.fromJson(confirmed.data);
          if (!binding.bound || !binding.cacheRootReady) {
            throw const ProbeFailure('binding_not_ready');
          }
          _evidence(
            'qr_confirmed',
            statusCode: confirmed.statusCode,
            sessionId: qr.id,
          );
        }

        final requested = await _requestJson(
          () => client.post<Object?>(
            'movies/$movieId/play-requests',
            data: <String, Object?>{'source_id': sourceId},
            options: Options(
              headers: <String, Object?>{
                'Idempotency-Key': 'real115-$clientId',
              },
            ),
          ),
          stage: 'play_request',
        );
        final play = PlayRequestResultDto.fromJson(requested.data);
        jobId = play.cacheJob.id;
        var job = play.cacheJob;
        _evidence(
          'play_request',
          statusCode: requested.statusCode,
          sourceId: sourceId,
          jobId: jobId,
          state: play.disposition.name,
        );

        final jobDeadline = DateTime.now().toUtc().add(
          const Duration(minutes: 20),
        );
        while (!const <String>{
          'ready',
          'awaiting_selection',
          'failed',
          'canceled',
          'cleaned',
          'cleanup_failed',
          'detached',
        }.contains(job.status)) {
          if (DateTime.now().toUtc().isAfter(jobDeadline)) {
            throw const ProbeFailure('cache_job_timeout');
          }
          await Future<void>.delayed(const Duration(seconds: 5));
          final current = await _requestJson(
            () => client.get<Object?>('cache-jobs/$jobId'),
            stage: 'cache_job_poll',
          );
          job = CacheJobDto.fromJson(current.data);
        }
        if (job.status == 'awaiting_selection') {
          final selection = _acceptanceSelection(job);
          final selected = await _requestJson(
            () => client.put<Object?>(
              'cache-jobs/$jobId/media-selection',
              data: <String, Object?>{'media_ids': selection},
            ),
            stage: 'media_selection',
          );
          job = CacheJobDto.fromJson(selected.data);
          _evidence(
            'media_selection',
            statusCode: selected.statusCode,
            jobId: jobId,
            state: 'segmented_${selection.length}',
          );
        }
        if (job.status != 'ready' || job.selectedMediaIds.isEmpty) {
          throw ProbeFailure('cache_job_${job.status}');
        }
        _evidence('cache_ready', jobId: jobId, state: job.status);

        final session = await _requestJson(
          () => client.post<Object?>(
            'cache-jobs/$jobId/playback-sessions',
            data: <String, Object?>{
              'media_id': job.selectedMediaIds.first,
              'mode': 'original',
              'platform': 'windows',
              'client_instance_id': clientId,
            },
          ),
          stage: 'playback_session',
        );
        manifest = PlaybackManifestDto.fromJson(
          session.data,
          serverOrigin: baseUri,
        );
        _evidence(
          'playback_session',
          statusCode: session.statusCode,
          jobId: jobId,
          sessionId: manifest.sessionId,
        );

        await _probeOriginalRanges(client, manifest);

        final blockedCleanup = await _requestJson(
          () => client.post<Object?>('cache-jobs/$jobId/cleanup'),
          stage: 'cleanup_active_lease',
          acceptedStatuses: const <int>{409},
        );
        if (blockedCleanup.data['code'] != 'cache_active_lease') {
          throw const ProbeFailure('cleanup_active_lease_protocol_error');
        }
        _evidence(
          'cleanup_blocked',
          statusCode: blockedCleanup.statusCode,
          jobId: jobId,
          state: 'cache_active_lease',
        );

        final compatibilitySession = await _requestJson(
          () => client.post<Object?>(
            'cache-jobs/$jobId/playback-sessions',
            data: <String, Object?>{
              'media_id': job.selectedMediaIds.first,
              'mode': 'compatibility',
              'platform': 'windows',
              'client_instance_id': clientId,
            },
          ),
          stage: 'compatibility_session',
        );
        final compatibility = PlaybackManifestDto.fromJson(
          compatibilitySession.data,
          serverOrigin: baseUri,
        );
        await _probeHls(client, compatibility);
        if (_skipExternalSubtitles(environment)) {
          _evidence('subtitle_external_skipped', state: 'operator_approved');
        } else {
          await _probeSubtitles(client, manifest);
        }

        final progress = manifest.progress;
        final compatibilityRelease = await _requestJson(
          () => client.put<Object?>(
            'playback/sessions/${compatibility.sessionId}/heartbeat',
            data: <String, Object?>{
              'client_instance_id': clientId,
              'progress': <String, Object?>{
                'position_seconds': progress?.positionSeconds ?? 0,
                'duration_seconds': progress?.durationSeconds ?? 100,
                'version': progress?.version ?? 0,
              },
              'playing': false,
            },
          ),
          stage: 'compatibility_lease_release',
        );
        final compatibilityHeartbeat = PlaybackHeartbeatDto.fromJson(
          compatibilityRelease.data,
        );
        if (compatibilityHeartbeat.leaseExpiresAt != null) {
          throw const ProbeFailure('compatibility_lease_release_failed');
        }
        final progressVersion =
            compatibilityHeartbeat.progress?.version ?? progress?.version ?? 0;
        final heartbeat = await _requestJson(
          () => client.put<Object?>(
            'playback/sessions/${manifest!.sessionId}/heartbeat',
            data: <String, Object?>{
              'client_instance_id': clientId,
              'progress': <String, Object?>{
                'position_seconds': 95,
                'duration_seconds': 100,
                'version': progressVersion,
              },
              'playing': false,
            },
          ),
          stage: 'progress_95',
        );
        final heartbeatDto = PlaybackHeartbeatDto.fromJson(heartbeat.data);
        if (heartbeatDto.leaseExpiresAt != null ||
            heartbeatDto.progress?.completed != true) {
          throw const ProbeFailure('progress_95_protocol_error');
        }
        _evidence(
          'progress_95',
          statusCode: heartbeat.statusCode,
          sessionId: manifest.sessionId,
          state: 'completed',
        );
        manifest = null;

        final cleanup = await _requestJson(
          () => client.post<Object?>('cache-jobs/$jobId/cleanup'),
          stage: 'cleanup',
        );
        _evidence(
          'cleanup_requested',
          statusCode: cleanup.statusCode,
          jobId: jobId,
        );
        final cleanupDeadline = DateTime.now().toUtc().add(
          const Duration(minutes: 5),
        );
        var cleaned = CacheJobDto.fromJson(cleanup.data);
        while (cleaned.status == 'cleaning') {
          if (DateTime.now().toUtc().isAfter(cleanupDeadline)) {
            throw const ProbeFailure('cleanup_timeout');
          }
          await Future<void>.delayed(const Duration(seconds: 3));
          final current = await _requestJson(
            () => client.get<Object?>('cache-jobs/$jobId'),
            stage: 'cleanup_poll',
          );
          cleaned = CacheJobDto.fromJson(current.data);
        }
        if (cleaned.status != 'cleaned') {
          throw ProbeFailure('cleanup_${cleaned.status}');
        }
        _evidence('cleanup_cleaned', jobId: jobId, state: cleaned.status);
        jobId = null;
      } finally {
        if (qrImage != null && await qrImage.exists()) {
          await qrImage.delete();
        }
        client.close(force: true);
        if (manifest != null || jobId != null) {
          _evidence(
            'operator_cleanup_required',
            jobId: jobId,
            sessionId: manifest?.sessionId,
          );
        }
      }
    },
    // Widget tests accept a boolean skip; when false, no network attempted:
    // the gate is evaluated before credentials or a client are constructed.
    skip: !enabled,
    timeout: const Timeout(Duration(minutes: 30)),
  );
}

Future<_ProbeResponse<Map<String, Object?>>> _requestJson(
  Future<Response<Object?>> Function() request, {
  required String stage,
  Set<int> acceptedStatuses = const <int>{200, 201, 202, 204},
}) async {
  final response = await _requestRaw(
    request,
    stage: stage,
    acceptedStatuses: acceptedStatuses,
  );
  if (response.data is! Map) {
    throw ProbeFailure('${stage}_protocol_error');
  }
  return _ProbeResponse<Map<String, Object?>>(
    statusCode: response.statusCode,
    data: Map<String, Object?>.from(response.data! as Map),
    headers: response.headers,
    realUri: response.realUri,
  );
}

Future<_ProbeResponse<Object?>> _requestRaw(
  Future<Response<Object?>> Function() request, {
  required String stage,
  Set<int> acceptedStatuses = const <int>{200, 201, 202, 204},
}) async {
  try {
    final response = await request();
    final status = response.statusCode ?? 0;
    if (!acceptedStatuses.contains(status)) {
      final body = response.data;
      final code =
          body is Map && body['code'] is String ? body['code'] as String : null;
      throw ProbeFailure(
        '${stage}_http_$status${code == null ? '' : '_$code'}',
      );
    }
    return _ProbeResponse<Object?>(
      statusCode: status,
      data: response.data,
      headers: response.headers,
      realUri: response.realUri,
    );
  } on DioException catch (error) {
    final status = error.response?.statusCode;
    throw ProbeFailure(
      '${stage}_transport_${error.type.name}'
      '${status == null ? '' : '_http_$status'}',
    );
  }
}

Future<void> _probeOriginalRanges(
  Dio client,
  PlaybackManifestDto manifest,
) async {
  final upstream = _mediaClient();
  try {
    final ranges = <String>[
      'bytes=0-0',
      'bytes=1048576-1048576',
      'bytes=2097152-2097152',
    ];
    for (final entry in ranges.indexed) {
      final index = entry.$1 + 1;
      final range = entry.$2;
      final redirect = await _requestRaw(
        () => client.get<Object?>(
          manifest.streamUri.toString(),
          options: Options(
            followRedirects: false,
            headers: <String, Object?>{
              'User-Agent': windowsPlaybackUserAgent,
              'Range': range,
            },
            responseType: ResponseType.bytes,
            receiveTimeout: const Duration(seconds: 30),
          ),
        ),
        stage: 'original_range_$index',
        acceptedStatuses: const <int>{206, 302},
      );
      final response =
          redirect.statusCode == 302
              ? await _requestRaw(
                () => upstream.getUri<Object?>(
                  _redirectTarget(redirect),
                  options: Options(
                    headers: <String, Object?>{
                      'User-Agent': windowsPlaybackUserAgent,
                      'Range': range,
                    },
                    responseType: ResponseType.bytes,
                  ),
                ),
                stage: 'original_upstream_range_$index',
                acceptedStatuses: const <int>{206},
              )
              : redirect;
      if (response.headers.value('content-range') == null ||
          response.data is! List<int> ||
          (response.data! as List<int>).isEmpty) {
        throw ProbeFailure('original_range_${index}_protocol_error');
      }
      _evidence(
        'original_range',
        statusCode: response.statusCode,
        sessionId: manifest.sessionId,
        state: 'request_$index',
      );
    }
  } finally {
    upstream.close(force: true);
  }
}

Future<void> _probeHls(Dio client, PlaybackManifestDto manifest) async {
  final upstream = _mediaClient();
  try {
    final redirect = await _requestRaw(
      () => client.get<Object?>(
        manifest.streamUri.toString(),
        options: Options(
          followRedirects: false,
          headers: const <String, Object?>{
            'User-Agent': windowsPlaybackUserAgent,
          },
          responseType: ResponseType.plain,
        ),
      ),
      stage: 'hls_redirect',
      acceptedStatuses: const <int>{200, 302},
    );
    final _HlsDocument document;
    if (redirect.statusCode == 302) {
      document = await _readHlsDocument(
        upstream,
        _redirectTarget(redirect),
        stage: 'hls_manifest',
      );
    } else {
      document = _parseHlsDocument(
        redirect.data,
        redirect.realUri,
        stage: 'hls_manifest',
      );
    }
    _evidence('hls_manifest', statusCode: 200, sessionId: manifest.sessionId);

    var childUri = _resolveMediaReference(
      document.baseUri,
      document.firstReference,
    );
    if (childUri.path.toLowerCase().endsWith('.m3u8')) {
      final child = await _readHlsDocument(
        upstream,
        childUri,
        stage: 'hls_variant',
      );
      _evidence('hls_child', statusCode: 200, state: 'highest_variant');
      childUri = _resolveMediaReference(child.baseUri, child.firstReference);
    }
    final childResponse = await _requestRaw(
      () => upstream.getUri<Object?>(
        childUri,
        options: Options(
          headers: const <String, Object?>{
            'User-Agent': windowsPlaybackUserAgent,
          },
          responseType: ResponseType.bytes,
        ),
      ),
      stage: 'hls_child',
      acceptedStatuses: const <int>{200, 206},
    );
    if (childResponse.data is! List<int> ||
        (childResponse.data! as List<int>).isEmpty) {
      throw const ProbeFailure('hls_child_protocol_error');
    }
    _evidence(
      'hls_child',
      statusCode: childResponse.statusCode,
      state: 'media',
    );
  } finally {
    upstream.close(force: true);
  }
}

Future<_HlsDocument> _readHlsDocument(
  Dio upstream,
  Uri uri, {
  required String stage,
}) async {
  final response = await _requestRaw(
    () => upstream.getUri<Object?>(
      uri,
      options: Options(
        headers: const <String, Object?>{
          'User-Agent': windowsPlaybackUserAgent,
        },
        responseType: ResponseType.plain,
      ),
    ),
    stage: stage,
    acceptedStatuses: const <int>{200},
  );
  return _parseHlsDocument(response.data, response.realUri, stage: stage);
}

_HlsDocument _parseHlsDocument(
  Object? data,
  Uri baseUri, {
  required String stage,
}) {
  if (data is! String || !data.trimLeft().startsWith('#EXTM3U')) {
    throw ProbeFailure('${stage}_protocol_error');
  }
  final lines =
      data.split(RegExp(r'\r?\n')).map((line) => line.trim()).toList();
  String? firstMediaReference;
  String? highestVariant;
  var highestBandwidth = -1;
  for (var index = 0; index < lines.length; index++) {
    final line = lines[index];
    if (line.startsWith('#EXT-X-STREAM-INF:')) {
      final attributes = line.substring('#EXT-X-STREAM-INF:'.length);
      final match = RegExp(
        r'(?:^|,)BANDWIDTH=([0-9]+)(?:,|$)',
      ).firstMatch(attributes);
      final bandwidth = int.tryParse(match?.group(1) ?? '');
      if (bandwidth == null || bandwidth <= 0 || index + 1 >= lines.length) {
        throw ProbeFailure('${stage}_variant_invalid');
      }
      final reference = lines[++index];
      if (reference.isEmpty || reference.startsWith('#')) {
        throw ProbeFailure('${stage}_variant_invalid');
      }
      if (bandwidth > highestBandwidth) {
        highestBandwidth = bandwidth;
        highestVariant = reference;
      }
    } else if (line.isNotEmpty && !line.startsWith('#')) {
      firstMediaReference ??= line;
    }
  }
  final reference = highestVariant ?? firstMediaReference;
  if (reference == null) {
    throw ProbeFailure('${stage}_child_missing');
  }
  return _HlsDocument(baseUri: baseUri, firstReference: reference);
}

Future<void> _probeSubtitles(Dio client, PlaybackManifestDto manifest) async {
  for (final format in const <String>['srt', 'ass']) {
    final options = manifest.subtitles.where((item) => item.format == format);
    if (options.isEmpty) {
      throw ProbeFailure('subtitle_${format}_missing');
    }
    final response = await _requestRaw(
      () => client.get<Object?>(
        'playback/sessions/${manifest.sessionId}/subtitles/'
        '${options.first.id}',
        options: Options(responseType: ResponseType.bytes),
      ),
      stage: 'subtitle_$format',
      acceptedStatuses: const <int>{200},
    );
    if (response.data is! List<int> || (response.data! as List<int>).isEmpty) {
      throw ProbeFailure('subtitle_${format}_empty');
    }
    _evidence(
      'subtitle_download',
      statusCode: response.statusCode,
      sessionId: manifest.sessionId,
      state: format,
    );
  }
}

Dio _mediaClient() => Dio(
  BaseOptions(
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 30),
    sendTimeout: const Duration(seconds: 15),
    validateStatus: (status) => status != null && status < 500,
  ),
);

Uri _redirectTarget(_ProbeResponse<Object?> response) {
  final value = response.headers.value('location');
  final uri = value == null ? null : Uri.tryParse(value);
  if (uri == null ||
      !uri.isAbsolute ||
      !const <String>{'http', 'https'}.contains(uri.scheme) ||
      uri.userInfo.isNotEmpty ||
      uri.fragment.isNotEmpty) {
    throw const ProbeFailure('invalid_media_redirect');
  }
  return uri;
}

Uri _resolveMediaReference(Uri baseUri, String reference) {
  final parsed = Uri.tryParse(reference);
  final resolved = parsed == null ? null : baseUri.resolveUri(parsed);
  if (resolved == null ||
      !resolved.isAbsolute ||
      !const <String>{'http', 'https'}.contains(resolved.scheme) ||
      resolved.userInfo.isNotEmpty ||
      resolved.fragment.isNotEmpty) {
    throw const ProbeFailure('invalid_hls_child');
  }
  return resolved;
}

final class _HlsDocument {
  const _HlsDocument({required this.baseUri, required this.firstReference});

  final Uri baseUri;
  final String firstReference;
}

List<String> _acceptanceSelection(CacheJobDto job) {
  final groups = <String, List<RemoteMediaDto>>{};
  for (final media in job.mediaCandidates.where((item) => item.isValid)) {
    groups.putIfAbsent(media.candidateId, () => <RemoteMediaDto>[]).add(media);
  }
  final hasSingle = groups.values.any((items) => items.length == 1);
  final segmented = groups.values.where((items) => items.length > 1).toList();
  if (groups.length < 2 || !hasSingle || segmented.isEmpty) {
    throw const ProbeFailure('media_shape_samples_incomplete');
  }
  segmented.sort((left, right) => right.length.compareTo(left.length));
  final selected =
      segmented.first
        ..sort((left, right) => left.sequenceNo.compareTo(right.sequenceNo));
  for (var index = 0; index < selected.length; index++) {
    if (selected[index].sequenceNo != index) {
      throw const ProbeFailure('segmented_sequence_invalid');
    }
  }
  _evidence('media_shapes', state: 'single_multi_segmented');
  return selected.map((item) => item.id).toList(growable: false);
}

Uri _normalizeBaseUri(String value) {
  final parsed = Uri.tryParse(value);
  if (parsed == null ||
      !parsed.isAbsolute ||
      !const <String>{'http', 'https'}.contains(parsed.scheme) ||
      parsed.userInfo.isNotEmpty ||
      parsed.query.isNotEmpty ||
      parsed.fragment.isNotEmpty) {
    throw const ProbeFailure('invalid_api_base_url');
  }
  final segments = <String>[
    ...parsed.pathSegments.where((segment) => segment.isNotEmpty),
  ];
  if (segments.length < 2 ||
      segments[segments.length - 2] != 'api' ||
      segments.last != 'v1') {
    segments.addAll(const <String>['api', 'v1']);
  }
  return parsed.replace(
    path: '/${segments.join('/')}/',
    query: null,
    fragment: null,
  );
}

String _required(Map<String, String> environment, String name) {
  final value = environment[name];
  if (value == null || value.trim().isEmpty) {
    throw ProbeFailure('missing_$name');
  }
  return value.trim();
}

bool _reuseConfirmedBinding(Map<String, String> environment) =>
    environment[_reuseBindingName] == '1';

bool _skipExternalSubtitles(Map<String, String> environment) =>
    environment[_skipExternalSubtitlesName] == '1';

String _requiredUuid(Map<String, String> environment, String name) {
  final value = _required(environment, name);
  if (!RegExp(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$',
  ).hasMatch(value)) {
    throw ProbeFailure('invalid_$name');
  }
  return value;
}

String _uuidV4() {
  final bytes = Uint8List.fromList(
    List<int>.generate(16, (_) => Random.secure().nextInt(256)),
  );
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  final hex =
      bytes.map((value) => value.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
      '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}

void _evidence(
  String stage, {
  int? statusCode,
  String? sourceId,
  String? jobId,
  String? sessionId,
  String? state,
  String? localFile,
}) {
  final fields = <String>[
    'real115_stage=$stage',
    if (statusCode != null) 'status_code=$statusCode',
    if (sourceId != null) 'source_id=$sourceId',
    if (jobId != null) 'job_id=$jobId',
    if (sessionId != null) 'session_id=$sessionId',
    if (state != null) 'state=$state',
    if (localFile != null) 'local_qr_file=$localFile',
  ];
  // ignore: avoid_print
  print(fields.join(' '));
}

final class _ProbeResponse<T> {
  const _ProbeResponse({
    required this.statusCode,
    required this.data,
    required this.headers,
    required this.realUri,
  });

  final int statusCode;
  final T data;
  final Headers headers;
  final Uri realUri;
}

final class ProbeFailure implements Exception {
  const ProbeFailure(this.code);

  final String code;

  @override
  String toString() => 'Real115 probe failed: $code';
}
