import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';

enum AppVisibility { foreground, background, detached }

abstract interface class AppNotificationSink {
  Future<bool> show(NotificationDto notification);
}

class NoopAppNotificationSink implements AppNotificationSink {
  const NoopAppNotificationSink();

  @override
  Future<bool> show(NotificationDto notification) async => false;
}

class AppLifecycleCoordinator with WidgetsBindingObserver {
  AppLifecycleCoordinator({required this.onVisibilityChanged});

  final Future<void> Function(AppVisibility visibility) onVisibilityChanged;
  bool _registered = false;
  AppVisibility _visibility = AppVisibility.foreground;

  AppVisibility get visibility => _visibility;
  bool get isRegistered => _registered;

  void register() {
    if (_registered) return;
    WidgetsBinding.instance.addObserver(this);
    _registered = true;
  }

  void unregister() {
    if (!_registered) return;
    WidgetsBinding.instance.removeObserver(this);
    _registered = false;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final next = switch (state) {
      AppLifecycleState.resumed => AppVisibility.foreground,
      AppLifecycleState.detached => AppVisibility.detached,
      _ => AppVisibility.background,
    };
    if (next == _visibility) return;
    _visibility = next;
    unawaited(_notify(next));
  }

  Future<void> _notify(AppVisibility next) async {
    try {
      await onVisibilityChanged(next);
    } on Exception {
      // Foreground recovery will retry on the next lifecycle transition.
    }
  }
}

class NotificationCoordinator {
  NotificationCoordinator({
    required AppNotificationSink sink,
    required Future<NotificationDto> Function(String id) markRead,
  }) : _sink = sink,
       _markRead = markRead;

  final AppNotificationSink _sink;
  final Future<NotificationDto> Function(String id) _markRead;
  final Set<String> _inFlight = <String>{};

  Future<NotificationDto?> deliver(NotificationDto notification) async {
    if (notification.readAt != null || !_inFlight.add(notification.id)) {
      return null;
    }
    try {
      final shown = await _sink.show(notification);
      if (!shown) return null;
      return await _markRead(notification.id);
    } on Exception {
      return null;
    } finally {
      _inFlight.remove(notification.id);
    }
  }
}
