import 'dart:async';

import 'package:dio/dio.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/auth/session_store.dart';

class ApiException implements Exception {
  const ApiException({
    required this.code,
    required this.message,
    this.statusCode,
    this.requestId,
    this.details,
  });

  final String code;
  final String message;
  final int? statusCode;
  final String? requestId;
  final Map<String, Object?>? details;

  @override
  String toString() => 'ApiException($code)';
}

class ApiClient {
  ApiClient({required Dio dio, required SessionStore sessionStore})
    : _dio = dio,
      _sessionStore = sessionStore {
    _dio.options
      ..connectTimeout = const Duration(seconds: 10)
      ..receiveTimeout = const Duration(seconds: 30)
      ..sendTimeout = const Duration(seconds: 30)
      ..validateStatus = (status) {
        return status != null && status < 600;
      }
      ..headers['Accept'] = 'application/json';
  }

  factory ApiClient.forServer({
    required Uri baseUri,
    required SessionStore sessionStore,
  }) => ApiClient(
    dio: Dio(BaseOptions(baseUrl: '${baseUri.toString()}/api/v1/')),
    sessionStore: sessionStore,
  );

  final Dio _dio;
  final SessionStore _sessionStore;
  Future<void>? _refreshInFlight;

  Future<BootstrapStatus> bootstrapStatus() async {
    final json = await _jsonRequest(
      'GET',
      'auth/bootstrap-status',
      auth: false,
    );
    return _parseDto(json, BootstrapStatus.fromJson);
  }

  Future<TokenPair> login({
    required String username,
    required String password,
    required String clientInstanceId,
  }) async {
    final json = await _jsonRequest(
      'POST',
      'auth/login',
      auth: false,
      data: <String, Object?>{
        'username': username,
        'password': password,
        'client_instance_id': clientInstanceId,
      },
    );
    final tokens = _parseDto(json, TokenPair.fromJson);
    await _sessionStore.setTokens(tokens);
    return tokens;
  }

  Future<TokenPair> bootstrap({
    required String username,
    required String password,
    required String clientInstanceId,
    required String bootstrapToken,
  }) async {
    final json = await _jsonRequest(
      'POST',
      'auth/bootstrap',
      auth: false,
      headers: <String, Object?>{'X-Bootstrap-Token': bootstrapToken},
      data: <String, Object?>{
        'username': username,
        'password': password,
        'client_instance_id': clientInstanceId,
      },
    );
    final tokens = _parseDto(json, TokenPair.fromJson);
    await _sessionStore.setTokens(tokens);
    return tokens;
  }

  Future<void> refreshSession() => _singleFlightRefresh();

  Future<void> logout() async {
    await _emptyRequest('POST', 'auth/logout', auth: true, allowRefresh: false);
  }

  Future<EventSnapshotDto> eventSnapshot() async {
    final json = await _jsonRequest('GET', 'events/snapshot');
    return _parseDto(json, EventSnapshotDto.fromJson);
  }

  Future<NotificationDto> markNotificationRead(String notificationId) async {
    _requireUuidPathSegment(notificationId);
    final json = await _jsonRequest(
      'PUT',
      'notifications/$notificationId/read',
    );
    return _parseDto(json, NotificationDto.fromJson);
  }

  Future<T> get<T>(
    String path, {
    Map<String, Object?>? query,
    required T Function(Map<String, Object?> json) decode,
  }) async => _parseDto(await _jsonRequest('GET', path, query: query), decode);

  Future<T> post<T>(
    String path, {
    Map<String, Object?>? data,
    Map<String, Object?>? query,
    required T Function(Map<String, Object?> json) decode,
  }) async => _parseDto(
    await _jsonRequest('POST', path, data: data, query: query),
    decode,
  );

  Future<T> put<T>(
    String path, {
    Map<String, Object?>? data,
    Map<String, Object?>? query,
    required T Function(Map<String, Object?> json) decode,
  }) async => _parseDto(
    await _jsonRequest('PUT', path, data: data, query: query),
    decode,
  );

  Future<List<int>> getBytes(String path, {Map<String, Object?>? query}) async {
    final response = await _request(
      'GET',
      path,
      query: query,
      responseType: ResponseType.bytes,
    );
    final data = response.data;
    if (data is! List<int>) {
      throw const ApiException(
        code: 'client_protocol_error',
        message: 'The server returned an invalid byte response.',
      );
    }
    return List<int>.unmodifiable(data);
  }

  Future<Map<String, Object?>> _jsonRequest(
    String method,
    String path, {
    bool auth = true,
    bool allowRefresh = true,
    Map<String, Object?>? data,
    Map<String, Object?>? query,
    Map<String, Object?>? headers,
  }) async {
    final response = await _request(
      method,
      path,
      auth: auth,
      allowRefresh: allowRefresh,
      data: data,
      query: query,
      headers: headers,
    );
    return _asJsonObject(response.data);
  }

  Future<void> _emptyRequest(
    String method,
    String path, {
    required bool auth,
    required bool allowRefresh,
  }) async {
    await _request(method, path, auth: auth, allowRefresh: allowRefresh);
  }

  Future<Response<Object?>> _request(
    String method,
    String path, {
    bool auth = true,
    bool allowRefresh = true,
    Map<String, Object?>? data,
    Map<String, Object?>? query,
    Map<String, Object?>? headers,
    ResponseType responseType = ResponseType.json,
  }) async {
    _validateRelativePath(path);
    final failedAccessToken = auth ? _sessionStore.accessToken : null;
    Response<Object?> response = await _send(
      method,
      path,
      auth: auth,
      data: data,
      query: query,
      headers: headers,
      responseType: responseType,
    );
    if (response.statusCode == 401 && auth && allowRefresh) {
      final currentAccessToken = _sessionStore.accessToken;
      if (currentAccessToken == null ||
          currentAccessToken == failedAccessToken) {
        await _singleFlightRefresh();
      }
      response = await _send(
        method,
        path,
        auth: true,
        data: data,
        query: query,
        headers: headers,
        responseType: responseType,
      );
    }
    _throwForError(response);
    return response;
  }

  Future<Response<Object?>> _send(
    String method,
    String path, {
    required bool auth,
    Map<String, Object?>? data,
    Map<String, Object?>? query,
    Map<String, Object?>? headers,
    required ResponseType responseType,
  }) async {
    final requestHeaders = <String, Object?>{...?headers};
    if (auth) {
      final accessToken = _sessionStore.accessToken;
      if (accessToken == null) {
        throw const ApiException(
          code: 'authentication_required',
          message: 'Authentication is required.',
          statusCode: 401,
        );
      }
      requestHeaders['Authorization'] = 'Bearer $accessToken';
    }
    try {
      return await _dio.request<Object?>(
        path,
        data: data,
        queryParameters: query,
        options: Options(
          method: method,
          headers: requestHeaders,
          responseType: responseType,
        ),
      );
    } on DioException catch (error) {
      final isTls = error.error.toString().toLowerCase().contains(
        'certificate',
      );
      throw ApiException(
        code: isTls ? 'client_tls_error' : 'client_transport_error',
        message:
            isTls
                ? 'The server certificate could not be verified.'
                : 'The server could not be reached.',
      );
    }
  }

  Future<void> _singleFlightRefresh() {
    final active = _refreshInFlight;
    if (active != null) return active;
    final operation = _performRefresh();
    _refreshInFlight = operation;
    void clearInFlight() {
      if (identical(_refreshInFlight, operation)) {
        _refreshInFlight = null;
      }
    }

    unawaited(
      operation.then<void>(
        (_) => clearInFlight(),
        onError: (Object _, StackTrace __) => clearInFlight(),
      ),
    );
    return operation;
  }

  Future<void> _performRefresh() async {
    final refreshToken = await _sessionStore.readRefreshToken();
    if (refreshToken == null) {
      await _sessionStore.clearTokens();
      throw const ApiException(
        code: 'refresh_invalid',
        message: 'The refresh session is unavailable.',
        statusCode: 401,
      );
    }
    try {
      final response = await _send(
        'POST',
        'auth/refresh',
        auth: false,
        data: <String, Object?>{'refresh_token': refreshToken},
        responseType: ResponseType.json,
      );
      _throwForError(response);
      await _sessionStore.setTokens(
        _parseDto(_asJsonObject(response.data), TokenPair.fromJson),
      );
    } on Exception {
      await _sessionStore.clearTokens();
      rethrow;
    }
  }

  static Map<String, Object?> _asJsonObject(Object? value) {
    if (value is! Map) {
      throw const ApiException(
        code: 'client_protocol_error',
        message: 'The server returned an invalid JSON response.',
      );
    }
    try {
      return Map<String, Object?>.from(value);
    } on TypeError {
      throw const ApiException(
        code: 'client_protocol_error',
        message: 'The server returned an invalid JSON object.',
      );
    }
  }

  static T _parseDto<T>(
    Map<String, Object?> json,
    T Function(Map<String, Object?> json) decode,
  ) {
    try {
      return decode(json);
    } on ProtocolException {
      throw const ApiException(
        code: 'client_protocol_error',
        message:
            'The server returned data that does not match the API contract.',
      );
    }
  }

  static void _throwForError(Response<Object?> response) {
    final status = response.statusCode ?? 0;
    if (status >= 200 && status < 300) return;
    try {
      final error = ApiErrorBody.fromJson(_asJsonObject(response.data));
      throw ApiException(
        code: error.code,
        message: error.message,
        statusCode: status,
        requestId: error.requestId,
        details: error.details,
      );
    } on ApiException {
      rethrow;
    } on ProtocolException {
      throw ApiException(
        code: 'client_protocol_error',
        message: 'The server returned an invalid error response.',
        statusCode: status,
      );
    }
  }

  static void _validateRelativePath(String path) {
    final uri = Uri.tryParse(path);
    if (uri == null ||
        uri.hasScheme ||
        uri.hasAuthority ||
        path.startsWith('/') ||
        uri.pathSegments.any((segment) => segment == '..')) {
      throw ArgumentError.value(
        path,
        'path',
        'must be a safe relative API path',
      );
    }
  }

  static void _requireUuidPathSegment(String value) {
    if (!RegExp(
      r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$',
    ).hasMatch(value)) {
      throw ArgumentError.value(value, 'value', 'must be a UUID');
    }
  }
}
