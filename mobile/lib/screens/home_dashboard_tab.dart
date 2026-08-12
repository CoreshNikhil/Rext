import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/resident.dart';
import '../services/api_client.dart';
import '../widgets/error_banner.dart';
import 'bill_detail_screen.dart';
import 'scan_meter_screen.dart';

class HomeDashboardTab extends StatefulWidget {
  const HomeDashboardTab({super.key});

  @override
  State<HomeDashboardTab> createState() => _HomeDashboardTabState();
}

class _HomeDashboardTabState extends State<HomeDashboardTab> {
  Future<ResidentHome>? _future;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    setState(() => _future = context.read<ApiClient>().getHome());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Home')),
      body: RefreshIndicator(
        onRefresh: () async {
          _load();
          await _future;
        },
        child: FutureBuilder<ResidentHome>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  ErrorBanner(
                    message: snapshot.error is ApiException ? (snapshot.error as ApiException).detail : 'Could not load home data.',
                  ),
                ],
              );
            }
            final home = snapshot.data!;
            return ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text('Welcome, ${home.fullName}', style: Theme.of(context).textTheme.titleLarge),
                Text('House ${home.houseNumber}', style: Theme.of(context).textTheme.bodyMedium),
                const SizedBox(height: 16),
                if (home.periodLabel != null) _billingPeriodCard(context, home) else _noPeriodCard(context),
                const SizedBox(height: 12),
                if (home.billId != null) _billCard(context, home),
                const SizedBox(height: 20),
                FilledButton.icon(
                  icon: const Icon(Icons.camera_alt),
                  label: const Text('Scan meter reading'),
                  onPressed: () async {
                    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ScanMeterScreen()));
                    _load();
                  },
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _noPeriodCard(BuildContext context) {
    return const Card(
      child: Padding(
        padding: EdgeInsets.all(16),
        child: Text('No billing period is currently open. Check back once your admin starts the next cycle.'),
      ),
    );
  }

  Widget _billingPeriodCard(BuildContext context, ResidentHome home) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Billing period ${home.periodLabel}', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text('Gas rate: Rs ${home.gasRatePerUnit ?? '-'} / unit'),
            if (home.readingDeadline != null) Text('Reading deadline: ${home.readingDeadline}'),
            Text('Status: ${home.billingPeriodStatus ?? '-'}'),
            const Divider(height: 24),
            Text('Reading status: ${home.readingStatus ?? 'Not submitted yet'}'),
            if (home.previousReadingValue != null) Text('Previous reading: ${home.previousReadingValue}'),
            if (home.currentReadingValue != null) Text('Current reading: ${home.currentReadingValue}'),
          ],
        ),
      ),
    );
  }

  Widget _billCard(BuildContext context, ResidentHome home) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.receipt_long),
        title: Text('Bill: Rs ${home.amountDue ?? '-'}'),
        subtitle: Text('Status: ${home.paymentStatus ?? '-'}'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () async {
          await Navigator.of(context).push(MaterialPageRoute(builder: (_) => BillDetailScreen(billId: home.billId!)));
          _load();
        },
      ),
    );
  }
}
