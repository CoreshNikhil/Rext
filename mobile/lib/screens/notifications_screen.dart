import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/app_notification.dart';
import '../services/api_client.dart';
import '../widgets/error_banner.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  Future<List<AppNotification>>? _future;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    setState(() => _future = context.read<ApiClient>().listOwnNotifications());
  }

  Future<void> _markRead(AppNotification n) async {
    try {
      await context.read<ApiClient>().markNotificationRead(n.notificationId);
      _load();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.detail)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications')),
      body: RefreshIndicator(
        onRefresh: () async {
          _load();
          await _future;
        },
        child: FutureBuilder<List<AppNotification>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return ListView(padding: const EdgeInsets.all(16), children: [
                ErrorBanner(
                    message:
                        snapshot.error is ApiException ? (snapshot.error as ApiException).detail : 'Could not load notifications.'),
              ]);
            }
            final notifications = snapshot.data!;
            if (notifications.isEmpty) return const Center(child: Text('No notifications.'));
            return ListView.builder(
              itemCount: notifications.length,
              itemBuilder: (context, i) {
                final n = notifications[i];
                return ListTile(
                  leading: Icon(n.isRead ? Icons.circle_outlined : Icons.circle, size: 12, color: n.isRead ? Colors.grey : Colors.blue),
                  title: Text(n.title, style: TextStyle(fontWeight: n.isRead ? FontWeight.normal : FontWeight.bold)),
                  subtitle: Text(n.message),
                  trailing: n.isRead ? null : TextButton(onPressed: () => _markRead(n), child: const Text('Mark read')),
                );
              },
            );
          },
        ),
      ),
    );
  }
}
