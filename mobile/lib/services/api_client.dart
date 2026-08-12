import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../config.dart';
import '../models/app_notification.dart';
import '../models/auth.dart';
import '../models/bill.dart';
import '../models/meter_reading.dart';
import '../models/payment.dart';
import '../models/resident.dart';
import 'auth_state.dart';

class ApiException implements Exception {
  final int statusCode;
  final String detail;
  final String errorType;

  ApiException({required this.statusCode, required this.detail, required this.errorType});

  @override
  String toString() => detail;
}

/// Mirrors admin_web/api_client.py's approach one layer up the stack:
/// one shared HTTP wrapper (auth headers, 401-refresh-and-retry, uniform
/// error unwrapping) plus one method per backend endpoint the resident
/// app needs. AuthState is the single source of truth for tokens; this
/// class only ever reads/writes through it, never keeps its own copy.
class ApiClient {
  final AuthState authState;
  final String baseUrl;

  ApiClient(this.authState, {this.baseUrl = AppConfig.backendUrl});

  Map<String, String> get _headers {
    final token = authState.accessToken;
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  Never _raiseForError(http.Response resp) {
    Map<String, dynamic> body = {};
    try {
      body = jsonDecode(resp.body) as Map<String, dynamic>;
    } catch (_) {
      // Non-JSON error body (rare) — fall through with a generic detail.
    }
    throw ApiException(
      statusCode: resp.statusCode,
      detail: body['detail']?.toString() ?? (resp.body.isNotEmpty ? resp.body : 'HTTP ${resp.statusCode}'),
      errorType: body['error_type'] as String? ?? 'error',
    );
  }

  Future<bool> _refreshAccessToken() async {
    final refreshToken = authState.refreshToken;
    if (refreshToken == null) return false;
    final resp = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/refresh'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'refresh_token': refreshToken}),
    );
    if (resp.statusCode != 200) return false;
    final pair = TokenPair.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
    await authState.updateAccessToken(accessToken: pair.accessToken, refreshToken: pair.refreshToken);
    return true;
  }

  Future<http.Response> _request(String method, String path, {Map<String, dynamic>? json}) async {
    final uri = Uri.parse('$baseUrl$path');
    Future<http.Response> send() {
      final body = json != null ? jsonEncode(json) : null;
      switch (method) {
        case 'GET':
          return http.get(uri, headers: _headers);
        case 'POST':
          return http.post(uri, headers: _headers, body: body);
        case 'PATCH':
          return http.patch(uri, headers: _headers, body: body);
        default:
          throw UnsupportedError('Unsupported method $method');
      }
    }

    var resp = await send();
    if (resp.statusCode == 401 && authState.refreshToken != null) {
      if (await _refreshAccessToken()) {
        resp = await send();
      }
    }
    if (resp.statusCode == 401) {
      await authState.clear();
    }
    if (resp.statusCode >= 400) {
      _raiseForError(resp);
    }
    return resp;
  }

  Map<String, dynamic> _decodeObject(http.Response resp) => jsonDecode(resp.body) as Map<String, dynamic>;
  List<dynamic> _decodeList(http.Response resp) => jsonDecode(resp.body) as List<dynamic>;

  // --- Auth (no token needed for these) -----------------------------

  Future<String?> signupRequestOtp(String houseNumber, String mobileNumber) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/resident/signup/request-otp'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'house_number': houseNumber, 'mobile_number': mobileNumber}),
    );
    if (resp.statusCode >= 400) _raiseForError(resp);
    return _decodeObject(resp)['dev_otp'] as String?;
  }

  Future<String> signupVerifyOtp(String houseNumber, String mobileNumber, String otpCode) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/resident/signup/verify-otp'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'house_number': houseNumber, 'mobile_number': mobileNumber, 'otp_code': otpCode}),
    );
    if (resp.statusCode >= 400) _raiseForError(resp);
    return _decodeObject(resp)['signup_token'] as String;
  }

  Future<TokenPair> signupSetPassword(String signupToken, String password) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/resident/signup/set-password'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'signup_token': signupToken, 'password': password}),
    );
    if (resp.statusCode >= 400) _raiseForError(resp);
    return TokenPair.fromJson(_decodeObject(resp));
  }

  Future<TokenPair> loginResident(String houseNumber, String password) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/resident/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'house_number': houseNumber, 'password': password}),
    );
    if (resp.statusCode >= 400) _raiseForError(resp);
    return TokenPair.fromJson(_decodeObject(resp));
  }

  Future<String?> passwordResetRequestOtp(String houseNumber, String mobileNumber) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/resident/password-reset/request-otp'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'house_number': houseNumber, 'mobile_number': mobileNumber}),
    );
    if (resp.statusCode >= 400) _raiseForError(resp);
    return _decodeObject(resp)['dev_otp'] as String?;
  }

  Future<String> passwordResetVerifyOtp(String houseNumber, String mobileNumber, String otpCode) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/resident/password-reset/verify-otp'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'house_number': houseNumber, 'mobile_number': mobileNumber, 'otp_code': otpCode}),
    );
    if (resp.statusCode >= 400) _raiseForError(resp);
    return _decodeObject(resp)['reset_token'] as String;
  }

  Future<void> passwordResetConfirm(String resetToken, String newPassword) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/resident/password-reset/confirm'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'reset_token': resetToken, 'new_password': newPassword}),
    );
    if (resp.statusCode >= 400) _raiseForError(resp);
  }

  Future<void> logout() async {
    final refreshToken = authState.refreshToken;
    if (refreshToken == null) return;
    try {
      await http.post(
        Uri.parse('$baseUrl/api/v1/auth/logout'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': refreshToken}),
      );
    } catch (_) {
      // Best-effort — the local session is cleared by the caller regardless.
    }
  }

  // --- Profile / home --------------------------------------------------

  Future<ResidentProfile> getOwnProfile() async {
    final resp = await _request('GET', '/api/v1/resident/me');
    return ResidentProfile.fromJson(_decodeObject(resp));
  }

  Future<ResidentProfile> updateOwnEmail(String email) async {
    final resp = await _request('PATCH', '/api/v1/resident/me', json: {'email': email});
    return ResidentProfile.fromJson(_decodeObject(resp));
  }

  Future<ResidentHome> getHome() async {
    final resp = await _request('GET', '/api/v1/resident/home');
    return ResidentHome.fromJson(_decodeObject(resp));
  }

  // --- Meter readings ----------------------------------------------------

  Future<MeterReading> submitReading(Uint8List imageBytes, String filename) async {
    final uri = Uri.parse('$baseUrl/api/v1/resident/meter-readings');
    final request = http.MultipartRequest('POST', uri);
    final token = authState.accessToken;
    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    request.files.add(http.MultipartFile.fromBytes('file', imageBytes, filename: filename));

    var streamed = await request.send();
    var resp = await http.Response.fromStream(streamed);

    if (resp.statusCode == 401 && authState.refreshToken != null) {
      if (await _refreshAccessToken()) {
        final retryRequest = http.MultipartRequest('POST', uri);
        retryRequest.headers['Authorization'] = 'Bearer ${authState.accessToken}';
        retryRequest.files.add(http.MultipartFile.fromBytes('file', imageBytes, filename: filename));
        streamed = await retryRequest.send();
        resp = await http.Response.fromStream(streamed);
      }
    }
    if (resp.statusCode >= 400) _raiseForError(resp);
    return MeterReading.fromJson(_decodeObject(resp));
  }

  Future<List<MeterReading>> listOwnReadings() async {
    final resp = await _request('GET', '/api/v1/resident/meter-readings');
    return _decodeList(resp).map((r) => MeterReading.fromJson(r as Map<String, dynamic>)).toList();
  }

  Future<MeterReading> getOwnReading(int id) async {
    final resp = await _request('GET', '/api/v1/resident/meter-readings/$id');
    return MeterReading.fromJson(_decodeObject(resp));
  }

  Future<MeterReading> confirmReading(int id) async {
    final resp = await _request('POST', '/api/v1/resident/meter-readings/$id/confirm');
    return MeterReading.fromJson(_decodeObject(resp));
  }

  Future<MeterReading> retakeReading(int id) async {
    final resp = await _request('POST', '/api/v1/resident/meter-readings/$id/retake');
    return MeterReading.fromJson(_decodeObject(resp));
  }

  // --- Bills -----------------------------------------------------------

  Future<List<Bill>> listOwnBills() async {
    final resp = await _request('GET', '/api/v1/resident/bills');
    return _decodeList(resp).map((b) => Bill.fromJson(b as Map<String, dynamic>)).toList();
  }

  Future<Bill?> getCurrentBill() async {
    final resp = await _request('GET', '/api/v1/resident/bills/current');
    final decoded = jsonDecode(resp.body);
    if (decoded == null) return null;
    return Bill.fromJson(decoded as Map<String, dynamic>);
  }

  Future<Bill> getOwnBill(int id) async {
    final resp = await _request('GET', '/api/v1/resident/bills/$id');
    return Bill.fromJson(_decodeObject(resp));
  }

  // --- Payments ----------------------------------------------------------

  Future<Payment> initiatePayment(int billId) async {
    final resp = await _request('POST', '/api/v1/resident/bills/$billId/payments');
    return Payment.fromJson(_decodeObject(resp));
  }

  Future<Payment> mockConfirmPayment(int paymentId, {required bool simulateSuccess}) async {
    final resp = await _request(
      'POST',
      '/api/v1/payments/$paymentId/mock-confirm',
      json: {'simulate_success': simulateSuccess},
    );
    return Payment.fromJson(_decodeObject(resp));
  }

  Future<List<Payment>> listOwnPayments() async {
    final resp = await _request('GET', '/api/v1/resident/payments');
    return _decodeList(resp).map((p) => Payment.fromJson(p as Map<String, dynamic>)).toList();
  }

  // --- Notifications -----------------------------------------------------

  Future<List<AppNotification>> listOwnNotifications() async {
    final resp = await _request('GET', '/api/v1/resident/notifications');
    return _decodeList(resp).map((n) => AppNotification.fromJson(n as Map<String, dynamic>)).toList();
  }

  Future<AppNotification> markNotificationRead(int id) async {
    final resp = await _request('POST', '/api/v1/resident/notifications/$id/read');
    return AppNotification.fromJson(_decodeObject(resp));
  }
}
