import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Holds the resident's session (JWT pair + house number for display),
/// persisted to SharedPreferences so a restart doesn't force a fresh
/// login. ApiClient reads tokens from here and writes back a refreshed
/// pair when a 401 is recovered from — this class owns the only copy of
/// truth for "is anyone logged in right now."
class AuthState extends ChangeNotifier {
  String? _accessToken;
  String? _refreshToken;
  String? _houseNumber;
  bool _loaded = false;

  String? get accessToken => _accessToken;
  String? get refreshToken => _refreshToken;
  String? get houseNumber => _houseNumber;
  bool get isAuthenticated => _accessToken != null;
  bool get isLoaded => _loaded;

  Future<void> loadFromStorage() async {
    final prefs = await SharedPreferences.getInstance();
    _accessToken = prefs.getString('access_token');
    _refreshToken = prefs.getString('refresh_token');
    _houseNumber = prefs.getString('house_number');
    _loaded = true;
    notifyListeners();
  }

  Future<void> setSession({required String accessToken, required String refreshToken, required String houseNumber}) async {
    _accessToken = accessToken;
    _refreshToken = refreshToken;
    _houseNumber = houseNumber;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('access_token', accessToken);
    await prefs.setString('refresh_token', refreshToken);
    await prefs.setString('house_number', houseNumber);
    notifyListeners();
  }

  Future<void> updateAccessToken({required String accessToken, required String refreshToken}) async {
    _accessToken = accessToken;
    _refreshToken = refreshToken;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('access_token', accessToken);
    await prefs.setString('refresh_token', refreshToken);
  }

  Future<void> clear() async {
    _accessToken = null;
    _refreshToken = null;
    _houseNumber = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('access_token');
    await prefs.remove('refresh_token');
    await prefs.remove('house_number');
    notifyListeners();
  }
}
