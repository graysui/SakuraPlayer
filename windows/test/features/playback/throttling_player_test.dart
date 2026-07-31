import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/throttling_player.dart';

void main() {
  test(
    '30 to 60 in-flight seeks execute only the first and final target',
    () async {
      final calls = <Duration>[];
      final gates = <Completer<void>>[];
      final player = ThrottlingPlayer((target) {
        calls.add(target);
        final gate = Completer<void>();
        gates.add(gate);
        return gate.future;
      });

      final futures = <Future<void>>[];
      for (var index = 0; index < 60; index++) {
        futures.add(player.seek(Duration(seconds: index)));
      }
      expect(calls, [Duration.zero]);

      gates.first.complete();
      await Future<void>.delayed(Duration.zero);
      expect(calls, [Duration.zero, const Duration(seconds: 59)]);
      gates.last.complete();
      await Future.wait(futures);
    },
  );

  test('seek error clears pending target and permits a later seek', () async {
    var calls = 0;
    final player = ThrottlingPlayer((_) async {
      calls++;
      if (calls == 1) throw StateError('seek failed');
    });

    await expectLater(
      player.seek(const Duration(seconds: 4)),
      throwsStateError,
    );
    await player.seek(const Duration(seconds: 8));
    expect(calls, 2);
  });
}
