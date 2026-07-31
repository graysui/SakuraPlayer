import 'dart:async';

class ThrottlingPlayer {
  ThrottlingPlayer(this._performSeek);

  final Future<void> Function(Duration target) _performSeek;
  Duration? _pending;
  Future<void>? _active;
  bool _disposed = false;

  Future<void> seek(Duration target) {
    if (_disposed) return Future<void>.error(StateError('player is disposed'));
    _pending = target < Duration.zero ? Duration.zero : target;
    final active = _active;
    if (active != null) return active;
    final operation = _drain();
    _active = operation;
    unawaited(
      operation.then<void>(
        (_) => _clear(operation),
        onError: (Object _, StackTrace __) => _clear(operation),
      ),
    );
    return operation;
  }

  Future<void> _drain() async {
    try {
      while (_pending != null && !_disposed) {
        final target = _pending!;
        _pending = null;
        await _performSeek(target);
      }
    } catch (_) {
      _pending = null;
      rethrow;
    }
  }

  void _clear(Future<void> operation) {
    if (identical(_active, operation)) _active = null;
  }

  void dispose() {
    _disposed = true;
    _pending = null;
  }
}
