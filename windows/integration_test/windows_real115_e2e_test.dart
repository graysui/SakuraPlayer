import 'real115_probe_test.dart' as real115_acceptance;

// TASK-212's probe remains the shared protocol implementation so both explicit
// entrypoints exercise one redacted, fail-closed real-account workflow.
void main() => real115_acceptance.main();
