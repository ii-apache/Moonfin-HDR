import 'dart:convert';
import 'dart:io';

/// Whether Plasma has HDR turned on for a connected, enabled output, read from
/// `kscreen-doctor -j`. Null when it cannot be read, so the caller holds its
/// last answer instead of guessing. MOONFIN_LINUX_HDR_DISPLAY=1 or 0 answers
/// for a setup where kscreen-doctor is missing or wrong.
Future<bool?> linuxDisplayHdrState() async {
  final forced = Platform.environment['MOONFIN_LINUX_HDR_DISPLAY']?.trim();
  if (forced == '1') return true;
  if (forced == '0') return false;
  try {
    final result = await Process.run('kscreen-doctor', [
      '-j',
    ]).timeout(const Duration(seconds: 3));
    if (result.exitCode != 0) return null;
    final decoded = jsonDecode(result.stdout as String);
    if (decoded is! Map || decoded['outputs'] is! List) return null;
    var sawOutput = false;
    for (final output in decoded['outputs'] as List) {
      if (output is! Map) continue;
      if (output['connected'] != true || output['enabled'] != true) continue;
      sawOutput = true;
      if (output['hdr'] == true) return true;
    }
    return sawOutput ? false : null;
  } catch (_) {
    return null;
  }
}
