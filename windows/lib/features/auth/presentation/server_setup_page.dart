import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/server_profile.dart';
import 'package:sakuraplayer_windows/features/auth/domain/auth_session_state.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/theme/app_theme.dart';

class ServerSetupPage extends ConsumerStatefulWidget {
  const ServerSetupPage({super.key});

  @override
  ConsumerState<ServerSetupPage> createState() => _ServerSetupPageState();
}

class _ServerSetupPageState extends ConsumerState<ServerSetupPage> {
  final _serverController = TextEditingController();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _bootstrapController = TextEditingController();
  bool _allowPrivateHttp = false;
  bool _obscurePassword = true;
  bool _obscureBootstrap = true;

  @override
  void dispose() {
    _serverController.dispose();
    _usernameController.dispose();
    _passwordController.dispose();
    _bootstrapController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final selectedTheme = ref.watch(appThemeModeProvider);
    if (_serverController.text.isEmpty && auth.serverBaseUri != null) {
      _serverController.text = auth.serverBaseUri.toString();
    }

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: AutofillGroup(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Icon(Icons.video_library_outlined, size: 48),
                    const SizedBox(height: 16),
                    Text(
                      'SakuraPlayer',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 28),
                    TextField(
                      controller: _serverController,
                      enabled:
                          auth.status == AuthSessionStatus.initializing ||
                          !auth.busy,
                      decoration: const InputDecoration(
                        labelText: '服务端地址',
                        hintText: 'https://server.example',
                        prefixIcon: Icon(Icons.dns_outlined),
                      ),
                      keyboardType: TextInputType.url,
                      textInputAction: TextInputAction.done,
                      onSubmitted: auth.busy ? null : (_) => _configureServer(),
                    ),
                    const SizedBox(height: 8),
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _allowPrivateHttp,
                      onChanged:
                          auth.busy
                              ? null
                              : (value) => setState(
                                () => _allowPrivateHttp = value ?? false,
                              ),
                      title: const Text('确认使用私网明文 HTTP'),
                      controlAffinity: ListTileControlAffinity.leading,
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: auth.busy ? null : _configureServer,
                      icon: const Icon(Icons.cable_outlined),
                      label: const Text('测试并保存地址'),
                    ),
                    if (auth.status == AuthSessionStatus.initializing) ...[
                      const SizedBox(height: 24),
                      const Center(child: CircularProgressIndicator()),
                    ],
                    if (auth.serverBaseUri != null &&
                        auth.status != AuthSessionStatus.initializing) ...[
                      const SizedBox(height: 28),
                      TextField(
                        controller: _usernameController,
                        enabled: !auth.busy,
                        autofillHints: const [AutofillHints.username],
                        decoration: const InputDecoration(
                          labelText: '用户名',
                          prefixIcon: Icon(Icons.person_outline),
                        ),
                        textInputAction: TextInputAction.next,
                      ),
                      const SizedBox(height: 16),
                      TextField(
                        controller: _passwordController,
                        enabled: !auth.busy,
                        autofillHints: const [AutofillHints.password],
                        decoration: InputDecoration(
                          labelText: '密码',
                          prefixIcon: const Icon(Icons.lock_outline),
                          suffixIcon: IconButton(
                            onPressed:
                                () => setState(
                                  () => _obscurePassword = !_obscurePassword,
                                ),
                            tooltip: _obscurePassword ? '显示密码' : '隐藏密码',
                            icon: Icon(
                              _obscurePassword
                                  ? Icons.visibility_outlined
                                  : Icons.visibility_off_outlined,
                            ),
                          ),
                        ),
                        obscureText: _obscurePassword,
                        textInputAction:
                            auth.bootstrapRequired
                                ? TextInputAction.next
                                : TextInputAction.done,
                        onSubmitted:
                            auth.bootstrapRequired
                                ? null
                                : (_) => _submitAuth(),
                      ),
                      if (auth.bootstrapRequired) ...[
                        const SizedBox(height: 16),
                        TextField(
                          key: const ValueKey('bootstrap-token-field'),
                          controller: _bootstrapController,
                          enabled: !auth.busy,
                          decoration: InputDecoration(
                            labelText: '一次性初始化口令',
                            prefixIcon: const Icon(Icons.key_outlined),
                            suffixIcon: IconButton(
                              onPressed:
                                  () => setState(
                                    () =>
                                        _obscureBootstrap = !_obscureBootstrap,
                                  ),
                              tooltip:
                                  _obscureBootstrap ? '显示初始化口令' : '隐藏初始化口令',
                              icon: Icon(
                                _obscureBootstrap
                                    ? Icons.visibility_outlined
                                    : Icons.visibility_off_outlined,
                              ),
                            ),
                          ),
                          obscureText: _obscureBootstrap,
                          enableSuggestions: false,
                          autocorrect: false,
                          textInputAction: TextInputAction.done,
                          onSubmitted: (_) => _submitAuth(),
                        ),
                      ],
                      const SizedBox(height: 20),
                      FilledButton.icon(
                        onPressed: auth.busy ? null : _submitAuth,
                        icon: Icon(
                          auth.bootstrapRequired
                              ? Icons.person_add_alt_1_outlined
                              : Icons.login,
                        ),
                        label: Text(auth.bootstrapRequired ? '创建管理员' : '登录'),
                      ),
                    ],
                    if (auth.errorMessage != null) ...[
                      const SizedBox(height: 16),
                      Text(
                        auth.errorMessage!,
                        key: const ValueKey('auth-error'),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ],
                    const SizedBox(height: 28),
                    SegmentedButton<AppThemeMode>(
                      showSelectedIcon: false,
                      segments: const [
                        ButtonSegment(
                          value: AppThemeMode.system,
                          icon: Icon(Icons.brightness_auto_outlined),
                          label: Text('系统'),
                        ),
                        ButtonSegment(
                          value: AppThemeMode.light,
                          icon: Icon(Icons.light_mode_outlined),
                          label: Text('浅色'),
                        ),
                        ButtonSegment(
                          value: AppThemeMode.dark,
                          icon: Icon(Icons.dark_mode_outlined),
                          label: Text('深色'),
                        ),
                      ],
                      selected: {selectedTheme},
                      onSelectionChanged: (selection) {
                        ref
                            .read(appThemeModeProvider.notifier)
                            .setMode(selection.single);
                      },
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _configureServer() async {
    try {
      await ref
          .read(authControllerProvider.notifier)
          .configureServer(
            _serverController.text,
            allowPrivateHttp: _allowPrivateHttp,
          );
    } on ServerAddressException {
      // The controller exposes a safe, user-facing error in state.
    } on ApiException {
      // Transport errors are likewise represented without response payloads.
    }
  }

  Future<void> _submitAuth() async {
    final controller = ref.read(authControllerProvider.notifier);
    final bootstrapRequired =
        ref.read(authControllerProvider).bootstrapRequired;
    final password = _passwordController.text;
    final bootstrapToken = _bootstrapController.text;
    try {
      if (bootstrapRequired) {
        await controller.bootstrap(
          username: _usernameController.text,
          password: password,
          bootstrapToken: bootstrapToken,
        );
      } else {
        await controller.login(
          username: _usernameController.text,
          password: password,
        );
      }
    } on ApiException {
      // Safe error state is rendered by the controller.
    } finally {
      _passwordController.clear();
      _bootstrapController.clear();
    }
  }
}
