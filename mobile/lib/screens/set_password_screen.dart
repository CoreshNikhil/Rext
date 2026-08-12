import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api_client.dart';
import '../services/auth_state.dart';
import '../widgets/error_banner.dart';
import 'home_screen.dart';
import 'login_screen.dart';
import 'otp_screen.dart';

/// Shared between "create password" (end of signup) and "reset password"
/// (end of forgot-password) — same form, different endpoint and
/// different destination on success.
class SetPasswordScreen extends StatefulWidget {
  final OtpPurpose purpose;
  final String token;
  final String houseNumber;

  const SetPasswordScreen({super.key, required this.purpose, required this.token, required this.houseNumber});

  @override
  State<SetPasswordScreen> createState() => _SetPasswordScreenState();
}

class _SetPasswordScreenState extends State<SetPasswordScreen> {
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _loading = false;
  String? _error;

  Future<void> _submit() async {
    if (_passwordController.text != _confirmController.text) {
      setState(() => _error = 'Passwords do not match.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = context.read<ApiClient>();
      final authState = context.read<AuthState>();
      if (widget.purpose == OtpPurpose.signup) {
        final pair = await api.signupSetPassword(widget.token, _passwordController.text);
        if (!mounted) return;
        await authState.setSession(accessToken: pair.accessToken, refreshToken: pair.refreshToken, houseNumber: widget.houseNumber);
        if (!mounted) return;
        Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const HomeScreen()), (route) => false);
      } else {
        await api.passwordResetConfirm(widget.token, _passwordController.text);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Password reset. Please log in with your new password.')),
        );
        Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const LoginScreen()), (route) => false);
      }
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isSignup = widget.purpose == OtpPurpose.signup;
    return Scaffold(
      appBar: AppBar(title: Text(isSignup ? 'Create password' : 'Reset password')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ErrorBanner(message: _error),
            TextField(
              controller: _passwordController,
              decoration: const InputDecoration(labelText: 'New password', border: OutlineInputBorder()),
              obscureText: true,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _confirmController,
              decoration: const InputDecoration(labelText: 'Confirm password', border: OutlineInputBorder()),
              obscureText: true,
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _loading ? null : _submit,
              child: _loading
                  ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(isSignup ? 'Create account' : 'Reset password'),
            ),
          ],
        ),
      ),
    );
  }
}
