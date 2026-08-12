import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:mobile/main.dart';

void main() {
  testWidgets('App boots to the splash screen without throwing', (WidgetTester tester) async {
    await tester.pumpWidget(const GasBillingApp());
    await tester.pump();

    expect(find.text('Gas Billing'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}
