import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class SecureKeyValueStore {
  Future<String?> read(String key);

  Future<void> write(String key, String value);

  Future<void> delete(String key);
}

class FlutterSecureKeyValueStore implements SecureKeyValueStore {
  FlutterSecureKeyValueStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

class MemorySecureKeyValueStore implements SecureKeyValueStore {
  final Map<String, String> values = <String, String>{};

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    values.remove(key);
  }
}

class SecureStore {
  SecureStore(this._store, {Random? random})
    : _random = random ?? Random.secure();

  static const refreshTokenKey = 'auth.refresh_token';
  static const clientInstanceIdKey = 'installation.client_instance_id';
  static const serverBaseUrlKey = 'server.base_url';

  final SecureKeyValueStore _store;
  final Random _random;

  Future<String?> readRefreshToken() => _store.read(refreshTokenKey);

  Future<void> writeRefreshToken(String value) =>
      _store.write(refreshTokenKey, value);

  Future<void> deleteRefreshToken() => _store.delete(refreshTokenKey);

  Future<String?> readServerBaseUrl() => _store.read(serverBaseUrlKey);

  Future<void> writeServerBaseUrl(String value) =>
      _store.write(serverBaseUrlKey, value);

  Future<String> clientInstanceId() async {
    final existing = await _store.read(clientInstanceIdKey);
    if (existing != null && _isUuidV4(existing)) {
      return existing;
    }
    final generated = _uuidV4();
    await _store.write(clientInstanceIdKey, generated);
    return generated;
  }

  String _uuidV4() {
    final bytes = List<int>.generate(16, (_) => _random.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex =
        bytes.map((value) => value.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
        '${hex.substring(12, 16)}-${hex.substring(16, 20)}-'
        '${hex.substring(20)}';
  }

  static bool _isUuidV4(String value) => RegExp(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$',
  ).hasMatch(value);
}
