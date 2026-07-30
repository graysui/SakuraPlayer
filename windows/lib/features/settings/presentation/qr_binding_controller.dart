import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/settings/data/settings_api.dart';

@immutable
class QrBindingState {
  const QrBindingState({
    required this.binding,
    required this.sessionId,
    required this.status,
    required this.imageBytes,
    required this.expiresAt,
    required this.errorCode,
    required this.isLoading,
    required this.isPolling,
  });

  const QrBindingState.initial()
    : binding = null,
      sessionId = null,
      status = null,
      imageBytes = null,
      expiresAt = null,
      errorCode = null,
      isLoading = false,
      isPolling = false;

  final Cloud115BindingDto? binding;
  final String? sessionId;
  final String? status;
  final Uint8List? imageBytes;
  final DateTime? expiresAt;
  final String? errorCode;
  final bool isLoading;
  final bool isPolling;

  QrBindingState copyWith({
    Object? binding = _absent,
    Object? sessionId = _absent,
    Object? status = _absent,
    Object? imageBytes = _absent,
    Object? expiresAt = _absent,
    Object? errorCode = _absent,
    bool? isLoading,
    bool? isPolling,
  }) => QrBindingState(
    binding:
        identical(binding, _absent)
            ? this.binding
            : binding as Cloud115BindingDto?,
    sessionId:
        identical(sessionId, _absent) ? this.sessionId : sessionId as String?,
    status: identical(status, _absent) ? this.status : status as String?,
    imageBytes:
        identical(imageBytes, _absent)
            ? this.imageBytes
            : imageBytes as Uint8List?,
    expiresAt:
        identical(expiresAt, _absent) ? this.expiresAt : expiresAt as DateTime?,
    errorCode:
        identical(errorCode, _absent) ? this.errorCode : errorCode as String?,
    isLoading: isLoading ?? this.isLoading,
    isPolling: isPolling ?? this.isPolling,
  );
}

final qrBindingControllerProvider =
    NotifierProvider<QrBindingController, QrBindingState>(
      QrBindingController.new,
    );

class QrBindingController extends Notifier<QrBindingState> {
  Timer? _timer;
  bool _pollInFlight = false;
  bool _confirmStarted = false;
  int _generation = 0;

  @override
  QrBindingState build() {
    ref.watch(authSessionStateProvider);
    _generation++;
    _timer?.cancel();
    _timer = null;
    _pollInFlight = false;
    _confirmStarted = false;
    ref.onDispose(() => _timer?.cancel());
    return const QrBindingState.initial();
  }

  Future<void> loadBinding() async {
    final generation = _generation;
    state = state.copyWith(isLoading: true, errorCode: null);
    try {
      final binding = await ref.read(settingsGatewayProvider).getBinding();
      if (generation != _generation) return;
      state = state.copyWith(
        binding: binding,
        isLoading: false,
        errorCode: null,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = state.copyWith(isLoading: false, errorCode: error.code);
    }
  }

  Future<void> startQr() async {
    _stopPolling(clearSession: true);
    final generation = _generation;
    state = state.copyWith(isLoading: true, errorCode: null, status: null);
    try {
      final session = await ref.read(settingsGatewayProvider).createQrSession();
      if (generation != _generation) return;
      state = state.copyWith(
        sessionId: session.id,
        status: session.status,
        imageBytes: session.imageBytes,
        expiresAt: session.expiresAt,
        isLoading: false,
        errorCode: null,
      );
      if (session.status == 'waiting' || session.status == 'scanned') {
        _startPolling();
      } else if (session.status == 'confirmed') {
        await _confirm(session.id, generation);
      }
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = state.copyWith(isLoading: false, errorCode: error.code);
    }
  }

  Future<void> pollOnce() async {
    final sessionId = state.sessionId;
    if (sessionId == null || _pollInFlight || !state.isPolling) return;
    _pollInFlight = true;
    final generation = _generation;
    try {
      final session = await ref
          .read(settingsGatewayProvider)
          .pollQrSession(sessionId);
      if (generation != _generation) return;
      state = state.copyWith(
        status: session.status,
        expiresAt: session.expiresAt,
      );
      if (session.status == 'confirmed') {
        await _confirm(session.id, generation);
      } else if (session.status == 'expired' || session.status == 'canceled') {
        _stopPolling(clearSession: true, status: session.status);
      }
    } on ApiException catch (error) {
      if (generation == _generation) {
        final requiresNewQr =
            error.code == 'cloud115_credentials_expired' ||
            error.code == 'cloud115_qr_session_not_found';
        _stopPolling(clearSession: requiresNewQr, errorCode: error.code);
      }
    } finally {
      _pollInFlight = false;
    }
  }

  Future<void> retry() async {
    final sessionId = state.sessionId;
    if (sessionId == null) return startQr();
    state = state.copyWith(errorCode: null);
    if (state.status == 'confirmed') {
      await _confirm(sessionId, _generation);
      return;
    }
    _startPolling();
    await pollOnce();
  }

  Future<void> unbind() async {
    final generation = _generation;
    state = state.copyWith(isLoading: true, errorCode: null);
    try {
      await ref.read(settingsGatewayProvider).unbind();
      if (generation != _generation) return;
      await loadBinding();
    } on ApiException catch (error) {
      if (generation == _generation) {
        state = state.copyWith(isLoading: false, errorCode: error.code);
      }
    }
  }

  void _startPolling() {
    _timer?.cancel();
    state = state.copyWith(isPolling: true);
    _timer = Timer.periodic(
      const Duration(seconds: 2),
      (_) => unawaited(pollOnce()),
    );
  }

  Future<void> _confirm(String sessionId, int generation) async {
    if (_confirmStarted) return;
    _confirmStarted = true;
    _timer?.cancel();
    _timer = null;
    state = state.copyWith(isPolling: false, isLoading: true);
    try {
      final binding = await ref
          .read(settingsGatewayProvider)
          .confirmQrSession(sessionId);
      if (generation != _generation) return;
      state = state.copyWith(
        binding: binding,
        status: 'confirmed',
        isLoading: false,
        sessionId: null,
        imageBytes: null,
        expiresAt: null,
        errorCode: null,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      final requiresNewQr =
          error.code == 'cloud115_credentials_expired' ||
          error.code == 'cloud115_qr_session_not_found';
      _confirmStarted = false;
      state = state.copyWith(
        isLoading: false,
        errorCode: error.code,
        status: 'confirmed',
        sessionId: requiresNewQr ? null : _absent,
        imageBytes: requiresNewQr ? null : _absent,
        expiresAt: requiresNewQr ? null : _absent,
      );
    }
  }

  void _stopPolling({
    required bool clearSession,
    String? status,
    String? errorCode,
  }) {
    _timer?.cancel();
    _timer = null;
    _pollInFlight = false;
    _confirmStarted = false;
    state = state.copyWith(
      isPolling: false,
      status: status ?? (clearSession ? state.status : _absent),
      sessionId: clearSession ? null : _absent,
      imageBytes: clearSession ? null : _absent,
      expiresAt: clearSession ? null : _absent,
      errorCode: errorCode ?? _absent,
    );
  }
}

const _absent = Object();
