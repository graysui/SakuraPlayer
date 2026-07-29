import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';

class SessionStore {
  SessionStore(this._secureStore);

  final SecureStore _secureStore;
  String? _accessToken;
  DateTime? _accessExpiresAt;
  DateTime? _refreshExpiresAt;

  String? get accessToken => _accessToken;
  DateTime? get accessExpiresAt => _accessExpiresAt;
  DateTime? get refreshExpiresAt => _refreshExpiresAt;
  bool get hasAccessToken => _accessToken != null;

  Future<String?> readRefreshToken() => _secureStore.readRefreshToken();

  Future<void> setTokens(TokenPair tokens) async {
    await _secureStore.writeRefreshToken(tokens.refreshToken);
    _accessToken = tokens.accessToken;
    _accessExpiresAt = tokens.accessExpiresAt;
    _refreshExpiresAt = tokens.refreshExpiresAt;
  }

  Future<void> clearTokens() async {
    _accessToken = null;
    _accessExpiresAt = null;
    _refreshExpiresAt = null;
    await _secureStore.deleteRefreshToken();
  }
}
