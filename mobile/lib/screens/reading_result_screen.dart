import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/meter_reading.dart';
import '../services/api_client.dart';
import '../widgets/error_banner.dart';
import 'scan_meter_screen.dart';

/// Merges "Reading result" and "Reading confirmation" into one screen —
/// both render the same data (reading, confidence, yes/scan-again) per
/// the approved design's screen-map consolidation.
class ReadingResultScreen extends StatefulWidget {
  final int readingId;

  const ReadingResultScreen({super.key, required this.readingId});

  @override
  State<ReadingResultScreen> createState() => _ReadingResultScreenState();
}

class _ReadingResultScreenState extends State<ReadingResultScreen> {
  MeterReading? _reading;
  bool _loading = true;
  bool _acting = false;
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
      final reading = await context.read<ApiClient>().getOwnReading(widget.readingId);
      setState(() => _reading = reading);
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _confirm() async {
    setState(() {
      _acting = true;
      _error = null;
    });
    try {
      await context.read<ApiClient>().confirmReading(widget.readingId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Reading confirmed.')));
      Navigator.of(context).popUntil((route) => route.isFirst);
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  Future<void> _retake() async {
    setState(() {
      _acting = true;
      _error = null;
    });
    try {
      await context.read<ApiClient>().retakeReading(widget.readingId);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const ScanMeterScreen()));
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Reading result')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Padding(
              padding: const EdgeInsets.all(16),
              child: ListView(
                children: [
                  ErrorBanner(message: _error),
                  if (_reading != null) ..._buildContent(_reading!),
                ],
              ),
            ),
    );
  }

  List<Widget> _buildContent(MeterReading reading) {
    return [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Reading: ${reading.submittedReadingValue ?? '—'} ${reading.unit ?? ''}',
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              if (reading.aiConfidence != null) Text('Confidence: ${reading.aiConfidence}'),
              Text('Status: ${_statusLabel(reading.status)}'),
              if (reading.aiReason != null && reading.aiReason!.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(reading.aiReason!, style: const TextStyle(fontStyle: FontStyle.italic)),
              ],
              if (reading.aiValidationNotes != null && reading.aiValidationNotes!.isNotEmpty) ...[
                const SizedBox(height: 8),
                ...reading.aiValidationNotes!.map((n) => Text('• $n')),
              ],
            ],
          ),
        ),
      ),
      const SizedBox(height: 20),
      if (reading.needsResidentConfirmation)
        Row(
          children: [
            Expanded(
              child: OutlinedButton(onPressed: _acting ? null : _retake, child: const Text('Scan again')),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton(
                onPressed: _acting ? null : _confirm,
                child: _acting
                    ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Yes, this is correct'),
              ),
            ),
          ],
        )
      else if (reading.canRetake)
        FilledButton(
          onPressed: _acting ? null : _retake,
          child: _acting
              ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
              : const Text('Retake photo'),
        )
      else if (reading.isFinalized)
        const Text('This reading has already been finalized and billed off of.', style: TextStyle(fontStyle: FontStyle.italic)),
    ];
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'ai_accepted':
        return 'Needs your confirmation';
      case 'needs_review':
        return 'Needs review — please retake';
      case 'rejected':
        return 'Rejected — please retake';
      case 'resident_confirmed':
        return 'Confirmed';
      case 'admin_overridden':
        return 'Corrected by admin';
      default:
        return status;
    }
  }
}
