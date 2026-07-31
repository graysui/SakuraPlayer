import 'dart:async';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/app_lifecycle.dart';

abstract interface class CacheToastPort {
  Future<void> initialize(void Function(String? payload) onActivated);

  Future<void> show({
    required int id,
    required String title,
    required String body,
    required String payload,
  });
}

class FlutterLocalNotificationsCacheToastPort implements CacheToastPort {
  FlutterLocalNotificationsCacheToastPort({
    FlutterLocalNotificationsPlugin? plugin,
  }) : _plugin = plugin ?? FlutterLocalNotificationsPlugin();

  final FlutterLocalNotificationsPlugin _plugin;

  @override
  Future<void> initialize(void Function(String? payload) onActivated) async {
    final initialized = await _plugin.initialize(
      const InitializationSettings(
        windows: WindowsInitializationSettings(
          appName: 'SakuraPlayer',
          appUserModelId: 'SakuraPlayer.Desktop.Client.1',
          guid: '8D0CF8F7-2C68-4D86-AC8F-F5810CCDF9C1',
        ),
      ),
      onDidReceiveNotificationResponse:
          (response) => onActivated(response.payload),
    );
    if (initialized != true) {
      throw StateError('Windows notifications could not be initialized');
    }
    final launch = await _plugin.getNotificationAppLaunchDetails();
    if (launch?.didNotificationLaunchApp == true) {
      onActivated(launch?.notificationResponse?.payload);
    }
  }

  @override
  Future<void> show({
    required int id,
    required String title,
    required String body,
    required String payload,
  }) => _plugin.show(
    id,
    title,
    body,
    const NotificationDetails(windows: WindowsNotificationDetails()),
    payload: payload,
  );
}

final cacheToastPortProvider = Provider<CacheToastPort>(
  (ref) => FlutterLocalNotificationsCacheToastPort(),
);

class WindowsCacheNotificationSink implements AppNotificationSink {
  WindowsCacheNotificationSink({
    required CacheToastPort port,
    required void Function() onOpenCache,
  }) : _port = port,
       _onOpenCache = onOpenCache;

  final CacheToastPort _port;
  final void Function() _onOpenCache;
  Future<void>? _initialization;

  @override
  Future<bool> show(NotificationDto notification) async {
    try {
      await (_initialization ??= _port.initialize(_onActivated));
      final content = CacheNotificationContent.from(notification);
      await _port.show(
        id: _stableNotificationId(notification.id),
        title: content.title,
        body: content.body,
        payload: notification.id,
      );
      return true;
    } catch (_) {
      _initialization = null;
      return false;
    }
  }

  void _onActivated(String? payload) {
    if (payload == null || !isValidUuid(payload)) return;
    _onOpenCache();
  }
}

class CacheNotificationContent {
  const CacheNotificationContent({required this.title, required this.body});

  factory CacheNotificationContent.from(NotificationDto notification) {
    final base = switch (notification.type) {
      'cache_started' => const CacheNotificationContent(
        title: '缓存任务开始',
        body: '任务正在后台处理，不会自动播放',
      ),
      'cache_ready' => const CacheNotificationContent(
        title: '缓存已就绪',
        body: '可在缓存页查看并播放',
      ),
      'cache_failed' => const CacheNotificationContent(
        title: '缓存任务失败',
        body: '可在缓存页查看失败原因',
      ),
      'credential_expired' => const CacheNotificationContent(
        title: '115 凭据已失效',
        body: '请在设置中重新扫码',
      ),
      _ => throw const ProtocolException('unknown notification type'),
    };
    final errorCode = notification.errorCode;
    if (errorCode == null || !RegExp(r'^[a-z0-9_]+$').hasMatch(errorCode)) {
      return base;
    }
    return CacheNotificationContent(
      title: base.title,
      body: '${base.body}（$errorCode）',
    );
  }

  final String title;
  final String body;
}

int _stableNotificationId(String uuid) {
  var hash = 0x811c9dc5;
  for (final codeUnit in uuid.codeUnits) {
    hash ^= codeUnit;
    hash = (hash * 0x01000193) & 0x7fffffff;
  }
  return hash;
}
