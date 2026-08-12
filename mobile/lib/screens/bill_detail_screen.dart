import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/bill.dart';
import '../services/api_client.dart';
import '../widgets/error_banner.dart';
import 'payment_checkout_screen.dart';

class BillDetailScreen extends StatefulWidget {
  final int billId;

  const BillDetailScreen({super.key, required this.billId});

  @override
  State<BillDetailScreen> createState() => _BillDetailScreenState();
}

class _BillDetailScreenState extends State<BillDetailScreen> {
  Bill? _bill;
  bool _loading = true;
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
      final bill = await context.read<ApiClient>().getOwnBill(widget.billId);
      setState(() => _bill = bill);
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Bill detail')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Padding(
              padding: const EdgeInsets.all(16),
              child: ListView(
                children: [
                  ErrorBanner(message: _error),
                  if (_bill != null) ..._content(_bill!),
                ],
              ),
            ),
    );
  }

  List<Widget> _content(Bill bill) {
    return [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Rs ${bill.totalAmountDue}', style: Theme.of(context).textTheme.headlineMedium),
              Text('Status: ${bill.status}'),
              const Divider(height: 24),
              _row('Previous reading', bill.previousReadingValue),
              _row('Current reading', bill.currentReadingValue),
              _row('Consumption', '${bill.consumptionUnits} units'),
              _row('Rate', 'Rs ${bill.ratePerUnit} / unit'),
              _row('Amount due', 'Rs ${bill.amountDue}'),
              _row('Fine', 'Rs ${bill.fineAmount}'),
              const Divider(height: 24),
              _row('Total due', 'Rs ${bill.totalAmountDue}'),
              _row('Due date', bill.dueDate),
              if (bill.paidAt != null) _row('Paid at', bill.paidAt!),
            ],
          ),
        ),
      ),
      const SizedBox(height: 20),
      if (bill.isPayable)
        FilledButton(
          onPressed: () async {
            await Navigator.of(context).push(MaterialPageRoute(builder: (_) => PaymentCheckoutScreen(billId: bill.billId)));
            _load();
          },
          child: const Text('Pay now'),
        ),
    ];
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [Text(label), Text(value)],
      ),
    );
  }
}
