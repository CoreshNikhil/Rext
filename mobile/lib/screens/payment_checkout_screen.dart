import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/payment.dart';
import '../services/api_client.dart';
import '../widgets/error_banner.dart';

/// There's no real payment gateway yet (see backend/providers/payment/
/// mock_payment_provider.py) — this screen stands in for a real checkout
/// page, letting the resident simulate either outcome of the "gateway
/// callback" so the confirm/fail wiring can be exercised end to end.
class PaymentCheckoutScreen extends StatefulWidget {
  final int billId;

  const PaymentCheckoutScreen({super.key, required this.billId});

  @override
  State<PaymentCheckoutScreen> createState() => _PaymentCheckoutScreenState();
}

class _PaymentCheckoutScreenState extends State<PaymentCheckoutScreen> {
  Payment? _payment;
  bool _loading = true;
  bool _confirming = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _initiate();
  }

  Future<void> _initiate() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final payment = await context.read<ApiClient>().initiatePayment(widget.billId);
      setState(() => _payment = payment);
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _confirm(bool simulateSuccess) async {
    if (_payment == null) return;
    setState(() {
      _confirming = true;
      _error = null;
    });
    try {
      final payment = await context.read<ApiClient>().mockConfirmPayment(_payment!.paymentId, simulateSuccess: simulateSuccess);
      setState(() => _payment = payment);
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _confirming = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Payment')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Padding(
              padding: const EdgeInsets.all(16),
              child: ListView(
                children: [
                  ErrorBanner(message: _error),
                  if (_payment != null) ..._content(_payment!),
                ],
              ),
            ),
    );
  }

  List<Widget> _content(Payment payment) {
    if (payment.status == 'success') {
      return [
        const Icon(Icons.check_circle, color: Colors.green, size: 64),
        const SizedBox(height: 12),
        Text('Payment of Rs ${payment.amount} was successful.', textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 20),
        FilledButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Done')),
      ];
    }
    if (payment.status == 'failed') {
      return [
        const Icon(Icons.error, color: Colors.red, size: 64),
        const SizedBox(height: 12),
        Text(payment.failureReason ?? 'Payment failed.', textAlign: TextAlign.center),
        const SizedBox(height: 20),
        OutlinedButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Back to bill')),
      ];
    }
    // INITIATED — mock gateway stand-in.
    return [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Text('Rs ${payment.amount}', style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 4),
              Text('via ${payment.providerName} (mock gateway)'),
            ],
          ),
        ),
      ),
      const SizedBox(height: 24),
      const Text('This is a mock payment gateway for development. Choose an outcome to simulate:'),
      const SizedBox(height: 16),
      FilledButton(
        onPressed: _confirming ? null : () => _confirm(true),
        child: _confirming
            ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
            : const Text('Simulate successful payment'),
      ),
      const SizedBox(height: 8),
      OutlinedButton(
        onPressed: _confirming ? null : () => _confirm(false),
        child: const Text('Simulate failed payment'),
      ),
    ];
  }
}
