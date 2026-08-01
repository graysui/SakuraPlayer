import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';

void main() {
  test(
    'secure store worker receives typed operations without logging values',
    () async {
      final calls = <(SecureStorageOperation, String, String?)>[];
      final store = FlutterSecureKeyValueStore(
        workerRunner: (operation, key, value) async {
          calls.add((operation, key, value));
          return operation == SecureStorageOperation.read
              ? 'stored-value'
              : null;
        },
      );

      expect(await store.read('read-key'), 'stored-value');
      await store.write('write-key', 'write-value');
      await store.delete('delete-key');

      expect(calls, <(SecureStorageOperation, String, String?)>[
        (SecureStorageOperation.read, 'read-key', null),
        (SecureStorageOperation.write, 'write-key', 'write-value'),
        (SecureStorageOperation.delete, 'delete-key', null),
      ]);
    },
  );

  test('secure store worker operation has a bounded timeout', () async {
    final pending = Completer<Object?>();
    final store = FlutterSecureKeyValueStore(
      operationTimeout: const Duration(milliseconds: 10),
      workerRunner: (_, _, _) => pending.future,
    );

    await expectLater(store.read('read-key'), throwsA(isA<TimeoutException>()));
  });
}
