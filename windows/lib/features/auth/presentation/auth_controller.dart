import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/server_profile.dart';
import 'package:sakuraplayer_windows/core/auth/session_store.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';
import 'package:sakuraplayer_windows/core/storage/subtitle_cache.dart';
import 'package:sakuraplayer_windows/features/auth/domain/auth_session_state.dart';

typedef ApiClientFactory =
    ApiClient Function(ServerProfile profile, SessionStore sessionStore);

final secureKeyValueStoreProvider = Provider<SecureKeyValueStore>(
  (ref) => FlutterSecureKeyValueStore(),
);

final secureStoreProvider = Provider<SecureStore>(
  (ref) => SecureStore(ref.watch(secureKeyValueStoreProvider)),
);

final sessionStoreProvider = Provider<SessionStore>(
  (ref) => SessionStore(ref.watch(secureStoreProvider)),
);

final serverAddressPolicyProvider = Provider<ServerAddressPolicy>(
  (ref) => const ServerAddressPolicy(),
);

final serverProfileRepositoryProvider = Provider<ServerProfileRepository>(
  (ref) => ServerProfileRepository(
    ref.watch(secureStoreProvider),
    ref.watch(serverAddressPolicyProvider),
  ),
);

final serverProbeProvider = Provider<ServerProbe>(
  (ref) => const ServerConnectionTester(),
);

final subtitleCacheProvider = Provider<SubtitleCache>(
  (ref) => DirectorySubtitleCache.forCurrentUser(),
);

final runtimeResetProvider = Provider<RuntimeResetCoordinator>(
  (ref) => RuntimeResetCoordinator(),
);

final apiClientFactoryProvider = Provider<ApiClientFactory>(
  (ref) => (profile, session) {
    return ApiClient(
      dio: Dio(BaseOptions(baseUrl: '${profile.baseUri}/api/v1/')),
      sessionStore: session,
    );
  },
);

final authControllerProvider =
    NotifierProvider<AuthController, AuthSessionState>(AuthController.new);

final authSessionStateProvider = Provider<AuthSessionState>(
  (ref) => ref.watch(authControllerProvider),
);

class RuntimeResetCoordinator {
  Future<void> Function()? _callback;

  void register(Future<void> Function() callback) {
    _callback = callback;
  }

  void unregister(Future<void> Function() callback) {
    if (identical(_callback, callback)) _callback = null;
  }

  Future<void> reset() async {
    await _callback?.call();
  }
}

class AuthController extends Notifier<AuthSessionState> {
  ApiClient? _apiClient;
  bool _initialized = false;

  ApiClient? get apiClient => _apiClient;

  @override
  AuthSessionState build() => const AuthSessionState.serverRequired();

  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    state = const AuthSessionState.initializing();
    final secure = ref.read(secureStoreProvider);
    await secure.clientInstanceId();
    final profile = await ref.read(serverProfileRepositoryProvider).load();
    if (profile == null) {
      state = const AuthSessionState.serverRequired();
      return;
    }
    await _restoreProfile(profile);
  }

  Future<void> configureServer(
    String input, {
    bool allowPrivateHttp = false,
  }) async {
    state = state.copyWith(busy: true, clearError: true);
    try {
      final profile = ref
          .read(serverAddressPolicyProvider)
          .normalize(input, allowPrivateHttp: allowPrivateHttp);
      final status = await ref.read(serverProbeProvider).test(profile);
      await ref.read(secureStoreProvider).clientInstanceId();
      final oldProfile = await ref.read(serverProfileRepositoryProvider).load();
      final wasAuthenticated = state.isAuthenticated;
      if (oldProfile != null && oldProfile.baseUri != profile.baseUri) {
        await _attemptOldLogout(oldProfile);
        await _clearLocalSession();
      }
      await ref.read(serverProfileRepositoryProvider).save(profile);
      _apiClient = ref.read(apiClientFactoryProvider)(
        profile,
        ref.read(sessionStoreProvider),
      );
      if (oldProfile?.baseUri == profile.baseUri && wasAuthenticated) {
        state = AuthSessionState.authenticated(serverBaseUri: profile.baseUri);
        return;
      }
      state = AuthSessionState.unauthenticated(
        serverBaseUri: profile.baseUri,
        bootstrapRequired: !status.initialized,
      );
    } on ServerAddressException catch (error) {
      state = state.copyWith(
        busy: false,
        errorCode: error.code,
        errorMessage: error.message,
      );
      rethrow;
    } on ApiException catch (error) {
      state = state.copyWith(
        busy: false,
        errorCode: error.code,
        errorMessage: error.message,
      );
      rethrow;
    }
  }

  Future<void> login({
    required String username,
    required String password,
  }) async {
    final client = _requireClient();
    state = state.copyWith(busy: true, clearError: true);
    try {
      await client.login(
        username: username,
        password: password,
        clientInstanceId:
            await ref.read(secureStoreProvider).clientInstanceId(),
      );
      state = AuthSessionState.authenticated(
        serverBaseUri: state.serverBaseUri!,
      );
    } on ApiException catch (error) {
      state = state.copyWith(
        busy: false,
        errorCode: error.code,
        errorMessage: error.message,
      );
      rethrow;
    }
  }

  Future<void> bootstrap({
    required String username,
    required String password,
    required String bootstrapToken,
  }) async {
    final client = _requireClient();
    state = state.copyWith(busy: true, clearError: true);
    try {
      await client.bootstrap(
        username: username,
        password: password,
        clientInstanceId:
            await ref.read(secureStoreProvider).clientInstanceId(),
        bootstrapToken: bootstrapToken,
      );
      state = AuthSessionState.authenticated(
        serverBaseUri: state.serverBaseUri!,
      );
    } on ApiException catch (error) {
      state = state.copyWith(
        busy: false,
        errorCode: error.code,
        errorMessage: error.message,
      );
      rethrow;
    }
  }

  Future<void> logout() async {
    final profile = state.serverBaseUri;
    try {
      if (_apiClient != null && ref.read(sessionStoreProvider).hasAccessToken) {
        await _apiClient!.logout();
      }
    } on Exception {
      // Local revocation is mandatory even when the old server is unreachable.
    } finally {
      await _clearLocalSession();
      state =
          profile == null
              ? const AuthSessionState.serverRequired()
              : AuthSessionState.unauthenticated(
                serverBaseUri: profile,
                bootstrapRequired: false,
              );
    }
  }

  Future<void> _restoreProfile(ServerProfile profile) async {
    _apiClient = ref.read(apiClientFactoryProvider)(
      profile,
      ref.read(sessionStoreProvider),
    );
    try {
      final status = await ref.read(serverProbeProvider).test(profile);
      final refresh = await ref.read(sessionStoreProvider).readRefreshToken();
      if (refresh != null && status.initialized) {
        try {
          await _apiClient!.refreshSession();
          state = AuthSessionState.authenticated(
            serverBaseUri: profile.baseUri,
          );
          return;
        } on ApiException {
          // Refresh failure already clears the local token pair.
        }
      }
      state = AuthSessionState.unauthenticated(
        serverBaseUri: profile.baseUri,
        bootstrapRequired: !status.initialized,
      );
    } on ApiException catch (error) {
      state = AuthSessionState.unauthenticated(
        serverBaseUri: profile.baseUri,
        bootstrapRequired: false,
        errorCode: error.code,
        errorMessage: error.message,
      );
    }
  }

  Future<void> _attemptOldLogout(ServerProfile oldProfile) async {
    final session = ref.read(sessionStoreProvider);
    final oldClient =
        _apiClient ?? ref.read(apiClientFactoryProvider)(oldProfile, session);
    try {
      if (!session.hasAccessToken && await session.readRefreshToken() != null) {
        await oldClient.refreshSession();
      }
      if (session.hasAccessToken) await oldClient.logout();
    } on Exception {
      // Address switching must continue with local cleanup.
    }
  }

  Future<void> _clearLocalSession() async {
    await ref.read(runtimeResetProvider).reset();
    await ref.read(sessionStoreProvider).clearTokens();
    await ref.read(subtitleCacheProvider).clear();
  }

  ApiClient _requireClient() {
    final client = _apiClient;
    if (client == null || state.serverBaseUri == null) {
      throw StateError('server profile is not configured');
    }
    return client;
  }
}
