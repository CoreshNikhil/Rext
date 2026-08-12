/// mobile app configuration — analogous to admin_web/config.py. Only
/// setting this app owns is where the backend lives; everything else is
/// server-computed and fetched over HTTP.
class AppConfig {
  // 10.0.2.2 is the Android emulator's alias for the host machine's
  // localhost; on the web build (what we verify with in this environment)
  // localhost resolves directly, so this default works for both without
  // extra configuration during development.
  static const String backendUrl = String.fromEnvironment(
    'BACKEND_URL',
    defaultValue: 'http://localhost:8000',
  );
}
