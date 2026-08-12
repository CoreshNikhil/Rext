import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'screens/splash_screen.dart';
import 'services/api_client.dart';
import 'services/auth_state.dart';

void main() {
  runApp(const GasBillingApp());
}

class GasBillingApp extends StatelessWidget {
  const GasBillingApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthState()),
        ProxyProvider<AuthState, ApiClient>(update: (context, authState, previous) => ApiClient(authState)),
      ],
      child: MaterialApp(
        title: 'Gas Billing',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(colorSchemeSeed: const Color(0xFFE65100), useMaterial3: true),
        home: const SplashScreen(),
      ),
    );
  }
}
