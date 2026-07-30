import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/images/gfriends_cache.dart';

void main() {
  test('uses the frozen cache, timeout and concurrency limits', () {
    expect(gfriendsMaxImageBytes, 8 * 1024 * 1024);
    expect(gfriendsMaxFiles, 512);
    expect(gfriendsMaxCacheBytes, 256 * 1024 * 1024);
    expect(gfriendsCacheTtl, const Duration(days: 7));
    expect(gfriendsMaxConcurrentDownloads, 4);
    expect(gfriendsConnectTimeout, const Duration(seconds: 10));
    expect(gfriendsReceiveTimeout, const Duration(seconds: 30));
  });

  test(
    'Dio downloader validates every redirect and sends no credentials',
    () async {
      final adapter = _RedirectAdapter();
      final dio = Dio()..httpClientAdapter = adapter;
      final downloader = DioGfriendsDownloader(dio: dio);

      final image = await downloader.download(
        _url('redirect.jpg'),
        cancelled: Completer<void>().future,
      );

      expect(image.extension, 'jpg');
      expect(image.bytes, _jpegBytes);
      expect(adapter.requests, hasLength(2));
      for (final request in adapter.requests) {
        expect(request.headers.containsKey('Authorization'), isFalse);
        expect(request.headers.containsKey('Cookie'), isFalse);
        expect(request.connectTimeout, gfriendsConnectTimeout);
        expect(request.receiveTimeout, gfriendsReceiveTimeout);
      }
    },
  );

  test(
    'rejects unsafe redirect, oversized response and invalid signature',
    () async {
      for (final mode in _BadResponseMode.values) {
        final dio = Dio()..httpClientAdapter = _BadResponseAdapter(mode);
        final downloader = DioGfriendsDownloader(dio: dio);
        await expectLater(
          downloader.download(
            _url('bad.jpg'),
            cancelled: Completer<void>().future,
          ),
          throwsA(isA<GfriendsCacheException>()),
          reason: mode.name,
        );
      }
    },
  );

  test('normal exit preserves hits and startup removes orphan files', () async {
    final fixture = await _fixture();
    addTearDown(fixture.dispose);
    final url = _url('preserved.jpg');
    final downloader = _ImmediateDownloader();
    final first = fixture.cache(downloader: downloader);
    await first.load(url).bytes;
    first.dispose();
    final orphan = File(
      '${first.directory.path}${Platform.pathSeparator}.orphan.tmp',
    );
    await orphan.writeAsString('orphan');

    final restored = fixture.cache(downloader: downloader);
    expect(await restored.load(url).bytes, _jpegBytes);
    expect(downloader.count(url), 1);
    expect(await orphan.exists(), isFalse);

    restored.dispose();
    final cachedImage =
        await restored.directory
            .list()
            .where((entity) => entity is File && entity.path.endsWith('.jpg'))
            .cast<File>()
            .single;
    await cachedImage.writeAsBytes(<int>[1, 2, 3, 4], flush: true);
    final repaired = fixture.cache(downloader: downloader);
    expect(await repaired.load(url).bytes, _jpegBytes);
    expect(downloader.count(url), 2);
  });

  test(
    'clear cancels an in-flight load and removes only its directory',
    () async {
      final fixture = await _fixture();
      addTearDown(fixture.dispose);
      final downloader = _ControlledDownloader();
      final cache = fixture.cache(downloader: downloader);
      final handle = cache.load(_url('in-flight.jpg'));
      await _waitUntil(() => downloader.calls.isNotEmpty);

      final clearing = cache.clear();
      await expectLater(
        handle.bytes,
        throwsA(
          isA<GfriendsCacheException>().having(
            (error) => error.code,
            'code',
            'cancelled',
          ),
        ),
      );
      await clearing;

      expect(await cache.directory.exists(), isFalse);
    },
  );

  test(
    'deduplicates a URL, caps downloads at four and isolates cancellation',
    () async {
      final fixture = await _fixture();
      addTearDown(fixture.dispose);
      final downloader = _ControlledDownloader();
      final cache = fixture.cache(downloader: downloader, maxConcurrent: 4);

      final duplicateA = cache.load(_url('same.jpg'));
      final duplicateB = cache.load(_url('same.jpg'));
      final others = <GfriendsLoadHandle>[
        for (var index = 0; index < 5; index++)
          cache.load(_url('other-$index.jpg')),
      ];
      await _waitUntil(() => downloader.calls.length == 4);

      expect(
        downloader.calls.where((url) => url.endsWith('same.jpg')),
        hasLength(1),
      );
      expect(downloader.active, 4);
      expect(downloader.maxActive, 4);

      duplicateA.cancel();
      await expectLater(
        duplicateA.bytes,
        throwsA(
          isA<GfriendsCacheException>().having(
            (error) => error.code,
            'code',
            'cancelled',
          ),
        ),
      );
      expect(downloader.cancelled, isEmpty);

      downloader.complete(_url('same.jpg'));
      expect(await duplicateB.bytes, _jpegBytes);
      await _waitUntil(() => downloader.calls.length == 5);
      expect(downloader.active, 4);

      for (final handle in others) {
        handle.cancel();
      }
      await Future.wait<void>(
        others.map(
          (handle) => handle.bytes.then<void>(
            (_) {},
            onError: (Object _, StackTrace __) {},
          ),
        ),
      );
      expect(downloader.cancelled, isNotEmpty);
    },
  );

  test(
    'uses sliding expiry and evicts stable least recently used entries',
    () async {
      final fixture = await _fixture();
      addTearDown(fixture.dispose);
      var now = DateTime.utc(2026, 7, 1);
      final downloader = _ImmediateDownloader();
      final cache = fixture.cache(
        downloader: downloader,
        now: () => now,
        maxFiles: 2,
        maxBytes: 1024,
      );
      final first = _url('first.jpg');
      final second = _url('second.jpg');
      final third = _url('third.jpg');

      await cache.load(first).bytes;
      now = now.add(const Duration(hours: 1));
      await cache.load(second).bytes;
      now = now.add(const Duration(hours: 1));
      await cache.load(first).bytes;
      now = now.add(const Duration(hours: 1));
      await cache.load(third).bytes;

      await cache.load(first).bytes;
      await cache.load(second).bytes;
      expect(downloader.count(first), 1);
      expect(downloader.count(second), 2);

      now = now.add(const Duration(days: 8));
      await cache.prune();
      await cache.load(first).bytes;
      expect(downloader.count(first), 2);
    },
  );

  test('evicts by total bytes independently from the file limit', () async {
    final fixture = await _fixture();
    addTearDown(fixture.dispose);
    final downloader = _ImmediateDownloader();
    final cache = fixture.cache(
      downloader: downloader,
      maxFiles: 10,
      maxBytes: _jpegBytes.length * 2 - 1,
    );
    final first = _url('byte-first.jpg');
    final second = _url('byte-second.jpg');

    await cache.load(first).bytes;
    await cache.load(second).bytes;
    await cache.load(second).bytes;
    await cache.load(first).bytes;

    expect(downloader.count(second), 1);
    expect(downloader.count(first), 2);
  });

  test(
    'failed loads and clear stay inside the managed cache directory',
    () async {
      final fixture = await _fixture();
      addTearDown(fixture.dispose);
      final sibling = File(
        '${fixture.root.path}${Platform.pathSeparator}catalog-images'
        '${Platform.pathSeparator}keep.jpg',
      );
      await sibling.parent.create(recursive: true);
      await sibling.writeAsBytes(_jpegBytes);
      final downloader = _ImmediateDownloader(fail: true);
      final cache = fixture.cache(downloader: downloader);

      await expectLater(
        cache.load(_url('failed.jpg')).bytes,
        throwsA(isA<GfriendsCacheException>()),
      );
      if (await cache.directory.exists()) {
        final imageFiles =
            await cache.directory
                .list()
                .where(
                  (entity) => entity is File && entity.path.endsWith('.jpg'),
                )
                .toList();
        expect(imageFiles, isEmpty);
      }

      await cache.clear();
      expect(await cache.directory.exists(), isFalse);
      expect(await sibling.exists(), isTrue);

      expect(
        () => DirectoryGfriendsCache(
          applicationRoot: fixture.root,
          cacheDirectory: fixture.root.parent,
          downloader: downloader,
        ),
        throwsStateError,
      );
    },
  );
}

const _jpegBytes = <int>[0xff, 0xd8, 0xff, 0xd9];

String _url(String name) =>
    'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/Test/$name';

Future<void> _waitUntil(bool Function() condition) async {
  for (var attempt = 0; attempt < 100; attempt++) {
    if (condition()) return;
    await Future<void>.delayed(const Duration(milliseconds: 5));
  }
  throw StateError('condition was not reached');
}

class _Fixture {
  const _Fixture(this.root);

  final Directory root;

  DirectoryGfriendsCache cache({
    required GfriendsDownloader downloader,
    DateTime Function()? now,
    int maxFiles = 512,
    int maxBytes = 256 * 1024 * 1024,
    int maxConcurrent = 4,
  }) => DirectoryGfriendsCache(
    applicationRoot: root,
    cacheDirectory: Directory(
      '${root.path}${Platform.pathSeparator}cache'
      '${Platform.pathSeparator}gfriends-v1',
    ),
    downloader: downloader,
    now: now,
    maxFiles: maxFiles,
    maxBytes: maxBytes,
    maxConcurrent: maxConcurrent,
  );

  Future<void> dispose() async {
    if (await root.exists()) await root.delete(recursive: true);
  }
}

Future<_Fixture> _fixture() async =>
    _Fixture(await Directory.systemTemp.createTemp('sakuraplayer-gfriends-'));

class _ImmediateDownloader implements GfriendsDownloader {
  _ImmediateDownloader({this.fail = false});

  final bool fail;
  final Map<String, int> _counts = <String, int>{};

  int count(String url) => _counts[url] ?? 0;

  @override
  Future<GfriendsDownload> download(
    String url, {
    required Future<void> cancelled,
  }) async {
    _counts.update(url, (value) => value + 1, ifAbsent: () => 1);
    if (fail) {
      throw const GfriendsCacheException('download_failed');
    }
    return GfriendsDownload(
      bytes: Uint8List.fromList(_jpegBytes),
      extension: 'jpg',
    );
  }
}

class _ControlledDownloader implements GfriendsDownloader {
  final List<String> calls = <String>[];
  final Set<String> cancelled = <String>{};
  final Map<String, Completer<GfriendsDownload>> _completers =
      <String, Completer<GfriendsDownload>>{};
  int active = 0;
  int maxActive = 0;

  @override
  Future<GfriendsDownload> download(
    String url, {
    required Future<void> cancelled,
  }) async {
    calls.add(url);
    active++;
    if (active > maxActive) maxActive = active;
    final completer = Completer<GfriendsDownload>();
    _completers[url] = completer;
    unawaited(
      cancelled.then((_) {
        this.cancelled.add(url);
        if (!completer.isCompleted) {
          completer.completeError(const GfriendsCacheException('cancelled'));
        }
      }),
    );
    try {
      return await completer.future;
    } finally {
      active--;
    }
  }

  void complete(String url) {
    _completers[url]!.complete(
      GfriendsDownload(bytes: Uint8List.fromList(_jpegBytes), extension: 'jpg'),
    );
  }
}

class _RedirectAdapter implements HttpClientAdapter {
  final List<RequestOptions> requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (requests.length == 1) {
      return ResponseBody.fromString(
        '',
        302,
        headers: <String, List<String>>{
          'location': <String>[_url('final.jpg')],
        },
      );
    }
    return ResponseBody(
      Stream<Uint8List>.value(Uint8List.fromList(_jpegBytes)),
      200,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>['image/jpeg'],
        Headers.contentLengthHeader: <String>['${_jpegBytes.length}'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

enum _BadResponseMode { unsafeRedirect, oversized, badSignature }

class _BadResponseAdapter implements HttpClientAdapter {
  _BadResponseAdapter(this.mode);

  final _BadResponseMode mode;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    if (mode == _BadResponseMode.unsafeRedirect) {
      return ResponseBody.fromString(
        '',
        302,
        headers: <String, List<String>>{
          'location': <String>['https://attacker.test/image.jpg'],
        },
      );
    }
    if (mode == _BadResponseMode.oversized) {
      return ResponseBody(
        const Stream<Uint8List>.empty(),
        200,
        headers: <String, List<String>>{
          Headers.contentTypeHeader: <String>['image/jpeg'],
          Headers.contentLengthHeader: <String>['${8 * 1024 * 1024 + 1}'],
        },
      );
    }
    return ResponseBody(
      Stream<Uint8List>.value(Uint8List.fromList(<int>[1, 2, 3, 4])),
      200,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>['image/jpeg'],
        Headers.contentLengthHeader: <String>['4'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
