import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/app_lifecycle.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';

abstract interface class EventConnection {
  Stream<Object?> get messages;
  int? get closeCode;

  void send(Object message);

  Future<void> close();
}

abstract interface class EventConnector {
  Future<EventConnection> connect(Uri uri, {required String accessToken});
}

class IoEventConnector implements EventConnector {
  const IoEventConnector();

  @override
  Future<EventConnection> connect(
    Uri uri, {
    required String accessToken,
  }) async => _IoEventConnection(
    await WebSocket.connect(
      uri.toString(),
      headers: <String, Object?>{'Authorization': 'Bearer $accessToken'},
    ),
  );
}

class _IoEventConnection implements EventConnection {
  const _IoEventConnection(this._socket);

  final WebSocket _socket;

  @override
  Stream<Object?> get messages => _socket;

  @override
  int? get closeCode => _socket.closeCode;

  @override
  void send(Object message) => _socket.add(message);

  @override
  Future<void> close() async {
    await _socket.close();
  }
}

class EventClient {
  EventClient({
    required Uri serverBaseUri,
    required String? Function() accessToken,
    required Future<void> Function() reauthenticate,
    required SnapshotController snapshots,
    EventConnector connector = const IoEventConnector(),
    Duration reconnectDelay = const Duration(seconds: 1),
    Duration pingInterval = const Duration(seconds: 30),
  }) : _serverBaseUri = serverBaseUri,
       _accessToken = accessToken,
       _reauthenticate = reauthenticate,
       _snapshots = snapshots,
       _connector = connector,
       _reconnectDelay = reconnectDelay,
       _pingInterval = pingInterval;

  final Uri _serverBaseUri;
  final String? Function() _accessToken;
  final Future<void> Function() _reauthenticate;
  final SnapshotController _snapshots;
  final EventConnector _connector;
  final Duration _reconnectDelay;
  final Duration _pingInterval;
  EventConnection? _connection;
  StreamSubscription<Object?>? _subscription;
  Timer? _pingTimer;
  Timer? _reconnectTimer;
  bool _disposed = false;
  bool _connecting = false;

  bool get isConnected => _connection != null;

  Future<void> start() async {
    if (_disposed) throw StateError('event client is disposed');
    await _snapshots.recover();
    await _connect();
  }

  Future<void> handleVisibility(AppVisibility visibility) async {
    switch (visibility) {
      case AppVisibility.foreground:
        await _snapshots.recover();
        await _connect();
      case AppVisibility.background:
        // Keep the in-process connection so the platform adapter can notify.
        return;
      case AppVisibility.detached:
        await dispose();
    }
  }

  Future<void> _connect() async {
    if (_disposed || _connecting || _connection != null) return;
    final token = _accessToken();
    if (token == null) return;
    _connecting = true;
    try {
      final connection = await _connector.connect(
        _webSocketUri(_serverBaseUri),
        accessToken: token,
      );
      if (_disposed) {
        await connection.close();
        return;
      }
      _connection = connection;
      _subscription = connection.messages.listen(
        _onMessage,
        onError: (Object _) => _onClosed(),
        onDone: _onClosed,
        cancelOnError: true,
      );
      _pingTimer = Timer.periodic(_pingInterval, (_) {
        final active = _connection;
        if (active == null) return;
        active.send(
          jsonEncode(<String, Object?>{
            'type': 'ping',
            'sent_at': DateTime.now().toUtc().toIso8601String(),
          }),
        );
      });
    } on Exception {
      if (!_disposed) _scheduleReconnect(null);
    } finally {
      _connecting = false;
    }
  }

  Future<void> _onMessage(Object? raw) async {
    if (raw is! String) {
      await _snapshots.recover();
      return;
    }
    late EventEnvelope event;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) {
        throw const FormatException('event must be an object');
      }
      final json = Map<String, Object?>.from(decoded);
      if (json['type'] == 'pong') return;
      event = EventEnvelope.fromJson(json);
    } on FormatException {
      await _snapshots.recover();
      return;
    } on ProtocolException {
      await _snapshots.recover();
      return;
    } on TypeError {
      await _snapshots.recover();
      return;
    }
    await _snapshots.apply(event);
  }

  void _onClosed() {
    final closeCode = _connection?.closeCode;
    _connection = null;
    _subscription = null;
    _pingTimer?.cancel();
    _pingTimer = null;
    if (_disposed) return;
    _scheduleReconnect(closeCode);
  }

  void _scheduleReconnect(int? closeCode) {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(_reconnectDelay, () async {
      if (_disposed) return;
      try {
        if (closeCode == 4401 || closeCode == 4403) {
          await _reauthenticate();
        }
        await _snapshots.recover();
        await _connect();
      } on Exception {
        if (!_disposed) {
          _scheduleReconnect(null);
        }
      }
    });
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    _reconnectTimer?.cancel();
    _pingTimer?.cancel();
    await _subscription?.cancel();
    await _connection?.close();
    _subscription = null;
    _connection = null;
  }

  static Uri _webSocketUri(Uri baseUri) => baseUri.replace(
    scheme: baseUri.scheme == 'https' ? 'wss' : 'ws',
    path: '/api/v1/events/ws',
    query: null,
    fragment: null,
  );
}
