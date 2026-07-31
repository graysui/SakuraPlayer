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

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  final enabled = Platform.environment[_markerName] == '1';

  test(
    'explicit QR and playback probe emits only redacted evidence',
    () async {
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
          receiveTimeout: const Duration(seconds: 30),
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
        if (job.status != 'ready' || job.selectedMediaIds.isEmpty) {
          throw ProbeFailure('cache_job_${job.status}');
        }

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

        final stream = await _requestRaw(
          () => client.get<Object?>(
            manifest!.streamUri.toString(),
            options: Options(
              followRedirects: false,
              headers: const <String, Object?>{
                'User-Agent': windowsPlaybackUserAgent,
                'Range': 'bytes=0-0',
              },
              responseType: ResponseType.bytes,
              receiveTimeout: const Duration(seconds: 30),
            ),
          ),
          stage: 'stream_probe',
          acceptedStatuses: const <int>{200, 206, 302},
        );
        _evidence(
          'stream_probe',
          statusCode: stream.statusCode,
          sessionId: manifest.sessionId,
        );

        final progress = manifest.progress;
        await _requestJson(
          () => client.put<Object?>(
            'playback/sessions/${manifest!.sessionId}/heartbeat',
            data: <String, Object?>{
              'client_instance_id': clientId,
              'progress': <String, Object?>{
                'position_seconds': progress?.positionSeconds ?? 0,
                'duration_seconds': progress?.durationSeconds,
                'version': progress?.version ?? 0,
              },
              'playing': false,
            },
          ),
          stage: 'lease_release',
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
    skip:
        enabled ? false : '$_markerName is not enabled; no network attempted.',
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
    return _ProbeResponse<Object?>(statusCode: status, data: response.data);
  } on DioException catch (error) {
    throw ProbeFailure('${stage}_transport_${error.type.name}');
  }
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
  const _ProbeResponse({required this.statusCode, required this.data});

  final int statusCode;
  final T data;
}

final class ProbeFailure implements Exception {
  const ProbeFailure(this.code);

  final String code;

  @override
  String toString() => 'Real115 probe failed: $code';
}
