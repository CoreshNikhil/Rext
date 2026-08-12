class Payment {
  final int paymentId;
  final int billId;
  final String amount;
  final String providerName;
  final String status;
  final String? failureReason;
  final String? completedAt;
  final String createdAt;

  Payment({
    required this.paymentId,
    required this.billId,
    required this.amount,
    required this.providerName,
    required this.status,
    this.failureReason,
    this.completedAt,
    required this.createdAt,
  });

  factory Payment.fromJson(Map<String, dynamic> json) => Payment(
        paymentId: json['payment_id'] as int,
        billId: json['bill_id'] as int,
        amount: json['amount'] as String,
        providerName: json['provider_name'] as String,
        status: json['status'] as String,
        failureReason: json['failure_reason'] as String?,
        completedAt: json['completed_at'] as String?,
        createdAt: json['created_at'] as String,
      );
}
