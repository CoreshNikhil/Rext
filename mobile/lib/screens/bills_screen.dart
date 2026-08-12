import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/bill.dart';
import '../models/payment.dart';
import '../services/api_client.dart';
import '../widgets/error_banner.dart';
import 'bill_detail_screen.dart';

/// Combines "Bills" and "Payment History" into one screen (two tabs) —
/// per the approved design's screen-map consolidation.
class BillsScreen extends StatefulWidget {
  const BillsScreen({super.key});

  @override
  State<BillsScreen> createState() => _BillsScreenState();
}

class _BillsScreenState extends State<BillsScreen> {
  Future<List<Bill>>? _billsFuture;
  Future<List<Payment>>? _paymentsFuture;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    setState(() {
      _billsFuture = context.read<ApiClient>().listOwnBills();
      _paymentsFuture = context.read<ApiClient>().listOwnPayments();
    });
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Bills & Payments'),
          bottom: const TabBar(tabs: [Tab(text: 'Bills'), Tab(text: 'Payment history')]),
        ),
        body: TabBarView(
          children: [_billsTab(), _paymentsTab()],
        ),
      ),
    );
  }

  Widget _billsTab() {
    return RefreshIndicator(
      onRefresh: () async {
        _load();
        await _billsFuture;
      },
      child: FutureBuilder<List<Bill>>(
        future: _billsFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return ListView(padding: const EdgeInsets.all(16), children: [
              ErrorBanner(message: snapshot.error is ApiException ? (snapshot.error as ApiException).detail : 'Could not load bills.'),
            ]);
          }
          final bills = snapshot.data!;
          if (bills.isEmpty) return const Center(child: Text('No bills yet.'));
          return ListView.builder(
            itemCount: bills.length,
            itemBuilder: (context, i) {
              final b = bills[i];
              return ListTile(
                leading: Icon(b.isPayable ? Icons.warning_amber : Icons.check_circle_outline,
                    color: b.isPayable ? Colors.orange : Colors.green),
                title: Text('Rs ${b.totalAmountDue}'),
                subtitle: Text('${b.status} • due ${b.dueDate}'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () async {
                  await Navigator.of(context).push(MaterialPageRoute(builder: (_) => BillDetailScreen(billId: b.billId)));
                  _load();
                },
              );
            },
          );
        },
      ),
    );
  }

  Widget _paymentsTab() {
    return RefreshIndicator(
      onRefresh: () async {
        _load();
        await _paymentsFuture;
      },
      child: FutureBuilder<List<Payment>>(
        future: _paymentsFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return ListView(padding: const EdgeInsets.all(16), children: [
              ErrorBanner(
                  message: snapshot.error is ApiException ? (snapshot.error as ApiException).detail : 'Could not load payments.'),
            ]);
          }
          final payments = snapshot.data!;
          if (payments.isEmpty) return const Center(child: Text('No payments yet.'));
          return ListView.builder(
            itemCount: payments.length,
            itemBuilder: (context, i) {
              final p = payments[i];
              return ListTile(
                leading: Icon(
                  p.status == 'success' ? Icons.check_circle : (p.status == 'failed' ? Icons.error : Icons.hourglass_top),
                  color: p.status == 'success' ? Colors.green : (p.status == 'failed' ? Colors.red : Colors.grey),
                ),
                title: Text('Rs ${p.amount}'),
                subtitle: Text('${p.status} • bill #${p.billId}${p.failureReason != null ? ' • ${p.failureReason}' : ''}'),
              );
            },
          );
        },
      ),
    );
  }
}
