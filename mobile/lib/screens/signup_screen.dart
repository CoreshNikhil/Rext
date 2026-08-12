import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api_client.dart';
import '../widgets/error_banner.dart';
import 'otp_screen.dart';

class SignupScreen extends StatefulWidget {
  const SignupScreen({super.key});

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> {
  final _houseNumberController = TextEditingController();
  final _mobileController = TextEditingController();
  bool _loading = false;
  String? _error;

  Future<void> _sendOtp() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = context.read<ApiClient>();
      final devOtp = await api.signupRequestOtp(_houseNumberController.text.trim(), _mobileController.text.trim());
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => OtpScreen(
            purpose: OtpPurpose.signup,
            houseNumber: _houseNumberController.text.trim(),
            mobileNumber: _mobileController.text.trim(),
            devOtp: devOtp,
          ),
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
      appBar: AppBar(title: const Text('Sign up')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Enter the house number and mobile number your admin registered for you.'),
            const SizedBox(height: 20),
            ErrorBanner(message: _error),
            TextField(
              controller: _houseNumberController,
              decoration: const InputDecoration(labelText: 'House number', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _mobileController,
              decoration: const InputDecoration(labelText: 'Mobile number', border: OutlineInputBorder()),
              keyboardType: TextInputType.phone,
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _loading ? null : _sendOtp,
              child: _loading
                  ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Send verification code'),
            ),
          ],
        ),
      ),
    );
  }
}
