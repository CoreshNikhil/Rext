import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/meter_reading.dart';
import '../services/api_client.dart';
import '../widgets/error_banner.dart';
import 'reading_result_screen.dart';

class ReadingHistoryScreen extends StatefulWidget {
  const ReadingHistoryScreen({super.key});

  @override
  State<ReadingHistoryScreen> createState() => _ReadingHistoryScreenState();
}

class _ReadingHistoryScreenState extends State<ReadingHistoryScreen> {
  Future<List<MeterReading>>? _future;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    setState(() => _future = context.read<ApiClient>().listOwnReadings());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Reading history')),
      body: RefreshIndicator(
        onRefresh: () async {
          _load();
          await _future;
        },
        child: FutureBuilder<List<MeterReading>>(
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
                    message: snapshot.error is ApiException ? (snapshot.error as ApiException).detail : 'Could not load readings.',
                  ),
                ],
              );
            }
            final readings = snapshot.data!;
            if (readings.isEmpty) {
              return const Center(child: Text('No readings submitted yet.'));
            }
            return ListView.builder(
              itemCount: readings.length,
              itemBuilder: (context, i) {
                final r = readings[i];
                return ListTile(
                  leading: const Icon(Icons.speed),
                  title: Text('${r.submittedReadingValue ?? '—'} ${r.unit ?? ''}'),
                  subtitle: Text('${r.status} • ${r.createdAt}'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () async {
                    await Navigator.of(context)
                        .push(MaterialPageRoute(builder: (_) => ReadingResultScreen(readingId: r.meterReadingId)));
                    _load();
                  },
                );
              },
            );
          },
        ),
      ),
    );
  }
}
