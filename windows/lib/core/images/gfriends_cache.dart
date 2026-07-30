import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/images/gfriends_url.dart';

const gfriendsMaxImageBytes = 8 * 1024 * 1024;
const gfriendsMaxFiles = 512;
const gfriendsMaxCacheBytes = 256 * 1024 * 1024;
const gfriendsCacheTtl = Duration(days: 7);
const gfriendsMaxConcurrentDownloads = 4;
const gfriendsConnectTimeout = Duration(seconds: 10);
const gfriendsReceiveTimeout = Duration(seconds: 30);

class GfriendsCacheException implements Exception {
  const GfriendsCacheException(this.code);

  final String code;

  @override
  String toString() => 'GfriendsCacheException($code)';
}

class GfriendsDownload {
  const GfriendsDownload({required this.bytes, required this.extension});

  final Uint8List bytes;
  final String extension;
}

abstract interface class GfriendsDownloader {
  Future<GfriendsDownload> download(
    String url, {
    required Future<void> cancelled,
  });
}

class DioGfriendsDownloader implements GfriendsDownloader {
  DioGfriendsDownloader({Dio? dio}) : _dio = dio ?? Dio() {
    _dio.options.connectTimeout = gfriendsConnectTimeout;
    _dio.options.receiveTimeout = gfriendsReceiveTimeout;
  }

  final Dio _dio;

  @override
  Future<GfriendsDownload> download(
    String url, {
    required Future<void> cancelled,
  }) async {
    var current = url;
    var redirects = 0;
    while (true) {
      if (!isAllowedGfriendsUrl(current)) {
        throw const GfriendsCacheException('url_not_allowed');
      }
      final cancelToken = CancelToken();
      unawaited(
        cancelled.then((_) {
          if (!cancelToken.isCancelled) cancelToken.cancel('cancelled');
        }),
      );
      late final Response<ResponseBody> response;
      try {
        response = await _dio.get<ResponseBody>(
          current,
          cancelToken: cancelToken,
          options: Options(
            responseType: ResponseType.stream,
            followRedirects: false,
            validateStatus: (status) => status != null && status < 600,
            receiveTimeout: gfriendsReceiveTimeout,
            headers: const <String, Object?>{
              'Accept': 'image/jpeg, image/png, image/webp',
            },
          ),
        );
      } on DioException catch (error) {
        if (CancelToken.isCancel(error)) {
          throw const GfriendsCacheException('cancelled');
        }
        throw const GfriendsCacheException('download_failed');
      }
      final status = response.statusCode ?? 0;
      if (_redirectStatuses.contains(status)) {
        if (redirects >= 3) {
          throw const GfriendsCacheException('redirect_limit_exceeded');
        }
        final location = response.headers.value('location');
        if (location == null || location.isEmpty) {
          throw const GfriendsCacheException('redirect_invalid');
        }
        final next = Uri.tryParse(current)?.resolve(location).toString();
        if (next == null || !isAllowedGfriendsUrl(next)) {
          throw const GfriendsCacheException('url_not_allowed');
        }
        current = next;
        redirects++;
        continue;
      }
      if (status != 200 || response.data == null) {
        throw const GfriendsCacheException('download_failed');
      }
      final declaredLength = int.tryParse(
        response.headers.value(Headers.contentLengthHeader) ?? '',
      );
      if (declaredLength != null && declaredLength > gfriendsMaxImageBytes) {
        throw const GfriendsCacheException('image_too_large');
      }
      final chunks = BytesBuilder(copy: false);
      try {
        await for (final chunk in response.data!.stream) {
          chunks.add(chunk);
          if (chunks.length > gfriendsMaxImageBytes) {
            cancelToken.cancel('image too large');
            throw const GfriendsCacheException('image_too_large');
          }
        }
      } on DioException catch (error) {
        if (CancelToken.isCancel(error)) {
          throw const GfriendsCacheException('cancelled');
        }
        throw const GfriendsCacheException('download_failed');
      }
      final bytes = chunks.takeBytes();
      final contentType =
          response.headers
              .value(Headers.contentTypeHeader)
              ?.split(';')
              .first
              .trim()
              .toLowerCase();
      final extension = _imageExtension(bytes);
      if (extension == null ||
          !(_contentTypes[extension]?.contains(contentType) ?? false)) {
        throw const GfriendsCacheException('image_format_invalid');
      }
      return GfriendsDownload(bytes: bytes, extension: extension);
    }
  }
}

class GfriendsLoadHandle {
  GfriendsLoadHandle({required this.bytes, required void Function() cancel})
    : _cancel = cancel;

  final Future<Uint8List> bytes;
  final void Function() _cancel;
  bool _cancelled = false;

  void cancel() {
    if (_cancelled) return;
    _cancelled = true;
    _cancel();
  }
}

abstract interface class GfriendsImageCache {
  GfriendsLoadHandle load(String url);

  Future<void> prune();

  Future<void> clear();

  void dispose();
}

class DirectoryGfriendsCache implements GfriendsImageCache {
  DirectoryGfriendsCache({
    required Directory applicationRoot,
    required Directory cacheDirectory,
    required GfriendsDownloader downloader,
    DateTime Function()? now,
    int maxFiles = gfriendsMaxFiles,
    int maxBytes = gfriendsMaxCacheBytes,
    Duration ttl = gfriendsCacheTtl,
    int maxConcurrent = gfriendsMaxConcurrentDownloads,
    String Function()? idFactory,
  }) : _applicationRoot = applicationRoot.absolute,
       directory = cacheDirectory.absolute,
       _downloader = downloader,
       _now = now ?? _utcNow,
       _maxFiles = maxFiles,
       _maxBytes = maxBytes,
       _ttl = ttl,
       _pool = _DownloadPool(maxConcurrent),
       _idFactory = idFactory ?? _randomId {
    if (maxFiles < 1 || maxBytes < 1 || ttl <= Duration.zero) {
      throw ArgumentError('cache bounds must be positive');
    }
    if (!_isManagedTarget(_applicationRoot, directory)) {
      throw StateError('GFriends cache is outside the managed directory');
    }
  }

  factory DirectoryGfriendsCache.forCurrentUser() {
    final localAppData = Platform.environment['LOCALAPPDATA'];
    if (localAppData == null || localAppData.isEmpty) {
      throw StateError('LOCALAPPDATA is unavailable');
    }
    final root = Directory(
      '$localAppData${Platform.pathSeparator}SakuraPlayer',
    );
    return DirectoryGfriendsCache(
      applicationRoot: root,
      cacheDirectory: Directory(
        '${root.path}${Platform.pathSeparator}cache'
        '${Platform.pathSeparator}gfriends-v1',
      ),
      downloader: DioGfriendsDownloader(),
    );
  }

  final Directory _applicationRoot;
  final Directory directory;
  final GfriendsDownloader _downloader;
  final DateTime Function() _now;
  final int _maxFiles;
  final int _maxBytes;
  final Duration _ttl;
  final _DownloadPool _pool;
  final String Function() _idFactory;
  final Map<String, _CacheEntry> _entries = <String, _CacheEntry>{};
  final Map<String, _SharedLoad> _loads = <String, _SharedLoad>{};
  Future<void>? _initialization;
  Future<void>? _clearInFlight;
  Future<void> _mutationTail = Future<void>.value();
  int _generation = 0;
  bool _disposed = false;

  File get _indexFile =>
      File('${directory.path}${Platform.pathSeparator}index.json');

  @override
  GfriendsLoadHandle load(String url) {
    if (_disposed) {
      return GfriendsLoadHandle(
        bytes: Future<Uint8List>.error(
          const GfriendsCacheException('disposed'),
        ),
        cancel: () {},
      );
    }
    if (!isAllowedGfriendsUrl(url)) {
      return GfriendsLoadHandle(
        bytes: Future<Uint8List>.error(
          const GfriendsCacheException('url_not_allowed'),
        ),
        cancel: () {},
      );
    }
    final shared = _loads.putIfAbsent(url, () => _startShared(url));
    return shared.subscribe();
  }

  _SharedLoad _startShared(String url) {
    final cancellation = _CancellationSignal();
    final generation = _generation;
    late final _SharedLoad shared;
    final future = _load(url, cancellation, generation);
    shared = _SharedLoad(future: future, cancellation: cancellation);
    future.then<void>(
      (_) {
        if (identical(_loads[url], shared)) _loads.remove(url);
      },
      onError: (Object _, StackTrace __) {
        if (identical(_loads[url], shared)) _loads.remove(url);
      },
    );
    return shared;
  }

  Future<Uint8List> _load(
    String url,
    _CancellationSignal cancellation,
    int generation,
  ) async {
    final clearing = _clearInFlight;
    if (clearing != null) await clearing;
    await _ensureInitialized();
    final cached = await _serialized(() => _readCached(url));
    if (cancellation.isCancelled || generation != _generation) {
      throw const GfriendsCacheException('cancelled');
    }
    if (cached != null) return cached;
    final download = await _pool.run(
      cancelled: cancellation.future,
      action: () => _downloader.download(url, cancelled: cancellation.future),
    );
    if (cancellation.isCancelled || generation != _generation) {
      throw const GfriendsCacheException('cancelled');
    }
    return _serialized(() => _store(url, download, cancellation, generation));
  }

  Future<void> _ensureInitialized() {
    final current = _initialization;
    if (current != null) return current;
    final operation = _initialize();
    _initialization = operation;
    return operation;
  }

  Future<void> _initialize() async {
    await directory.create(recursive: true);
    final index = _indexFile;
    if (await index.exists()) {
      try {
        final decoded = jsonDecode(await index.readAsString());
        if (decoded is! Map ||
            decoded['version'] != 1 ||
            decoded['entries'] is! List) {
          throw const FormatException('invalid cache index');
        }
        for (final raw in decoded['entries'] as List<Object?>) {
          final entry = _CacheEntry.fromJson(raw);
          if (_entries.containsKey(entry.url)) {
            throw const FormatException('duplicate cache URL');
          }
          _entries[entry.url] = entry;
        }
      } on Object {
        await _resetDirectory();
      }
    }
    await _pruneInternal();
    await _writeIndex();
  }

  Future<Uint8List?> _readCached(String url) async {
    final entry = _entries[url];
    if (entry == null) return null;
    final now = _now().toUtc();
    final file = _fileFor(entry);
    if (!entry.lastAccessedAt.add(_ttl).isAfter(now) || !await file.exists()) {
      await _removeEntry(entry);
      await _writeIndex();
      return null;
    }
    final bytes = await file.readAsBytes();
    if (bytes.length != entry.byteSize ||
        _imageExtension(bytes) != entry.extension) {
      await _removeEntry(entry);
      await _writeIndex();
      return null;
    }
    _entries[url] = entry.copyWith(lastAccessedAt: now);
    await _writeIndex();
    return Uint8List.fromList(bytes);
  }

  Future<Uint8List> _store(
    String url,
    GfriendsDownload download,
    _CancellationSignal cancellation,
    int generation,
  ) async {
    if (download.bytes.isEmpty ||
        download.bytes.length > gfriendsMaxImageBytes ||
        !_extensions.contains(download.extension)) {
      throw const GfriendsCacheException('image_format_invalid');
    }
    if (cancellation.isCancelled || generation != _generation) {
      throw const GfriendsCacheException('cancelled');
    }
    await directory.create(recursive: true);
    final id = _idFactory();
    if (!_idPattern.hasMatch(id)) {
      throw StateError('GFriends cache generated an invalid file ID');
    }
    final entry = _CacheEntry(
      url: url,
      fileId: id,
      byteSize: download.bytes.length,
      extension: download.extension,
      lastAccessedAt: _now().toUtc(),
    );
    final temporary = File(
      '${directory.path}${Platform.pathSeparator}.$id.tmp',
    );
    final target = _fileFor(entry);
    try {
      await temporary.writeAsBytes(download.bytes, flush: true);
      if (cancellation.isCancelled || generation != _generation) {
        throw const GfriendsCacheException('cancelled');
      }
      await temporary.rename(target.path);
      final replaced = _entries[url];
      _entries[url] = entry;
      if (replaced != null && replaced.fileId != entry.fileId) {
        await _deleteIfExists(_fileFor(replaced));
      }
      await _pruneInternal();
      await _writeIndex();
      return Uint8List.fromList(download.bytes);
    } catch (_) {
      await _deleteIfExists(temporary);
      if (_entries[url]?.fileId != entry.fileId) {
        await _deleteIfExists(target);
      }
      rethrow;
    }
  }

  @override
  Future<void> prune() async {
    final clearing = _clearInFlight;
    if (clearing != null) await clearing;
    await _ensureInitialized();
    await _serialized(() async {
      await _pruneInternal();
      await _writeIndex();
    });
  }

  Future<void> _pruneInternal() async {
    final now = _now().toUtc();
    for (final entry in List<_CacheEntry>.of(_entries.values)) {
      if (!entry.lastAccessedAt.add(_ttl).isAfter(now) ||
          !await _fileFor(entry).exists()) {
        await _removeEntry(entry);
      }
    }
    var totalBytes = _entries.values.fold<int>(
      0,
      (total, entry) => total + entry.byteSize,
    );
    final ordered =
        _entries.values.toList()..sort((left, right) {
          final time = left.lastAccessedAt.compareTo(right.lastAccessedAt);
          return time != 0 ? time : left.fileId.compareTo(right.fileId);
        });
    while (_entries.length > _maxFiles || totalBytes > _maxBytes) {
      final entry = ordered.removeAt(0);
      totalBytes -= entry.byteSize;
      await _removeEntry(entry);
    }
    if (await directory.exists()) {
      final referenced =
          <String>{
            _indexFile.path,
            for (final entry in _entries.values) _fileFor(entry).path,
          }.map(_normalized).toSet();
      await for (final entity in directory.list(followLinks: false)) {
        if (entity is File && !referenced.contains(_normalized(entity.path))) {
          await entity.delete();
        }
      }
    }
  }

  Future<void> _removeEntry(_CacheEntry entry) async {
    _entries.remove(entry.url);
    await _deleteIfExists(_fileFor(entry));
  }

  Future<void> _writeIndex() async {
    await directory.create(recursive: true);
    final temporary = File(
      '${directory.path}${Platform.pathSeparator}.index.tmp',
    );
    final ordered =
        _entries.values.toList()
          ..sort((left, right) => left.fileId.compareTo(right.fileId));
    await temporary.writeAsString(
      jsonEncode(<String, Object?>{
        'version': 1,
        'entries': <Object?>[for (final entry in ordered) entry.toJson()],
      }),
      flush: true,
    );
    try {
      await temporary.rename(_indexFile.path);
    } on FileSystemException {
      await _deleteIfExists(_indexFile);
      await temporary.rename(_indexFile.path);
    }
  }

  Future<T> _serialized<T>(Future<T> Function() action) {
    final result = Completer<T>();
    _mutationTail = _mutationTail.then((_) async {
      try {
        result.complete(await action());
      } catch (error, stackTrace) {
        result.completeError(error, stackTrace);
      }
    });
    return result.future;
  }

  @override
  Future<void> clear() {
    final active = _clearInFlight;
    if (active != null) return active;
    final operation = _performClear();
    _clearInFlight = operation;
    void finish() {
      if (identical(_clearInFlight, operation)) _clearInFlight = null;
    }

    unawaited(
      operation.then<void>(
        (_) => finish(),
        onError: (Object _, StackTrace __) => finish(),
      ),
    );
    return operation;
  }

  Future<void> _performClear() async {
    _generation++;
    for (final load in _loads.values) {
      load.cancelUnderlying();
    }
    _loads.clear();
    final initialization = _initialization;
    if (initialization != null) {
      try {
        await initialization;
      } on Object {
        // Cleanup still owns the managed directory after failed startup.
      }
    }
    await _serialized(() async {
      _entries.clear();
      _initialization = null;
      await _resetDirectory(recreate: false);
    });
  }

  Future<void> _resetDirectory({bool recreate = true}) async {
    if (!_isManagedTarget(_applicationRoot, directory)) {
      throw StateError('GFriends cache clear target is unsafe');
    }
    if (await directory.exists()) await directory.delete(recursive: true);
    _entries.clear();
    if (recreate) await directory.create(recursive: true);
  }

  @override
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    _generation++;
    for (final load in _loads.values) {
      load.cancelUnderlying();
    }
    _loads.clear();
  }

  File _fileFor(_CacheEntry entry) => File(
    '${directory.path}${Platform.pathSeparator}'
    '${entry.fileId}.${entry.extension}',
  );
}

final gfriendsCacheProvider = Provider<GfriendsImageCache>((ref) {
  final cache = DirectoryGfriendsCache.forCurrentUser();
  ref.onDispose(cache.dispose);
  return cache;
});

class _SharedLoad {
  _SharedLoad({required this.future, required this.cancellation});

  final Future<Uint8List> future;
  final _CancellationSignal cancellation;
  int _subscribers = 0;

  GfriendsLoadHandle subscribe() {
    _subscribers++;
    final localCancellation = Completer<void>();
    var released = false;
    void release() {
      if (released) return;
      released = true;
      _subscribers--;
      if (_subscribers == 0) cancellation.cancel();
    }

    final result = Future.any<Uint8List>(<Future<Uint8List>>[
      future,
      localCancellation.future.then<Uint8List>(
        (_) => throw const GfriendsCacheException('cancelled'),
      ),
    ]);
    result.then<void>(
      (_) => release(),
      onError: (Object _, StackTrace __) => release(),
    );
    return GfriendsLoadHandle(
      bytes: result,
      cancel: () {
        if (!localCancellation.isCompleted) localCancellation.complete();
      },
    );
  }

  void cancelUnderlying() => cancellation.cancel();
}

class _CancellationSignal {
  final Completer<void> _completer = Completer<void>();

  bool get isCancelled => _completer.isCompleted;
  Future<void> get future => _completer.future;

  void cancel() {
    if (!_completer.isCompleted) _completer.complete();
  }
}

class _DownloadPool {
  _DownloadPool(this.maximum) {
    if (maximum < 1) throw ArgumentError.value(maximum, 'maximum');
  }

  final int maximum;
  final List<_PermitRequest> _waiting = <_PermitRequest>[];
  int _active = 0;

  Future<T> run<T>({
    required Future<void> cancelled,
    required Future<T> Function() action,
  }) async {
    await _acquire(cancelled);
    try {
      return await action();
    } finally {
      _release();
    }
  }

  Future<void> _acquire(Future<void> cancelled) {
    if (_active < maximum) {
      _active++;
      return Future<void>.value();
    }
    final request = _PermitRequest();
    _waiting.add(request);
    unawaited(
      cancelled.then((_) {
        if (request.granted || request.cancelled) return;
        request.cancelled = true;
        request.completer.completeError(
          const GfriendsCacheException('cancelled'),
        );
      }),
    );
    return request.completer.future;
  }

  void _release() {
    while (_waiting.isNotEmpty) {
      final request = _waiting.removeAt(0);
      if (request.cancelled) continue;
      request.granted = true;
      request.completer.complete();
      return;
    }
    _active--;
  }
}

class _PermitRequest {
  final Completer<void> completer = Completer<void>();
  bool granted = false;
  bool cancelled = false;
}

class _CacheEntry {
  const _CacheEntry({
    required this.url,
    required this.fileId,
    required this.byteSize,
    required this.extension,
    required this.lastAccessedAt,
  });

  factory _CacheEntry.fromJson(Object? raw) {
    if (raw is! Map) throw const FormatException('invalid cache entry');
    final json = Map<String, Object?>.from(raw);
    final url = json['url'];
    final fileId = json['file_id'];
    final byteSize = json['byte_size'];
    final extension = json['extension'];
    final lastAccessedAt = DateTime.tryParse('${json['last_accessed_at']}');
    if (url is! String ||
        !isAllowedGfriendsUrl(url) ||
        fileId is! String ||
        !_idPattern.hasMatch(fileId) ||
        byteSize is! int ||
        byteSize < 1 ||
        byteSize > gfriendsMaxImageBytes ||
        extension is! String ||
        !_extensions.contains(extension) ||
        lastAccessedAt == null) {
      throw const FormatException('invalid cache entry');
    }
    return _CacheEntry(
      url: url,
      fileId: fileId,
      byteSize: byteSize,
      extension: extension,
      lastAccessedAt: lastAccessedAt.toUtc(),
    );
  }

  final String url;
  final String fileId;
  final int byteSize;
  final String extension;
  final DateTime lastAccessedAt;

  _CacheEntry copyWith({DateTime? lastAccessedAt}) => _CacheEntry(
    url: url,
    fileId: fileId,
    byteSize: byteSize,
    extension: extension,
    lastAccessedAt: lastAccessedAt ?? this.lastAccessedAt,
  );

  Map<String, Object?> toJson() => <String, Object?>{
    'url': url,
    'file_id': fileId,
    'byte_size': byteSize,
    'extension': extension,
    'last_accessed_at': lastAccessedAt.toIso8601String(),
  };
}

String? _imageExtension(Uint8List bytes) {
  if (bytes.length >= 3 &&
      bytes[0] == 0xff &&
      bytes[1] == 0xd8 &&
      bytes[2] == 0xff) {
    return 'jpg';
  }
  if (bytes.length >= 8 &&
      bytes[0] == 0x89 &&
      bytes[1] == 0x50 &&
      bytes[2] == 0x4e &&
      bytes[3] == 0x47 &&
      bytes[4] == 0x0d &&
      bytes[5] == 0x0a &&
      bytes[6] == 0x1a &&
      bytes[7] == 0x0a) {
    return 'png';
  }
  if (bytes.length >= 12 &&
      ascii.decode(bytes.sublist(0, 4), allowInvalid: true) == 'RIFF' &&
      ascii.decode(bytes.sublist(8, 12), allowInvalid: true) == 'WEBP') {
    return 'webp';
  }
  return null;
}

Future<void> _deleteIfExists(File file) async {
  if (await file.exists()) await file.delete();
}

bool _isManagedTarget(Directory root, Directory target) {
  final expected = _normalized(
    '${root.absolute.path}${Platform.pathSeparator}cache'
    '${Platform.pathSeparator}gfriends-v1',
  );
  return _normalized(target.absolute.path) == expected;
}

String _normalized(String value) {
  final normalized = value.replaceAll('/', Platform.pathSeparator);
  return Platform.isWindows ? normalized.toLowerCase() : normalized;
}

DateTime _utcNow() => DateTime.now().toUtc();

String _randomId() {
  final random = Random.secure();
  return List<int>.generate(
    16,
    (_) => random.nextInt(256),
  ).map((byte) => byte.toRadixString(16).padLeft(2, '0')).join();
}

const _redirectStatuses = <int>{301, 302, 303, 307, 308};
const _extensions = <String>{'jpg', 'png', 'webp'};
const _contentTypes = <String, Set<String>>{
  'jpg': <String>{'image/jpeg'},
  'png': <String>{'image/png'},
  'webp': <String>{'image/webp'},
};
final _idPattern = RegExp(r'^[0-9a-f]{32}$');
