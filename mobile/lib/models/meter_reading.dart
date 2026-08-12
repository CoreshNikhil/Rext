class MeterReading {
  final int meterReadingId;
  final int billingPeriodId;
  final String? previousReadingValue;
  final String? submittedReadingValue;
  final String? unit;
  final String? aiConfidence;
  final String? aiStatus;
  final String? aiReason;
  final List<String>? aiValidationNotes;
  final String status;
  final String submittedBy;
  final String? finalReadingValue;
  final String? residentConfirmedAt;
  final String createdAt;

  MeterReading({
    required this.meterReadingId,
    required this.billingPeriodId,
    this.previousReadingValue,
    this.submittedReadingValue,
    this.unit,
    this.aiConfidence,
    this.aiStatus,
    this.aiReason,
    this.aiValidationNotes,
    required this.status,
    required this.submittedBy,
    this.finalReadingValue,
    this.residentConfirmedAt,
    required this.createdAt,
  });

  factory MeterReading.fromJson(Map<String, dynamic> json) => MeterReading(
        meterReadingId: json['meter_reading_id'] as int,
        billingPeriodId: json['billing_period_id'] as int,
        previousReadingValue: json['previous_reading_value'] as String?,
        submittedReadingValue: json['submitted_reading_value'] as String?,
        unit: json['unit'] as String?,
        aiConfidence: json['ai_confidence'] as String?,
        aiStatus: json['ai_status'] as String?,
        aiReason: json['ai_reason'] as String?,
        aiValidationNotes: (json['ai_validation_notes'] as List<dynamic>?)?.map((e) => e as String).toList(),
        status: json['status'] as String,
        submittedBy: json['submitted_by'] as String,
        finalReadingValue: json['final_reading_value'] as String?,
        residentConfirmedAt: json['resident_confirmed_at'] as String?,
        createdAt: json['created_at'] as String,
      );

  bool get needsResidentConfirmation => status == 'ai_accepted';
  bool get isFinalized => status == 'resident_confirmed' || status == 'admin_overridden';
  bool get canRetake => status == 'needs_review' || status == 'rejected';
}
