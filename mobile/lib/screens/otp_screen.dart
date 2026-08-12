import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api_client.dart';
import '../widgets/error_banner.dart';
import 'set_password_screen.dart';

enum OtpPurpose { signup, passwordReset }

/// Shared between signup and "forgot password" — the two flows only
/// differ in which verify-otp endpoint they call and what token they
/// hand off to SetPasswordScreen, per the approved design's screen map.
class OtpScreen extends StatefulWidget {
  final OtpPurpose purpose;
  final String houseNumber;
  final String mobileNumber;
  final String? devOtp;

  const OtpScreen({super.key, required this.purpose, required this.houseNumber, required this.mobileNumber, this.devOtp});

  @override
  State<OtpScreen> createState() => _OtpScreenState();
}

class _OtpScreenState extends State<OtpScreen> {
  final _otpController = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (widget.devOtp != null) _otpController.text = widget.devOtp!;
  }

  Future<void> _verify() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = context.read<ApiClient>();
      final String token;
      if (widget.purpose == OtpPurpose.signup) {
        token = await api.signupVerifyOtp(widget.houseNumber, widget.mobileNumber, _otpController.text.trim());
      } else {
        token = await api.passwordResetVerifyOtp(widget.houseNumber, widget.mobileNumber, _otpController.text.trim());
      }
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => SetPasswordScreen(purpose: widget.purpose, token: token, houseNumber: widget.houseNumber),
        ),
      );
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Verify code')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Enter the 6-digit code sent to ${widget.mobileNumber}.'),
            if (widget.devOtp != null) ...[
              const SizedBox(height: 8),
              Text('Dev mode code: ${widget.devOtp}', style: const TextStyle(fontStyle: FontStyle.italic)),
            ],
            const SizedBox(height: 20),
            ErrorBanner(message: _error),
            TextField(
              controller: _otpController,
              decoration: const InputDecoration(labelText: 'Verification code', border: OutlineInputBorder()),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _loading ? null : _verify,
              child: _loading
                  ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Verify'),
            ),
          ],
        ),
      ),
    );
  }
}
