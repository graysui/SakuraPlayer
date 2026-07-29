import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';
import 'package:sakuraplayer_windows/app/app.dart';
import 'package:sakuraplayer_windows/app/composition_root.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  MediaKit.ensureInitialized();
  runApp(
    const ProviderScope(
      child: SakuraPlayerCompositionRoot(child: SakuraPlayerApp()),
    ),
  );
}
