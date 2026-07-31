import 'dart:io';

const maxSubtitleBytes = 8 * 1024 * 1024;
const supportedSubtitleFormats = <String>{'srt', 'ass', 'ssa', 'vtt'};

class SubtitleCacheException implements Exception {
  const SubtitleCacheException(this.code);

  final String code;

  @override
  String toString() => 'SubtitleCacheException($code)';
}

abstract interface class SubtitleCache {
  Future<Uri?> resolve({
    required String cacheJobId,
    required String subtitleId,
    required String format,
    required DateTime now,
  });

  Future<Uri> store({
    required String cacheJobId,
    required String subtitleId,
    required String format,
    required List<int> bytes,
    required DateTime expiresAt,
  });

  Future<void> removeCacheJob(String cacheJobId);
  Future<void> removeExpired({required DateTime now});
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

  Directory jobDirectory(String cacheJobId) {
    _requireUuid(cacheJobId, 'cacheJobId');
    return Directory(
      '${_subtitleDirectory.path}${Platform.pathSeparator}$cacheJobId',
    );
  }

  @override
  Future<Uri?> resolve({
    required String cacheJobId,
    required String subtitleId,
    required String format,
    required DateTime now,
  }) {
    _validateIdentity(cacheJobId, subtitleId, format);
    return _resolve(
      cacheJobId: cacheJobId,
      subtitleId: subtitleId,
      format: format,
      now: now.toUtc(),
    );
  }

  Future<Uri?> _resolve({
    required String cacheJobId,
    required String subtitleId,
    required String format,
    required DateTime now,
  }) async {
    final file = _subtitleFile(cacheJobId, subtitleId, format);
    final expiry = _expiryFile(cacheJobId, subtitleId);
    if (!await file.exists() || !await expiry.exists()) return null;
    final expiresAt = DateTime.tryParse(await expiry.readAsString());
    if (expiresAt == null || !now.isBefore(expiresAt.toUtc())) {
      await _removeSubtitle(cacheJobId, subtitleId);
      return null;
    }
    return file.uri;
  }

  @override
  Future<Uri> store({
    required String cacheJobId,
    required String subtitleId,
    required String format,
    required List<int> bytes,
    required DateTime expiresAt,
  }) {
    _validateIdentity(cacheJobId, subtitleId, format);
    if (bytes.length > maxSubtitleBytes) {
      throw const SubtitleCacheException('subtitle_too_large');
    }
    return _store(
      cacheJobId: cacheJobId,
      subtitleId: subtitleId,
      format: format,
      bytes: bytes,
      expiresAt: expiresAt.toUtc(),
    );
  }

  Future<Uri> _store({
    required String cacheJobId,
    required String subtitleId,
    required String format,
    required List<int> bytes,
    required DateTime expiresAt,
  }) async {
    final job = jobDirectory(cacheJobId);
    await job.create(recursive: true);
    final file = _subtitleFile(cacheJobId, subtitleId, format);
    final expiry = _expiryFile(cacheJobId, subtitleId);
    await _atomicWriteBytes(file, bytes);
    await _atomicWriteString(expiry, expiresAt.toIso8601String());
    return file.uri;
  }

  @override
  Future<void> removeCacheJob(String cacheJobId) {
    final job = jobDirectory(cacheJobId);
    _requireInsideRoot(job.path);
    return _deleteDirectory(job);
  }

  @override
  Future<void> removeExpired({required DateTime now}) async {
    if (!await _subtitleDirectory.exists()) return;
    await for (final entity in _subtitleDirectory.list(followLinks: false)) {
      if (entity is! Directory) continue;
      final jobId = _basename(entity.path);
      if (!_isUuid(jobId)) continue;
      var hasLiveCopy = false;
      await for (final child in entity.list(followLinks: false)) {
        if (child is! File || !child.path.endsWith('.expiry')) continue;
        final subtitleId = _basename(
          child.path.substring(0, child.path.length - '.expiry'.length),
        );
        if (!_isUuid(subtitleId)) continue;
        final expiresAt = DateTime.tryParse(await child.readAsString());
        if (expiresAt == null || !now.toUtc().isBefore(expiresAt.toUtc())) {
          await _removeSubtitle(jobId, subtitleId);
        } else {
          hasLiveCopy = true;
        }
      }
      if (!hasLiveCopy && await entity.exists()) {
        await _deleteDirectory(entity);
      }
    }
  }

  @override
  Future<void> clear() async {
    _requireInsideRoot(_subtitleDirectory.path);
    if (await _subtitleDirectory.exists()) {
      await _subtitleDirectory.delete(recursive: true);
    }
  }

  File _subtitleFile(String jobId, String subtitleId, String format) => File(
    '${jobDirectory(jobId).path}${Platform.pathSeparator}$subtitleId.$format',
  );

  File _expiryFile(String jobId, String subtitleId) => File(
    '${jobDirectory(jobId).path}${Platform.pathSeparator}$subtitleId.expiry',
  );

  Future<void> _removeSubtitle(String jobId, String subtitleId) async {
    final job = jobDirectory(jobId);
    if (!await job.exists()) return;
    await for (final entity in job.list(followLinks: false)) {
      if (entity is! File) continue;
      final name = _basename(entity.path);
      if (name == '$subtitleId.expiry' ||
          supportedSubtitleFormats.any(
            (format) => name == '$subtitleId.$format',
          )) {
        await entity.delete();
      }
    }
  }

  Future<void> _atomicWriteBytes(File target, List<int> bytes) async {
    final temporary = File('${target.path}.tmp');
    await temporary.writeAsBytes(bytes, flush: true);
    if (await target.exists()) await target.delete();
    await temporary.rename(target.path);
  }

  Future<void> _atomicWriteString(File target, String value) async {
    final temporary = File('${target.path}.tmp');
    await temporary.writeAsString(value, flush: true);
    if (await target.exists()) await target.delete();
    await temporary.rename(target.path);
  }

  Future<void> _deleteDirectory(Directory target) async {
    if (await target.exists()) await target.delete(recursive: true);
  }

  void _validateIdentity(String jobId, String subtitleId, String format) {
    _requireUuid(jobId, 'cacheJobId');
    _requireUuid(subtitleId, 'subtitleId');
    if (!supportedSubtitleFormats.contains(format)) {
      throw ArgumentError.value(format, 'format', 'is not supported');
    }
  }

  void _requireInsideRoot(String path) {
    final root = _normalized(_applicationRoot.path);
    final target = _normalized(path);
    if (target == root ||
        !target.startsWith('$root${Platform.pathSeparator}')) {
      throw StateError('subtitle cache is outside the application root');
    }
  }

  static void _requireUuid(String value, String name) {
    if (!_isUuid(value)) {
      throw ArgumentError.value(value, name, 'must be a UUID');
    }
  }

  static bool _isUuid(String value) => RegExp(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$',
  ).hasMatch(value);

  static String _basename(String path) =>
      path.split(Platform.pathSeparator).last;

  static String _normalized(String value) {
    final normalized = value.replaceAll('/', Platform.pathSeparator);
    return Platform.isWindows ? normalized.toLowerCase() : normalized;
  }
}

class MemorySubtitleCache implements SubtitleCache {
  bool cleared = false;
  final Map<String, ({Uri uri, DateTime expiresAt})> _entries = {};

  String _key(String jobId, String subtitleId, String format) =>
      '$jobId/$subtitleId.$format';

  @override
  Future<Uri?> resolve({
    required String cacheJobId,
    required String subtitleId,
    required String format,
    required DateTime now,
  }) async {
    final key = _key(cacheJobId, subtitleId, format);
    final entry = _entries[key];
    if (entry == null) return null;
    if (!now.toUtc().isBefore(entry.expiresAt)) {
      _entries.remove(key);
      return null;
    }
    return entry.uri;
  }

  @override
  Future<Uri> store({
    required String cacheJobId,
    required String subtitleId,
    required String format,
    required List<int> bytes,
    required DateTime expiresAt,
  }) async {
    if (bytes.length > maxSubtitleBytes) {
      throw const SubtitleCacheException('subtitle_too_large');
    }
    final uri = Uri.parse('memory://subtitles/$cacheJobId/$subtitleId.$format');
    _entries[_key(cacheJobId, subtitleId, format)] = (
      uri: uri,
      expiresAt: expiresAt.toUtc(),
    );
    return uri;
  }

  @override
  Future<void> removeCacheJob(String cacheJobId) async {
    _entries.removeWhere((key, _) => key.startsWith('$cacheJobId/'));
  }

  @override
  Future<void> removeExpired({required DateTime now}) async {
    _entries.removeWhere((_, entry) => !now.toUtc().isBefore(entry.expiresAt));
  }

  @override
  Future<void> clear() async {
    _entries.clear();
    cleared = true;
  }
}
