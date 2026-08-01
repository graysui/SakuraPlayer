import 'dart:async';
import 'dart:isolate';
import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_secure_storage_windows/flutter_secure_storage_windows.dart';
import 'package:flutter/services.dart';

abstract interface class SecureKeyValueStore {
  Future<String?> read(String key);

  Future<void> write(String key, String value);

  Future<void> delete(String key);
}

enum SecureStorageOperation { read, write, delete }

typedef SecureStorageWorkerRunner =
    Future<Object?> Function(
      SecureStorageOperation operation,
      String key,
      String? value,
    );

class FlutterSecureKeyValueStore implements SecureKeyValueStore {
  FlutterSecureKeyValueStore({
    FlutterSecureStorage? storage,
    SecureStorageWorkerRunner? workerRunner,
    this.operationTimeout = const Duration(seconds: 5),
  }) : _storage = storage,
       _workerRunner = workerRunner;

  final FlutterSecureStorage? _storage;
  final SecureStorageWorkerRunner? _workerRunner;
  final Duration operationTimeout;

  @override
  Future<String?> read(String key) async =>
      await _perform(SecureStorageOperation.read, key, null) as String?;

  @override
  Future<void> write(String key, String value) async {
    await _perform(SecureStorageOperation.write, key, value);
  }

  @override
  Future<void> delete(String key) async {
    await _perform(SecureStorageOperation.delete, key, null);
  }

  Future<Object?> _perform(
    SecureStorageOperation operation,
    String key,
    String? value,
  ) {
    final storage = _storage;
    final workerRunner = _workerRunner;
    final operationFuture =
        storage != null
            ? _performWithStorage(storage, operation, key, value)
            : workerRunner != null
            ? workerRunner(operation, key, value)
            : _performInIsolate(operation, key, value);
    return operationFuture.timeout(operationTimeout);
  }

  static Future<Object?> _performWithStorage(
    FlutterSecureStorage storage,
    SecureStorageOperation operation,
    String key,
    String? value,
  ) => switch (operation) {
    SecureStorageOperation.read => storage.read(key: key),
    SecureStorageOperation.write => storage.write(key: key, value: value!),
    SecureStorageOperation.delete => storage.delete(key: key),
  };

  Future<Object?> _performInIsolate(
    SecureStorageOperation operation,
    String key,
    String? value,
  ) async {
    final rootToken = RootIsolateToken.instance;
    if (rootToken == null) {
      throw StateError('root isolate token is unavailable');
    }
    final responsePort = ReceivePort();
    final errorPort = ReceivePort();
    final result = Completer<Object?>();
    final responseSubscription = responsePort.listen((message) {
      if (result.isCompleted) return;
      if (message is List<Object?> && message.firstOrNull == true) {
        result.complete(message.length > 1 ? message[1] : null);
      } else {
        result.completeError(const SecureStorageWorkerException());
      }
    });
    final errorSubscription = errorPort.listen((_) {
      if (!result.isCompleted) {
        result.completeError(const SecureStorageWorkerException());
      }
    });
    final isolate = await Isolate.spawn<List<Object?>>(
      _secureStorageWorker,
      <Object?>[rootToken, responsePort.sendPort, operation.index, key, value],
      onError: errorPort.sendPort,
      errorsAreFatal: true,
    );
    try {
      return await result.future.timeout(operationTimeout);
    } finally {
      isolate.kill(priority: Isolate.immediate);
      await responseSubscription.cancel();
      await errorSubscription.cancel();
      responsePort.close();
      errorPort.close();
    }
  }
}

class SecureStorageWorkerException implements Exception {
  const SecureStorageWorkerException();
}

@pragma('vm:entry-point')
Future<void> _secureStorageWorker(List<Object?> request) async {
  final rootToken = request[0] as RootIsolateToken;
  final responsePort = request[1] as SendPort;
  final operation = SecureStorageOperation.values[request[2] as int];
  final key = request[3] as String;
  final value = request[4] as String?;
  try {
    BackgroundIsolateBinaryMessenger.ensureInitialized(rootToken);
    final storage = FlutterSecureStorageWindows();
    const options = <String, String>{'useBackwardCompatibility': 'false'};
    Object? result;
    switch (operation) {
      case SecureStorageOperation.read:
        result = await storage.read(key: key, options: options);
        break;
      case SecureStorageOperation.write:
        await storage.write(key: key, value: value!, options: options);
        break;
      case SecureStorageOperation.delete:
        await storage.delete(key: key, options: options);
        break;
    }
    responsePort.send(<Object?>[true, result]);
  } catch (_) {
    responsePort.send(<Object?>[false]);
  }
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
