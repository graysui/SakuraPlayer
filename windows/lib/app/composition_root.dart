import 'dart:async';

import 'package:flutter/widgets.dart' hide SnapshotController;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/events/app_lifecycle.dart';
import 'package:sakuraplayer_windows/core/events/event_client.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
import 'package:sakuraplayer_windows/core/images/gfriends_cache.dart';
import 'package:sakuraplayer_windows/features/auth/domain/auth_session_state.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';

class SakuraPlayerCompositionRoot extends ConsumerStatefulWidget {
  const SakuraPlayerCompositionRoot({required this.child, super.key});

  final Widget child;

  @override
  ConsumerState<SakuraPlayerCompositionRoot> createState() =>
      _SakuraPlayerCompositionRootState();
}

class _SakuraPlayerCompositionRootState
    extends ConsumerState<SakuraPlayerCompositionRoot> {
  ProviderSubscription<AuthSessionState>? _authSubscription;
  EventClient? _events;
  AppLifecycleCoordinator? _lifecycle;
  SnapshotController? _snapshots;
  VoidCallback? _snapshotListener;

  @override
  void initState() {
    super.initState();
    ref.read(runtimeResetProvider).register(_resetRuntime);
    ref.read(privateCacheResetProvider).register(_clearPrivateCaches);
    _authSubscription = ref.listenManual<AuthSessionState>(
      authControllerProvider,
      (_, next) => _onAuthChanged(next),
      fireImmediately: true,
    );
    unawaited(ref.read(authControllerProvider.notifier).initialize());
  }

  Future<void> _onAuthChanged(AuthSessionState auth) async {
    if (!auth.isAuthenticated) {
      await _resetRuntime();
      return;
    }
    if (_events != null) return;
    final api = ref.read(authControllerProvider.notifier).apiClient;
    final server = auth.serverBaseUri;
    if (api == null || server == null) return;
    final snapshots = SnapshotController(
      loadSnapshot: api.eventSnapshot,
      notifications: NotificationCoordinator(
        sink: const NoopAppNotificationSink(),
        markRead: api.markNotificationRead,
      ),
    );
    void publishSnapshot() {
      ref.read(snapshotStateProvider.notifier).replace(snapshots.state);
    }

    snapshots.addListener(publishSnapshot);
    final events = EventClient(
      serverBaseUri: server,
      accessToken: () => ref.read(sessionStoreProvider).accessToken,
      reauthenticate: api.refreshSession,
      snapshots: snapshots,
    );
    final lifecycle = AppLifecycleCoordinator(
      onVisibilityChanged: events.handleVisibility,
    )..register();
    _events = events;
    _lifecycle = lifecycle;
    _snapshots = snapshots;
    _snapshotListener = publishSnapshot;
    try {
      await events.start();
    } on Exception {
      // A later foreground transition retries snapshot and connection recovery.
    }
  }

  Future<void> _resetRuntime() async {
    _lifecycle?.unregister();
    _lifecycle = null;
    final events = _events;
    _events = null;
    await events?.dispose();
    final snapshots = _snapshots;
    final listener = _snapshotListener;
    _snapshots = null;
    _snapshotListener = null;
    if (listener != null) snapshots?.removeListener(listener);
    snapshots?.dispose();
    ref.read(snapshotStateProvider.notifier).clear();
  }

  Future<void> _clearPrivateCaches() async {
    await ref.read(gfriendsCacheProvider).clear();
  }

  @override
  void dispose() {
    ref.read(runtimeResetProvider).unregister(_resetRuntime);
    ref.read(privateCacheResetProvider).unregister(_clearPrivateCaches);
    _authSubscription?.close();
    unawaited(_resetRuntime());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
