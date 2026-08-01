import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/features/settings/data/settings_api.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/qr_binding_controller.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/settings_controller.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/settings_labels.dart';

class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({this.onOpenDiagnostics, super.key});
  final VoidCallback? onOpenDiagnostics;
  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  final _ttl = TextEditingController();
  final _javdbUsername = TextEditingController();
  final _javdbPassword = TextEditingController();
  final _aiBaseUrl = TextEditingController();
  final _aiModel = TextEditingController();
  final _aiTimeout = TextEditingController();
  final _aiApiKey = TextEditingController();
  String? _loadedSignature;
  int _sectionIndex = 0;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 4, vsync: this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(settingsControllerProvider.notifier).load();
      ref.read(qrBindingControllerProvider.notifier).loadBinding();
    });
  }

  @override
  void dispose() {
    _tabs.dispose();
    for (final controller in [
      _ttl,
      _javdbUsername,
      _javdbPassword,
      _aiBaseUrl,
      _aiModel,
      _aiTimeout,
      _aiApiKey,
    ]) {
      controller.clear();
      controller.dispose();
    }
    super.dispose();
  }

  void _syncFields(SettingsDto value) {
    final signature =
        '${value.javdb.version}:${value.ai.version}:${value.cacheTtlHours}';
    if (_loadedSignature == signature) return;
    _loadedSignature = signature;
    _ttl.text = '${value.cacheTtlHours}';
    _javdbUsername.text = value.javdb.username ?? '';
    _javdbPassword.clear();
    _aiBaseUrl.text = value.ai.baseUrl ?? '';
    _aiModel.text = value.ai.model ?? '';
    _aiTimeout.text = '${value.ai.timeoutSeconds ?? 60}';
    _aiApiKey.clear();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(settingsControllerProvider);
    final settings = state.settings;
    if (settings != null) _syncFields(settings);
    return LayoutBuilder(
      builder: (context, constraints) {
        final narrow = constraints.maxWidth < 900;
        final horizontal = narrow ? 16.0 : 24.0;
        final content = _section(context, _sectionIndex, state);
        return Align(
          alignment: Alignment.topLeft,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1280),
            child: Padding(
              padding: EdgeInsets.fromLTRB(horizontal, 16, horizontal, 24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          '管理员设置',
                          style: Theme.of(context).textTheme.headlineSmall,
                        ),
                      ),
                      IconButton(
                        onPressed:
                            state.status == SettingsStatus.loading
                                ? null
                                : ref
                                    .read(settingsControllerProvider.notifier)
                                    .load,
                        tooltip: '刷新设置',
                        icon: const Icon(Icons.refresh),
                      ),
                      IconButton(
                        onPressed: widget.onOpenDiagnostics,
                        tooltip: '诊断与任务',
                        icon: const Icon(Icons.monitor_heart_outlined),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (narrow)
                    TabBar(
                      controller: _tabs,
                      isScrollable: true,
                      onTap: (index) => setState(() => _sectionIndex = index),
                      tabs: const [
                        Tab(text: '115'),
                        Tab(text: '缓存'),
                        Tab(text: '服务'),
                        Tab(text: '同步'),
                      ],
                    ),
                  if (state.errorCode != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        settingsErrorLabel(state.errorCode),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ),
                  const SizedBox(height: 12),
                  Expanded(
                    child:
                        state.status == SettingsStatus.loading &&
                                settings == null
                            ? const Center(child: CircularProgressIndicator())
                            : narrow
                            ? SingleChildScrollView(child: content)
                            : Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                SizedBox(
                                  width: 190,
                                  child: _SideNavigation(
                                    index: _sectionIndex,
                                    onSelected: (index) {
                                      _tabs.index = index;
                                      setState(() => _sectionIndex = index);
                                    },
                                  ),
                                ),
                                const VerticalDivider(width: 32),
                                Expanded(
                                  child: SingleChildScrollView(child: content),
                                ),
                              ],
                            ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _section(BuildContext context, int index, SettingsState state) =>
      switch (index) {
        0 => _Cloud115Section(),
        1 => _CacheSettings(ttl: _ttl, state: state),
        2 => _ProviderSettings(
          state: state,
          javdbUsername: _javdbUsername,
          javdbPassword: _javdbPassword,
          aiBaseUrl: _aiBaseUrl,
          aiModel: _aiModel,
          aiTimeout: _aiTimeout,
          aiApiKey: _aiApiKey,
        ),
        _ => _SyncSettings(settings: state.settings),
      };
}

class _SideNavigation extends StatelessWidget {
  const _SideNavigation({required this.index, required this.onSelected});
  final int index;
  final ValueChanged<int> onSelected;
  @override
  Widget build(BuildContext context) {
    const items = [
      (Icons.qr_code, '115 绑定'),
      (Icons.storage_outlined, '缓存策略'),
      (Icons.settings_ethernet, '服务配置'),
      (Icons.sync, '同步状态'),
    ];
    return Column(
      children: List.generate(items.length, (itemIndex) {
        final item = items[itemIndex];
        return ListTile(
          selected: index == itemIndex,
          leading: Icon(item.$1),
          title: Text(item.$2),
          onTap: () => onSelected(itemIndex),
        );
      }),
    );
  }
}

class _Cloud115Section extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(qrBindingControllerProvider);
    final binding = state.binding;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('115 绑定', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        Text(
          binding == null
              ? '尚未读取绑定状态'
              : '${binding.displayName ?? '未绑定账号'} · ${cloud115BindingStatusLabel(binding.status)}',
        ),
        if (state.errorCode != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              _qrError(state.errorCode!),
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        if (state.imageBytes != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: SizedBox.square(
              dimension: 240,
              child: Image.memory(
                state.imageBytes!,
                key: const ValueKey('qr-image'),
                gaplessPlayback: false,
              ),
            ),
          ),
        if (state.status != null) Text('扫码状态：${qrStatusLabel(state.status!)}'),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            FilledButton.icon(
              onPressed:
                  state.isLoading
                      ? null
                      : state.errorCode == null
                      ? ref.read(qrBindingControllerProvider.notifier).startQr
                      : ref.read(qrBindingControllerProvider.notifier).retry,
              icon: const Icon(Icons.qr_code_scanner),
              label: Text(
                state.errorCode != null
                    ? '重试'
                    : state.status == 'expired' || state.status == 'canceled'
                    ? '重新扫码'
                    : '开始扫码',
              ),
            ),
            if (binding?.bound ?? false)
              OutlinedButton.icon(
                onPressed:
                    state.isLoading ? null : () => _confirmUnbind(context, ref),
                icon: Icon(
                  Icons.link_off,
                  color: Theme.of(context).colorScheme.error,
                ),
                label: const Text('解除绑定'),
              ),
          ],
        ),
      ],
    );
  }
}

class _CacheSettings extends ConsumerWidget {
  const _CacheSettings({required this.ttl, required this.state});
  final TextEditingController ttl;
  final SettingsState state;
  @override
  Widget build(BuildContext context, WidgetRef ref) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text('缓存策略', style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 12),
      Row(
        children: [
          IconButton(
            onPressed: () => _step(ttl, -1),
            tooltip: '减少一小时',
            icon: const Icon(Icons.remove),
          ),
          SizedBox(
            width: 120,
            child: TextField(
              key: const ValueKey('ttl-input'),
              controller: ttl,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                labelText: 'TTL（小时）',
                border: OutlineInputBorder(),
              ),
            ),
          ),
          IconButton(
            onPressed: () => _step(ttl, 1),
            tooltip: '增加一小时',
            icon: const Icon(Icons.add),
          ),
          const SizedBox(width: 8),
          FilledButton.icon(
            onPressed:
                state.inFlight.contains('ttl')
                    ? null
                    : () {
                      final value = int.tryParse(ttl.text);
                      if (value != null && value >= 1 && value <= 168) {
                        ref
                            .read(settingsControllerProvider.notifier)
                            .saveTtl(value);
                      }
                    },
            icon: const Icon(Icons.save_outlined),
            label: const Text('保存'),
          ),
        ],
      ),
      const SizedBox(height: 20),
      const Text('就绪缓存上限：20'),
      const Text('元数据并发：3'),
      const Text('元数据超时：600 秒'),
    ],
  );
}

class _ProviderSettings extends ConsumerWidget {
  const _ProviderSettings({
    required this.state,
    required this.javdbUsername,
    required this.javdbPassword,
    required this.aiBaseUrl,
    required this.aiModel,
    required this.aiTimeout,
    required this.aiApiKey,
  });
  final SettingsState state;
  final TextEditingController javdbUsername,
      javdbPassword,
      aiBaseUrl,
      aiModel,
      aiTimeout,
      aiApiKey;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = state.settings;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('JavDB', style: Theme.of(context).textTheme.titleLarge),
        Text(
          '状态：${settingsStatusLabel(settings?.javdb.status ?? 'unknown')} · ${settingsErrorLabel(settings?.javdb.lastErrorCode)}',
        ),
        Text('密码已配置：${settings?.javdb.passwordConfigured == true ? '是' : '否'}'),
        const SizedBox(height: 8),
        _Field(controller: javdbUsername, label: '用户名'),
        const SizedBox(height: 8),
        _Field(
          controller: javdbPassword,
          label: '新密码',
          secret: true,
          keyValue: 'javdb-password',
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: [
            FilledButton.icon(
              onPressed:
                  state.inFlight.contains('javdb')
                      ? null
                      : () async {
                        await ref
                            .read(settingsControllerProvider.notifier)
                            .replaceJavdb(
                              username: javdbUsername.text,
                              password: javdbPassword.text,
                            );
                        javdbPassword.clear();
                      },
              icon: const Icon(Icons.save_outlined),
              label: const Text('替换配置'),
            ),
            OutlinedButton(
              onPressed:
                  (settings?.javdb.version ?? 0) < 1
                      ? null
                      : () => _confirmClear(
                        context,
                        () =>
                            ref
                                .read(settingsControllerProvider.notifier)
                                .clearJavdb(),
                      ),
              child: const Text('清除'),
            ),
            _TestButton(target: 'javdb'),
          ],
        ),
        const Divider(height: 40),
        Text('AI 翻译', style: Theme.of(context).textTheme.titleLarge),
        Text(
          '状态：${settingsStatusLabel(settings?.ai.status ?? 'unknown')} · ${settingsErrorLabel(settings?.ai.lastErrorCode)}',
        ),
        Text(
          'API key 已配置：${settings?.ai.apiKeyConfigured == true ? '是' : '否'}',
        ),
        const SizedBox(height: 8),
        _Field(controller: aiBaseUrl, label: 'Base URL'),
        const SizedBox(height: 8),
        _Field(controller: aiModel, label: '模型'),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: _Field(
                controller: aiTimeout,
                label: '超时（秒）',
                numeric: true,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _Field(
                controller: aiApiKey,
                label: '新 API key',
                secret: true,
                keyValue: 'ai-api-key',
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: [
            FilledButton.icon(
              onPressed:
                  state.inFlight.contains('ai')
                      ? null
                      : () async {
                        final timeout = int.tryParse(aiTimeout.text);
                        if (timeout == null) return;
                        await ref
                            .read(settingsControllerProvider.notifier)
                            .replaceAi(
                              baseUrl: aiBaseUrl.text,
                              apiKey: aiApiKey.text,
                              model: aiModel.text,
                              timeoutSeconds: timeout,
                            );
                        aiApiKey.clear();
                      },
              icon: const Icon(Icons.save_outlined),
              label: const Text('替换配置'),
            ),
            OutlinedButton(
              onPressed:
                  (settings?.ai.version ?? 0) < 1
                      ? null
                      : () => _confirmClear(
                        context,
                        () =>
                            ref
                                .read(settingsControllerProvider.notifier)
                                .clearAi(),
                      ),
              child: const Text('清除'),
            ),
            _TestButton(target: 'ai'),
          ],
        ),
        const Divider(height: 40),
        Text('连接测试', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (settings != null)
          ...settings.providers.entries.map(
            (entry) => Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Text(
                '${settingsTargetLabel(entry.key)} · ${settingsStatusLabel(entry.value.status)} · ${settingsErrorLabel(entry.value.lastErrorCode)}',
              ),
            ),
          ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children:
              connectionTargets
                  .map((target) => _TestButton(target: target))
                  .toList(),
        ),
        if (state.connectionTests.isNotEmpty) ...[
          const SizedBox(height: 12),
          ...state.connectionTests.values.map(
            (result) => Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Text(
                '${settingsTargetLabel(result.target)} · ${settingsStatusLabel(result.status)} · ${settingsErrorLabel(result.errorCode)} · ${result.elapsedMs} ms · ${_formatTimestamp(result.checkedAt)}',
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _TestButton extends ConsumerWidget {
  const _TestButton({required this.target});
  final String target;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(settingsControllerProvider);
    final result = state.connectionTests[target];
    return OutlinedButton.icon(
      key: ValueKey('connection-test-$target'),
      onPressed:
          state.inFlight.contains('test:$target')
              ? null
              : () => ref
                  .read(settingsControllerProvider.notifier)
                  .testConnection(target),
      icon: const Icon(Icons.network_check),
      label: Text(
        result == null
            ? settingsTargetLabel(target)
            : '${settingsTargetLabel(target)} · ${settingsStatusLabel(result.status)}',
      ),
    );
  }
}

class _SyncSettings extends StatelessWidget {
  const _SyncSettings({required this.settings});
  final SettingsDto? settings;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text('AVdb 同步', style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 12),
      _SyncRow(label: '30D 增量', value: settings?.incrementalSync),
      _SyncRow(label: '全量校对', value: settings?.fullSync),
    ],
  );
}

class _SyncRow extends StatelessWidget {
  const _SyncRow({required this.label, required this.value});
  final String label;
  final SyncRunStateDto? value;
  @override
  Widget build(BuildContext context) => Container(
    constraints: const BoxConstraints(minHeight: 72),
    decoration: BoxDecoration(
      border: Border(
        bottom: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
      ),
    ),
    child: Row(
      children: [
        Expanded(child: Text(label)),
        Text(
          '${settingsStatusLabel(value?.status ?? 'unknown')} · 已导入 ${value?.importedCount ?? 0} 条',
        ),
      ],
    ),
  );
}

class _Field extends StatelessWidget {
  const _Field({
    required this.controller,
    required this.label,
    this.secret = false,
    this.numeric = false,
    this.keyValue,
  });
  final TextEditingController controller;
  final String label;
  final bool secret, numeric;
  final String? keyValue;
  @override
  Widget build(BuildContext context) => TextField(
    key: keyValue == null ? null : ValueKey<String>(keyValue!),
    controller: controller,
    obscureText: secret,
    keyboardType: numeric ? TextInputType.number : null,
    inputFormatters: numeric ? [FilteringTextInputFormatter.digitsOnly] : null,
    decoration: InputDecoration(
      labelText: label,
      border: const OutlineInputBorder(),
    ),
  );
}

void _step(TextEditingController controller, int delta) {
  final value = (int.tryParse(controller.text) ?? 24) + delta;
  controller.text = '${value.clamp(1, 168)}';
}

String _qrError(String code) => switch (code) {
  'cloud115_credentials_expired' => '凭据已失效，请重新扫码',
  'cloud115_unavailable' => '115 暂时不可用，请稍后重试',
  'cloud115_qr_session_not_found' => '二维码已失效，请重新扫码',
  _ => settingsErrorLabel(code),
};

String _formatTimestamp(DateTime value) =>
    value.toLocal().toIso8601String().replaceFirst('T', ' ').split('.').first;

Future<void> _confirmUnbind(BuildContext context, WidgetRef ref) async {
  final confirmed =
      await showDialog<bool>(
        context: context,
        builder:
            (context) => AlertDialog(
              title: const Text('解除 115 绑定？'),
              content: const Text('活动缓存任务可能阻止解绑。'),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('返回'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('确认解绑'),
                ),
              ],
            ),
      ) ??
      false;
  if (confirmed) await ref.read(qrBindingControllerProvider.notifier).unbind();
}

Future<void> _confirmClear(
  BuildContext context,
  Future<void> Function() action,
) async {
  final confirmed =
      await showDialog<bool>(
        context: context,
        builder:
            (context) => AlertDialog(
              title: const Text('清除配置？'),
              content: const Text('已保存的凭据将被删除。'),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('返回'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('确认清除'),
                ),
              ],
            ),
      ) ??
      false;
  if (confirmed) await action();
}
