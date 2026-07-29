import 'dart:io';

abstract interface class SubtitleCache {
  Future<void> clear();
}

class DirectorySubtitleCache implements SubtitleCache {
  DirectorySubtitleCache({required Directory applicationRoot})
    : _applicationRoot = applicationRoot.absolute,
      _subtitleDirectory = Directory(
        '${applicationRoot.absolute.path}${Platform.pathSeparator}subtitles',
      );

  factory DirectorySubtitleCache.forCurrentUser() {
    final localAppData = Platform.environment['LOCALAPPDATA'];
    if (localAppData == null || localAppData.isEmpty) {
      throw StateError('LOCALAPPDATA is unavailable');
    }
    return DirectorySubtitleCache(
      applicationRoot: Directory(
        '$localAppData${Platform.pathSeparator}SakuraPlayer',
      ),
    );
  }

  final Directory _applicationRoot;
  final Directory _subtitleDirectory;

  Directory get directory => _subtitleDirectory;

  @override
  Future<void> clear() async {
    final root = _normalized(_applicationRoot.path);
    final target = _normalized(_subtitleDirectory.path);
    if (target == root ||
        !target.startsWith('$root${Platform.pathSeparator}')) {
      throw StateError('subtitle cache is outside the application root');
    }
    if (await _subtitleDirectory.exists()) {
      await _subtitleDirectory.delete(recursive: true);
    }
  }

  static String _normalized(String value) {
    final normalized = value.replaceAll('/', Platform.pathSeparator);
    return Platform.isWindows ? normalized.toLowerCase() : normalized;
  }
}

class MemorySubtitleCache implements SubtitleCache {
  bool cleared = false;

  @override
  Future<void> clear() async {
    cleared = true;
  }
}
