import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

enum AuthSessionStatus { unauthenticated, authenticated }

@immutable
class AuthSessionState {
  const AuthSessionState._(this.status);

  const AuthSessionState.unauthenticated()
    : this._(AuthSessionStatus.unauthenticated);

  const AuthSessionState.authenticated()
    : this._(AuthSessionStatus.authenticated);

  final AuthSessionStatus status;

  bool get isAuthenticated => status == AuthSessionStatus.authenticated;
}

final authSessionStateProvider = Provider<AuthSessionState>(
  (ref) => const AuthSessionState.unauthenticated(),
);
