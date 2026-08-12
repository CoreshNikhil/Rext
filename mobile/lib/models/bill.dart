class Bill {
  final int billId;
  final int billingPeriodId;
  final String previousReadingValue;
  final String currentReadingValue;
  final String consumptionUnits;
  final String ratePerUnit;
  final String amountDue;
  final String fineAmount;
  final String totalAmountDue;
  final String dueDate;
  final String status;
  final String? paidAt;
  final String createdAt;

  Bill({
    required this.billId,
    required this.billingPeriodId,
    required this.previousReadingValue,
    required this.currentReadingValue,
    required this.consumptionUnits,
    required this.ratePerUnit,
    required this.amountDue,
    required this.fineAmount,
    required this.totalAmountDue,
    required this.dueDate,
    required this.status,
    this.paidAt,
    required this.createdAt,
  });

  factory Bill.fromJson(Map<String, dynamic> json) => Bill(
        billId: json['bill_id'] as int,
        billingPeriodId: json['billing_period_id'] as int,
        previousReadingValue: json['previous_reading_value'] as String,
        currentReadingValue: json['current_reading_value'] as String,
        consumptionUnits: json['consumption_units'] as String,
        ratePerUnit: json['rate_per_unit'] as String,
        amountDue: json['amount_due'] as String,
        fineAmount: json['fine_amount'] as String,
        totalAmountDue: json['total_amount_due'] as String,
        dueDate: json['due_date'] as String,
        status: json['status'] as String,
        paidAt: json['paid_at'] as String?,
        createdAt: json['created_at'] as String,
      );

  bool get isPayable => status == 'issued' || status == 'overdue';
}
