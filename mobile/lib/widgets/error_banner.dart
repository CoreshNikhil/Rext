import 'package:flutter/material.dart';

/// Displays an ApiException's (or any) message consistently across every
/// screen — a single place to change the look of an inline error.
class ErrorBanner extends StatelessWidget {
  final String? message;

  const ErrorBanner({super.key, this.message});

  @override
  Widget build(BuildContext context) {
    if (message == null) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(message!, style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer)),
    );
  }
}
