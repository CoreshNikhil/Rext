# Gas Billing System — Resident Mobile App

A Flutter app for residents: signup, meter reading submission (photo → AI extraction → confirm), bills, mock payments, notifications, and profile. Calls the [backend](../backend/README.md) over `http` only — no business logic here, matching the same "thin client" rule as `admin_web/`.

## Screens

Splash (auth gate) → Login ⇄ Signup → OTP verification (shared with password reset) → Set/Reset password (shared) → Home (bottom-nav shell: Home, Reading history, Bills & Payments, Notifications, Profile) → Scan meter → Reading result/confirm → Bill detail → Payment checkout.

Two deliberate consolidations from the original 14-screen list: "Reading result" and "Reading confirmation" are one screen (`reading_result_screen.dart`) since both render the same data; "Bills" and "Payment history" are two tabs of one screen (`bills_screen.dart`) rather than separate pages.

## Structure

```
lib/config.dart         Backend URL (BACKEND_URL, set via --dart-define)
lib/models/              Typed request/response models, one file per resource
lib/services/
  auth_state.dart        ChangeNotifier holding the JWT pair, persisted via
                          SharedPreferences — the only source of truth for
                          "is anyone logged in"
  api_client.dart         http wrapper — one method per backend endpoint,
                          401-triggered refresh-and-retry, unwraps the
                          backend's uniform error envelope into ApiException
lib/screens/             One file per screen
lib/widgets/             Small shared widgets (ErrorBanner)
```

State management is `provider` (`ChangeNotifierProvider` for `AuthState`, `ProxyProvider` for `ApiClient`) — deliberately minimal for an app this size, no routing package beyond `Navigator.push`/`pushReplacement`.

## Running (web, for development)

No Android/iOS toolchain is required to verify this app — Chrome via `flutter build web` is enough:

```bash
cd mobile
flutter build web --release
python3 -m http.server 8503 --directory build/web
```

The backend's `CORS_ORIGINS` must include `http://localhost:8503` for the web build specifically (already set in `.env.example`) — a real device build talks to the backend directly and doesn't need CORS at all. `mobile/run_web.sh` wraps both steps; `.claude/launch.json`'s `mobile_web` entry runs it.

For a real Android/iOS build later: `flutter run` (device/emulator required) or `flutter build apk` / `flutter build ios`.

## Known limitations

- Verified so far via Chrome/web only — no Android/iOS device testing yet (no SDK/emulator on this machine at time of writing).
- `image_picker`'s file-selection dialog can't be driven by browser automation (it opens a native OS file picker), so the photo-upload UI itself is verified by inspection/manual use; the reading submission *pipeline* it feeds into (upload → AI extraction → confirm → bill → payment) is verified end-to-end via direct API calls exercised through the same screens.
