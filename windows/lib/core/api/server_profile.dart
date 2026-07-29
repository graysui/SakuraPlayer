import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/auth/session_store.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';

class ServerAddressException implements Exception {
  const ServerAddressException(this.code, this.message);

  final String code;
  final String message;

  @override
  String toString() => 'ServerAddressException($code)';
}

@immutable
class ServerProfile {
  const ServerProfile(this.baseUri);

  final Uri baseUri;
}

class ServerAddressPolicy {
  const ServerAddressPolicy();

  ServerProfile normalize(String input, {bool allowPrivateHttp = false}) {
    final trimmed = input.trim();
    final uri = Uri.tryParse(trimmed);
    if (uri == null || !uri.isAbsolute || uri.host.isEmpty) {
      throw const ServerAddressException(
        'server_url_invalid',
        '请输入完整的服务端地址，例如 https://server.example。',
      );
    }
    final scheme = uri.scheme.toLowerCase();
    if (scheme != 'http' && scheme != 'https') {
      throw const ServerAddressException(
        'server_scheme_invalid',
        '服务端地址只能使用 HTTPS 或受限的 HTTP。',
      );
    }
    if (uri.userInfo.isNotEmpty || uri.hasQuery || uri.hasFragment) {
      throw const ServerAddressException(
        'server_url_components_forbidden',
        '服务端地址不能包含账号、查询参数或片段。',
      );
    }
    if (uri.path.isNotEmpty && uri.path != '/') {
      throw const ServerAddressException(
        'server_url_path_forbidden',
        '服务端地址不能包含路径。',
      );
    }
    final host = uri.host.toLowerCase();
    if (scheme == 'http' && !_isLoopback(host)) {
      if (!_isPrivateLiteral(host)) {
        throw const ServerAddressException(
          'public_http_forbidden',
          '公网或无法确认是私网的地址必须使用 HTTPS。',
        );
      }
      if (!allowPrivateHttp) {
        throw const ServerAddressException(
          'private_http_confirmation_required',
          '私网明文 HTTP 有泄露风险，需要明确确认后才能使用。',
        );
      }
    }
    final normalized = Uri(
      scheme: scheme,
      host: host,
      port: uri.hasPort ? uri.port : null,
    );
    return ServerProfile(normalized);
  }

  static bool _isLoopback(String host) {
    if (host == 'localhost') return true;
    final address = InternetAddress.tryParse(host);
    if (address == null) return false;
    final bytes = address.rawAddress;
    if (address.type == InternetAddressType.IPv4) {
      return bytes[0] == 127;
    }
    return bytes.take(15).every((value) => value == 0) && bytes[15] == 1;
  }

  static bool _isPrivateLiteral(String host) {
    final address = InternetAddress.tryParse(host);
    if (address == null) return false;
    final bytes = address.rawAddress;
    if (address.type == InternetAddressType.IPv4) {
      final first = bytes[0];
      final second = bytes[1];
      return first == 10 ||
          (first == 172 && second >= 16 && second <= 31) ||
          (first == 192 && second == 168) ||
          (first == 169 && second == 254);
    }
    final isUniqueLocal = (bytes[0] & 0xfe) == 0xfc;
    final isLinkLocal = bytes[0] == 0xfe && (bytes[1] & 0xc0) == 0x80;
    return isUniqueLocal || isLinkLocal;
  }
}

class ServerProfileRepository {
  const ServerProfileRepository(this._secureStore, this._policy);

  final SecureStore _secureStore;
  final ServerAddressPolicy _policy;

  Future<ServerProfile?> load() async {
    final value = await _secureStore.readServerBaseUrl();
    return value == null
        ? null
        : _policy.normalize(value, allowPrivateHttp: true);
  }

  Future<void> save(ServerProfile profile) =>
      _secureStore.writeServerBaseUrl(profile.baseUri.toString());
}

abstract interface class ServerProbe {
  Future<BootstrapStatus> test(ServerProfile profile);
}

class ServerConnectionTester implements ServerProbe {
  const ServerConnectionTester();

  @override
  Future<BootstrapStatus> test(ServerProfile profile) async {
    final scratchSecure = SecureStore(MemorySecureKeyValueStore());
    final session = SessionStore(scratchSecure);
    final dio = Dio(BaseOptions(baseUrl: '${profile.baseUri}/api/v1/'));
    return ApiClient(dio: dio, sessionStore: session).bootstrapStatus();
  }
}
