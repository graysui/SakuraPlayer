import 'package:flutter/foundation.dart';

enum AuthSessionStatus {
  initializing,
  serverRequired,
  unauthenticated,
  authenticated,
}

@immutable
class AuthSessionState {
  const AuthSessionState({
    required this.status,
    this.serverBaseUri,
    this.bootstrapRequired = false,
    this.busy = false,
    this.errorCode,
    this.errorMessage,
  });

  const AuthSessionState.initializing()
    : this(status: AuthSessionStatus.initializing, busy: true);

  const AuthSessionState.serverRequired()
    : this(status: AuthSessionStatus.serverRequired);

  const AuthSessionState.unauthenticated({
    required Uri serverBaseUri,
    required bool bootstrapRequired,
    bool busy = false,
    String? errorCode,
    String? errorMessage,
  }) : this(
         status: AuthSessionStatus.unauthenticated,
         serverBaseUri: serverBaseUri,
         bootstrapRequired: bootstrapRequired,
         busy: busy,
         errorCode: errorCode,
         errorMessage: errorMessage,
       );

  const AuthSessionState.authenticated({required Uri serverBaseUri})
    : this(
        status: AuthSessionStatus.authenticated,
        serverBaseUri: serverBaseUri,
      );

  final AuthSessionStatus status;
  final Uri? serverBaseUri;
  final bool bootstrapRequired;
  final bool busy;
  final String? errorCode;
  final String? errorMessage;

  bool get isAuthenticated => status == AuthSessionStatus.authenticated;

  AuthSessionState copyWith({
    bool? busy,
    String? errorCode,
    String? errorMessage,
    bool clearError = false,
  }) => AuthSessionState(
    status: status,
    serverBaseUri: serverBaseUri,
    bootstrapRequired: bootstrapRequired,
    busy: busy ?? this.busy,
    errorCode: clearError ? null : errorCode ?? this.errorCode,
    errorMessage: clearError ? null : errorMessage ?? this.errorMessage,
  );
}
