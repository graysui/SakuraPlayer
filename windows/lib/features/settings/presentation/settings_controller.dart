import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/settings/data/settings_api.dart';

enum SettingsStatus { idle, loading, ready, failed }

@immutable
class SettingsState {
  const SettingsState({
    required this.status,
    required this.settings,
    required this.errorCode,
    required this.inFlight,
    required this.connectionTests,
  });
  const SettingsState.initial()
    : status = SettingsStatus.idle,
      settings = null,
      errorCode = null,
      inFlight = const {},
      connectionTests = const {};
  final SettingsStatus status;
  final SettingsDto? settings;
  final String? errorCode;
  final Set<String> inFlight;
  final Map<String, ConnectionTestDto> connectionTests;
  SettingsState copyWith({
    SettingsStatus? status,
    Object? settings = _absent,
    Object? errorCode = _absent,
    Set<String>? inFlight,
    Map<String, ConnectionTestDto>? connectionTests,
  }) => SettingsState(
    status: status ?? this.status,
    settings:
        identical(settings, _absent) ? this.settings : settings as SettingsDto?,
    errorCode:
        identical(errorCode, _absent) ? this.errorCode : errorCode as String?,
    inFlight: inFlight ?? this.inFlight,
    connectionTests: connectionTests ?? this.connectionTests,
  );
}

final settingsControllerProvider =
    NotifierProvider<SettingsController, SettingsState>(SettingsController.new);

class SettingsController extends Notifier<SettingsState> {
  int _generation = 0;
  @override
  SettingsState build() {
    ref.watch(authSessionStateProvider);
    _generation++;
    return const SettingsState.initial();
  }

  Future<void> load() async {
    final generation = ++_generation;
    state = state.copyWith(
      status: SettingsStatus.loading,
      errorCode: null,
      inFlight: const {},
    );
    try {
      final settings = await ref.read(settingsGatewayProvider).getSettings();
      if (generation != _generation) return;
      state = state.copyWith(
        status: SettingsStatus.ready,
        settings: settings,
        errorCode: null,
      );
    } on ApiException catch (error) {
      if (generation == _generation) {
        state = state.copyWith(
          status: SettingsStatus.failed,
          errorCode: error.code,
        );
      }
    }
  }

  Future<void> saveTtl(int hours) =>
      _mutate('ttl', () => ref.read(settingsGatewayProvider).updateTtl(hours));
  Future<void> replaceJavdb({
    required String username,
    required String password,
  }) {
    final current = state.settings;
    if (current == null) return Future.value();
    return _mutate(
      'javdb',
      () => ref
          .read(settingsGatewayProvider)
          .replaceJavdb(
            expectedVersion: current.javdb.version,
            username: username,
            password: password,
          ),
    );
  }

  Future<void> clearJavdb() {
    final current = state.settings;
    if (current == null) return Future.value();
    return _mutate(
      'javdb',
      () => ref.read(settingsGatewayProvider).clearJavdb(current.javdb.version),
    );
  }

  Future<void> replaceAi({
    required String baseUrl,
    required String apiKey,
    required String model,
    required int timeoutSeconds,
  }) {
    final current = state.settings;
    if (current == null) return Future.value();
    return _mutate(
      'ai',
      () => ref
          .read(settingsGatewayProvider)
          .replaceAi(
            expectedVersion: current.ai.version,
            baseUrl: baseUrl,
            apiKey: apiKey,
            model: model,
            timeoutSeconds: timeoutSeconds,
          ),
    );
  }

  Future<void> clearAi() {
    final current = state.settings;
    if (current == null) return Future.value();
    return _mutate(
      'ai',
      () => ref.read(settingsGatewayProvider).clearAi(current.ai.version),
    );
  }

  Future<void> testConnection(String target) async {
    if (!connectionTargets.contains(target) ||
        state.inFlight.contains('test:$target')) {
      return;
    }
    final generation = _generation;
    final key = 'test:$target';
    state = state.copyWith(inFlight: {...state.inFlight, key}, errorCode: null);
    try {
      final result = await ref
          .read(settingsGatewayProvider)
          .testConnection(target);
      if (generation != _generation) return;
      state = state.copyWith(
        inFlight: {...state.inFlight}..remove(key),
        connectionTests: {...state.connectionTests, target: result},
      );
    } on ApiException catch (error) {
      if (generation == _generation) {
        state = state.copyWith(
          inFlight: {...state.inFlight}..remove(key),
          errorCode: error.code,
        );
      }
    }
  }

  Future<void> _mutate(
    String key,
    Future<SettingsDto> Function() operation,
  ) async {
    if (state.settings == null || state.inFlight.contains(key)) return;
    final generation = _generation;
    state = state.copyWith(inFlight: {...state.inFlight, key}, errorCode: null);
    try {
      final settings = await operation();
      if (generation != _generation) return;
      state = state.copyWith(
        status: SettingsStatus.ready,
        settings: settings,
        inFlight: {...state.inFlight}..remove(key),
        errorCode: null,
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = state.copyWith(
        inFlight: {...state.inFlight}..remove(key),
        errorCode: error.code,
      );
      if (error.code == 'state_conflict') await load();
    }
  }
}

enum DiagnosticsStatus { idle, loading, ready, failed }

@immutable
class DiagnosticsState {
  const DiagnosticsState({
    required this.status,
    required this.diagnostics,
    required this.jobs,
    required this.nextCursor,
    required this.errorCode,
    required this.isAppending,
    required this.inFlightIds,
  });
  const DiagnosticsState.initial()
    : status = DiagnosticsStatus.idle,
      diagnostics = null,
      jobs = const [],
      nextCursor = null,
      errorCode = null,
      isAppending = false,
      inFlightIds = const {};
  final DiagnosticsStatus status;
  final DiagnosticsDto? diagnostics;
  final List<MetadataJobDto> jobs;
  final String? nextCursor;
  final String? errorCode;
  final bool isAppending;
  final Set<String> inFlightIds;
  DiagnosticsState copyWith({
    DiagnosticsStatus? status,
    Object? diagnostics = _absent,
    List<MetadataJobDto>? jobs,
    Object? nextCursor = _absent,
    Object? errorCode = _absent,
    bool? isAppending,
    Set<String>? inFlightIds,
  }) => DiagnosticsState(
    status: status ?? this.status,
    diagnostics:
        identical(diagnostics, _absent)
            ? this.diagnostics
            : diagnostics as DiagnosticsDto?,
    jobs: jobs ?? this.jobs,
    nextCursor:
        identical(nextCursor, _absent)
            ? this.nextCursor
            : nextCursor as String?,
    errorCode:
        identical(errorCode, _absent) ? this.errorCode : errorCode as String?,
    isAppending: isAppending ?? this.isAppending,
    inFlightIds: inFlightIds ?? this.inFlightIds,
  );
}

final diagnosticsControllerProvider =
    NotifierProvider<DiagnosticsController, DiagnosticsState>(
      DiagnosticsController.new,
    );

class DiagnosticsController extends Notifier<DiagnosticsState> {
  int _generation = 0;
  @override
  DiagnosticsState build() {
    ref.watch(authSessionStateProvider);
    _generation++;
    return const DiagnosticsState.initial();
  }

  Future<void> load() async {
    final generation = ++_generation;
    state = state.copyWith(
      status: DiagnosticsStatus.loading,
      jobs: const [],
      nextCursor: null,
      errorCode: null,
    );
    try {
      final gateway = ref.read(settingsGatewayProvider);
      final results = await Future.wait<Object>([
        gateway.getDiagnostics(),
        gateway.listMetadataJobs(),
      ]);
      if (generation != _generation) return;
      final page = results[1] as MetadataJobPageDto;
      state = state.copyWith(
        status: DiagnosticsStatus.ready,
        diagnostics: results[0] as DiagnosticsDto,
        jobs: page.items,
        nextCursor: page.nextCursor,
        errorCode: null,
      );
    } on ApiException catch (error) {
      if (generation == _generation) {
        state = state.copyWith(
          status: DiagnosticsStatus.failed,
          errorCode: error.code,
        );
      }
    }
  }

  Future<void> loadMore() async {
    final cursor = state.nextCursor;
    if (state.status != DiagnosticsStatus.ready ||
        cursor == null ||
        state.isAppending) {
      return;
    }
    final generation = _generation;
    state = state.copyWith(isAppending: true);
    try {
      final page = await ref
          .read(settingsGatewayProvider)
          .listMetadataJobs(cursor: cursor);
      if (generation != _generation) return;
      final byId = <String, MetadataJobDto>{
        for (final item in state.jobs) item.id: item,
      };
      for (final item in page.items) {
        byId[item.id] = item;
      }
      state = state.copyWith(
        jobs: List.unmodifiable(byId.values),
        nextCursor: page.nextCursor,
        isAppending: false,
      );
    } on ApiException catch (error) {
      if (generation == _generation) {
        state = state.copyWith(isAppending: false, errorCode: error.code);
      }
    }
  }

  Future<void> retryFull(String jobId) {
    MetadataJobDto? job;
    for (final item in state.jobs) {
      if (item.id == jobId) {
        job = item;
        break;
      }
    }
    final coreSucceeded =
        job?.stages.any(
          (stage) => stage.stage == 'javdb_core' && stage.status == 'succeeded',
        ) ??
        false;
    if (job == null || job.status != 'failed' || coreSucceeded) {
      return Future<void>.value();
    }
    return _retry(
      jobId,
      () => ref.read(settingsGatewayProvider).retryMetadataJob(jobId),
    );
  }

  Future<void> retryEnrichment(String jobId, List<String> stages) {
    MetadataJobDto? job;
    for (final item in state.jobs) {
      if (item.id == jobId) {
        job = item;
        break;
      }
    }
    if (job == null) return Future.value();
    return _retry(
      jobId,
      () => ref
          .read(settingsGatewayProvider)
          .retryMetadataEnrichment(jobId, stages, job!.retryableStages),
    );
  }

  Future<void> _retry(
    String jobId,
    Future<MetadataJobDto> Function() operation,
  ) async {
    if (state.inFlightIds.contains(jobId)) return;
    final generation = _generation;
    state = state.copyWith(
      inFlightIds: {...state.inFlightIds, jobId},
      errorCode: null,
    );
    try {
      final created = await operation();
      if (generation != _generation) return;
      state = state.copyWith(
        jobs: [created, ...state.jobs],
        inFlightIds: {...state.inFlightIds}..remove(jobId),
      );
    } on ApiException catch (error) {
      if (generation != _generation) return;
      state = state.copyWith(
        inFlightIds: {...state.inFlightIds}..remove(jobId),
        errorCode: error.code,
      );
    }
  }
}

const _absent = Object();
