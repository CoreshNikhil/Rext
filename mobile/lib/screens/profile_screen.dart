import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/resident.dart';
import '../services/api_client.dart';
import '../services/auth_state.dart';
import '../widgets/error_banner.dart';
import 'login_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  ResidentProfile? _profile;
  final _emailController = TextEditingController();
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final profile = await context.read<ApiClient>().getOwnProfile();
      setState(() {
        _profile = profile;
        _emailController.text = profile.email ?? '';
      });
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _saveEmail() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final profile = await context.read<ApiClient>().updateOwnEmail(_emailController.text.trim());
      setState(() => _profile = profile);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Email updated.')));
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _logout() async {
    final api = context.read<ApiClient>();
    final authState = context.read<AuthState>();
    await api.logout();
    if (!mounted) return;
    await authState.clear();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const LoginScreen()), (route) => false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                ErrorBanner(message: _error),
                if (_profile != null) ..._content(_profile!),
              ],
            ),
    );
  }

  List<Widget> _content(ResidentProfile profile) {
    return [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(profile.fullName, style: Theme.of(context).textTheme.titleLarge),
              Text('House ${profile.houseNumber}'),
              Text('Mobile: ${profile.mobileNumber}'),
              const SizedBox(height: 8),
              Text('Meters: ${profile.meters.isEmpty ? 'none assigned' : profile.meters.map((m) => m.meterSerialNumber).join(', ')}'),
            ],
          ),
        ),
      ),
      const SizedBox(height: 16),
      TextField(
        controller: _emailController,
        decoration: const InputDecoration(labelText: 'Email', border: OutlineInputBorder()),
        keyboardType: TextInputType.emailAddress,
      ),
      const SizedBox(height: 8),
      FilledButton(
        onPressed: _saving ? null : _saveEmail,
        child: _saving
            ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
            : const Text('Save email'),
      ),
      const SizedBox(height: 24),
      OutlinedButton.icon(
        onPressed: _logout,
        icon: const Icon(Icons.logout),
        label: const Text('Log out'),
      ),
    ];
  }
}
