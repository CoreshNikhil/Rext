class Meter {
  final int meterId;
  final String meterSerialNumber;
  final String? installDate;
  final bool isActive;

  Meter({required this.meterId, required this.meterSerialNumber, this.installDate, required this.isActive});

  factory Meter.fromJson(Map<String, dynamic> json) => Meter(
        meterId: json['meter_id'] as int,
        meterSerialNumber: json['meter_serial_number'] as String,
        installDate: json['install_date'] as String?,
        isActive: json['is_active'] as bool,
      );
}

class ResidentProfile {
  final int residentId;
  final String houseNumber;
  final String fullName;
  final String mobileNumber;
  final String? email;
  final bool isActive;
  final List<Meter> meters;

  ResidentProfile({
    required this.residentId,
    required this.houseNumber,
    required this.fullName,
    required this.mobileNumber,
    this.email,
    required this.isActive,
    required this.meters,
  });

  factory ResidentProfile.fromJson(Map<String, dynamic> json) => ResidentProfile(
        residentId: json['resident_id'] as int,
        houseNumber: json['house_number'] as String,
        fullName: json['full_name'] as String,
        mobileNumber: json['mobile_number'] as String,
        email: json['email'] as String?,
        isActive: json['is_active'] as bool,
        meters: (json['meters'] as List<dynamic>? ?? [])
            .map((m) => Meter.fromJson(m as Map<String, dynamic>))
            .toList(),
      );
}

class ResidentHome {
  final int residentId;
  final String houseNumber;
  final String fullName;

  final int? billingPeriodId;
  final String? periodLabel;
  final String? gasRatePerUnit;
  final String? readingDeadline;
  final String? billingPeriodStatus;

  final String? readingStatus;
  final String? previousReadingValue;
  final String? currentReadingValue;

  final int? billId;
  final String? amountDue;
  final String? paymentStatus;

  final int unreadNotificationCount;

  ResidentHome({
    required this.residentId,
    required this.houseNumber,
    required this.fullName,
    this.billingPeriodId,
    this.periodLabel,
    this.gasRatePerUnit,
    this.readingDeadline,
    this.billingPeriodStatus,
    this.readingStatus,
    this.previousReadingValue,
    this.currentReadingValue,
    this.billId,
    this.amountDue,
    this.paymentStatus,
    required this.unreadNotificationCount,
  });

  factory ResidentHome.fromJson(Map<String, dynamic> json) => ResidentHome(
        residentId: json['resident_id'] as int,
        houseNumber: json['house_number'] as String,
        fullName: json['full_name'] as String,
        billingPeriodId: json['billing_period_id'] as int?,
        periodLabel: json['period_label'] as String?,
        gasRatePerUnit: json['gas_rate_per_unit'] as String?,
        readingDeadline: json['reading_deadline'] as String?,
        billingPeriodStatus: json['billing_period_status'] as String?,
        readingStatus: json['reading_status'] as String?,
        previousReadingValue: json['previous_reading_value'] as String?,
        currentReadingValue: json['current_reading_value'] as String?,
        billId: json['bill_id'] as int?,
        amountDue: json['amount_due'] as String?,
        paymentStatus: json['payment_status'] as String?,
        unreadNotificationCount: json['unread_notification_count'] as int,
      );
}
