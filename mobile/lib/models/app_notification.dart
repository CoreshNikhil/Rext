class AppNotification {
  final int notificationId;
  final String type;
  final String title;
  final String message;
  final bool isRead;
  final String sentAt;

  AppNotification({
    required this.notificationId,
    required this.type,
    required this.title,
    required this.message,
    required this.isRead,
    required this.sentAt,
  });

  factory AppNotification.fromJson(Map<String, dynamic> json) => AppNotification(
        notificationId: json['notification_id'] as int,
        type: json['type'] as String,
        title: json['title'] as String,
        message: json['message'] as String,
        isRead: json['is_read'] as bool,
        sentAt: json['sent_at'] as String,
      );
}
