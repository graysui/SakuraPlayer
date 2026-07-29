import 'dart:async';

import 'package:flutter/widgets.dart' hide SnapshotController;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/events/app_lifecycle.dart';
import 'package:sakuraplayer_windows/core/events/event_client.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
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

  @override
  void initState() {
    super.initState();
    ref.read(runtimeResetProvider).register(_resetRuntime);
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
  }

  @override
  void dispose() {
    ref.read(runtimeResetProvider).unregister(_resetRuntime);
    _authSubscription?.close();
    unawaited(_resetRuntime());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
