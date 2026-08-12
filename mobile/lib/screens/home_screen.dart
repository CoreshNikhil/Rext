import 'package:flutter/material.dart';

import 'bills_screen.dart';
import 'home_dashboard_tab.dart';
import 'notifications_screen.dart';
import 'profile_screen.dart';
import 'reading_history_screen.dart';

/// App shell after login: bottom nav across the 5 top-level sections.
/// Each tab is a fully self-contained Scaffold, rebuilt fresh every time
/// it's selected (rather than kept alive in an IndexedStack) so its data
/// load always reflects what just happened elsewhere in the app — e.g.
/// switching to Readings right after submitting one on Home must show it
/// immediately, not whatever was cached from the tab's last initState.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;

  static const _tabs = [
    HomeDashboardTab(),
    ReadingHistoryScreen(),
    BillsScreen(),
    NotificationsScreen(),
    ProfileScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _tabs[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.speed_outlined), selectedIcon: Icon(Icons.speed), label: 'Readings'),
          NavigationDestination(icon: Icon(Icons.receipt_long_outlined), selectedIcon: Icon(Icons.receipt_long), label: 'Bills'),
          NavigationDestination(
              icon: Icon(Icons.notifications_outlined), selectedIcon: Icon(Icons.notifications), label: 'Alerts'),
          NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Profile'),
        ],
      ),
    );
  }
}
